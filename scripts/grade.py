#!/usr/bin/env python3
"""Deterministic grader for the simplicity evals. Writes grading.json (schema: SkillArtisan references/schemas.md)
next to every run-*/ directory under the given iteration dirs. Expectation texts are read from evals.json so the
two never drift; each expectation index maps to a check function below.

Usage: python3 scripts/grade.py .eval-workspace/just-ask/iteration-1-sonnet [...more iteration dirs]"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def payloads(text):
    """Parse every fenced json block; normalize to a list of question lists."""
    out = []
    for block in re.findall(r"```json\s*(.*?)```", text, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            out.append(None)
            continue
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            out.append(data["questions"])
        elif isinstance(data, list):
            out.append(("BARE_ARRAY", data))
        else:
            out.append(None)
    return out


def prose(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def norm(qs):
    """Coerce malformed questions/options (plain strings) into dicts so checks fail cleanly instead of crashing."""
    out = []
    for q in qs:
        q = q if isinstance(q, dict) else {"question": str(q)}
        q = dict(q, options=[o if isinstance(o, dict) else {"label": str(o), "description": ""} for o in q.get("options", [])])
        out.append(q)
    return out


def qtext(qs):
    return " ".join(json.dumps(q).lower() for q in qs)


# ---------- just-ask checks ----------
def ask_one_payload(r, qs, p):
    ok = len(p) == 1 and isinstance(p[0], list)
    return ok, f"{len(p)} json block(s); first is {'a {questions:[...]} object' if ok else ('a bare array' if isinstance(p[0], tuple) else 'unparseable') if p else 'absent'}"


def ask_max4(r, qs, p):
    return qs is not None and 1 <= len(qs) <= 4, f"{len(qs) if qs is not None else 'no'} questions"


def ask_headers(r, qs, p):
    if qs is None:
        return False, "no payload"
    bad = [q.get("header", "") for q in qs if len(q.get("header", "")) > 12 or not q.get("header")]
    return not bad, f"headers over 12 chars or missing: {bad}" if bad else "all headers ≤12 chars"


def ask_recommended_first(r, qs, p):
    if qs is None:
        return False, "no payload"
    bad = []
    for q in qs:
        opts = q.get("options", [])
        if not (2 <= len(opts) <= 4) or not opts[0].get("label", "").endswith("(Recommended)"):
            bad.append(q.get("header", q.get("question", "?"))[:30])
        elif any("(Recommended)" in o.get("label", "") for o in opts[1:]):
            bad.append(q.get("header", "?") + " (multiple)")
    return not bad, f"violations: {bad}" if bad else "every question: 2–4 options, first labelled (Recommended)"


def ask_no_other(r, qs, p):
    if qs is None:
        return False, "no payload"
    bad = [o["label"] for q in qs for o in q.get("options", []) if o.get("label", "").strip().lower().startswith("other")]
    return not bad, f"manual Other options: {bad}" if bad else "no manual Other option"


def ask_descriptions(r, qs, p):
    if qs is None:
        return False, "no payload"
    bad = [o.get("label") for q in qs for o in q.get("options", []) if len(o.get("description", "").strip()) < 20]
    return not bad, f"missing/thin descriptions: {bad}" if bad else "every option has a reasoning description"


def not_asked(*pats):
    def check(r, qs, p):
        if qs is None:
            return False, "no payload"
        hits = [pt for pt in pats if re.search(pt, qtext(qs))]
        return not hits, f"asked about {hits}" if hits else f"none of {list(pats)} asked"
    return check


def asked(*pats):
    def check(r, qs, p):
        if qs is None:
            return False, "no payload"
        hit = [pt for pt in pats if re.search(pt, qtext(qs))]
        return bool(hit), f"matched {hit}" if hit else f"no question matches {list(pats)}"
    return check


def ask_round_or_assumptions(r, qs, p):
    t = prose(r).lower()
    ok = bool(re.search(r"round|assum|default|settled|dropped|convention", t))
    return ok, "prose mentions a further round or stated assumptions" if ok else "no mention of remaining items"


def ask_exact_none(r, qs, p):
    return r.strip() == "No open questions.", f"reply: {r.strip()[:80]!r}"


def ask_no_payload(r, qs, p):
    return not p, f"{len(p)} json block(s)"


# ---------- just-say-it checks ----------
ITEM = re.compile(r"^\d+\.\s+\*\*[^*]+\*\*\s+—\s+\S")


def lines(r):
    return [l for l in r.strip().splitlines() if l.strip()]


def say_no_preamble(r, meta):
    ls = lines(r)
    return bool(ls) and ls[0].startswith("1."), f"first line: {ls[0][:70]!r}" if ls else "empty"


def body(r):
    return [l for l in lines(r) if not l.startswith("Open decisions:")]


def say_format(r, meta):
    bad = [l[:50] for l in body(r) if not ITEM.match(l)]
    return not bad, f"non-conforming lines: {bad}" if bad else "every line is `N. **Label** — sentence`"


def say_max7(r, meta):
    n = sum(1 for l in body(r) if re.match(r"^\d+\.", l))
    return 1 <= n <= 7, f"{n} items"


def say_labels(r, meta):
    labels = [m.group(1) for l in body(r) if (m := re.match(r"^\d+\.\s+\*\*([^*]+)\*\*", l))]
    bad = [lb for lb in labels if len(lb.split()) > 4]
    return bool(labels) and not bad, f"labels over 4 words: {bad}" if bad else f"{len(labels)} labels, all ≤4 words"


def say_one_sentence(r, meta):
    bad = []
    for l in body(r):
        s = re.sub(r"`[^`]*`", "X", l.split("—", 1)[-1])
        s = re.sub(r"\b(e\.g|i\.e|vs|etc)\.", "", s)
        if len(re.findall(r"[.!?](\s|$)", s.strip())) > 1:
            bad.append(l[:40])
    return not bad, f"multi-sentence items: {bad}" if bad else "one sentence per item"


def say_no_tools(r, meta):
    return meta.get("num_turns", 1) <= 1, f"num_turns={meta.get('num_turns')}"


def say_covers(*groups):
    def check(r, meta):
        t = r.lower()
        miss = [g for g in groups if not re.search(g, t)]
        return not miss, f"missing: {miss}" if miss else "covers every key point"
    return check


def say_handoff(r, meta):
    last = lines(r)[-1] if lines(r) else ""
    ok = last.startswith("Open decisions:") and "/simplicity:just-ask" in last
    return ok, f"last line: {last[:90]!r}"


def say_no_handoff(r, meta):
    ok = not any(l.startswith("Open decisions:") for l in lines(r))
    return ok, "no open-decisions line" if ok else "spurious open-decisions line"


SAY_COMMON = [say_no_preamble, say_format, say_max7, say_labels, say_one_sentence, say_no_tools]
CHECKS = {
    ("just-ask", 1): [ask_one_payload, ask_max4, ask_headers, ask_recommended_first, ask_no_other, ask_descriptions,
                      not_asked(r"python", r"match statement"), not_asked(r"windows"), ask_round_or_assumptions],
    ("just-ask", 2): [ask_exact_none, ask_no_payload],
    ("just-ask", 3): [ask_one_payload, ask_max4, ask_headers, ask_recommended_first, ask_no_other, ask_descriptions,
                      not_asked(r"test runner", r"vitest", r"jest"), not_asked(r"ioredis", r"redis client", r"add a (redis )?client"),
                      asked(r"lock", r"429"), asked(r"reset", r"successful login")],
    ("just-say-it", 1): SAY_COMMON + [say_covers(r"n\+1|inventory_levels", r"carousel|recommendation", r"avif|webp|image", r"cache"), say_no_handoff],
    ("just-say-it", 2): SAY_COMMON + [say_covers(r"pip", r"docker", r"xdist|-n auto|parallel", r"shard|pytest-split|matrix"), say_no_handoff],
    ("just-say-it", 3): SAY_COMMON + [say_covers(r"adapter|storage", r"presigned", r"checksum|migrat"), say_handoff],
}


def grade_run(skill, eid, texts, run_dir):
    r = (run_dir / "outputs" / "response.md").read_text()
    meta = json.loads((run_dir / "outputs" / "result.json").read_text())
    checks = CHECKS[(skill, eid)]
    assert len(checks) == len(texts), f"{skill} eval {eid}: {len(checks)} checks vs {len(texts)} expectations"
    results = []
    for text, fn in zip(texts, checks):
        if skill == "just-ask":
            p = payloads(r)
            qs = p[0] if p and isinstance(p[0], list) else (p[0][1] if p and isinstance(p[0], tuple) else None)
            qs = norm(qs) if qs is not None else None
            ok, ev = fn(r, qs, p)
        else:
            ok, ev = fn(r, meta)
        results.append({"text": text, "passed": bool(ok), "evidence": ev})
    passed = sum(x["passed"] for x in results)
    timing = json.loads((run_dir / "timing.json").read_text())
    metrics = json.loads((run_dir / "outputs" / "metrics.json").read_text())
    (run_dir / "grading.json").write_text(json.dumps({
        "expectations": results,
        "summary": {"passed": passed, "failed": len(results) - passed, "total": len(results),
                    "pass_rate": round(passed / len(results), 2)},
        "execution_metrics": metrics,
        "timing": {"executor_duration_seconds": timing["executor_duration_seconds"], "grader_duration_seconds": 0.0,
                   "total_duration_seconds": timing["executor_duration_seconds"]},
    }, indent=2))
    return passed, len(results)


def main():
    for it_dir in map(Path, sys.argv[1:]):
        skill = it_dir.parent.name
        evals = {e["id"]: e for e in json.loads((REPO / "skills" / skill / "evals" / "evals.json").read_text())["evals"]}
        for eval_dir in sorted(it_dir.glob("eval-*")):
            eid = int(eval_dir.name.split("-")[1])
            for run_dir in sorted(eval_dir.glob("*/run-*")):
                p, t = grade_run(skill, eid, evals[eid]["expectations"], run_dir)
                print(f"{run_dir.relative_to(it_dir.parent.parent)}: {p}/{t}")


if __name__ == "__main__":
    main()
