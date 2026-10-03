---
name: rename-session
description: Renames the current session after what the conversation has actually been about, as a 2 to 5 word ALL CAPS title that names where the work ended up, so the session is findable later in the resume picker. An argument is used as the topic to name. Invoked by the user as /simplicity:rename-session [topic].
disable-model-invocation: true
argument-hint: "[topic]"
license: MIT, Copyright (c) 2026 voidharbor (see LICENSE in this directory)
compatibility: Claude Code (uses the Claude Code-only disable-model-invocation and argument-hint fields). Needs Python 3, the CLAUDE_CODE_SESSION_ID environment variable and a session transcript on disk.
---

Rename this session so it is findable later in the resume picker, at claude.ai/code, and
in any cross-session triage.

## Derive the title

Read the whole conversation and name what the session is REALLY about: the dominant
work, not the first message and not the most recent tangent. If the session pivoted,
name the destination, not the origin.

Rules:

- 2 to 5 words, ALL CAPS, so titles stay scannable in a list of twenty
- Concrete nouns beat categories: "CHECKOUT RETRY BUG" not "BUG FIXING"
- No dashes as punctuation, and no filler words like SESSION, CHAT or WORK
- If the user passed arguments, treat them as the topic they want named. Uppercase them
  and use them, tightening only for length.

The test for a good title: six weeks from now, in a list of thirty sessions, does this
one line tell them which session this was. "IMAGE GENERATION" fails that test when three
sessions touched image generation. "PRODUCT CARD THUMBNAILS" passes.

## Apply it

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/rename-session.py" "THE TITLE"
```

The helper finds the transcript through the `CLAUDE_CODE_SESSION_ID` environment
variable, never by newest modification time, which matters once several sessions are
open at once. It writes the title to both of the places the app itself writes on a
rename: the `custom-title` line appended to the transcript `.jsonl`, and the
`custom-title.json` sidecar beside it.

## Confirm

Tell the user the new name in one line.

Worth knowing: the pane or tab header of the live session may not pick up the new name
until it is reopened. The stored name is what the resume picker and any triage tool
read, so the rename has taken effect even when the header still shows the old one. Say
so rather than renaming twice.

## Requirements

Python 3, and a session that has written a transcript. The transcript is appended to,
never rewritten.

## Lifecycle

**Encoded-preference, timelessness 5/10, last verified against claude-opus-5 (2026-10).** The title rules are a fixed naming preference, so better models don't make them obsolete. It scores 5 because the helper writes Claude Code's internal `custom-title` records, which aren't a documented interface: a CLI update can change where titles are stored and break the rename. Re-check both writes against a session renamed in the app after each Claude Code update, and retire the helper if Claude Code ships a supported way to rename a session from inside it. The check was one run per eval: Haiku, Sonnet and Opus each passed 6 of 6 expectations with the skill, against 10 of 18 in total without it.

## Credits

Adapted from `rename-session` by [voidharbor](https://github.com/voidharbor), [voidharbor/claude-plugins@397b270](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/rename-session), MIT.

- The command is now a skill: `commands/rename-session.md` became this `SKILL.md`, and the helper moved to `scripts/` beside it.
- It is user-invoked only (`disable-model-invocation: true`), as `/simplicity:rename-session`.
- The helper script was hardened with the same behavior: pathlib, type hints, docstrings, errors on stderr with a nonzero exit, and unit tests.
