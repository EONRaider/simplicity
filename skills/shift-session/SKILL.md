---
name: shift-session
description: Hands the current session's work to a fresh child session before the context window bloats. Commits and pushes all work (never to the default branch, never forced, holding back any branch with a secret), updates whichever trackers the project has, writes a self-contained handoff prompt, starts a child session titled "<topic> -> Part N", renames this one "<topic> -> Handed Off", runs /simplicity:cleanup and archives it, or leaves it open when something is pending. Opens a PR only with --pr. Invoked by the user as /simplicity:shift-session [--pr]. Use when the user names /simplicity:shift-session or asks for shift-session by name, including mid-sentence, where the command isn't expanded and reaches the model as text, or when the simplicity context hook reports that context use reached the shift threshold, in which case pass --auto and it asks the user once before acting. Never on a paraphrase of what it does: a request in other words, such as "hand this off to a new session" or "start a fresh chat", is not a request for this skill.
argument-hint: "[--pr]"
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/../rename-session/scripts/rename-session.py" *), Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/context-check.py" --mark-handed-off*)
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git, plus an authenticated GitHub CLI (gh) or the GitHub MCP server's tools to push and open PRs. Starting the child session uses the desktop app's session tools; in the CLI and other UIs without them it prints the handoff prompt instead. The threshold hook and the handed-off marker need Python 3.
---

# shift-session

Close this session out safely and hand its work to a fresh child session, so the work goes on with an empty context window. One shift runs steps 0 to 6 in order.

Keep a running **pending list** from step 1 on. Anything that stops a step from finishing cleanly goes on it. The pending list goes into the handoff prompt and decides step 6. Never repeat a secret's value anywhere, including the pending list and the handoff.

If the session is in plan mode, stop and say that this command commits and pushes, so it can't run in plan mode. If this session's title already ends in "-> Handed Off" (or "-&gt; Handed Off", as the app may return it), stop and say it was handed off already: the work continues in its child.

## 0. Manual or automatic

The arguments this run was given: "$ARGUMENTS". They're empty when there were none.

**Manual run.** The user asked for the command by name: their latest message is `/simplicity:shift-session`, with or without arguments, or names it mid-sentence ("can you run /simplicity:shift-session --pr?"), and the arguments don't include `--auto`. Asking for it by name is the user's go-ahead for the whole shift: committing, pushing, updating trackers, starting the child, renaming, cleanup and archiving. Don't ask for confirmation.

**Automatic run.** Anything else: the arguments include `--auto`, or the skill was invoked because the simplicity context hook said the context reached the threshold. Before anything is committed, pushed or written anywhere, ask the user once with `AskUserQuestion`:

- question: "Context is at <percent>%. Shift this session to a fresh one now?" Take the percent from the hook's message, or from the app's usage tool if one exists.
- options: "Shift now (Recommended)", described as committing and pushing the work, commenting on the trackers the project has (comments can notify their watchers) and starting the child; and "Not now", described as continuing here, with the hook asking again 10 points later.

On "Shift now", run steps 1 to 6 without asking anything else. On anything else, say in one line that the session continues, and stop. Nothing before the answer may commit, push, update a tracker, rename or start a session; reading state is fine.

`--pr` works the same in both modes.

## 1. Commit and push

Work out the repositories this session touched. For each one, read `git status --short --branch`, `git stash list`, `git worktree list`, the current branch, and the default branch (`gh repo view --json nameWithOwner,defaultBranchRef`, or `git symbolic-ref refs/remotes/origin/HEAD`). Run `git fetch origin` so `origin/<default>` is current.

**Transport.** Use `gh` when `gh auth status` succeeds, otherwise the GitHub MCP server's tools, as `/simplicity:just-finish-it` describes. Plain `git push` needs neither. If the remote isn't GitHub, push only and put the PR (when `--pr` was passed) on the pending list.

**Scan before staging.** Look at every changed and untracked file. If one holds a credential (an `.env` file, a key, a token, a connection string with a password, anything named like a secret), never stage it: stage the other files by name, not with `git add -A` or `git add .`. Put the held-back file on the pending list with the file and the kind of secret, never the value.

**On the default branch, move the work to a new branch.** If the current branch is the default branch and it has uncommitted changes or commits its remote doesn't have, run `git switch -c shift/<topic-slug>` (the topic from step 3, lowercase, words joined by dashes) and carry on there. The local commits on the default branch come along on the new branch. Put one item on the pending list: "the local `<default>` is ahead of `origin/<default>`. Next: reset it to `origin/<default>` once the `shift/<topic-slug>` work is merged." Never push to the default branch.

**Then, on the working branch.** Run each git step below as its own command, never chained with `&&`, so a refusal stops only that step. If a permission rule or the auto-mode classifier denies a step, don't retry it, reword it or work around it, and don't stop to ask the user what to do: a denial never ends the shift and never turns into a question. Put the step on the pending list with the next step "approve it in the conversation, or run `<the command>` yourself", skip the steps that depend on it, and go straight on to step 2. A denied commit leaves the work uncommitted and means nothing to push. A denied push leaves the branch committed locally. Either way the handoff says exactly what's left, and step 6 ends with the Pending finish.


1. **Commit.** Stage the changes, except held-back files, and commit with a message that says what the work is and that it's a handoff, following any commit conventions in the project's CLAUDE.md. A half-finished state is fine to commit: the handoff says what's unfinished. Don't commit stashes; list them as pending.
2. **Scan the branch.** Read `git diff origin/<default>...<branch>`, which now includes the handoff commit. If anything in it holds a secret, don't push the branch. Put it on the pending list with the file and the kind of secret, and the next step of removing it from the branch's history.
3. **Push.** `git push -u origin <branch>`. Never force-push. If the push is rejected because the remote moved, don't pull, rebase or merge on your own: put the branch on the pending list.
4. **PR, only with `--pr`.** If the branch has no PR, open one against the default branch (`gh pr create`, or the MCP `create_pull_request`), as a draft when the work isn't finished. Without `--pr`, open no PR, even when the project's CLAUDE.md or your own habits would normally open one.

Record each branch's pushed head SHA for the handoff. A clean tree whose branch is already pushed needs no commit and no push; say so.

## 2. Update the trackers that exist

Detect each tracker; never assume one. Go through every row below and do every one whose evidence is present, before moving on. Write the state of the work: what's done, what's pending, the branch or PR, and that the work continues in "<topic> -> Part N". Skip a row whose evidence is absent and say so in the report. Never @mention people, never reassign, and never close or move an item to done unless the work is actually merged.

| Tracker | Present when | Update with |
|---|---|---|
| The tracker named in the project's CLAUDE.md | CLAUDE.md names one (a file, a board, an issue tracker) and how to update it | What CLAUDE.md says. For a file, edit it with the file-editing tool, in the format it asks for |
| Jira | The Atlassian MCP tools are loaded and the session, branch or commits name a Jira key (such as `ABC-123`) | `addCommentToJiraIssue` on that key |
| GitHub issues and PRs | The branch has a PR, or the session or commits reference an issue (`#123`, `Fixes #123`) | `gh issue comment <n>` / `gh pr comment <n>`, or the MCP `add_issue_comment` |
| Claude task list | The session has a task list with items | `TaskUpdate` (or `TodoWrite`): mark finished items completed, leave unfinished ones open and name them in the handoff |
| Claude memory files | The session has a memory directory | Save only facts a future session needs that the repo and the handoff don't hold, per the memory rules; skip it when there are none |

A tracker update that fails goes on the pending list. It doesn't stop the shift.

## 3. Write the handoff prompt

**Topic and part number.** Read this session's title (`get_session` with `"self"` in the desktop app). The app may return `->` HTML-escaped as `-&gt;`, or as `→`; read all three as `->`, and always write titles with a plain `->`. If it reads `<topic> -> Part N`, keep that topic and use N+1. If it's a specific title someone chose or the app generated from the work, use it as the topic as it is. Only when there's no title, or a generic one such as "New session", name the topic the way `/simplicity:rename-session` does (2 to 5 words, sentence case, what the work is really about). Then use Part 2. The `<topic> -> Part N` and `<topic> -> Handed Off` formats are deliberate, and they override `rename-session`'s rules for these two titles only, dashes included.

Write one prompt that a fresh session can act on without reading this transcript. Write it to the child, in plain markdown:

- First line: ask the child to rename itself "<topic> -> Part N" if its title isn't that already. In the desktop app it uses the session title tool. In the CLI it runs `rename-session`'s helper with the exact title, as step 5 shows, because `/simplicity:rename-session` itself would rewrite the title to its own rules.
- **Goal**: what the user is trying to achieve, in their terms.
- **Done**: what's finished and verified, with commit SHAs or PR links.
- **Pending**: everything unfinished, including every item on the pending list, each with its next step.
- **Repository state**: for each repo, its path, the branch, whether it's pushed and at which SHA, the PR if any, and anything left uncommitted. A child in the desktop app may start in a fresh worktree, so tell it which branch to check out.
- **Next step**: the one concrete action to take first.
- **Context**: decisions made, constraints the user stated, and approaches tried that failed. Only what the child needs.
- Last line, only when step 4 will use a chip and the pending list is empty: "Once you're running, archive the parent session `<this session's id>` with the session-archive tool. It has nothing pending. It may still be finishing its last turn when you start. If the archive is refused because it's still working, wait about 30 seconds without blocking (run `sleep 30` as a background command, which notifies you when it ends), then try again. Try up to three times in all; if it's still refused, tell the user it can be archived from the sidebar once it's idle."

Wherever the prompt goes in step 4, pass its full text. Never pass a placeholder or a reference such as "the prompt above": the child sees only what it's given.

## 4. Start the child session

Use the first of these that works, and record each one you tried and why it failed, for the report:

1. **Automatic start.** Look for a tool that starts a new session with a prompt and no click, such as `start_session` or `hand_off_to_session` in the desktop app; they may be deferred tools to load first. If one exists, start the child with the handoff prompt in this session's folder, then title it "<topic> -> Part N" with the session title tool if the start call took no title. If the user is watching, it can be opened beside this one.
2. **One-click chip.** In the desktop app without such a tool, call `spawn_task` with the handoff prompt as `prompt`, "<topic> -> Part N" as `title`, and a `tldr` saying this session is handing off at its context limit. The user starts it with one click.
3. **No session tools.** In the CLI, an IDE extension, or any UI without either tool, print the handoff prompt in a fenced code block and suggest starting the child with:

   ```bash
   claude "<the handoff prompt>"
   ```

   Say that the child should be renamed "<topic> -> Part N" once it starts, which the prompt's first line asks it to do.

The handoff happens even when the pending list isn't empty. That's when the child needs it most.

## 5. Rename this session

Rename this session "<topic> -> Handed Off", with the same topic as the child. In the desktop app use the session title tool with `"self"`. In the CLI run `rename-session`'s helper directly, since its title rules don't allow this format:

```bash
python3 "${CLAUDE_SKILL_DIR}/../rename-session/scripts/rename-session.py" "<topic> -> Handed Off"
```

Then mark the session handed off, so the context hook stops suggesting shifts in it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/context-check.py" --mark-handed-off
```

## 6. Cleanup, then archive or stop

Run `/simplicity:cleanup` (the command is `/simplicity:cleanup`, never bare `/cleanup`): load it with the Skill tool and follow its checklist, rather than running similar checks from memory. Follow it with these changes, since this skill decides what happens next:

- Wherever cleanup says to ask the user, add the item to the pending list instead.
- Its working-tree findings come after step 1, so anything it still flags is pending.
- Skip its closing offer to archive.
- Send no messages to people beyond the tracker updates step 2 made.

Then write the report as normal markdown:

- **Shifted to**: the child's title, and how it was started (started, chip waiting for a click, or prompt printed).
- **Committed and pushed**: one line per branch with its SHA, and the PR if `--pr` opened one.
- **Trackers**: one line per tracker, updated or skipped and why.
- **Child session**: in the desktop app, each method tried in step 4 and why it didn't work, if any failed.
- **Still to do**, whenever the pending list isn't empty: a numbered list, one item per line, each with a **Next:** step the user can take now, the same format `/simplicity:just-finish-it` uses. The child has the same list in its handoff. If the child got the archive line and cleanup then added something, say here that its archive request should be declined.

Then finish with exactly one of these:

- **Archive.** When the pending list is empty, the child was started automatically (step 4, option 1) and the session-archive tool exists: say the session is handed off, then archive it with the session-archive tool and `"self"` as your very last action. The run already counts as the user's agreement to archive.
- **Chip.** When the child is a chip and the pending list is empty: leave this session open, because a chip that hasn't been clicked yet belongs to this session and archiving could take it away. Say "Click the Part N chip to continue. The child archives this session once it starts."
- **Pending.** When anything is pending: don't archive. Say why in one line, above the Still to do list.
- **CLI.** Without session tools: end with "Ready to close."

## Lifecycle

**Encoded-preference, timelessness 6/10, last verified against claude-opus-5-5, Claude Code 2.1.284 and desktop app 2.9939.4 (2026-10).** The order of a shift and its safety rules (never push to the default branch, never force-push, hold back secrets, archive only with nothing pending) are fixed preferences. It scores 6 because step 4 leans on whichever session tools the host exposes, which change often, and the threshold hook reads Claude Code's internal transcript format and a model-to-window table. On 2026-10-05 the desktop app listed no `start_session` or `hand_off_to_session` tool, so step 4 fell back to the chip there. Re-check step 4 whenever the session tools change, and re-check the hook's measurement after each Claude Code update.
