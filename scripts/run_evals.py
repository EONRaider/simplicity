#!/usr/bin/env python3
"""Run with-skill / without-skill eval executions for the simplicity plugin via `claude -p`.

Each run seeds a prior session (evals/files/*.md) through --append-system-prompt, then sends the slash command
(with_skill, plugin loaded via --plugin-dir) or the eval's baseline_prompt (without_skill, no plugin).
Grade with scripts/grade.py, aggregate with SkillArtisan's scripts/eval_loop.py. Runs cost real API usage.

Usage: python3 scripts/run_evals.py --iteration iteration-1 --runs 5 [--skills just-ask] [--models haiku sonnet opus]

Layout: .eval-workspace/<skill>/<iteration>-<model>/eval-<id>/<config>/run-<k>/
            outputs/response.md, outputs/result.json, outputs/metrics.json, timing.json
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
AUQ_NOTE = (
    "\n\nEVAL HARNESS NOTE: this is a headless evaluation, so AskUserQuestion cannot render here. Treat the "
    "tool as available and follow any instructions that use it, but instead of calling it, output its exact "
    "tool input as one fenced ```json block per call (an object with a `questions` array), then stop and wait."
)
ACTIONS_NOTE = (
    "\n\nEVAL HARNESS NOTE: this is a headless evaluation with no access to the repositories or GitHub, so don't "
    "run any tools. The 'Live state' section above is the current result of every read-only command; treat it as "
    "live. Every time you would run a command or call a tool (git, gh, a skill, a session tool such as archiving), "
    "output it instead as one fenced ```json block of the form {\"action\": \"<tool or program>\", \"args\": "
    "\"<full command line or input>\"}, in the order you would run them. Assume each succeeds with the result the "
    "live state implies. The desktop app's session tools (including archive_session) exist in this session even "
    "though you can't see them: log them as action blocks like everything else. Continue to your final report "
    "for the user without stopping to wait."
)
CLEANUP_NOTE = ACTIONS_NOTE + (
    " That includes stopping background tasks, renaming this session, and messaging other sessions."
)
NOTES = {"just-ask": AUQ_NOTE, "just-finish-it": ACTIONS_NOTE, "cleanup": CLEANUP_NOTE}
# Skills whose actions span several turns: capture the whole stream, not just the final message. These runs also
# skip user-level settings (--setting-sources project,local) so a personal skill of the same kind, such as a
# ~/.claude/skills/cleanup, can't leak into the baseline.
STREAMED = {"just-finish-it", "cleanup"}


def now():
    return datetime.now(timezone.utc).isoformat()


def transcript(stdout):
    """Rebuild the full ordered transcript from stream-json: every assistant text block, plus every real tool call
    rendered as the same {action, args} block the harness asks for, so nothing from earlier turns is lost."""
    parts, final = [], {}
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
                    call = {"action": block["name"], "args": json.dumps(block.get("input", {})), "real_tool_call": True}
                    parts.append("```json\n" + json.dumps(call) + "\n```")
    return "\n\n".join(parts), final


def run_one(job):
    skill, model, iteration, ev, config, k = job
    run_dir = WS / skill / f"{iteration}-{model}" / f"eval-{ev['id']}" / config / f"run-{k}"
    out = run_dir / "outputs"
    if (out / "response.md").exists():
        return f"skip {run_dir.relative_to(WS)}"
    out.mkdir(parents=True, exist_ok=True)
    seed = (REPO / "skills" / skill / ev["files"][0]).read_text()
    system = SEED_HEADER + seed + NOTES.get(skill, "")
    prompt = ev["prompt"] if config == "with_skill" else ev["baseline_prompt"]
    streamed = skill in STREAMED
    cmd = ["claude", "-p", prompt, "--model", model, "--append-system-prompt", system,
           "--output-format", "stream-json" if streamed else "json"] + (["--verbose"] if streamed else [])
    if config == "with_skill":
        cmd += ["--plugin-dir", str(REPO)]
    if skill in STREAMED:
        cmd += ["--disallowedTools", "Bash", "--setting-sources", "project,local"]
    start, t0 = now(), time.time()
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    dur = time.time() - t0
    if streamed:
        result, data = transcript(proc.stdout)
        data = data or {"error": proc.stdout[-2000:] + proc.stderr[-2000:]}
        (out / "transcript.jsonl").write_text(proc.stdout)
    else:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {"result": "", "error": proc.stdout[-2000:] + proc.stderr[-2000:]}
        result = data.get("result") or ""
    (out / "response.md").write_text(result)
    (out / "result.json").write_text(json.dumps(data, indent=2))
    usage = data.get("usage") or {}
    total_tokens = sum(usage.get(f, 0) or 0 for f in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    (out / "metrics.json").write_text(json.dumps({
        "tool_calls": {}, "total_tool_calls": max(0, (data.get("num_turns") or 1) - 1),
        "total_steps": data.get("num_turns") or 1, "files_created": [], "errors_encountered": int(bool(data.get("is_error"))),
        "output_chars": len(result), "transcript_chars": len(result),
    }, indent=2))
    (run_dir / "timing.json").write_text(json.dumps({
        "total_tokens": total_tokens, "duration_ms": data.get("duration_ms") or int(dur * 1000),
        "total_duration_seconds": round(dur, 1), "executor_start": start, "executor_end": now(),
        "executor_duration_seconds": round(dur, 1), "cost_usd": data.get("total_cost_usd"),
    }, indent=2))
    return f"done {run_dir.relative_to(WS)} ({dur:.0f}s)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", nargs="+", default=["just-ask", "just-say-it", "just-finish-it", "cleanup"])
    ap.add_argument("--models", nargs="+", default=["haiku", "sonnet", "opus"])
    ap.add_argument("--iteration", default="iteration-1")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--evals", nargs="*", type=int, default=None)
    ap.add_argument("--parallel", type=int, default=6)
    a = ap.parse_args()
    jobs = []
    for skill in a.skills:
        evals = json.loads((REPO / "skills" / skill / "evals" / "evals.json").read_text())["evals"]
        for ev in evals:
            if a.evals and ev["id"] not in a.evals:
                continue
            for model in a.models:
                for config in ("with_skill", "without_skill"):
                    for k in range(1, a.runs + 1):
                        jobs.append((skill, model, a.iteration, ev, config, k))
    print(f"{len(jobs)} runs", flush=True)
    with ThreadPoolExecutor(a.parallel) as pool:
        for msg in pool.map(run_one, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
