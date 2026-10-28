---
name: cleanup
description: Runs an end-of-session closing checklist, invoked as `/simplicity:cleanup`. Stops background tasks/servers and the containers this session started, flags the volumes and databases it created instead of deleting them, checks the working tree(s) for uncommitted, unpushed, or stashed changes and flags them without auto-committing or discarding anything, removes disposable scratch files, notifies other active sessions only when there's a concrete handoff reason, and reports the session as ready before offering to archive it. Use whenever the user says "wrap this session up", "run the cleanup checklist", "prepare this session for archival", or otherwise wants to close out a session responsibly before it goes idle or gets archived. Not for cleaning up or refactoring code.
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

A harness Stop hook may report "N unpushed commits" by comparing `HEAD` with `origin/<current-branch>` only, so it also counts commits that already sit on another remote ref. That happens after the branch's PR merged, or after the branch was fast-forwarded to inspect main. Check with `git rev-list HEAD --not --remotes --count`, which counts only the commits no remote ref holds. If it prints 0, nothing is at risk: say so in the report, and don't push just to quiet the hook. Never fast-forward, reset or force-push the working branch to make the count go away. To read the default branch's history, use the `origin/<default>` refs directly instead of moving the working branch. The hook belongs to the harness, not the repo, so report it and don't try to edit it.

Report findings plainly. This step is reconnaissance, not remediation — do not commit, stash, discard, or push anything on your own initiative. If something looks unfinished or risky (uncommitted work, unpushed commits someone might be waiting on), surface it and ask what to do rather than deciding for the user.

Before calling any of this clean, look at what's actually staged or modified — don't just report the file list. If anything staged or changed looks like it could hold a credential (`.env`, keys, tokens, connection strings with passwords, anything named like a secret), open it and check, the same instinct as before any commit. Flag what you find; don't unstage or edit it yourself. Name the file and the kind of secret ("a database password in `DATABASE_URL`"), but never repeat the value itself in your report: that copies it into the transcript.

## 2. Stop what you started

Anything this session spawned that would otherwise keep running or waiting after the conversation goes idle:

- Preview/dev servers — list them and stop the ones no longer needed
- Background shell tasks and subagents you no longer need output from
- Persistent monitors watching logs/CI/PRs that have already served their purpose
- Scheduled wakeups or cron jobs you set up to drive this session's own loop, if they were meant to end with the session — leave alone anything the user clearly wants to keep running independently of this conversation

Don't stop something you're unsure about — ask first if a background task's purpose isn't obvious from the conversation so far.

## 2b. Containers and data stores

Some things this session started keep running, or keep their data, after the command that made them has returned, so they never show up as background tasks: detached containers (`docker run -d`, `docker compose up -d`, the same under `podman`), compose stacks, named volumes and networks, and databases or schemas created inside a server (`createdb`, `CREATE DATABASE`). A database that lives in a file, such as SQLite, is a scratch file and belongs to step 3.

Find them in the conversation, from the commands this session actually ran, then confirm their state with read-only commands: `docker ps -a`, `docker compose -p <project> ps`, `docker volume ls`, `psql -l`. Shell commands work in the CLI too, so this step runs there. If Docker or the database can't be reached, say so and move on.

- **Only what this session created.** A container, volume or database that was already there when the session started, or that the user started, is the user's, even if this session used it. Leave it running and leave its data alone. Never treat everything `docker ps` lists as this session's, and never run a prune (`docker system prune`, `docker volume prune`, `docker container prune`): a prune reaches past this session.
- **Stop without asking.** Stopping can be undone with a start, so it's a step 2 action: stop the containers and stacks this session started and no longer needs (`docker stop <name>`, `docker compose -p <project> stop`). Leave one running if the work continues somewhere that needs it, such as a handoff in step 4, and say why.
- **Ask before deleting.** Removing a container (`docker rm`, `docker compose down`), a volume (`docker volume rm`, `down -v`) or a network, or dropping a database (`dropdb`, `DROP DATABASE`), can't be undone. Even when this session created it, its data may be what the user wants to keep: seeded rows, migration results, a fixture someone else is about to read. List each one by name, with what it holds if the conversation says, and ask which to delete as a direct question. Delete only the ones the user names in this step. Until they answer, the question is open, so step 6 doesn't offer to archive: in a cloud session, archiving releases the container, and its containers and volumes go with it.
- **When unsure who started it**, leave it running and mention it.

A connection string or password in one of these commands is a credential: name it, don't repeat it, the same as step 1.

## 3. Scratch cleanup

If this session created temporary or scratch files (a scratch workspace, `/tmp`, a scratchpad directory) that aren't meant to outlive the session, remove them. Never touch files inside a real project's working tree, or anything the user might plausibly want to keep. When genuinely unsure whether a file is disposable, leave it and mention it rather than guessing.

## 4. Notify other sessions — only if there's a concrete reason

Check for other active Claude sessions. Send a message only when there's a specific, concrete reason another session needs to know something this one did — a handoff already discussed in this conversation, a branch another session is known to be building on, a resource another session is known to be using. Don't message reflexively just because other sessions exist; staying silent is the right outcome most of the time. If genuinely unsure whether a heads-up is warranted, ask the user rather than deciding unilaterally.

Messages to people (teammates in chat, email, PR comments) are different: never send one from this checklist without the user confirming that exact message first.

## 5. Tidy loose ends

- **Session title**: check this session's current title. If it's still a generic auto-generated one and real work happened, propose a short, specific replacement reflecting what actually got done and rename it. If the user set the title themselves, leave it — renaming will prompt for their approval anyway, so don't manufacture a rename just to have done something here.
- **Stale suggestion chips**: if this session spawned any background-task suggestion chips earlier on, check whether each is still relevant. Dismiss the ones that are now moot — already fixed, superseded, or no longer applicable — with a short reason. Leave the rest for the user to act on.

## 6. Report, then offer to archive

Summarize what you found and did in steps 1-5 — plainly, no padding: working-tree state per repo, what you stopped, the containers, volumes and databases left for the user to decide on, what you cleaned, who (if anyone) you notified and why, any title change or dismissed chips. Then ask whether the user wants to archive this session now.

**Side sessions first.** In the desktop app, archiving a session also archives its side sessions that are idle or share its worktree, and by default it removes the archived session's worktree. Before offering, list this session's linked sessions (the session list tool with `{"linked": true}`); its side sessions are the rows whose `startedBy` is this session's id and that aren't archived. If one's `cwd` is this session's folder, it shares the worktree and can't be detached: don't offer to archive, and say why in one line, naming it. Otherwise, once the user agrees, detach each side session with the detach tool so it lives on at top level, then archive. If a detach is refused, or there's no detach tool, don't archive: say why in one line. Detach nothing before the user agrees.

Only archive after the user explicitly confirms in this step — never speculatively, even though invoking `/simplicity:cleanup` signals intent to wrap up; a session with live background work or an unresolved question from steps 1-5 shouldn't be offered for archival in the first place.

**When `/simplicity:just-finish-it` runs this checklist**, it owns every decision that would come back to the user: wherever a step above says to ask, hand the item back to `just-finish-it` as pending instead of asking, send no messages to people, and stop after the summary without asking about archiving. `just-finish-it` continues from its own next step.

**When `/simplicity:shift-session` runs this checklist**, the same holds: it owns every decision that would come back to the user. Wherever a step above says to ask, hand the item back to `shift-session` as pending instead of asking, send no messages to people beyond the tracker updates `shift-session` already made, and stop after the summary without asking about archiving. `shift-session` has already committed and pushed in its own first step, which it does on the user's say-so, and it decides about archiving from its own pending list.

## Lifecycle

**Encoded-preference, timelessness 8/10, last verified against claude-opus-5-5 (2026-09), with step 6's side-session check measured in desktop app 2.9939.4 (2026-10-28).** The checklist is a fixed closing routine, and better models don't make "check the working tree before archiving" obsolete. It scores 8 rather than higher because steps 4–6 lean on the desktop app's current session-management tools. Re-verify them when those tools change.
