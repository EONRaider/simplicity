---
name: cleanup
description: Runs an end-of-session closing checklist, invoked as `/simplicity:cleanup`. Stops background tasks/servers this session started, checks the working tree(s) for uncommitted, unpushed, or stashed changes and flags them without auto-committing or discarding anything, removes disposable scratch files, notifies other active sessions only when there's a concrete handoff reason, and reports the session as ready before offering to archive it. Use whenever the user says "cleanup", "wrap this session up", "prepare this session for archival", or otherwise wants to close out a session responsibly before it goes idle or gets archived.
license: MIT (see plugin root LICENSE)
compatibility: Built for the Claude Code desktop app, where session-management tools (rename, archive, suggestion chips, other sessions) exist. In the CLI, steps that need those tools are skipped and the closing report says so.
---

# Cleanup

A repeatable closing checklist for the end of a session: reduce the odds of an orphaned background process, forgotten uncommitted work, or a collaborator left hanging, before the session goes idle or gets archived. Work through the steps in order — later steps assume the earlier ones already ran.

Steps 2 and 4–6 use the desktop app's session tools (background tasks, other sessions, the session title, suggestion chips, archiving). When one of those tools doesn't exist, as in the CLI, skip that item and say so in the report; in the CLI, end with "ready to close" instead of offering to archive.

## 1. Working tree check

For every git repository this session touched:

- `git status` — uncommitted changes, untracked files
- `git stash list` — forgotten stashes
- the commits on the current branch not yet on its tracked remote (e.g. `git log @{u}.. --oneline`, or note there's no upstream if that's the case)

Report findings plainly. This step is reconnaissance, not remediation — do not commit, stash, discard, or push anything on your own initiative. If something looks unfinished or risky (uncommitted work, unpushed commits someone might be waiting on), surface it and ask what to do rather than deciding for the user.

Before calling any of this clean, look at what's actually staged or modified — don't just report the file list. If anything staged or changed looks like it could hold a credential (`.env`, keys, tokens, connection strings with passwords, anything named like a secret), open it and check, the same instinct as before any commit. Flag what you find; don't unstage or edit it yourself. Name the file and the kind of secret ("a database password in `DATABASE_URL`"), but never repeat the value itself in your report: that copies it into the transcript.

## 2. Stop what you started

Anything this session spawned that would otherwise keep running or waiting after the conversation goes idle:

- Preview/dev servers — list them and stop the ones no longer needed
- Background shell tasks and subagents you no longer need output from
- Persistent monitors watching logs/CI/PRs that have already served their purpose
- Scheduled wakeups or cron jobs you set up to drive this session's own loop, if they were meant to end with the session — leave alone anything the user clearly wants to keep running independently of this conversation

Don't stop something you're unsure about — ask first if a background task's purpose isn't obvious from the conversation so far.

## 3. Scratch cleanup

If this session created temporary or scratch files (a scratch workspace, `/tmp`, a scratchpad directory) that aren't meant to outlive the session, remove them. Never touch files inside a real project's working tree, or anything the user might plausibly want to keep. When genuinely unsure whether a file is disposable, leave it and mention it rather than guessing.

## 4. Notify other sessions — only if there's a concrete reason

Check for other active Claude sessions. Send a message only when there's a specific, concrete reason another session needs to know something this one did — a handoff already discussed in this conversation, a branch another session is known to be building on, a resource another session is known to be using. Don't message reflexively just because other sessions exist; staying silent is the right outcome most of the time. If genuinely unsure whether a heads-up is warranted, ask the user rather than deciding unilaterally.

Messages to people (teammates in chat, email, PR comments) are different: never send one from this checklist without the user confirming that exact message first.

## 5. Tidy loose ends

- **Session title**: check this session's current title. If it's still a generic auto-generated one and real work happened, propose a short, specific replacement reflecting what actually got done and rename it. If the user set the title themselves, leave it — renaming will prompt for their approval anyway, so don't manufacture a rename just to have done something here.
- **Stale suggestion chips**: if this session spawned any background-task suggestion chips earlier on, check whether each is still relevant. Dismiss the ones that are now moot — already fixed, superseded, or no longer applicable — with a short reason. Leave the rest for the user to act on.

## 6. Report, then offer to archive

Summarize what you found and did in steps 1-5 — plainly, no padding: working-tree state per repo, what you stopped, what you cleaned, who (if anyone) you notified and why, any title change or dismissed chips. Then ask whether the user wants to archive this session now.

Only archive after the user explicitly confirms in this step — never speculatively, even though invoking `/simplicity:cleanup` signals intent to wrap up; a session with live background work or an unresolved question from steps 1-5 shouldn't be offered for archival in the first place.

**When `/simplicity:just-finish-it` runs this checklist**, it owns every decision that would come back to the user: wherever a step above says to ask, hand the item back to `just-finish-it` as pending instead of asking, send no messages to people, and stop after the summary without asking about archiving. `just-finish-it` continues from its own next step.

## Lifecycle

**Encoded-preference, timelessness 8/10, last verified against claude-opus-5-5 (2026-09).** The checklist is a fixed closing routine, and better models don't make "check the working tree before archiving" obsolete. It scores 8 rather than higher because steps 4–6 lean on the desktop app's current session-management tools. Re-verify them when those tools change.
