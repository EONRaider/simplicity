---
name: call-it-a-day
description: Puts the current session on hold when the user stops work for the day, so the same work can be picked up at a later date with nothing lost. Commits any uncommitted work as a WIP commit and pushes it (never to the default branch, never forced, holding back any branch with a secret), updates whichever trackers the project has, saves a handoff note to the project's memory directory, records this session's title and renames it "<topic> -> On hold", and prints a self-contained handoff prompt. It leaves the session open, starts no new session, merges nothing and never marks the work finished. When the work resumes, in this session or in a new one started from the prompt, the session gets its pre-hold title back. Opens a draft PR only with --pr. Invoked by the user as /simplicity:call-it-a-day [--pr]. The everyday phrase "let's call it a day", written without hyphens, is not a request for this skill. Use when the user names /simplicity:call-it-a-day or asks for call-it-a-day by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[--pr]"
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/on-hold.py" *), Bash(python3 "${CLAUDE_SKILL_DIR}/../rename-session/scripts/rename-session.py" *)
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git, plus an authenticated GitHub CLI (gh) or the GitHub MCP server's tools to push and open PRs. Reads shift-session's SKILL.md from the same plugin. Renaming uses the desktop app's session title tool, or rename-session's helper in the CLI. The hold record and the resume hook need Python 3.
---

# call-it-a-day

The user is stopping for the day. Put this session on hold: persist everything, so the same work can be picked up at a later date, in this session or in a new one, with nothing lost. One hold runs steps 0 to 7 in order.

Asking for the command by name, typed or mid-sentence, is the user's go-ahead for the whole hold: the WIP commit, the push, the tracker updates, the memory note and the rename. Don't ask for confirmation, and don't stop to ask anything later either.

How this differs from its neighbours:

- `/simplicity:shift-session` hands the work to a new child session right away. This skill starts no session: the work pauses here and resumes later.
- `/simplicity:cleanup` only reports state. This skill leaves the state persisted.
- `/simplicity:just-finish-it` ships the work and closes it. This skill never merges a PR, never marks a PR ready for review, never closes an issue or moves a ticket to done, and never archives this session.

Like every simplicity skill it is conservative: it never discards or stashes work, never bypasses a check, and never messages a person beyond the tracker updates in step 2.

## 0. Before you start

**Read shift-session.** This skill reuses `/simplicity:shift-session`'s rules instead of repeating them. Read `${CLAUDE_SKILL_DIR}/../shift-session/SKILL.md` with the Read tool now. Don't load it with the Skill tool, which would start a shift. Wherever a step below says "shift-session's step N", follow that step as it's written there, with the changes listed here. Where the two disagree, this file wins.

**Stop early** when:

- the session is in plan mode: say that this command commits and pushes, so it can't run in plan mode;
- this session's title ends in "-> Handed Off" (or `-&gt;`, or `→`): say it was handed off already, so the work continues in its child.

A title that already ends in "-> On hold" doesn't stop the run: the session is going on hold again, and step 3 keeps its first pre-hold title.

The arguments this run was given: "$ARGUMENTS". They're empty when there were none. `--pr` is the only one.

Keep a running **pending list** from step 1 on, as shift-session does. Anything that stops a step from finishing cleanly goes on it, each item with the next step that clears it. Never repeat a secret's value anywhere, including the pending list, the trackers, the memory note and the handoff.

## 1. Commit and push

Follow shift-session's step 1 with all of its rules. They are, in short:

- never push to the default branch: work found there moves to a new branch first;
- never force-push;
- never stage a file that holds a secret: stage the other files by name;
- hold back any branch whose `git diff origin/<default>...<branch>` or `git log -p origin/<default>..<branch>` holds a secret, and don't try to fix it now;
- run each git step as its own command, and put a denied step on the pending list: never retry it, reword it or work around it, and never turn it into a question.

The changes for a hold:

- **A WIP commit.** Commit the uncommitted work even when it's half-done or doesn't build: that's the point of the hold. Start the message with `WIP:` unless the project's CLAUDE.md sets another convention, and say what the work is, that it's on hold, and where it stops. Never stash, discard or reset anything, and leave stashes in place: list them as pending.
- **The branch for default-branch work** is `hold/<topic-slug>` (the topic from step 3, lowercase, words joined by dashes) instead of `shift/<topic-slug>`. The pending item about the local default branch being ahead is the same.
- **PR, only with `--pr`.** If the branch has no PR, open one against the default branch, always as a draft, after the push. Without `--pr`, open none. Either way, never mark a PR ready, never merge one and never enable auto-merge.

Record each branch's pushed head SHA. A clean tree whose branch is already pushed needs no commit and no push; say so.

## 2. Update the trackers that exist

Follow shift-session's step 2: go through every row of its table, update each tracker whose evidence is present, skip the rest and say so. The changes for a hold:

- The update says the work is **on hold**, not finished: what's done, what's pending, the branch or PR, and that it resumes from the session "<topic> -> On hold" or from the handoff note.
- **Task list.** Mark completed only the items whose work is actually done. Leave every unfinished item open, and name it in the handoff.
- **Memory.** Step 4 writes the handoff note, so skip shift-session's memory row here.
- Never close an item, move it to done, reassign it or @mention anyone.

A tracker update that fails goes on the pending list and doesn't stop the hold.

## 3. Titles and the handoff prompt

**Read this session's title.** In the desktop app use `get_session` with `"self"`. In the CLI run `python3 "${CLAUDE_SKILL_DIR}/scripts/on-hold.py" title`, which prints the title or fails when the session has none. Read `-&gt;` and `→` as `->`, as shift-session's step 3 says, and always write a plain `->`.

- **Pre-hold title.** The title as read. If it already ends in "-> On hold", take the pre-hold title from `python3 "${CLAUDE_SKILL_DIR}/scripts/on-hold.py" show` instead, or, when that has no record, the title without the suffix.
- **Topic.** The pre-hold title without a trailing "-> Part N". When there's no title, or only a generic one such as "New session", name the topic the way `/simplicity:rename-session` does (2 to 5 words, sentence case, what the work is really about), and use it as the pre-hold title too.
- **On-hold title.** "<topic> -> On hold", with "On hold" in sentence case, never ALL CAPS. Like shift-session's two titles, this format overrides `rename-session`'s rules for this one title only, dash included.

**Write the handoff prompt** with shift-session's step 3 sections, **Goal**, **Done**, **Pending**, **Repository state**, **Next step** and **Context**, written so a session can act on it without this transcript. The changes for a hold:

- **It opens with the resume steps**, addressed to whichever session picks the work up:

  > This resumes work put on hold on <date> in session `<this session's id>`, titled "<topic> -> On hold". Before anything else:
  > 1. Rename this session "<pre-hold title>": the session title tool with `"self"` in the desktop app; in the CLI, `python3 "<absolute path of rename-session's rename-session.py>" "<pre-hold title>"`.
  > 2. If this session isn't `<this session's id>`, give that one its title back too: the session title tool with its id in the desktop app; in the CLI, the same helper with `CLAUDE_CODE_SESSION_ID=<this session's id>` in front. Leave it open: archiving it is the user's call.
  > 3. Clear the hold: `rm -f ~/.claude/simplicity/call-it-a-day/<this session's id>.json`, and delete the memory note `<its path>` and its line in the memory index.
  > 4. Run `git fetch origin` and check out `<branch>` before you read any code: this may be another machine or a fresh worktree.

  Leave out item 3's memory note when step 4 couldn't write one.
- **No archive line** and no "Part N": nothing starts a child.
- **Pending** includes every item on the pending list with its next step, and, for anything that couldn't be pushed, says plainly that it exists only on this machine.

Wherever the prompt goes, pass its full text, never a placeholder.

## 4. Save the state

The state must survive even if this session is later archived or lost. It lives in three places: the pushed branches (step 1), the trackers (step 2), and the two records below.

1. **The memory note.** When the session has a memory directory, save the handoff prompt there as `on-hold-<topic-slug>.md`, following the session's memory rules, and add a one-line pointer to the memory index if it keeps one (such as `MEMORY.md`). Start the note with this line, so an unrelated session that reads its memory leaves it alone: "On hold since <date>, from session `<id>` ("<topic> -> On hold"). Use this note only when the user asks to continue this work, then follow its resume steps." When there's no memory directory, say so in the report; the hold record still keeps the handoff on this machine.
2. **The hold record.** Run:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/on-hold.py" hold --title "<pre-hold title>" --topic "<topic>" --handoff "<memory note path>"
   ```

   Without a memory note, write the handoff to a scratch file and pass that path instead. The helper copies the note into `~/.claude/simplicity/call-it-a-day/<session id>.json` along with both titles, and the resume hook reads it. If it fails (no Python, no session id), say so in the report: the handoff prompt's resume steps still work without it.

## 5. Stop what this session started

Nothing should run overnight on the session's behalf. Stop what this session started, using cleanup's step 2 rules (`${CLAUDE_SKILL_DIR}/../cleanup/SKILL.md`): dev and preview servers, background shell tasks, monitors, and the wakeups, loops and check-ins it armed to drive its own work. Leave anything the user set up to keep running independently, such as a PR watch they asked for, and name it in the report. When a task's purpose isn't clear, leave it running and put it on the pending list rather than asking. Don't run `/simplicity:cleanup` itself, since it offers to archive, and don't delete scratch files.

## 6. Rename this session

Rename this session "<topic> -> On hold", last, once the state is saved. In the desktop app use the session title tool with `"self"`. In the CLI run `rename-session`'s helper directly, since its title rules don't allow this format:

```bash
python3 "${CLAUDE_SKILL_DIR}/../rename-session/scripts/rename-session.py" "<topic> -> On hold"
```

Never archive this session and never start another one.

## 7. Report

Write the report as normal markdown:

- **On hold as**: the new title, and the pre-hold title it gets back on resume.
- **Committed and pushed**: one line per branch with its SHA, and the draft PR if `--pr` opened one.
- **Trackers**: one line per tracker, updated or skipped and why.
- **Saved**: the memory note's path, or that there was no memory directory, and the hold record.
- **Stopped**: what step 5 stopped, and what it left running.
- **Still to do**, whenever the pending list isn't empty: a numbered list, one item per line, each with a **Next:** step the user can take now, in the format shift-session's step 6 uses. Say plainly if anything exists only on this machine.

Then write "To resume, keep typing in this session, or paste this prompt into a new one:", followed by the full handoff prompt in a fenced code block. In the CLI, add that `claude --resume <session id>` reopens this session.

End with one line: "On hold. Nothing was merged or archived."

## Resuming

There's no resume command. Work resumes when the user comes back, and is detected three ways:

- **The hook, in this session.** The plugin's `UserPromptSubmit` hook runs `on-hold.py`. On the first prompt in a session that has a hold record, it adds a note that the session is on hold, with its pre-hold title and the commands to restore it. It repeats on every prompt until the hold is cleared, and stays silent in a prompt that names call-it-a-day.
- **The transcript, in this session.** Where the hook can't run (no Python, or a cloud container that was reclaimed), this skill's text and the hold report are still in this session's context. A message in a session titled "<topic> -> On hold" that continues the work is the resume.
- **The handoff, in a new session.** The pasted handoff prompt and the memory note both open with the resume steps.

On resume, before anything else: rename the session to its pre-hold title, give the held session its title back too if it's a different one, clear the hold (`python3 "${CLAUDE_SKILL_DIR}/scripts/on-hold.py" resume`, which prints the pre-hold title, or delete the record file), and delete the memory note and its index line. Then carry on with what the user asked. Resuming commits nothing, pushes nothing and doesn't run this skill again. A message that only acknowledges the hold ("thanks", "good night") or asks about it isn't a resume: answer it and leave the hold in place.

## Lifecycle

**Encoded-preference, timelessness 6/10, last verified against claude-opus-5-5 and Claude Code 2.1.291 (2026-10), with seeded evals only.** The order of a hold and its safety rules (a WIP commit instead of lost work, never push to the default branch, never force-push, hold back secrets, never merge, never archive) are fixed preferences, and the shared ones live in shift-session. It scores 6 because it leans on the host's session title tools, on Claude Code's internal `custom-title` transcript records in the CLI, on the session's memory directory, and on the `UserPromptSubmit` hook input carrying `session_id` and `prompt`. Re-check step 3, step 6 and the resume hook whenever those change, and re-check step 0's pointers whenever shift-session's steps are renumbered.
