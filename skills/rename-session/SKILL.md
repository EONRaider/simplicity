---
name: rename-session
description: Renames the current session after what the conversation has actually been about, as a 2 to 5 word sentence-case title that names where the work ended up, so the session is findable later in the resume picker. An argument is used as the topic to name. Invoked by the user as /simplicity:rename-session [topic]. Use it only when the user names /simplicity:rename-session or asks for rename-session by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[topic]"
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/rename-session.py" *)
license: MIT, Copyright (c) 2026 voidharbor (see LICENSE in this directory)
compatibility: Claude Code (uses the Claude Code-only argument-hint field). In the desktop app it uses the app's session title tool. In the CLI it needs Python 3, the CLAUDE_CODE_SESSION_ID environment variable and a session transcript on disk.
---

Rename this session so it is findable later in the resume picker, at claude.ai/code, and
in any cross-session triage.

## Derive the title

Read the whole conversation and name what the session is REALLY about: the dominant
work, not the first message and not the most recent tangent. If the session pivoted,
name the destination, not the origin.

Rules:

- 2 to 5 words, in sentence case like the app's own titles: capitalise the first word and
  keep names and acronyms as they are written (`CI`, `Stripe`). Never ALL CAPS
- Concrete nouns beat categories: "Checkout retry bug" not "Bug fixing"
- No dashes as punctuation, and no filler words like session, chat or work
- If the user passed arguments, treat them as the topic they want named. Use them
  as typed, capitalising the first word and tightening only for length.

The test for a good title: six weeks from now, in a list of thirty sessions, does this
one line tell them which session this was. "Image generation" fails that test when three
sessions touched image generation. "Product card thumbnails" passes.

## Apply it

**In the desktop app, use the app's own session tool.** The app keeps its own title for
each session and never reads the transcript, so the helper below succeeds there and
changes nothing the user can see. If a tool that sets a session's title exists
(`set_session_title`; it may be listed as a deferred tool that you load first), call it
for this session with the title, and don't run the helper. The app may ask the user to
approve the new title.

**Everywhere else, run the helper:**

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

Worth knowing, when the helper did the rename: the pane or tab header of the live session
may not pick up the new name until it is reopened. The stored name is what the resume picker and any triage tool
read, so the rename has taken effect even when the header still shows the old one. Say
so rather than renaming twice.

## Requirements

For the helper: Python 3, and a session that has written a transcript. The transcript is appended to,
never rewritten.

## Lifecycle

**Encoded-preference, timelessness 5/10, last verified against claude-opus-5 (2026-10).** The title rules are a fixed naming preference, so better models don't make them obsolete. It scores 5 because both ways of renaming lean on things that can change: the desktop app's session title tool, and, in the CLI, Claude Code's internal `custom-title` records, which aren't a documented interface. Re-check the tool's name when the app's session tools change, re-check both of the helper's writes after each Claude Code update, and retire the helper if Claude Code ships a supported way to rename a session from inside it. The check was one run per eval: with the skill Sonnet and Opus each passed 6 of 6 expectations and Haiku 5 of 6, against 13 of 18 in total without it.

## Credits

Adapted from `rename-session` by [voidharbor](https://github.com/voidharbor), [voidharbor/claude-plugins@397b270](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/rename-session), MIT.

- The command is now a skill: `commands/rename-session.md` became this `SKILL.md`, and the helper moved to `scripts/` beside it.
- It runs as `/simplicity:rename-session`, and the model may invoke it, but only when the user names it, so a mid-sentence mention still runs. Upstream's command could only be typed.
- Titles are in sentence case. Upstream's are ALL CAPS.
- In the desktop app it renames through the app's session title tool, because the app doesn't read the records the helper writes. Upstream always runs the helper.
- `allowed-tools` lets the skill run its own helper script without a permission prompt.
- The helper script was hardened with the same behavior: pathlib, type hints, docstrings, errors on stderr with a nonzero exit, and unit tests.
