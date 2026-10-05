#!/usr/bin/env python3
"""Run with-skill / without-skill eval executions for the simplicity plugin via `claude -p`.

Each run seeds a prior session (evals/files/*.md) through --append-system-prompt, then sends the slash command
(with_skill, plugin loaded via --plugin-dir) or the eval's baseline_prompt (without_skill, no plugin).
Grade with scripts/grade.py, aggregate with SkillArtisan's scripts/eval_loop.py. Every run is a `claude -p` call,
so it counts against your Claude plan's usage limits, or bills your API key if one is configured.

Every run is isolated from the machine it runs on: user-level settings, skills and plugins are skipped
(--setting-sources project,local), MCP servers and claude.ai connectors are skipped (--strict-mcp-config), and the
only tool available is Skill (--tools), so a with-skill run can still load a skill it invokes. Everything else the
model would do is logged as a JSON action block instead of executed.

Usage: python3 scripts/run_evals.py --iteration <fresh-name> --runs 5 [--skills just-ask] [--models haiku sonnet opus] [--configs with_skill]
Runs whose response.md already exists (and didn't error) are skipped, so reuse an iteration name only to resume it.

Layout: .eval-workspace/<skill>/<iteration>-<model>/eval-<id>/<config>/run-<k>/
            outputs/response.md, outputs/result.json, outputs/transcript.jsonl, outputs/metrics.json, timing.json
"""
import argparse
import json
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WS = REPO / ".eval-workspace"
SEED_HEADER = (
    "The following is the conversation so far in this session. You are the Assistant in it; "
    "treat those turns as your own prior responses and continue from the user's latest message.\n\n"
)
NO_REPO_NOTE = (
    "\n\nEVAL HARNESS NOTE: this is a headless evaluation. The repository and files discussed above aren't "
    "available here, and you have no file or shell tools; the conversation above is the only source of state."
)
AUQ_NOTE = NO_REPO_NOTE + (
    " AskUserQuestion can't render here either. Treat the tool as available and follow any instructions that use "
    "it, but instead of calling it, output its exact tool input as one fenced ```json block per call (an object "
    "with a `questions` array), then stop and wait."
)
ACTIONS_NOTE = (
    "\n\nEVAL HARNESS NOTE: this is a headless evaluation with no access to the repositories or GitHub. You can't "
    "run any tool, except Skill to load a different skill that your instructions tell you to run; the user's "
    "latest message is already loaded and doesn't need it, unless it names a skill as plain text, mid-sentence. The 'Live state' section above is the current result "
    "of every read-only command; treat it as live. Every time you would run any other command or tool (git, gh, file edits, a "
    "session tool such as archiving, renaming this session, stopping a background task, or messaging another "
    "session), output it instead as one fenced ```json block of the form {\"action\": \"<tool or program>\", "
    "\"args\": \"<full command line or input>\"}, in the order you would run them. Assume each succeeds with the "
    "result the live state implies. The desktop app's session tools exist in this session even though you can't "
    "see them: log them as action blocks like everything else. Continue to your final report for the user "
    "without stopping to wait."
)
PROMPTFY_NOTE = ACTIONS_NOTE + (
    " Two more rules apply here. First, a subagent can't run either: log the call as an action block whose args "
    "hold its full tool input, including its `model` and the brief, then write the subagent's result yourself, "
    "following the brief you gave it, and carry on as if it had come back. Second, AskUserQuestion can't render: "
    "when you would call it, first finish everything that comes before the call, then output its exact tool input "
    "as one fenced ```json block per call (an object with a `questions` array), and stop there to wait for the "
    "answers. That is the only point at which you stop."
)
NOTES = {"just-ask": AUQ_NOTE, "just-say-it": NO_REPO_NOTE, "what-now": NO_REPO_NOTE, "just-finish-it": ACTIONS_NOTE, "cleanup": ACTIONS_NOTE,
         "rename-session": ACTIONS_NOTE, "promptfy": PROMPTFY_NOTE}
ISOLATION = ["--setting-sources", "project,local", "--strict-mcp-config", "--tools", "Skill"]


def now():
    return datetime.now(timezone.utc).isoformat()


def transcript(stdout):
    """Rebuild the full ordered transcript from stream-json: every assistant text block, plus every real tool call
    rendered as the same {action, args} block the harness asks for, so nothing from earlier turns is lost. Calls
    whose tool_result came back as an error are marked "error": true; the grader ignores them."""
    parts, calls, errored, final = [], {}, set(), {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            final = ev
        elif ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text" and block["text"].strip():
                    parts.append(block["text"].strip())
                elif block.get("type") == "tool_use":
                    calls[block["id"]] = len(parts)
                    parts.append({"action": block["name"], "args": json.dumps(block.get("input", {})),
                                  "real_tool_call": True})
        elif ev.get("type") == "user":
            for block in (ev.get("message", {}).get("content") or []):
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    errored.add(block.get("tool_use_id"))
    for tool_id in errored & calls.keys():
        parts[calls[tool_id]]["error"] = True
    text = [p if isinstance(p, str) else "```json\n" + json.dumps(p) + "\n```" for p in parts]
    return "\n\n".join(text), final


def run_one(job):
    skill, model, iteration, ev, config, k = job
    run_dir = WS / skill / f"{iteration}-{model}" / f"eval-{ev['id']}" / config / f"run-{k}"
    out = run_dir / "outputs"
    if (out / "response.md").exists() and not json.loads((out / "result.json").read_text()).get("error"):
        return f"skip {run_dir.relative_to(WS)}"
    out.mkdir(parents=True, exist_ok=True)
    seed = (REPO / "skills" / skill / ev["files"][0]).read_text()
    system = SEED_HEADER + seed + NOTES.get(skill, "")
    prompt = ev["prompt"] if config == "with_skill" else ev["baseline_prompt"]
    cmd = ["claude", "-p", prompt, "--model", model, "--append-system-prompt", system,
           "--output-format", "stream-json", "--verbose"] + ISOLATION
    if config == "with_skill":
        # A skill the model loads itself, rather than one the user typed, asks before it loads when it declares
        # allowed-tools. Allowing Skill stands in for the user approving that prompt.
        cmd += ["--plugin-dir", str(REPO), "--allowedTools", "Skill"]
    start, t0 = now(), time.time()
    with tempfile.TemporaryDirectory() as cwd:
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            out_ = e.stdout or ""
            stdout, stderr = out_.decode(errors="replace") if isinstance(out_, bytes) else out_, "timed out after 600s"
    dur = time.time() - t0
    result, data = transcript(stdout)
    data = data or {"error": stdout[-2000:] + stderr[-2000:]}
    (out / "transcript.jsonl").write_text(stdout)
    (out / "response.md").write_text(result)
    (out / "result.json").write_text(json.dumps(data, indent=2))
    usage = data.get("usage") or {}
    total_tokens = sum(usage.get(f, 0) or 0 for f in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    (out / "metrics.json").write_text(json.dumps({
        "tool_calls": {}, "total_tool_calls": max(0, (data.get("num_turns") or 1) - 1),
        "total_steps": data.get("num_turns") or 1, "files_created": [], "errors_encountered": int(bool(data.get("is_error"))),
        "output_chars": len(result), "transcript_chars": len(result),
        "models": sorted((data.get("modelUsage") or {}).keys()),
    }, indent=2))
    (run_dir / "timing.json").write_text(json.dumps({
        "total_tokens": total_tokens, "duration_ms": data.get("duration_ms") or int(dur * 1000),
        "total_duration_seconds": round(dur, 1), "executor_start": start, "executor_end": now(),
        "executor_duration_seconds": round(dur, 1), "cost_usd": data.get("total_cost_usd"),
    }, indent=2))
    return f"done {run_dir.relative_to(WS)} ({dur:.0f}s)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", nargs="+", default=["just-ask", "just-say-it", "what-now", "just-finish-it", "cleanup",
                                                 "rename-session", "promptfy"])
    ap.add_argument("--models", nargs="+", default=["haiku", "sonnet", "opus"])
    ap.add_argument("--iteration", default="iteration-1")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--evals", nargs="*", type=int, default=None)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--configs", nargs="+", choices=("with_skill", "without_skill"),
                    default=["with_skill", "without_skill"])
    a = ap.parse_args()
    jobs = []
    for skill in a.skills:
        evals = json.loads((REPO / "skills" / skill / "evals" / "evals.json").read_text())["evals"]
        for ev in evals:
            if a.evals and ev["id"] not in a.evals:
                continue
            for model in a.models:
                for config in a.configs:
                    for k in range(1, a.runs + 1):
                        jobs.append((skill, model, a.iteration, ev, config, k))
    print(f"{len(jobs)} runs", flush=True)
    with ThreadPoolExecutor(a.parallel) as pool:
        for msg in pool.map(run_one, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
