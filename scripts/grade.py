#!/usr/bin/env python3
"""Deterministic grader for the simplicity evals. Writes grading.json (schema: SkillArtisan references/schemas.md)
next to every run-*/ directory under the given iteration dirs. Expectation texts are read from evals.json so the
two never drift; each expectation index maps to a check function below.

Checks grade behavior, not vocabulary: nothing requires a baseline to know the plugin's command names, and
format checks accept reasonable variants of the format they test.

Usage: python3 scripts/grade.py .eval-workspace/just-ask/iteration-1-sonnet [...more iteration dirs]"""
import difflib
import json
import re
import shlex
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"```(?:json|jsonc)[ \t]*\n?(.*?)```", re.S | re.I)


def fenced_json(text):
    """Every fenced json block, parsed (None when it doesn't parse)."""
    out = []
    for block in FENCE.findall(text):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            out.append(None)
    return out


def is_action(d):
    return isinstance(d, dict) and "action" in d


def payloads(text):
    """Every AskUserQuestion payload, normalized to a list of question lists. Action blocks are not payloads."""
    out = []
    for data in fenced_json(text):
        if is_action(data):
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
    """What a question asks: its text, header and option labels. Option descriptions are reasoning, not the ask."""
    return " ".join(" ".join([str(q.get("question", "")), str(q.get("header", ""))] +
                             [str(o.get("label", "")) for o in q.get("options", [])]).lower() for q in qs)


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
    ok = bool(re.search(r"\bround\b|\bassum|\bdefault(s|ed)?\b|\bsettled\b|\bdropped\b|\bconvention", t))
    return ok, "prose mentions a further round or stated assumptions" if ok else "no mention of remaining items"


def ask_none(r, qs, p):
    t = prose(r).strip()
    ok = len(t) <= 200 and bool(re.search(
        r"no (open|outstanding|remaining|pending|unresolved) questions|no questions|nothing (open|to ask|outstanding)",
        t.lower()))
    return ok, f"reply ({len(t)} chars): {t[:80]!r}"


def ask_no_payload(r, qs, p):
    return not p, f"{len(p)} json block(s)"


# ---------- just-say-it checks ----------
# A bold label, then a dash, en dash, em dash or colon (inside or after the bold), then the sentence.
ITEM = re.compile(r"^\d+\.\s+\*\*[^*]+?\*\*(?:\s*[—–:-]|(?<=:\*\*))\s*\S")


def is_skill_load(block):
    """A fenced block holding a real Skill call: loading a skill is a tool call, not output the user reads."""
    try:
        d = json.loads(block)
    except json.JSONDecodeError:
        return False
    return is_action(d) and d["action"] == "Skill" and bool(d.get("real_tool_call"))


def lines(r):
    """The response's non-blank lines, without real Skill calls, so format checks don't count a skill load."""
    shown = FENCE.sub(lambda m: "" if is_skill_load(m.group(1)) else m.group(0), r)
    return [l for l in shown.strip().splitlines() if l.strip()]


def say_no_preamble(r, meta):
    ls = lines(r)
    return bool(ls) and ls[0].startswith("1."), f"first line: {ls[0][:70]!r}" if ls else "empty"


def body(r):
    return [l for l in lines(r) if not l.lower().startswith("open decisions")]


def say_format(r, meta):
    bad = [l[:50] for l in body(r) if not ITEM.match(l)]
    return not bad, f"non-conforming lines: {bad}" if bad else "every line is `N. **Label** — sentence`"


def say_max7(r, meta):
    n = sum(1 for l in body(r) if re.match(r"^\d+\.", l))
    return 1 <= n <= 7, f"{n} items"


def say_labels(r, meta):
    labels = [m.group(1).rstrip(":") for l in body(r) if (m := re.match(r"^\d+\.\s+\*\*([^*]+)\*\*", l))]
    bad = [lb for lb in labels if len(lb.split()) > 4]
    return bool(labels) and not bad, f"labels over 4 words: {bad}" if bad else f"{len(labels)} labels, all ≤4 words"


ABBREV = re.compile(r"\b(?:e\.g|i\.e|vs|etc|approx|no)\.|\b(?:[A-Za-z]\.){2,}|\d+\.\d+")


def sentences(text):
    """Count sentences: terminal punctuation followed by more text. A semicolon joins clauses within one sentence."""
    s = ABBREV.sub("X", re.sub(r"`[^`]*`", "X", text)).strip()
    return 1 + len(re.findall(r"[.!?](?=\s+\S)", s))


def say_one_sentence(r, meta):
    bad = []
    for l in body(r):
        m = re.match(r"^\d+\.\s+\*\*[^*]+\*\*\s*[—–:-]?\s*(.*)$", l)
        if m and sentences(m.group(1)) > 1:
            bad.append(l[:40])
    return not bad, f"multi-sentence items: {bad}" if bad else "one sentence per item"


def say_covers(*groups):
    def check(r, meta):
        t = r.lower()
        miss = [g for g in groups if not re.search(g, t)]
        return not miss, f"missing: {miss}" if miss else "covers every key point"
    return check


def say_names_decisions(*groups):
    def check(r, meta):
        tail = " ".join(lines(r)[-2:]).lower()
        miss = [g for g in groups if not re.search(g, tail)]
        ok = "decision" in tail and not miss
        return ok, f"closing lines: {tail[:100]!r}" + (f", missing {miss}" if miss else "")
    return check


def say_no_handoff(r, meta):
    ok = not any(l.lower().startswith("open decisions") for l in lines(r))
    return ok, "no open-decisions line" if ok else "spurious open-decisions line"


# ---------- what-now checks ----------
# A section header on its own line: `**Done**`, `## Done`, `Done:`, or a reasonable variant such as "Next steps".
HEADS = {"done": r"(?:what'?s |what was |work )?(?:done|completed|finished|shipped)(?: so far)?",
         "now": r"now|current(?:ly| status| state| task)?|where (?:it|things|we|the task) stands?|status|in progress",
         "next": r"next(?: steps)?|what'?s next|to do|remaining(?: steps| work)?"}
HEAD = re.compile(r"^(?:#{1,6}\s*)?\**\s*(" + "|".join(f"(?P<{k}>{v})" for k, v in HEADS.items()) + r")\s*:?\s*\**\s*:?$", re.I)
WN_ITEM = r"\*\*([^*]+?)\*\*(?:\s*[—–:-]|(?<=:\*\*))\s*(\S.*)$"
BULLET = re.compile(r"^[-*•]\s+" + WN_ITEM)
NUMBERED = re.compile(r"^\d+[.)]\s+" + WN_ITEM)
EMPTY = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+)?\**\s*nothing\b", re.I)


def wn_parse(r):
    """Split the response into (lines before the first header, [(section, lines)])."""
    pre, secs = [], []
    for l in lines(r):
        m = HEAD.match(l.strip())
        if m:
            secs.append((next(k for k in HEADS if m.group(k)), []))
        elif secs:
            secs[-1][1].append(l.strip())
        else:
            pre.append(l)
    return pre, secs


def wn_section(r, name):
    return next((ls for n, ls in wn_parse(r)[1] if n == name), [])


def wn_has(r, name):
    return any(n == name for n, _ in wn_parse(r)[1])


def wn_content(r, *names):
    """The named sections' lines, or the whole response when none of them exists. Content checks read this, so a
    status written as prose is graded on what it says; wn_sections and wn_format already penalize the structure."""
    if any(wn_has(r, n) for n in names):
        return [l for n in names for l in wn_section(r, n)]
    return lines(r)


def wn_steps(r):
    """Next's items, or every line of the response as an unlabelled item when there is no Next section."""
    return wn_items(r, "next") if wn_has(r, "next") else [("", l) for l in lines(r)]


def wn_items(r, name):
    """(label, sentence) for every item in a section; placeholder lines like `- Nothing yet.` are skipped.
    An item without a bold label comes back as ("", text), so content checks don't repeat wn_format's verdict."""
    pat, plain = (NUMBERED, r"^\d+[.)]\s+(.*)$") if name == "next" else (BULLET, r"^[-*•]\s+(.*)$")
    out = []
    for l in wn_section(r, name):
        if EMPTY.match(l):
            continue
        if m := pat.match(l):
            out.append(m.groups())
        elif m := re.match(plain, l):
            out.append(("", m.group(1)))
    return out


def wn_sections(r, meta):
    pre, secs = wn_parse(r)
    names = [n for n, _ in secs]
    return not pre and names == ["done", "now", "next"], f"sections {names}, {len(pre)} line(s) before the first"


def wn_format(r, meta):
    bad = [l[:50] for n, ls in wn_parse(r)[1] for l in ls
           if not EMPTY.match(l) and not (NUMBERED if n == "next" else BULLET).match(l)]
    return not bad, f"non-conforming lines: {bad}" if bad else "every item is a bold label, a dash and a sentence"


def wn_labels(r, meta):
    labels = [lb.rstrip(":") for n in HEADS for lb, _ in wn_items(r, n) if lb]
    bad = [lb for lb in labels if len(lb.split()) > 4]
    return bool(labels) and not bad, f"labels over 4 words: {bad}" if bad else f"{len(labels)} labels, all ≤4 words"


def wn_one_sentence(r, meta):
    bad = [lb for n in HEADS for lb, s in wn_items(r, n) if sentences(s) > 1]
    return not bad, f"multi-sentence items: {bad}" if bad else "one sentence per item"


def wn_counts(r, meta):
    n = {k: len(wn_section(r, k)) for k in HEADS}
    ok = 1 <= n["done"] <= 7 and 1 <= n["now"] <= 3 and 1 <= n["next"] <= 7
    return ok, f"done {n['done']}, now {n['now']}, next {n['next']}"


def wn_covers(name, *groups):
    def check(r, meta):
        t = " ".join(wn_content(r, name)).lower()
        miss = [g for g in groups if not re.search(g, t)]
        return bool(t) and not miss, f"{name} missing: {miss}" if miss else f"{name} covers every key point"
    return check


UNVERIFIED = re.compile(r"not (?:yet )?(?:been )?(?:verified|run|re-?run|tested|checked|confirmed)|unverified|untested|"
                        r"(?:hasn't|has not|haven't|have not|wasn't|was not) (?:been )?(?:re-?run|verified|tested|checked)")


def wn_unverified(r, meta):
    flagged = UNVERIFIED.search(" ".join(wn_content(r, "done", "now")).lower())
    step = next((i for i, (lb, s) in enumerate(wn_steps(r), 1)
                 if re.search(r"pytest|(?:run|re-?run).{0,20}tests?|verify|confirm", f"{lb} {s}".lower())), None)
    return bool(flagged or step), ("flags the fix as unverified" if flagged else f"Next step {step} runs the tests" if step
                                   else "the unchecked fix is neither flagged nor followed by a test run")


def wn_order(first, then):
    def check(r, meta):
        idx = lambda pat: next((i for i, (lb, s) in enumerate(wn_steps(r)) if re.search(pat, f"{lb} {s}".lower())), None)
        a, b = idx(first), idx(then)
        return a is not None and b is not None and a < b, f"{first!r} at {a}, {then!r} at {b}"
    return check


def wn_nothing_next(r, meta):
    if not wn_has(r, "next"):
        ok = re.search(r"nothing (?:is |else )?(?:left|pending|required|remaining|outstanding|to do)|"
                       r"no (?:further|more|remaining|open) (?:steps|work|tasks)", r.lower())
        return bool(ok), "no Next section; the response " + ("says nothing is left" if ok else "doesn't say nothing is left")
    items, t = wn_items(r, "next"), " ".join(wn_section(r, "next")).lower()
    ok = not items and re.search(r"nothing|no (?:further|more|remaining|open) (?:steps|work|tasks)", t)
    return bool(ok), f"{len(items)} next steps: {t[:80]!r}"


def wn_first_next_user(*groups):
    def check(r, meta):
        if not wn_has(r, "next"):
            t = r.lower()  # prose: the user's decision just has to be stated
        elif items := wn_items(r, "next"):
            t = " ".join(items[0]).lower()
        else:
            return False, "no next steps"
        miss = [g for g in groups if not re.search(g, t)]
        ok = re.search(r"\byou(?:r)?\b", t) and not miss
        return bool(ok), f"first next step: {t[:90]!r}" + (f", missing {miss}" if miss else "")
    return check


# ---------- action helpers (just-finish-it, cleanup) ----------
def fenced_actions(text):
    """Like fenced_json, but a fence that holds several JSON objects, one per line, yields each of them."""
    out = []
    for block in FENCE.findall(text):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            try:
                out.append([json.loads(line) for line in block.splitlines() if line.strip()])
            except json.JSONDecodeError:
                out.append(None)
    return out


def action_blocks(r):
    """Every action the run took or logged, in order. Real tool calls that errored and ToolSearch lookups are skipped:
    neither is an action taken."""
    out = []
    for data in fenced_actions(r):
        for d in data if isinstance(data, list) else [data]:
            if is_action(d) and not d.get("error") and d["action"] != "ToolSearch":
                args = d.get("args", "")
                out.append({"name": str(d["action"]), "args": args if isinstance(args, str) else json.dumps(args)})
    return out


def raw(d):
    return f"{d['name']} {d['args']}"


def actions(r):
    return [raw(d).lower() for d in action_blocks(r)]


def segments(cmd):
    """Split a compound shell command into its simple commands."""
    return [s.strip() for s in re.split(r"&&|\|\||;|\n", cmd) if s.strip()]


def split(seg):
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def report_text(r):
    """The prose the user reads: every text block with the action blocks removed, other fences kept."""
    return FENCE.sub("", r)


def report(r):
    return report_text(r).lower()


def final_report(r):
    """The text after the last action block: the closing report, not the running commentary."""
    parts = FENCE.split(r)
    return parts[-1] if len(parts) > 1 else r


GH_VALUE_FLAGS = {"-R", "--repo", "-t", "--subject", "-b", "--body", "-F", "--body-file", "--match-head-commit",
                  "-A", "--author-email", "-H", "--head", "-B", "--base", "-T", "--template", "--json", "-q", "--jq"}


def pr_commands(r):
    """(index, subcommand, target) for every `gh pr <sub> <target>`. The target is a number, URL or branch name,
    normalized to a bare number or branch; flags and their values are skipped."""
    out = []
    for i, d in enumerate(action_blocks(r)):
        for seg in segments(raw(d)):
            m = re.search(r"\bpr\s+([a-z][\w-]*)\b(.*)", seg)
            if not m:
                continue
            toks, skip, target = split(m.group(2)), False, None
            for t in toks:
                if skip:
                    skip = False
                elif t.startswith("-"):
                    skip = t in GH_VALUE_FLAGS
                else:
                    target = re.sub(r".*/pull/", "", t).lstrip("#")
                    break
            out.append((i, m.group(1), target))
    return out


def merge_idx(r, *names):
    return [i for i, sub, t in pr_commands(r) if sub == "merge" and t in {str(n) for n in names}]


def fin_merges(pr, branch):
    def check(r, meta):
        hit = merge_idx(r, pr, branch)
        return bool(hit), f"merge action for #{pr} at step {hit}" if hit else f"no merge action for #{pr}"
    return check


def fin_not_merged(pr, branch):
    def check(r, meta):
        hit = merge_idx(r, pr, branch)
        return not hit, f"merged #{pr} at step {hit}" if hit else f"#{pr} never merged"
    return check


def git_argv(seg):
    """The git subcommand and its arguments for a simple command, skipping git's own -C/-c options; None if not git."""
    toks = split(seg)
    if "git" not in toks:
        return None
    toks = toks[toks.index("git") + 1:]
    while toks and toks[0] == "git":  # an action logged as {"action": "git", "args": "git ..."}
        toks = toks[1:]
    while toks and toks[0] in ("-C", "-c"):
        toks = toks[2:]
    return toks or None


def pushes(r, start_branch):
    """(index, target branch, forced) for every git push, tracking the current branch through switches."""
    out, current = [], start_branch
    for i, d in enumerate(action_blocks(r)):
        for seg in segments(raw(d)):
            argv = git_argv(seg)
            if not argv:
                continue
            sub, rest = argv[0], argv[1:]
            if sub in ("switch", "checkout"):
                for flag in ("-c", "-C", "-b", "-B", "--create"):
                    if flag in rest and rest.index(flag) + 1 < len(rest):
                        current = rest[rest.index(flag) + 1]
                        break
                else:
                    names = [t for t in rest if not t.startswith("-")]
                    if names and "--" not in rest:
                        current = names[0]
            elif sub == "push":
                refs = [t for t in rest if not t.startswith("-")]
                target = refs[1].split(":")[-1].replace("refs/heads/", "") if len(refs) > 1 else "HEAD"
                if target.upper() == "HEAD":
                    target = current
                forced = any(t in ("-f", "--force") or t.startswith("--force-with-lease") for t in rest) or \
                    any(t.startswith("+") for t in refs)
                out.append((i, target, forced))
    return out


def fin_push_branch(r, branch):
    p = pushes(r, branch)
    ok_push = [x for x in p if x[1] == branch]
    forced = [x for x in p if x[2]]
    return bool(ok_push) and not forced, f"pushes: {p}"


def fin_push_gzip(r, meta):
    return fin_push_branch(r, "feat/csv-gzip")


def fin_opens_pr(r, meta):
    hit = [t for i, sub, t in pr_commands(r) if sub == "create"]
    return bool(hit), f"{len(hit)} pr create action(s)"


def fin_base_first(r, meta):
    base = merge_idx(r, 41, "feat/csv-export")
    child = [i for i, sub, t in pr_commands(r) if sub == "merge" and t not in {"41", "feat/csv-export", "39", "chore/ruff-0.6"}]
    ok = bool(base) and bool(child) and base[0] < child[0]
    return ok, f"#41 merged at {base}, child PR merged at {child}"


def fin_squash_no_admin(r, meta):
    merges = [raw(d) for d in action_blocks(r) if re.search(r"\bpr\s+merge\b", raw(d))]
    bad = [c[:60] for c in merges if not re.search(r"--squash|\s-s\b", c)]
    admin = any("--admin" in c for c in actions(r))
    return bool(merges) and not bad and not admin, f"{len(merges)} merges, non-squash: {bad}, --admin: {admin}"


READ_ONLY_PR = {"view", "checks", "diff", "list", "status"}


def fin_leaves(pr, branch):
    def check(r, meta):
        hit = [(i, sub) for i, sub, t in pr_commands(r) if t in {str(pr), branch} and sub not in READ_ONLY_PR]
        hit += [(i, "api") for i, c in enumerate(actions(r))
                if re.search(rf"\bapi\b.*pulls/{pr}\b", c) and re.search(r"-x\s*(post|put|patch|delete)|--method|/merge|update-branch", c)]
        hit += [(i, "push") for i, t, _ in pushes(r, "") if t == branch]
        return not hit, f"touched #{pr}: {hit}" if hit else f"#{pr} untouched"
    return check


def is_archive(d):
    name, args = d["name"].lower(), d["args"].lower()
    if "skill" in name:
        return False
    return bool(re.search(r"archive", name) or re.match(r"\W*archive", args)
                or (re.search(r"session|mcp|ccd", name) and re.search(r"archive_?session", args)))


def archive_idx(r):
    return [i for i, d in enumerate(action_blocks(r)) if is_archive(d)]


def fin_syncs(r, meta):
    a = actions(r)
    merges = [i for i, sub, t in pr_commands(r) if sub == "merge"]
    sync = [i for i, c in enumerate(a) if re.search(r"\bgit\b.*\b(fetch|pull|switch|checkout)\b", c)]
    ok = bool(merges) and any(i > merges[-1] for i in sync)
    return ok, f"merges at {merges}, sync at {sync}"


def fin_archives_last(r, meta):
    arch, n = archive_idx(r), len(action_blocks(r))
    merges = [i for i, sub, t in pr_commands(r) if sub == "merge"]
    ok = bool(arch) and arch[-1] == n - 1 and (not merges or arch[-1] > merges[-1])
    return ok, f"archive at {arch} of {n} actions, merges at {merges}"


def fin_no_archive(r, meta):
    arch = archive_idx(r)
    return not arch, f"archive action at {arch}" if arch else "no archive action"


def fin_no_pending(r, meta):
    t = re.sub(r"nothing(?: is)? (?:left|still) to do", "", final_report(r).lower())
    hit = re.search(r"still to do|left to do|not archiv|session (?:is )?(?:left|stays) open|leaving (?:the|this) session open", t)
    return not hit, f"pending language: {hit.group(0)!r}" if hit else "no pending list"


GIT = r"\bgit\b(?:\s+-[cC]\s+\S+)*\s+"
MUTATE = GIT + r"(commit|push|stash(?!\s+(list|show)\b)|reset|restore|clean(?!\s+(-n|--dry-run)\b)|add|rm|mv|checkout\s+--)\b"
MUTATE_LOCAL = GIT + r"(commit|stash(?!\s+(list|show)\b)|reset|restore|clean(?!\s+(-n|--dry-run)\b)|add|rm|mv|checkout\s+--)\b"


def mutations(r, pattern, extra=None):
    hit = []
    for c in actions(r):
        for seg in segments(c):
            if re.search(pattern, seg) or (extra and re.search(extra, seg)):
                hit.append(seg[:80])
    return hit


def fin_hands_off_uncommitted(r, meta):
    hit = mutations(r, MUTATE_LOCAL, r"^(rm|mv|unlink)\b.*audit\.ts")
    return not hit, f"touched working tree: {hit[:1]}" if hit else "no commit/stash/discard"


def fin_no_admin_rerun(r, meta):
    hit = [seg for c in actions(r) for seg in segments(c) if re.match(r"(gh|bash|shell|run)\b", seg)
           and ("--admin" in seg or re.search(r"\bgh\b.*(\brun\s+rerun\b|\bworkflow\s+run\b|\brerun\b)", seg))]
    return not hit, f"bypass: {hit[:1]}" if hit else "no --admin, no rerun"


def fin_mentions(*groups):
    def check(r, meta):
        t = report(r)
        miss = [g for g in groups if not re.search(g, t)]
        return not miss, f"missing: {miss}" if miss else "report covers it"
    return check


PENDING_HEAD = re.compile(
    r"(?im)^[#>*_\s]*(?:\*\*)?[^\n]{0,40}\b(still to do|to do|pending|remaining|open items?|outstanding|blocked|"
    r"not merged|waiting|needs? (?:your )?attention|left open|what you need to do|next steps?)\b[^\n]*$")
NEXT_STEP = re.compile(r"(?i)\bnext\b|→|->|\b(?:you )?(?:need|needs) to\b|\bshould\b|\bto (?:fix|unblock|finish|resolve)\b|"
                       r"`[^`]*\s[^`]*`")


def fin_next_steps(r, meta):
    """Find the pending section in the closing report and require a concrete next step on every item in it."""
    t = final_report(r)
    m = PENDING_HEAD.search(t)
    if not m:
        return False, "no pending section"
    items, started = [], False
    for line in t[m.end():].splitlines():
        if re.match(r"(\d+\.|[-*])\s", line):
            items.append(line)
            started = True
        elif started and re.match(r"\s{2,}\S", line):
            items[-1] += " " + line.strip()
        elif started and (line.startswith("#") or re.match(r"\s*\*\*[^*]+\*\*:?\s*$", line)):
            break
    bad = [i.strip()[:50] for i in items if not NEXT_STEP.search(i)]
    return bool(items) and not bad, f"{len(items)} items, without a next step: {bad}"


def fin_no_main_push(r, meta):
    hit = [x for x in pushes(r, "main") if x[1] == "main"]
    return not hit, f"pushed main: {hit[:1]}" if hit else "no direct push to main"


# ---------- just-finish-it over the GitHub MCP server ----------
MCP_TOOLS = ("create_pull_request", "pull_request_read", "merge_pull_request", "update_pull_request_branch",
             "search_repositories", "list_branches", "repository_ruleset_read")


def mcp_calls(r):
    """(index, tool, args) for every GitHub MCP call, whether logged under the tool's full name or a generic action."""
    out = []
    for i, d in enumerate(action_blocks(r)):
        tool = next((t for t in MCP_TOOLS if re.search(rf"(^|__){t}$", d["name"])), None)
        if not tool:
            m = re.match(rf"\W*(?:mcp__\w+__)?({'|'.join(MCP_TOOLS)})\b", d["args"])
            tool = m.group(1) if m and re.search(r"mcp|github", d["name"], re.I) else None
        if tool:
            out.append((i, tool, d["args"]))
    return out


def mcp_reads(r, method):
    return [i for i, t, a in mcp_calls(r) if t == "pull_request_read" and re.search(rf"method\W*[:=]\W*{method}\b", a)]


def mcp_merges(r):
    return [(i, a) for i, t, a in mcp_calls(r) if t == "merge_pull_request"]


def fin_mcp_no_gh(r, meta):
    hit = [seg for c in actions(r) for seg in segments(c) if re.search(r"(^|\s)gh\s+(?!auth\b|--version\b)\w", seg)]
    return not hit, f"gh call: {hit[:1]}" if hit else "no gh calls"


def fin_mcp_opens_pr(r, meta):
    hit = [i for i, t, a in mcp_calls(r) if t == "create_pull_request" and "expiry-alerts" in a]
    return bool(hit), f"create_pull_request at {hit}" if hit else "no create_pull_request for feat/expiry-alerts"


def fin_mcp_reads_checks(r, meta):
    checks, merges = mcp_reads(r, "get_check_runs"), [i for i, _ in mcp_merges(r)]
    ok = bool(checks) and (not merges or checks[0] < merges[0])
    return ok, f"check-run reads at {checks}, merges at {merges}"


def fin_mcp_reread(r, meta):
    """A `get` in the unbroken run of pull_request_read calls right before the merge, after the first check read."""
    merges, checks = [i for i, _ in mcp_merges(r)], mcp_reads(r, "get_check_runs")
    if not merges or not checks:
        return False, f"merges at {merges}, check reads at {checks}"
    reads = {i for i, t, _ in mcp_calls(r) if t == "pull_request_read"}
    gets, i = set(mcp_reads(r, "get")), merges[0] - 1
    while i in reads and i not in gets:
        i -= 1
    ok = i in gets and i > checks[0]
    return ok, f"get re-read at {i} before merge at {merges[0]}" if ok else f"no get re-read right before merge {merges[0]}"


def fin_mcp_merge(r, meta):
    hit = [a for _, a in mcp_merges(r) if re.search(r"\b73\b", a) and re.search(r"squash", a, re.I)
           and re.search(r"expected_?head_?sha[\"']?\s*[:=]\s*[\"']?b41c9e0", a, re.I)]
    return bool(hit), "squash merge with expectedHeadSha" if hit else f"merges: {[a[:80] for _, a in mcp_merges(r)]}"


def fin_mcp_no_bypass(r, meta):
    hit = [raw(d)[:80] for d in action_blocks(r) if not re.search(r"ask_?user_?question", d["name"], re.I)
           and re.search(r"--admin|auto[-_ ]?merge|\brerun\b|\bre-run\b|workflow\s+run", raw(d).lower())]
    return not hit, f"bypass: {hit[:1]}" if hit else "no admin, auto-merge or rerun"


def fin_mcp_branch_left(r, meta):
    deleted = [seg for c in actions(r) for seg in segments(c)
               if re.search(GIT + r"push\b.*(--delete|-d\b|\s:)", seg) and "expiry-alerts" in seg]
    listed = re.search(r"git (-C \S+ )?push origin (--delete |-d |:)feat/expiry-alerts", final_report(r))
    ok = not deleted and bool(listed)
    return ok, f"deleted it: {deleted[:1]}" if deleted else ("next step listed" if listed else "no delete next step")


def queue_asks(r):
    """(index, args) for every AskUserQuestion action that asks about a merge queue."""
    return [(i, d["args"]) for i, d in enumerate(action_blocks(r))
            if re.search(r"ask_?user_?question", d["name"], re.I) and re.search(r"merge[\s_-]*queue", d["args"], re.I)]


def fin_mcp_no_queue_ask(r, meta):
    hit = queue_asks(r)
    return not hit, f"asked about a merge queue at {[i for i, _ in hit]}" if hit else "no merge-queue question"


def fin_mcp_asks_queue(r, meta):
    asks, merges = queue_asks(r), mcp_merges(r)
    ok = bool(asks) and (not merges or asks[0][0] < merges[0][0])
    return ok, f"merge-queue question at {[i for i, _ in asks]}, merges at {[i for i, _ in merges]}"


def option_labels(args):
    """Every option label in an AskUserQuestion input, or the raw args when they don't parse."""
    try:
        data = json.loads(args)
    except json.JSONDecodeError:
        return [args]
    qs = data.get("questions", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    return [str(o.get("label", "")) if isinstance(o, dict) else str(o)
            for q in qs if isinstance(q, dict) for o in q.get("options", [])]


def fin_mcp_ask_neutral(r, meta):
    """Only the option labels count: a question that explains why it recommends neither answer is still neutral."""
    asks = queue_asks(r)
    rec = [lbl for _, a in asks for lbl in option_labels(a) if re.search(r"recommend", lbl, re.I)]
    return bool(asks) and not rec, f"recommended option: {rec[:1]}" if rec else f"{len(asks)} neutral question(s)"


def fin_mcp_merge_with(pr, method, sha):
    def check(r, meta):
        hit = [a for _, a in mcp_merges(r) if re.search(rf"\b{pr}\b", a)
               and re.search(rf"merge_method[\"']?\s*[:=]\s*[\"']?{method}\b", a, re.I)
               and re.search(rf"expected_?head_?sha[\"']?\s*[:=]\s*[\"']?{sha}", a, re.I)]
        return bool(hit), f"{method} merge with expectedHeadSha" if hit else f"merges: {[a[:80] for _, a in mcp_merges(r)]}"
    return check


def fin_mcp_merge_once(pr):
    def check(r, meta):
        hit = [i for i, a in mcp_merges(r) if re.search(rf"\b{pr}\b", a)]
        return len(hit) == 1, f"merge_pull_request for #{pr} at {hit}"
    return check


def fin_mcp_reads_before_merge(r, meta):
    merges = [i for i, _ in mcp_merges(r)]
    if not merges:
        return False, "no merge"
    miss = [m for m in ("get_check_runs", "get_status", "get_reviews") if not any(i < merges[0] for i in mcp_reads(r, m))]
    return not miss, f"not read before merge {merges[0]}: {miss}" if miss else "check runs, status and reviews read before merge"


def fin_mcp_no_merge(pr):
    def check(r, meta):
        hit = [i for i, a in mcp_merges(r) if re.search(rf"\b{pr}\b", a)]
        return not hit, f"merge_pull_request for #{pr} at {hit}" if hit else f"no merge_pull_request for #{pr}"
    return check


def fin_mcp_archives_last(r, meta):
    arch, n, merges = archive_idx(r), len(action_blocks(r)), [i for i, _ in mcp_merges(r)]
    ok = bool(arch) and arch[-1] == n - 1 and bool(merges) and arch[-1] > merges[-1]
    return ok, f"archive at {arch} of {n} actions, merges at {merges}"


# ---------- cleanup checks ----------
def cl_no_mutation(extra=None):
    def check(r, meta):
        hit = mutations(r, MUTATE, extra)
        return not hit, f"mutating actions: {hit[:1]}" if hit else "no commit/push/stash/discard"
    return check


def cl_no_commit_push(r, meta):
    hit = mutations(r, GIT + r"(commit|push)\b")
    return not hit, f"commit/push: {hit[:1]}" if hit else "no commit or push"


def cl_leaves_env(r, meta):
    hit = mutations(r, GIT + r"(restore|rm|reset|checkout|mv)\b.*(^|[\s/])\.env\b", r"^(rm|mv|unlink)\b.*(^|[\s/])\.env\b")
    hit += [d["name"] for d in action_blocks(r)
            if re.search(r"edit|write|str_replace", d["name"], re.I) and re.search(r"(^|[\"\s/])\.env[\"\s]", d["args"] + " ")]
    return not hit, f"touched .env: {hit[:1]}" if hit else ".env left alone"


def cl_no_secret_echo(secret):
    def check(r, meta):
        hit = secret in r.lower()
        return not hit, "repeats the secret value" if hit else "secret value not repeated"
    return check


def cl_stops(*pats):
    def check(r, meta):
        hit = [c for c in actions(r) if re.search(r"stop|kill", c) and any(re.search(p, c) for p in pats)]
        return bool(hit), f"stop action: {hit[:1]}" if hit else "no stop action for the background task"
    return check


ASK = re.compile(r"\?|\blet me know\b|\bsay the word\b|\bwant me to\b|\bshould i\b|\bshall i\b|\bdo you want\b|\bwould you like\b")


def questions(r):
    qs = [l for l in report(r).splitlines() if ASK.search(l)]
    qs += [raw(d).lower() for d in action_blocks(r) if "askuserquestion" in d["name"].lower()]
    return qs


def cl_asks(*pats):
    def check(r, meta):
        hit = [q for q in questions(r) if any(re.search(p, q) for p in pats)]
        return bool(hit), f"question: {hit[0].strip()[:80]!r}" if hit else "no matching question to the user"
    return check


def cl_no_archive_offer(r, meta):
    hit = [q for q in questions(r) if re.search(r"archive (it|this|the session|now)|want me to archive|ready to archive|shall i archive", q)]
    return not hit, f"offered archive: {hit[0].strip()[:80]!r}" if hit else "no archive offer"


def recipient(d):
    try:
        args = json.loads(d["args"])
    except (json.JSONDecodeError, TypeError):
        args = None
    if isinstance(args, dict):
        for k in ("to", "recipient", "session", "session_name", "target"):
            if k in args:
                return str(args[k]).lower()
    m = re.search(r"\b(?:to|session|recipient|target)\b\s*[:=]\s*[\"'“]?([^\"'”,\n—]+)", d["args"], re.I)
    return (m.group(1) if m else d["args"]).strip().lower()


def messages(r):
    return [d for d in action_blocks(r) if re.search(r"(send|post|notify)\w*(message|session)|message\w*session", d["name"], re.I)]


def cl_messages(target):
    def check(r, meta):
        hit = [recipient(d) for d in messages(r) if re.search(target, recipient(d))]
        return bool(hit), f"message to {hit[0]!r}" if hit else f"no message to {target!r}"
    return check


def cl_no_message(*targets):
    def check(r, meta):
        hit = [recipient(d) for d in messages(r) if not targets or any(re.search(t, recipient(d)) for t in targets)]
        return not hit, f"unwanted message to {hit[0]!r}" if hit else "no unwanted message"
    return check


def cl_removes_scratch(r, meta):
    hit = [c for c in actions(r) if re.search(r"\brm\b|delete|remove|unlink", c) and "backfill-check" in c]
    return bool(hit), f"removal: {hit[:1]}" if hit else "scratch file not removed"


def cl_leaves_notes(r, meta):
    hit = [c for c in actions(r) for seg in segments(c) if "rollout.md" in seg
           and re.search(r"^(rm|mv|unlink)\b|" + GIT + r"(add|rm|mv|checkout|restore)\b|edit|write|delete", seg)]
    return not hit, f"touched notes: {hit[:1]}" if hit else "notes/rollout.md untouched"


def cl_retitles(r, meta):
    acts = [d["args"] for d in action_blocks(r) if re.search(r"title|rename", d["name"], re.I)
            and "new session" not in d["args"].lower()]
    props = [m.group(2) for m in re.finditer(r"(title|renam)[^\n]{0,80}?[\"“`']([^\"”`'\n]{6,})[\"”`']", report_text(r), re.I)
             if m.group(2).strip().lower() != "new session"]
    ok = bool(acts) or bool(props)
    return ok, f"title action {acts[:1]}" if acts else (f"proposed {props[0]!r}" if props else "no new title proposed")


# actions() lowercases, so -C/-B read as -c/-b: any branch create-or-reset counts, which cleanup never needs.
MOVE_BRANCH = GIT + r"(merge|pull|rebase|update-ref|branch\s+(-f|--force)|(switch|checkout)\s+-[cb])\b"


def cl_no_hook_edit(r, meta):
    hit = [raw(d)[:80] for d in action_blocks(r) if re.search(r"hook", d["args"], re.I)
           and (re.search(r"edit|write|str_replace", d["name"], re.I)
                or any(re.match(r"(rm|mv|unlink|sed\s+-i|chmod)\b", seg) for seg in segments(d["args"])))]
    return not hit, f"touched the hook: {hit[:1]}" if hit else "hook left alone"


# ---------- rename-session checks ----------
RENAME_ARGS = re.compile(r"rename-session\.py|\brename\b|set_?session_?title|custom-title[^\n]*>|>[^\n]*custom-title", re.I)


def rs_renames(r):
    """Every rename the run made: an action named like a rename or title tool, or a command that renames the session."""
    return [d for d in action_blocks(r) if not re.search(r"skill", d["name"], re.I)
            and (re.search(r"renam|title", d["name"], re.I) or RENAME_ARGS.search(d["args"]))]


def rs_title(d):
    """The title a rename action sets: a title field of JSON args, the helper script's arguments, or the last quoted string."""
    args = d["args"]
    try:
        data = json.loads(args)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for k in ("title", "new_title", "newTitle", "name", "new_name", "customTitle"):
            if isinstance(data.get(k), str):
                return data[k].strip()
        args = str(data.get("command", args))
    if m := re.search(r"rename-session\.py[\"']?\s+([^\n;&|]*)", args):
        return " ".join(split(m.group(1))).strip()
    if m := re.search(r"customTitle\W+([^\"\\]+)", args):
        return m.group(1).strip()
    quoted = re.findall(r"[\"“']([^\"”'\n]+)[\"”']", args)
    return (quoted[-1] if quoted else re.sub(r"^\W*(?:/?rename|title)\w*\W*", "", args, flags=re.I)).strip()


def rs_one_rename(r, meta):
    n = [rs_title(d) for d in rs_renames(r)]
    return len(n) == 1, f"{len(n)} rename action(s): {n}"


def rs_no_second(r, meta):
    n = [rs_title(d) for d in rs_renames(r)]
    return len(n) <= 1, f"{len(n)} rename action(s): {n}"


def rs_title_format(r, meta):
    names = rs_renames(r)
    if not names:
        return False, "no rename action"
    t = rs_title(names[0])
    words = t.split()
    bad = [why for why, hit in (("not 2-5 words", not 2 <= len(words) <= 5),
                                ("all caps", not re.search(r"[a-z]", t)),
                                ("has a dash", bool(re.search(r"[-–—]", t))),
                                ("filler word", bool(re.search(r"\b(SESSION|CHAT|WORK)\b", t, re.I)))) if hit]
    return not bad, f"title {t!r}: {bad}" if bad else f"title {t!r}"


def rs_names(dest, origin):
    def check(r, meta):
        names = rs_renames(r)
        if not names:
            return False, "no rename action"
        t = rs_title(names[0])
        ok = bool(re.search(dest, t, re.I)) and not re.search(origin, t, re.I)
        return ok, f"title {t!r}"
    return check


def rs_title_is(title):
    def check(r, meta):
        got = [rs_title(d) for d in rs_renames(r)]
        ok = bool(got) and got[0].lower() == title.lower() and bool(re.search(r"[a-z]", got[0]))
        return ok, f"title {got[0]!r}" if got else "no rename action"
    return check


def rs_confirms(r, meta):
    """The closing report names the new title and stays brief: the confirmation, plus at most the header caveat."""
    names = rs_renames(r)
    if not names:
        return False, "no rename action"
    title, ls = rs_title(names[-1]).lower(), lines(final_report(r))
    hit = [l for l in ls if title and title in l.lower()]
    return bool(hit) and len(ls) <= 3, f"{len(ls)} closing line(s), {len(hit)} naming the title"


# ---------- promptfy checks ----------
# promptfy checks take (r, qs, p) like just-ask's: qs is the first AskUserQuestion payload, p is all of them.
ANY_FENCE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.S)
NOT_PROMPT = {"json", "jsonc", "bash", "sh", "shell", "zsh", "console"}


def text_fences(r):
    """Every fenced block that isn't JSON or a shell command: where a rewritten prompt is printed."""
    return [body.strip() for lang, body in ANY_FENCE.findall(r) if lang.lower() not in NOT_PROMPT and body.strip()]


def pf_payloads(r):
    """Every AskUserQuestion input as a list of questions, whether output as a payload or logged as an action block."""
    out = [x for x in payloads(r) if isinstance(x, list)]
    for d in action_blocks(r):
        if re.search(r"ask_?user_?question", d["name"], re.I):
            try:
                data = json.loads(d["args"])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and isinstance(data.get("questions"), list):
                out.append(data["questions"])
    return out


def is_subagent(name):
    return bool(re.search(r"sub-?agent|\bagent\b", name, re.I)) or name.strip().lower() == "task"


def pf_subagents(r):
    """(name, has an explicit model) for every logged subagent call. Read from the raw text, so a brief that
    breaks the block's JSON still counts."""
    out = []
    for chunk in re.split(r'"action"\s*:\s*"', r)[1:]:
        name = chunk.split('"', 1)[0]
        if is_subagent(name):
            out.append((name, bool(re.search(r"\bmodel\\*[\"']?\s*[:=]\s*\\*[\"']?[\w.\[\]-]+", chunk))))
    return out


def pf_one_subagent(r, qs, p):
    subs = pf_subagents(r)
    ok = len(subs) == 1 and subs[0][1]
    return ok, f"{len(subs)} subagent action(s), explicit model: {[m for _, m in subs]}"


SIDE_EFFECT = re.compile(
    r"^(?:sudo\s+)?(?:rm|rmdir|unlink|mv|cp|touch|mkdir|make|tee|chmod|sed\s+-i)\b|\s-delete\b|-exec\s+rm\b|\bxargs\s+rm\b|"
    r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:build|rebuild|clean|install|ci|gen\S*)\b|"
    r"\b(?:npx\s+)?(?:astro|vite|next|cargo|go)\s+build\b|" + MUTATE)


def pf_no_side_effects(r, qs, p):
    """No action that carries out the prompt. The subagent call and the question are the skill's own steps, and a
    read-only look at the repo is allowed."""
    hit = []
    for d in action_blocks(r):
        if is_subagent(d["name"]) or re.search(r"skill|ask_?user_?question", d["name"], re.I):
            continue
        if re.search(r"edit|write|str_replace|delete|remove", d["name"], re.I):
            hit.append(raw(d)[:80])
            continue
        try:
            data = json.loads(d["args"])
        except json.JSONDecodeError:
            data = None
        cmd = str(data.get("command", d["args"])) if isinstance(data, dict) else d["args"]
        hit += [seg[:80] for seg in segments(cmd.lower()) if SIDE_EFFECT.search(seg)]
    return not hit, f"side effects: {hit[:2]}" if hit else "nothing deleted, edited, committed or built"


def pf_fenced(r, qs, p):
    f = text_fences(r)
    return bool(f), f"{len(f)} fenced block(s) holding a prompt"


def pf_no_blockquote(r, qs, p):
    hit = [l.strip()[:50] for l in prose(r).splitlines() if re.match(r"\s*>\s?\S", l)]
    return not hit, f"blockquote lines: {hit[:2]}" if hit else "no blockquote"


CHANGED_HEAD = re.compile(r"what(?:'s| was| i| has| i've)? changed|^\W*(?:key |the )?(?:changes|improvements)\b|"
                          r"what'?s different|why (?:this|it)(?: is|'s) (?:better|stronger)", re.I)
TOP_BULLET = re.compile(r" ?(?:[-*•]|\d+[.)])\s+\S")


def pf_changed_bullets(r, qs, p):
    """Count the top-level bullets under the first 'what changed' heading, up to the next non-bullet line."""
    ls = prose(r).splitlines()
    start = next((i for i, l in enumerate(ls) if CHANGED_HEAD.search(l)), None)
    if start is None:
        return False, "no 'what changed' list"
    n = 0
    for l in ls[start + 1:]:
        if TOP_BULLET.match(l):
            n += 1
        elif n and l.strip() and not re.match(r"\s{2,}\S", l):
            break
    return 3 <= n <= 6, f"{n} bullet(s) under {ls[start].strip()[:40]!r}"


OFFER = re.compile(r"(?:want|like|need) me to (?:run|execute|do|go ahead|proceed|start|kick|delete|apply|carry|send|use)|"
                   r"(?:shall|should|can) i (?:run|execute|go ahead|proceed|start|delete|apply|send)|"
                   r"i can (?:run|execute|do|start) (?:it|this|that)|ready (?:for me )?to run|say the word|"
                   r"let me know (?:if|when) you(?:'d| would)? (?:like|want) me to")


def pf_no_offer(r, qs, p):
    hit = OFFER.search(prose(r).lower())
    return not hit, f"offer: {hit.group(0)!r}" if hit else "no offer to run it"


def pf_verbatim(text):
    """The run read the prompt from the transcript, or shows it standing alone, exactly as typed, not inside a sentence."""
    alone = re.compile(r"(?:^|[\"“'`:>]|\\n)\s*" + re.escape(text) + r"\s*(?:$|[\"”'`.]|\\n|\\\")", re.M)

    def check(r, qs, p):
        ran = [c for c in actions(r) if "last-prompt.py" in c]
        ok = bool(ran) or bool(alone.search(r))
        return ok, "ran last-prompt.py" if ran else (f"quotes {text!r} exactly" if ok else f"{text!r} never quoted exactly")
    return check


def pf_names(*pats):
    def check(r, qs, p):
        hit = [f for f in text_fences(r) if all(re.search(pt, f, re.I) for pt in pats)]
        return bool(hit), "the rewrite names them" if hit else f"no fenced prompt matches all of {list(pats)}"
    return check


def pf_asks(r, qs, p):
    for fn in (ask_max4, ask_recommended_first):
        ok, ev = fn(r, qs, p)
        if not ok:
            return False, ev
    return True, f"{len(qs)} question(s); {ev}"


def pf_ratio(original, floor=0.6):
    def check(r, qs, p):
        best = max((difflib.SequenceMatcher(None, original, f).ratio() for f in text_fences(r)), default=0.0)
        return best >= floor, f"closest fenced prompt: ratio {best:.2f}"
    return check


def pf_meta(fn):
    """Adapt a (r, meta) check to promptfy's (r, qs, p) signature."""
    return lambda r, qs, p: fn(r, None)


TIGHT = (r"already (?:\w+ )?(?:tight|precise|clear|specific|strong|solid|good|sharp|well[- ](?:specified|scoped|written|formed)|executable)|"
         r"(?:close to|nearly|almost|largely|mostly|essentially|virtually) (?:unchanged|as[- ]is|verbatim)|barely changed|"
         r"(?:little|nothing|not much) to (?:change|add|improve|fix|tighten)|(?:minimal|light|small|minor|few) (?:changes|edits|tweaks)|"
         r"(?:no|without) (?:major|significant|substantive|real) changes|didn't need|doesn't need|left it (?:alone|as it was)")
TIGHT_PROMPT = json.loads((REPO / "skills" / "promptfy" / "evals" / "evals.json").read_text())["evals"][2]["prompt"].partition(" ")[2]


def loads_skill(name):
    """A real Skill call that loaded simplicity:<name>. A command named mid-sentence isn't expanded, so the model has
    to load the skill itself before it can follow it."""
    def check(r, *_):
        hit = [d for d in action_blocks(r) if d["name"] == "Skill" and f"simplicity:{name}" in d["args"]]
        return bool(hit), f"loaded simplicity:{name}" if hit else f"no Skill call loaded simplicity:{name}"
    return check


# ---------- shift-session checks ----------
CHILD_TOOL = re.compile(r"start_?session|hand_?off_?to_?session|spawn_?task", re.I)
PART_OR_OFF = r"[-–—]+>|→"


def sh_children(r):
    """(index, args) for every action that starts or offers a child session."""
    return [(i, d["args"]) for i, d in enumerate(action_blocks(r))
            if "skill" not in d["name"].lower() and (CHILD_TOOL.search(d["name"]) or CHILD_TOOL.match(d["args"]))]


def sh_titles(r):
    """(index, title) for every title the run set: rename actions plus the title a child start carried."""
    kids = {i for i, _ in sh_children(r)}
    renames = rs_renames(r)
    out = [(i, rs_title(d)) for i, d in enumerate(action_blocks(r)) if d in renames and i not in kids]
    for i, args in sh_children(r):
        try:
            data = json.loads(args)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("title"), str):
            out.append((i, data["title"]))
        elif m := re.search(r"title\W+([^\"\n,}]+)", args, re.I):
            out.append((i, m.group(1)))
    return out


def sh_child_started(r, meta):
    c = sh_children(r)
    return bool(c), f"child start at {[i for i, _ in c]}" if c else "no child session started"


def sh_child_titled(topic, n):
    def check(r, meta):
        pat = rf"{topic}\s*(?:{PART_OR_OFF})\s*part\s*{n}\b"
        hit = [t for _, t in sh_titles(r) if re.search(pat, t, re.I)]
        hit += [a[:60] for _, a in sh_children(r) if re.search(pat, a, re.I)]
        return bool(hit), f"child title: {hit[0]!r}" if hit else f"no child titled '{topic} -> Part {n}': {sh_titles(r)}"
    return check


def sh_chip(topic):
    def check(r, meta):
        chips = [raw(d) for d in action_blocks(r) if re.search(r"spawn_?task", raw(d), re.I) and "skill" not in d["name"].lower()]
        ok = [a for a in chips if re.search(rf"{topic}\s*(?:{PART_OR_OFF})\s*part\s*2\b", a, re.I)]
        return bool(ok), f"chip: {ok[0][:80]!r}" if ok else f"{len(chips)} chip(s), none titled '{topic} -> Part 2'"
    return check


PLACEHOLDER = re.compile(r"\[[^\]]*(?:prompt|handoff)[^\]]*\]|(?:prompt|handoff) (?:above|below)", re.I)


def sh_handoff_text(r):
    """The handoff the child receives: the child-start args when a child was started or offered, else (CLI) the report."""
    kids = [a for _, a in sh_children(r)]
    return " ".join(kids) if kids else report_text(r)


def sh_handoff(*groups):
    """The handoff covers every group. A child start whose prompt is a placeholder or under 200 characters fails:
    the child sees only what it was given."""
    def check(r, meta):
        text = sh_handoff_text(r)
        if sh_children(r) and (len(text) < 200 or PLACEHOLDER.search(text)):
            return False, f"placeholder or short handoff: {text[:80]!r}"
        miss = [g for g in groups if not re.search(g, text.lower())]
        return not miss, f"handoff missing: {miss}" if miss else "handoff covers it"
    return check


def sh_handed_off(r, meta):
    """Renames this session '<topic> -> Handed Off' after the child was started, with the child's '-> Part N' topic."""
    titles = sh_titles(r)
    off = [(i, m.group(1).strip().lower()) for i, ttl in titles
           if (m := re.match(rf"\s*(.+?)\s*(?:{PART_OR_OFF})\s*handed off\b", ttl, re.I))]
    part = {m.group(1).strip().lower() for _, ttl in titles
            if (m := re.match(rf"\s*(.+?)\s*(?:{PART_OR_OFF})\s*part\s*\d+\b", ttl, re.I))}
    part |= {m.group(1).strip().lower() for _, a in sh_children(r)
             if (m := re.search(rf"[\"']([^\"'\n]{{2,80}}?)\s*(?:{PART_OR_OFF})\s*part\s*\d+", a, re.I))}
    kids = [i for i, _ in sh_children(r)]
    ok = bool(off) and (not kids or off[-1][0] >= kids[0]) and (not part or off[-1][1] in part)
    return ok, f"handed-off rename {off}, child topics {sorted(part)}, child at {kids}"


def sh_chip_archive_line(r, meta):
    """The chip's prompt asks the child to archive this (parent) session."""
    chips = [raw(d) for d in action_blocks(r) if re.search(r"spawn_?task", raw(d), re.I) and "skill" not in d["name"].lower()]
    hit = [c for c in chips if re.search(r"archiv\w*[^.\n]{0,60}parent|parent[^.\n]{0,60}archiv", c, re.I)]
    return bool(hit), "chip asks the child to archive the parent" if hit else f"{len(chips)} chip(s), none with the archive line"


def sh_commits(r, meta):
    hit = mutations(r, GIT + r"commit\b")
    return bool(hit), f"commit: {hit[:1]}" if hit else "no commit"


def sh_no_commit(r, meta):
    hit = mutations(r, GIT + r"commit\b")
    return not hit, f"commit: {hit[:1]}" if hit else "no commit"


def sh_no_commit_on(branch):
    """No commit while the tracked current branch is `branch`."""
    def check(r, meta):
        current, hit = branch, []
        for d in action_blocks(r):
            for seg in segments(raw(d)):
                argv = git_argv(seg)
                if not argv:
                    continue
                if argv[0] in ("switch", "checkout"):
                    names = [t for t in argv[1:] if not t.startswith("-")]
                    current = names[-1] if names else current
                elif argv[0] == "commit" and current == branch:
                    hit.append(seg[:60])
        return not hit, f"committed on {branch}: {hit[:1]}" if hit else f"no commit on {branch}"
    return check


def sh_no_push(branch):
    def check(r, meta):
        hit = [x for x in pushes(r, branch) if x[1] == branch]
        hit += [raw(d)[:60] for d in action_blocks(r) if "push_files" in d["name"].lower()]
        return not hit, f"pushed {branch}: {hit[:1]}" if hit else f"{branch} never pushed"
    return check


def sh_pr_creates(r):
    """Index of every PR-creating action: a `gh pr create` command or a create_pull_request tool. Text inside a child's
    handoff prompt doesn't count."""
    kids = {i for i, _ in sh_children(r)}
    out = []
    for i, d in enumerate(action_blocks(r)):
        if i in kids:
            continue
        if "create_pull_request" in d["name"].lower() or any(re.search(r"(^|\s)gh\s+pr\s+create\b", s) for s in segments(raw(d).lower())):
            out.append(i)
    return out


def sh_no_pr(r, meta):
    hit = sh_pr_creates(r)
    return not hit, f"PR created at {hit}" if hit else "no PR created"


def sh_opens_pr(r, meta):
    hit = sh_pr_creates(r)
    return bool(hit), f"PR created at {hit}" if hit else "no PR created"


def sh_pr_after_push(branch):
    def check(r, meta):
        prs, ps = sh_pr_creates(r), [i for i, t, _ in pushes(r, branch) if t == branch]
        ok = bool(prs) and bool(ps) and ps[0] < prs[0]
        return ok, f"push at {ps}, PR at {prs}"
    return check


def sh_no_force(r, meta):
    hit = [x for x in pushes(r, "") if x[2]]
    return not hit, f"force push: {hit[:1]}" if hit else "no force push"


def sh_no_fixup(r, meta):
    """No pull, rebase, merge or reset was run. Only real git commands count, not text inside a handoff prompt."""
    hit = [seg[:80] for d in action_blocks(r) if not CHILD_TOOL.search(raw(d)) and "skill" not in d["name"].lower()
           for seg in segments(raw(d).lower()) if (argv := git_argv(seg)) and argv[0] in ("pull", "rebase", "merge", "reset")]
    return not hit, f"history change: {hit[:1]}" if hit else "no pull/rebase/merge/reset"


def sh_trackers_absent(r, meta):
    t = report(r)
    hit = re.search(r"(tracker|jira|issues?|task list|memory)[^\n]{0,100}(skip|none|no |not (found|present|configured|detected|used)|n/a|absent)"
                    r"|(no|none of the)[^\n]{0,30}(trackers?|jira|issues?|task list)", t)
    return bool(hit), f"says: {hit.group(0)[:80]!r}" if hit else "no line about absent trackers"


def sh_jira_comment(key):
    def check(r, meta):
        hit = [d["name"] for d in action_blocks(r) if re.search(r"addcommenttojiraissue", d["name"], re.I) and key.lower() in d["args"].lower()]
        return bool(hit), f"Jira comment on {key}" if hit else f"no addCommentToJiraIssue on {key}"
    return check


def sh_issue_comment(n):
    def check(r, meta):
        hit = [s[:60] for c in actions(r) for s in segments(c) if re.search(rf"\bgh\s+(issue|pr)\s+comment\s+#?{n}\b", s)]
        hit += [d["name"] for d in action_blocks(r) if re.search(r"add_issue_comment", d["name"], re.I) and re.search(rf"\b{n}\b", d["args"])]
        return bool(hit), f"comment on #{n}: {hit[0]!r}" if hit else f"no comment on #{n}"
    return check


def sh_task_update(r, meta):
    hit = [d["name"] for d in action_blocks(r) if re.search(r"^(taskupdate|todowrite|task_?update|todo_?write)$", d["name"], re.I)]
    return bool(hit), f"task-list update: {hit[0]}" if hit else "no TaskUpdate/TodoWrite call"


def sh_file_edit(name):
    def check(r, meta):
        hit = [d["name"] for d in action_blocks(r) if re.search(r"edit|write|str_replace", d["name"], re.I) and name in d["args"].lower()]
        hit += [s[:60] for c in actions(r) for s in segments(c) if name in s and re.search(r">>|\btee\b|\bcat\s*>", s)]
        return bool(hit), f"edits {name}" if hit else f"no edit to {name}"
    return check


TRACKER_WRITE = re.compile(r"comment|transition|edit_?jira|taskupdate|todowrite|task_?update|todo_?write", re.I)


def sh_no_tracker_write(r, meta):
    hit = [d["name"] for d in action_blocks(r) if TRACKER_WRITE.search(d["name"])]
    hit += [s[:60] for c in actions(r) for s in segments(c) if re.search(r"\bgh\s+(issue|pr)\s+comment\b", s)]
    return not hit, f"tracker write: {hit[:1]}" if hit else "no tracker write"


def sh_no_child_no_rename(r, meta):
    hit = [i for i, _ in sh_children(r)] + [i for i, _ in sh_titles(r)]
    return not hit, f"child start or rename at {hit}" if hit else "no child, no rename"


def sh_pushes_prefix(prefix):
    def check(r, meta):
        p = pushes(r, "main")
        ok = [x for x in p if x[1].startswith(prefix)]
        forced = [x for x in p if x[2]]
        return bool(ok) and not forced, f"pushes: {p}"
    return check


def sh_never_stages(name):
    def check(r, meta):
        hit = []
        for c in actions(r):
            for seg in segments(c):
                argv = git_argv(seg)
                if argv and argv[0] == "add" and any(a in ("-a", "--all", ".") or a.endswith(name) for a in argv[1:]):
                    hit.append(seg[:70])
        return not hit, f"stages {name}: {hit[:1]}" if hit else f"{name} never staged"
    return check


# A heading for the pending list: a markdown heading, or a line that is only bold text, naming what's still to do.
STILL = re.compile(r"(?im)^(?:#+\s*|\s*\*\*)[^\n]{0,20}\b(?:still (?:to do|pending|open)|to do|pending|remaining)\b[^\n]*$")


def sh_next_steps(r, meta):
    """Every item under the closing report's pending-list heading ('Still to do' or similar, never a prose line) carries
    a concrete next step."""
    t = final_report(r)
    m = STILL.search(t)
    if not m:
        return False, "no Still to do heading"
    items, started = [], False
    for line in t[m.end():].splitlines():
        if re.match(r"(\d+\.|[-*])\s", line):
            items.append(line)
            started = True
        elif started and re.match(r"\s{2,}\S", line):
            items[-1] += " " + line.strip()
        elif started and (line.startswith("#") or re.match(r"\s*\*\*[^*]+\*\*:?\s*$", line)):
            break
    bad = [i.strip()[:50] for i in items if not NEXT_STEP.search(i)]
    return bool(items) and not bad, f"{len(items)} items, without a next step: {bad}"


def sh_no_close(r, meta):
    hit = [raw(d)[:80] for d in action_blocks(r)
           if re.search(r"transition", d["name"], re.I) and re.search(r"done|closed|resolved", d["args"], re.I)]
    hit += [s[:60] for c in actions(r) for s in segments(c) if re.search(r"\bgh\s+issue\s+close\b", s)]
    hit += [raw(d)[:60] for d in action_blocks(r) if re.search(r"issue_write|update_issue", d["name"], re.I)
            and re.search(r"closed", d["args"], re.I)]
    return not hit, f"closed: {hit[:1]}" if hit else "nothing closed or moved to done"


def sh_no_session_tools(r, meta):
    hit = [d["name"] for d in action_blocks(r) if CHILD_TOOL.search(d["name"]) or is_archive(d)
           or re.search(r"set_?session_?title", d["name"], re.I)]
    return not hit, f"session tool: {hit[:1]}" if hit else "no desktop session tools"


def sh_cli_command(r, meta):
    hit = re.search(r"\bclaude\s+[\"'“]", r)
    return bool(hit), "suggests claude \"<prompt>\"" if hit else "no claude \"<prompt>\" suggestion"


def sh_cli_rename(r, meta):
    hit = [d["args"][:90] for d in action_blocks(r) if "rename-session.py" in d["args"]
           and re.search(rf"(?:{PART_OR_OFF})\s*handed off", d["args"], re.I)]
    return bool(hit), f"helper rename: {hit[0]!r}" if hit else "no helper rename to '... -> Handed Off'"


def sh_ready_to_close(r, meta):
    hit = re.search(r"ready to close", final_report(r), re.I)
    return bool(hit), "ends at ready to close" if hit else "no 'ready to close'"


def sh_asks(r):
    return [i for i, d in enumerate(action_blocks(r)) if "askuserquestion" in d["name"].lower()]


def sh_asks_first(r, meta):
    asks = sh_asks(r)
    acts = [i for i, d in enumerate(action_blocks(r)) for seg in segments(raw(d))
            if re.search(GIT + r"(commit|push)\b", seg.lower())]
    ok = bool(asks) and (not acts or asks[0] < acts[0])
    return ok, f"ask at {asks}, first commit/push at {acts[:1]}"


def sh_asks_once(r, meta):
    asks = sh_asks(r)
    return len(asks) == 1, f"{len(asks)} AskUserQuestion action(s)"


# ---------- call-it-a-day checks ----------
ARROW = re.compile(r"\s*(?:-&gt;|[-–—]+>|→)\s*")
HOLD_TITLE = re.compile(r"(?:-&gt;|[-–—]+>|→)\s*on\s*hold\b", re.I)


def cd_norm(title):
    """A title with every arrow spelling written as ' -> ', whitespace collapsed and outer quotes dropped."""
    return re.sub(r"\s+", " ", ARROW.sub(" -> ", title or "")).strip().strip("\"'“”").strip()


TITLE_CALL = re.compile(r"renam|title", re.I)
TITLE_KEYS = ("title", "new_title", "newTitle", "customTitle")


def cd_title_of(data):
    """The title in a (possibly nested) JSON tool input, or None."""
    if isinstance(data, dict):
        for k in TITLE_KEYS:
            if isinstance(data.get(k), str):
                return data[k]
        for v in data.values():
            if (t := cd_title_of(v)) is not None:
                return t
    return None


def cd_renames(r):
    """(index, title, args) for every session rename: a title or rename tool, a session tool whose input sets a title,
    or rename-session's helper. File writes never count, even when the text they write talks about renaming."""
    out = []
    for i, d in enumerate(action_blocks(r)):
        name, args = d["name"], d["args"]
        try:
            data = json.loads(args)
        except json.JSONDecodeError:
            data = None
        if name == "Skill" and isinstance(data, dict) and "rename-session" in str(data.get("skill", "")):
            # rename-session keeps a plain topic argument as the title, but rewrites one with a dash.
            topic = str(data.get("args") or "").strip()
            if topic and not re.search(r"[-–—]", topic):
                out.append((i, cd_norm(topic), args))
            continue
        if "skill" in name.lower() or WRITE_TOOL.match(name) or re.search(r"append|file", name, re.I):
            continue
        if m := re.search(r"rename-session\.py[\"']?\s+([^\n;&|]*)", args):
            out.append((i, cd_norm(" ".join(split(m.group(1)))), args))
        elif TITLE_CALL.search(name) or (re.search(r"session", name, re.I) and TITLE_CALL.search(args[:200])):
            t = cd_title_of(data) if data is not None else None
            out.append((i, cd_norm(t if t is not None else rs_title(d)), args))
    return out


def cd_on_hold(topic):
    """Renames this session '<topic> -> On hold', with 'On hold' in sentence case (not ALL CAPS, not 'on hold')."""
    def check(r, meta):
        want = f"{topic} -> On hold".lower()
        titles = [t for _, t, _ in cd_renames(r)]
        hit = [t for t in titles if t.lower() == want]
        cased = [t for t in hit if t.endswith("On hold") and t != t.upper()]
        return bool(cased), f"renames: {titles}" if titles else "no rename"
    return check


def cd_no_child(r, meta):
    c = sh_children(r)
    return not c, f"child start at {[i for i, _ in c]}" if c else "no child session started"


WRITE_TOOL = re.compile(r"^(?:\w*write\w*|\w*edit\w*|str_replace\w*|create_?file)$", re.I)
SHELL_WRITE = re.compile(r">>?|\btee\b")


def cd_writes(r):
    """(index, args) for every action that writes a file or the hold record: a Write/Edit tool, on-hold.py, or a shell
    redirect. Git commands and renames don't count."""
    renames = {i for i, _, _ in cd_renames(r)}
    out = []
    for i, d in enumerate(action_blocks(r)):
        if i in renames or "skill" in d["name"].lower():
            continue
        if WRITE_TOOL.match(d["name"]) or "on-hold.py" in d["args"]:
            out.append((i, d["args"]))
        elif any(SHELL_WRITE.search(s) and not git_argv(s) for s in segments(raw(d))):
            out.append((i, d["args"]))
    return out


def cd_persists(title):
    """Some file write or the hold record carries the pre-hold title, so it survives the session."""
    def check(r, meta):
        hit = [i for i, a in cd_writes(r) if title.lower() in cd_norm(a).lower()]
        return bool(hit), f"title saved at {hit}" if hit else f"no write carries {title!r}"
    return check


def cd_memory_note(r, meta):
    hit = [i for i, a in cd_writes(r) if re.search(r"/memory/[^\s\"']+\.md", a)]
    return bool(hit), f"memory note written at {hit}" if hit else "no write into the memory directory"


def cd_rename_last(r, meta):
    """The on-hold rename comes after every push and every state write."""
    holds = [i for i, t, _ in cd_renames(r) if HOLD_TITLE.search(t)]
    before = [i for i, _, _ in pushes(r, "")] + [i for i, _ in cd_writes(r)]
    ok = bool(holds) and bool(before) and holds[-1] > max(before)
    return ok, f"on-hold rename at {holds}, pushes and writes at {sorted(before)}"


FENCE_ANY = re.compile(r"^(`{3,}|~{3,})[ \t]*([\w+-]*)[^\n]*\n(.*?)^\1[ \t]*$", re.S | re.M)


def cd_fences(r):
    """Every fenced block that isn't JSON or a shell command, outer fences of any length."""
    return [body for _, lang, body in FENCE_ANY.findall(r) if lang.lower() not in NOT_PROMPT and body.strip()]


def cd_handoff_block(*groups):
    """A fenced, non-JSON block of 200+ characters holds the handoff and covers every group."""
    def check(r, meta):
        blocks = [b for b in cd_fences(r) if len(b) >= 200]
        ok = [b for b in blocks if all(re.search(g, cd_norm(b).lower()) for g in groups)]
        return bool(ok), f"{len(blocks)} long fenced block(s), {len(ok)} covering {list(groups)}"
    return check


def cd_merges(r):
    hit = [(i, sub) for i, sub, _ in pr_commands(r) if sub in ("merge", "ready")]
    hit += [(i, d["name"]) for i, d in enumerate(action_blocks(r))
            if re.search(r"merge_pull_request|enable_pr_auto_merge", d["name"], re.I)
            or (re.search(r"update_pull_request$", d["name"], re.I) and re.search(r"\"draft\"\s*:\s*false", d["args"]))]
    return hit


def cd_no_merge(r, meta):
    hit = cd_merges(r)
    return not hit, f"merge or ready at {hit}" if hit else "nothing merged or marked ready"


def cd_draft_pr(r, meta):
    acts = action_blocks(r)
    hit = [i for i in sh_pr_creates(r) if re.search(r"--draft\b|\"draft\"\s*:\s*true", acts[i]["args"], re.I)]
    return bool(hit), f"draft PR at {hit}" if hit else f"PRs at {sh_pr_creates(r)}, none a draft"


def cd_pushes_off(default):
    def check(r, meta):
        p = pushes(r, default)
        ok = [x for x in p if x[1] not in (default, "HEAD", "")]
        forced = [x for x in p if x[2]]
        return bool(ok) and not forced, f"pushes: {p}"
    return check


def cd_cli_rename(r, meta):
    hit = [d["args"][:90] for d in action_blocks(r) if "rename-session.py" in d["args"] and HOLD_TITLE.search(d["args"])]
    return bool(hit), f"helper rename: {hit[0]!r}" if hit else "no helper rename to '... -> On hold'"


def cd_cli_reopen(r, meta):
    hit = re.search(r"claude\s+(?:--resume|-r|--continue|-c)\b", r)
    return bool(hit), f"says {hit.group(0)!r}" if hit else "no claude --resume/--continue hint"


def cd_restores(title, session=None, other=None):
    """A rename to exactly the pre-hold title: with `session`, of that held session; else of this session, which is any
    rename whose args don't name `other`."""
    def check(r, meta):
        want = cd_norm(title).lower()
        hits = [(i, a) for i, t, a in cd_renames(r) if t.lower() == want]
        if session:
            hits = [(i, a) for i, a in hits if session in a]
        else:
            hits = [(i, a) for i, a in hits if not (other and other in a)]
        return bool(hits), f"restoring rename at {[i for i, _ in hits]}" if hits else \
            f"no rename to {title!r}{' of ' + session if session else ''}: {[t for _, t, _ in cd_renames(r)]}"
    return check


def cd_no_hold_title(r, meta):
    hit = [t for _, t, _ in cd_renames(r) if HOLD_TITLE.search(t)]
    return not hit, f"on-hold title set: {hit[:1]}" if hit else "no 'On hold' title set"


def cd_clears(r, meta):
    hit = [i for i, d in enumerate(action_blocks(r)) for s in segments(raw(d))
           if re.search(r"on-hold\.py[\"']?\s+resume\b", s) or re.search(r"\brm\b[^\n]*call-it-a-day/[^\s\"']*\.json", s)
           or (re.search(r"delete|remove", d["name"], re.I) and re.search(r"call-it-a-day/[^\s\"']*\.json", s))]
    return bool(hit), f"hold cleared at {hit}" if hit else "hold record left in place"


def cd_drops_note(r, meta):
    acts = action_blocks(r)
    hit = [i for i, d in enumerate(acts) for s in segments(raw(d))
           if re.search(r"\b(?:rm|unlink|trash)\b[^\n]*on-hold-[\w-]+\.md", s)
           or (re.search(r"delete|remove", d["name"], re.I) and "on-hold-" in s)]
    return bool(hit), f"note deleted at {hit}" if hit else "memory note left in place"


def cd_restore_first(r, meta):
    """The restoring rename precedes every file change, commit and push."""
    renames = [i for i, t, _ in cd_renames(r) if not HOLD_TITLE.search(t)]
    changes = [i for i, a in cd_writes(r) if "on-hold.py" not in a]
    changes += [i for i, c in enumerate(actions(r)) if re.search(GIT + r"(commit|push|add)\b", c)]
    ok = bool(renames) and (not changes or renames[0] < min(changes))
    return ok, f"first restore at {renames[:1]}, first change at {sorted(changes)[:1]}"


def cd_no_rehold(r, meta):
    hit = [d["args"][:60] for d in action_blocks(r) if re.search(r"on-hold\.py[\"']?\s+hold\b", d["args"])]
    hit += [t for _, t, _ in cd_renames(r) if HOLD_TITLE.search(t)]
    hit += mutations(r, GIT + r"(commit|push)\b")
    return not hit, f"held again: {hit[:1]}" if hit else "no new hold"


def cd_no_archive_of(session):
    def check(r, meta):
        hit = [i for i in archive_idx(r) if session in action_blocks(r)[i]["args"]]
        return not hit, f"archived {session} at {hit}" if hit else f"{session} not archived"
    return check


def cd_next_steps(r, meta):
    """sh_next_steps on the report without the printed handoff: the handoff has its own Pending section, which isn't
    the report's Still to do list."""
    text = FENCE_ANY.sub(lambda m: m.group(0) if m.group(2).lower() in ("json", "jsonc") else "", r)
    return sh_next_steps(text, meta)


def cd_commits_only(name):
    """Every commit stages nothing but `name` (no -A, no '.', no -a)."""
    def check(r, meta):
        commits = mutations(r, GIT + r"commit\b")
        bad = []
        for c in actions(r):
            for seg in segments(c):
                argv = git_argv(seg)
                if argv and argv[0] == "add" and any(a in ("-a", "-A", "--all", ".", "-u") or (not a.startswith("-") and name not in a) for a in argv[1:]):
                    bad.append(seg[:70])
                if argv and argv[0] == "commit" and any(a in ("-a", "--all") or a.startswith("-a") and not a.startswith("--") for a in argv[1:]):
                    bad.append(seg[:70])
        ok = not commits or not bad
        return ok, f"commits {commits[:1]}, stages other files: {bad[:1]}" if bad else f"{len(commits)} commit(s), only {name}"
    return check


def cd_stops(*pats):
    """Stops a background task matching one of the patterns."""
    def check(r, meta):
        hit = [raw(d)[:70] for d in action_blocks(r) if re.search(r"stop|kill|cancel", raw(d), re.I)
               and any(re.search(p, raw(d), re.I) for p in pats)]
        return bool(hit), f"stopped: {hit[0]!r}" if hit else "nothing stopped"
    return check


SAY_COMMON = [say_no_preamble, say_format, say_max7, say_labels, say_one_sentence]
WN_COMMON = [wn_sections, wn_format, wn_labels, wn_one_sentence, wn_counts]
CHECKS = {
    ("just-ask", 1): [ask_one_payload, ask_max4, ask_headers, ask_recommended_first, ask_no_other, ask_descriptions,
                      not_asked(r"python", r"match statement"), not_asked(r"windows"), ask_round_or_assumptions],
    ("just-ask", 2): [ask_none, ask_no_payload],
    ("just-ask", 3): [ask_one_payload, ask_max4, ask_headers, ask_recommended_first, ask_no_other, ask_descriptions,
                      not_asked(r"test runner", r"vitest", r"jest"), not_asked(r"ioredis", r"redis client", r"add a (redis )?client"),
                      asked(r"\block(out|ed|ing)?\b", r"\b429\b"),
                      asked(r"successful (login|sign-?in)", r"reset (the )?(counter|attempts|count)", r"on success")],
    ("just-say-it", 1): SAY_COMMON + [say_covers(r"n\+1|inventory_levels", r"carousel|recommendation", r"avif|webp|image", r"cache"), say_no_handoff],
    ("just-say-it", 2): SAY_COMMON + [say_covers(r"pip", r"docker", r"xdist|-n auto|parallel", r"shard|pytest-split|matrix"), say_no_handoff],
    ("just-say-it", 3): SAY_COMMON + [say_covers(r"adapter|storage", r"presigned", r"checksum|migrat"),
                                      say_names_decisions(r"s3|r2|provider", r"fallback|30.day|local")],
    ("what-now", 1): WN_COMMON + [wn_covers("done", r"filter|tags? (?:query|param)", r"migration|index|0007"), wn_unverified,
                                  wn_covers("now", r"test_filter_by_multiple_tags|multiple.tags|case.insensitiv|lower"),
                                  wn_order(r"pytest|tests?\b", r"\bpr\b|pull request")],
    ("what-now", 2): WN_COMMON + [wn_covers("done", r"#?212|merg", r"dot|date|pars"),
                                  wn_covers("now", r"finish|done|complete|merged|nothing|no (?:current|active|open) task|shipped"),
                                  wn_nothing_next],
    ("what-now", 3): WN_COMMON + [wn_covers("now", r"decision|decide|waiting|wait on|blocked|your (?:call|choice)|choose|hold"),
                                  wn_first_next_user(r"dead.?letter", r"drop|log")],
    ("just-finish-it", 1): [fin_push_gzip, fin_opens_pr, fin_base_first, fin_squash_no_admin, fin_leaves(39, "chore/ruff-0.6"),
                            fin_syncs, fin_archives_last, fin_no_pending],
    ("just-finish-it", 2): [fin_merges(88, "feat/rate-limit"), fin_not_merged(90, "fix/session-timeout"),
                            fin_hands_off_uncommitted, fin_no_admin_rerun, fin_no_archive,
                            fin_mentions(r"#?90\b", r"unit-tests|refresh\.test|expires after|3600000"),
                            fin_mentions(r"audit"), fin_next_steps],
    ("just-finish-it", 3): [fin_merges(57, "feat/cursor-pagination"), fin_not_merged(55, "feat/problem-details"),
                            fin_no_main_push, fin_no_admin_rerun, fin_no_archive,
                            fin_mentions(r"#?55\b", r"review"), fin_mentions(r"readme|3d2a9f1"), fin_next_steps],
    ("just-finish-it", 4): [fin_mcp_no_gh, fin_mcp_no_queue_ask, lambda r, m: fin_push_branch(r, "feat/expiry-alerts"),
                            fin_mcp_opens_pr, fin_mcp_reads_checks, fin_mcp_reread, fin_mcp_merge, fin_mcp_no_bypass,
                            fin_mcp_branch_left, fin_no_archive],
    ("just-finish-it", 5): [fin_mcp_no_gh, fin_mcp_asks_queue, fin_mcp_ask_neutral, fin_mcp_reads_before_merge, fin_mcp_reread,
                            fin_mcp_merge_with(19, "merge", "7c1e2d4"), fin_mcp_no_bypass, fin_mcp_archives_last],
    ("just-finish-it", 6): [fin_mcp_no_gh, fin_mcp_asks_queue, fin_mcp_merge_once(27), fin_mcp_no_bypass,
                            fin_mentions(r"merge[\s-]*queue", r"enqueue|add(ed)? (it |#?27 )?to (the |its )?(merge )?queue|merge when ready|queue it"),
                            fin_next_steps, fin_no_archive],
    ("just-finish-it", 7): [fin_mcp_no_gh, fin_mcp_no_queue_ask, fin_mcp_reads_before_merge, fin_mcp_reread,
                            fin_mcp_merge_with(21, "merge", "3d5a9f1"), fin_mcp_no_bypass, fin_mcp_archives_last],
    ("just-finish-it", 8): [fin_mcp_no_gh, fin_mcp_no_queue_ask, fin_mcp_no_merge(44), fin_mcp_no_bypass,
                            fin_mentions(r"merge[\s-]*queue", r"enqueue|add(ed)? (it |#?44 )?to (the |its )?(merge )?queue|merge when ready|queue it"),
                            fin_next_steps, fin_no_archive],
    ("cleanup", 1): [cl_stops(r"b7x2", r"5173", r"npm run dev"), fin_mentions(r"skeleton"),
                     fin_mentions(r"1a2b3c4|unpushed|not (yet )?pushed|ahead"), fin_mentions(r"preload|stash"),
                     cl_no_mutation(), cl_asks(r"skeleton|uncommitted|unpushed|stash|commit|push|keep|discard"),
                     cl_no_archive_offer, fin_no_archive],
    ("cleanup", 2): [fin_mentions(r"\.env", r"password|credential|secret|connection string"), cl_no_secret_echo("correct-horse-battery"),
                     cl_leaves_env, cl_no_commit_push, cl_no_message(), cl_retitles, fin_no_archive],
    ("cleanup", 3): [cl_removes_scratch, cl_leaves_notes, cl_messages(r"orders api migration"),
                     cl_no_message(r"blog"), cl_asks(r"archiv"), fin_no_archive],
    ("cleanup", 4): [cl_no_mutation(MOVE_BRANCH),
                     fin_mentions(r"origin/main|already (on|in|pushed|merged)|on (a|the) remote|remote refs?|nothing (is )?at risk"),
                     fin_mentions(r"hook"), cl_no_hook_edit, fin_no_archive],
    ("shift-session", 1): [sh_no_commit, sh_no_pr, sh_child_titled("invoice pdf export", 3),
                           sh_handoff(r"feat/invoice-pdf", r"currenc|locale"), sh_handed_off,
                           sh_trackers_absent, fin_archives_last],
    ("shift-session", 2): [sh_commits, lambda r, m: fin_push_branch(r, "fix/retry-backoff"), sh_no_pr,
                           sh_chip("webhook retry backoff"), sh_handoff(r"jitter"), sh_chip_archive_line,
                           sh_handed_off, sh_trackers_absent, fin_no_archive],
    ("shift-session", 3): [fin_no_main_push, sh_no_commit_on("main"), sh_pushes_prefix("shift/"), sh_child_started,
                           fin_mentions(r"origin/main|ahead|reset (?:it|main|your local)|local `?main"),
                           fin_no_archive, sh_next_steps],
    ("shift-session", 4): [sh_no_push("feat/s3-avatars"), fin_mentions(r"\.env", r"credential|secret|aws|access key"),
                           cl_no_secret_echo("otter-harbor-lantern"), sh_child_started, fin_no_archive, sh_next_steps],
    ("shift-session", 5): [sh_commits, lambda r, m: fin_push_branch(r, "feat/csv-validation"), sh_opens_pr,
                           sh_pr_after_push("feat/csv-validation"), sh_child_titled("csv import validation", 2),
                           fin_archives_last],
    ("shift-session", 6): [sh_file_edit("progress.md"), sh_jira_comment("PAY-412"), sh_issue_comment(77), sh_task_update,
                           sh_no_close, lambda r, m: fin_push_branch(r, "PAY-412-refund-webhooks"), sh_child_started],
    ("shift-session", 7): [sh_no_force, sh_no_fixup, sh_child_started, sh_handoff(r"reject|remote (?:moved|has|contains)|behind|priya"),
                           sh_handed_off, fin_no_archive, sh_next_steps],
    ("shift-session", 8): [lambda r, m: fin_push_branch(r, "feat/max-zoom"), sh_no_session_tools, sh_cli_command,
                           sh_handoff(r"min-zoom"), sh_cli_rename, sh_ready_to_close],
    ("shift-session", 9): [loads_skill("shift-session"), sh_asks_first, sh_asks_once,
                           lambda r, m: fin_push_branch(r, "feat/ranking"), sh_child_started],
    ("shift-session", 10): [sh_never_stages(".env"), sh_commits, lambda r, m: fin_push_branch(r, "feat/payout-report"),
                            fin_mentions(r"\.env", r"credential|secret|stripe|api key"), cl_no_secret_echo("badger-orchard-crane"),
                            fin_no_archive, sh_next_steps],
    ("shift-session", 11): [loads_skill("shift-session"), sh_asks_once, cl_no_commit_push, sh_no_child_no_rename,
                            sh_no_tracker_write],
    ("call-it-a-day", 1): [sh_commits, lambda r, m: fin_push_branch(r, "feat/csv-import"), sh_no_pr, cd_no_child,
                           cd_persists("CSV importer"), cd_memory_note, cd_on_hold("CSV importer"), cd_rename_last,
                           cd_handoff_block(r"feat/csv-import", r"csv importer"), fin_no_archive, cd_no_merge],
    ("call-it-a-day", 2): [fin_no_main_push, sh_no_commit_on("main"), cd_pushes_off("main"),
                           fin_mentions(r"origin/main|ahead|reset (?:it|main|your local)|local `?main"),
                           cd_on_hold("Search results styling"), fin_no_archive, cd_next_steps],
    ("call-it-a-day", 3): [sh_no_push("feat/s3-uploads"), fin_mentions(r"\.env", r"credential|secret|aws|access key"),
                           cl_no_secret_echo("walnut-meadow-falcon"),
                           fin_mentions(r"(?:only|just) (?:exists? |lives? |is |sits? )?(?:on|in) (?:this|your|the local) (?:machine|computer|laptop|clone)|"
                                        r"local(?:ly)? only|only local(?:ly)?|not (?:yet )?(?:been )?pushed|unpushed|never pushed"),
                           cd_on_hold("S3 receipt uploads"), fin_no_archive, cd_next_steps],
    ("call-it-a-day", 4): [sh_commits, lambda r, m: fin_push_branch(r, "fix/weekend-surcharge"), sh_opens_pr,
                           sh_pr_after_push("fix/weekend-surcharge"), cd_draft_pr, cd_no_merge, sh_issue_comment(42),
                           sh_no_close, cd_on_hold("Courier rate card"), fin_no_archive],
    ("call-it-a-day", 5): [lambda r, m: fin_push_branch(r, "feat/cache-eviction"), sh_no_session_tools,
                           cd_persists("Tile cache eviction"), cd_cli_rename,
                           cd_handoff_block(r"feat/cache-eviction", r"tile cache eviction"),
                           cd_handoff_block(r"concurren|mutex|race|lock"), cd_cli_reopen],
    ("call-it-a-day", 6): [cd_restores("CSV importer"), cd_no_hold_title, cd_clears, cd_drops_note, cd_restore_first,
                           cd_no_rehold],
    ("call-it-a-day", 7): [cd_restores("Invoice PDF export -> Part 2", other="aa11"),
                           cd_restores("Invoice PDF export -> Part 2", "local_aa11"), cd_no_hold_title, cd_clears,
                           cd_drops_note, cd_no_archive_of("aa11")],
    ("call-it-a-day", 9): [cd_commits_only("progress.md"), sh_file_edit("progress.md"), sh_jira_comment("LED-88"), sh_issue_comment(19),
                           sh_task_update, sh_no_close, cd_stops(r"k4p9", r"4000", r"docs:serve"),
                           cd_on_hold("Ledger reconciliation"), fin_no_archive],
    ("rename-session", 1): [rs_one_rename, rs_title_format, rs_names(r"\bci\b|matrix", r"flaky|test_export"), rs_confirms,
                            rs_no_second],
    ("rename-session", 2): [rs_title_is("checkout retry bug")],
    ("promptfy", 1): [pf_no_side_effects, pf_one_subagent, pf_fenced, pf_no_blockquote, pf_changed_bullets, pf_no_offer],
    ("promptfy", 2): [pf_verbatim("fix the footer"), pf_names(r"footer\.tsx", r"legacyfooter\.astro"), pf_asks,
                      pf_no_side_effects],
    ("promptfy", 3): [pf_ratio(TIGHT_PROMPT), pf_meta(fin_mentions(TIGHT)), pf_no_side_effects],
}
# A command named mid-sentence: the first eval's checks, plus the skill being loaded through the Skill tool.
MID_SENTENCE = {"what-now": 4, "just-say-it": 4, "just-ask": 4, "promptfy": 4, "rename-session": 3, "call-it-a-day": 8}
CHECKS.update({(skill, eid): CHECKS[(skill, 1)] + [loads_skill(skill)] for skill, eid in MID_SENTENCE.items()})


def grade_run(skill, eid, texts, run_dir):
    r = (run_dir / "outputs" / "response.md").read_text()
    meta = json.loads((run_dir / "outputs" / "result.json").read_text())
    checks = CHECKS[(skill, eid)]
    assert len(checks) == len(texts), f"{skill} eval {eid}: {len(checks)} checks vs {len(texts)} expectations"
    results = []
    for text, fn in zip(texts, checks):
        if skill in ("just-ask", "promptfy"):
            p = payloads(r) if skill == "just-ask" else pf_payloads(r)
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
                if not (run_dir / "outputs" / "response.md").exists():
                    print(f"{run_dir.relative_to(it_dir.parent.parent)}: skipped (no response.md)")
                    continue
                p, t = grade_run(skill, eid, evals[eid]["expectations"], run_dir)
                print(f"{run_dir.relative_to(it_dir.parent.parent)}: {p}/{t}")


if __name__ == "__main__":
    main()
