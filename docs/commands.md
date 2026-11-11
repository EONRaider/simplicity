# Commands

What each skill does in full, with its requirements, limits and platform differences. The [README](../README.md) has the one-line version.

## Calling a command

- Claude Code runs a typed command only when it starts the message. Named anywhere else ("can you run `/simplicity:what-now`?"), the command reaches Claude as plain text, and Claude loads the skill itself. That works for every skill except `just-finish-it`, which pushes and merges, so it runs only when typed as the first thing in a message. Named mid-sentence, Claude can't load it and may tell you it isn't installed. It is installed: send `/simplicity:just-finish-it` as its own message.
- No skill fires on a paraphrase of what it does, with one exception: `cleanup` can also run when you ask Claude to wrap a session up.
- Four things can act without a typed command. `shift-session`'s hook suggests a shift once the context window is 60% full, and asks you before doing anything. `call-it-a-day`'s hook speaks only in a session you put on hold, to give it its old title back when you come back to it. And `just-move` can schedule a resume that fires into the session after your usage limit resets, but only once you've agreed to it. And `disk-cleanup` can start from another session's message that names it, as when an orchestrator orders its workers to clean up: that run sweeps and asks you, and deletes only on your answer in that session.

## just-ask

`/simplicity:just-ask [focus]`

Collects every question still open in the session and asks them all at once, each option with a recommendation. It sweeps the session (your messages, the plan, the task list and Claude's own earlier responses) and drops anything the repo or the conversation already answers. It asks the rest through `AskUserQuestion` in rounds of up to four. Every option has a recommendation and the reasoning behind it.

### Notes

- `AskUserQuestion` exists only in Claude Code. On other surfaces, `just-ask` falls back to a numbered markdown list with the same recommendations.

## just-move

`/simplicity:just-move [focus]`

Gets the session ready to run on its own for as long as possible, including across usage-limit resets. It asks every open decision the way `just-ask` does, together with the blockers that would stop the run partway: permission prompts, missing credentials or tools, disk, unwatched PRs, context headroom. Then it fixes what it can once you agree. In cloud sessions it subscribes to the PRs, schedules a resume for a few minutes after your usage limit resets, plus an hourly fallback that switches itself off by a 7-day deadline, and writes a handoff note to the project's memory directory. It never commits, pushes or changes permission settings. It ends with a readiness report that says whether the session is clear to run.

### Notes

- `just-move` needs the cloud session tools (`send_later`, `create_trigger`, `update_trigger`, `subscribe_pr_activity`) to schedule a resume and watch PRs. In the CLI, and anywhere else without them, nothing can fire while Claude Code isn't running: it says so, still writes the handoff note, and prints a resume prompt to paste once the limit resets.
- It asks for the reset time shown in `/usage`, unless the session already says it, and repeats it back in UTC.
- The hourly fallback checks a handoff note before it does anything, so it stays quiet while the run is moving, and switches itself off after the 7-day deadline or once the work resumes.
- In plan mode it asks its questions and defers every fix.
- It reads `just-ask`'s and `shift-session`'s SKILL.md files, so all three must come from the same plugin version.

## speed-up

`/simplicity:speed-up [focus]`

Finds which remaining tasks can safely start earlier or run in parallel, and reorders the task list once you agree. It keeps the session's goals exactly as they are and changes only the order and concurrency of what's left. It writes out every open task with what it depends on, what it writes and what it waits on. From that it proposes the safe speed-ups: tasks whose inputs are ready, independent tasks that sub-agents can run side by side (at most three at once), work that can overlap a CI run or a long command, and tasks already done. It never moves a task ahead of what it depends on, never lets two parallel workers write the same file, and never starts anything that waits on a decision of yours. It has the proposal reviewed before you see it, asks you once, and only after your yes applies the new task list and tells the sessions affected by the change.

### Notes

- Nothing changes before your yes: not the task list, not a sub-agent, not a message. In plan mode it still analyses, reviews and asks, and lists the update and the messages as deferred until plan mode ends.
- The review uses the `advisor` tool when your session has one, and otherwise one read-only sub-agent briefed to find the dependency the reordering breaks, the file two workers would both write, and the step that silently assumes a decision. Without either, it says the proposal is unreviewed.
- An open decision a task waits on stays open: `speed-up` names it and points you to `just-ask`, rather than asking it in its own approval question.
- It notifies only sessions and agents that the host's tools show exist, and only those the change affects: the session that started this one, the sessions this one started, and the sub-agents and teammates it runs. Each gets one message at priority `next`, which never interrupts a running turn, saying what moved and what to do differently. It never messages a person. In a session with nobody to tell, it says "No supervised or supervising parties found."
- The desktop app applies the list with its task list (`update_plan`, up to 12 items; a longer list folds its tail into one item) and finds the parent and child sessions with its session tools. The CLI uses `TaskCreate` or `TodoWrite` and can message only its own agents and teammates, so a parent session named only in the conversation is reported, not messaged. Cloud sessions can message the sessions they created. Without task tools it prints the list as the plan of record; without message tools it names who should be told and sends nothing.
- It never commits, pushes or changes permission settings. Workers in a parallel group don't commit; the session commits after the group ends.
- It reads `just-ask`'s and `call-it-a-day`'s SKILL.md files, so all three must come from the same plugin version.

## just-say-it

`/simplicity:just-say-it [N | topic | commit | #PR | file or URL | text]`

Re-states recent responses, or explains a commit, PR, document or snippet, as a short numbered list in plain language. With no argument it re-states the last response; with a count or a topic, the last N responses or everything said on that topic. Each item is a bold label plus one plain sentence. It adds no preamble and no new information. If the content leaves decisions open, it ends by pointing you to `just-ask`. Give it a commit, a PR (`#16`), a file path, a URL, a connected doc or a pasted snippet instead, and it explains that in the same format, in plain words with no technical jargon. It only reads what you named, and explains it without judging it. A bare number is always a count of responses, never a PR.

### Notes

- `just-say-it` has two modes. Summarizing the session only compresses: it makes no tool calls and adds nothing. Explaining a commit, PR, document or snippet makes read-only calls for that one item (git, the GitHub MCP server or `gh`, a fetch tool, or a connector), and adds only plain-word definitions, never opinions or a review.
- If you want terser output in every session, set an output style or a CLAUDE.md instruction instead.

## what-now

`/simplicity:what-now`

Takes stock of the session and lists what's done, where the current task stands, and the next steps to finish it. Each item in the three lists is a bold label plus one plain sentence. It makes no tool calls and counts work as done only when the session shows it done, so a fix that was never tested is marked unverified. A step that needs you, such as a decision, says so.

## just-finish-it

`/simplicity:just-finish-it [PR numbers | repo path]`

Ships the session's work and closes it: pushes, merges the PRs whose CI is green, cleans up and archives the session. It pushes this session's branches, opens any missing PRs, waits for CI, and merges the PRs whose checks all pass, base-first for stacked PRs. It then deletes the merged branches, remote and local, syncs your local repos, runs `cleanup`, and archives the session. It never uses `--admin`, auto-merge or force-push, never commits work for you, and never pushes to the default branch. If anything is still pending (red CI, a missing review, uncommitted work, unfinished tasks), or if you scoped the run, it skips archiving. It ends with a numbered "Still to do" list, each item with its next step.

### Notes

- `just-finish-it` needs `git`, plus an authenticated `gh` or the GitHub MCP server's tools (cloud sessions often have only the MCP server).
- On the MCP path it can't always see a merge queue. If the default branch is protected and the server's `governance` toolset doesn't show one, it takes the answer your CLAUDE.md or CONTRIBUTING states, and asks you only when neither says, once per run. If GitHub then refuses the merge because of a queue, the PR goes on "Still to do" for you to enqueue.
- The MCP server has no branch-delete tool, so a merged branch the repo doesn't auto-delete goes on the "Still to do" list.
- Archiving uses the desktop app's session tools. In the CLI it stops at "ready to close".
- Archiving a session in the desktop app also archives its side sessions that are idle or share its worktree, and removes its worktree. So before archiving, it lists this session's linked sessions and detaches each side session it started so it lives on at top level. If a detach is refused, which happens when a side session shares this session's worktree, it doesn't archive and says why.

## shift-session

`/simplicity:shift-session [--pr]`

Hands the session's work to a fresh child session before the context window bloats. It commits and pushes the work, updates whichever trackers the project has (the one named in CLAUDE.md, Jira, GitHub issues and PRs, the task list, memory files), writes a self-contained handoff prompt, and starts the child as `<topic> -> Part 2` (Part 3 on the next shift, and so on). Then it renames this session `<topic> -> Handed Off`, runs `cleanup`, and archives it. It follows `just-finish-it`'s rules: it never pushes to the default branch (work found there moves to a new `shift/<topic>` branch), never force-pushes, never stages a file holding a secret, and holds back any branch whose diff or commit history holds one. It opens a PR only with `--pr`. If anything is pending, the child still gets the work, with the pending list in its handoff, and this session stays open. A plugin hook suggests a shift once context use reaches `SIMPLICITY_SHIFT_THRESHOLD` percent (default 60); a suggested shift asks you once, then runs to the end.

### Notes

- `shift-session` starts the child in the most automatic way the UI allows. If the desktop app offers a tool that starts a session with a prompt (`start_session` or `hand_off_to_session`), it uses that, starting the child in its own worktree, and archives this session at the end. Without such a tool it creates a suggestion chip you start with one click. Archiving a session removes its unclicked chip, so the parent stays open, and the child archives it once it runs; if the parent is still finishing its turn, the child waits and retries, up to three times, before leaving it to you.
- Archiving a session in the desktop app also archives its side sessions that are idle or share its worktree, and removes its worktree. So before archiving, it lists this session's linked sessions and detaches each side session it started so it lives on at top level. If a detach is refused, which happens when a side session shares this session's worktree, it doesn't archive, leaves this session titled `<topic> -> Handed Off`, and says why. A child that has to share the folder, as when this session moved into its worktree with EnterWorktree, is the usual cause.
- The desktop app starts a new session only on a turn you started by typing. When the shift comes up on a turn another session's message, a side-session event or a scheduled event began, `shift-session` commits and pushes the work, then asks you in one line to type a short reply such as "go" in that session, and shifts on that reply. It never reads where you are from the Remote Control fields. If a start is still refused, the chip it falls back to quotes the app's refusal word for word.
- In auto permission mode, the auto-mode classifier may refuse the push even though you asked for the shift. The push then goes on the "Still to do" list, and the shift continues; approve the push in the conversation, or push the branch yourself.
- In the CLI and other UIs without session tools, it prints the handoff prompt and suggests `claude "<prompt>"`, and stops at "ready to close".
- `shift-session` pushes, like `just-finish-it`, but it can't be typed-only: its hook has Claude load it. So you can also name it mid-sentence, and Claude treats that as your go-ahead. When the hook starts it, it asks you once before committing anything. Named mid-sentence, it asks before it loads, because it declares `allowed-tools` for its helper scripts.

### The context hook

- The hook runs on every prompt and tool call, reads the tail of the session transcript, and stays silent below the threshold.
- No hook input carries context usage, so it sums the last assistant message's token usage, the way Claude Code counts it, and works out the window from the model id.
- Set `SIMPLICITY_CONTEXT_WINDOW` (in tokens) if your model's window isn't the one it assumes, and `SIMPLICITY_SHIFT_THRESHOLD=off` (or `0`) to turn the hook off.
- It suggests a shift once per 10 points from the threshold up (60%, 70%, ...), so declining doesn't silence it for good, and goes quiet for good in a session that was handed off.
- It needs `python3` on your PATH; without it the hook does nothing.
- It reads Claude Code's internal transcript format, so a Claude Code update could break it; it then stays silent rather than getting in the way.

## call-it-a-day

`/simplicity:call-it-a-day [--pr]`

Puts the session on hold when you stop for the day, so you can pick the same work up later with nothing lost. When the session supervises agents or sessions (background sub-agents, workflows, side or child sessions, teammates, and the loops that feed them work), it winds them down first: it writes a shutdown task list with its own hold as the last item, stops the dispatchers so nothing new starts, lets every task that is already running finish, asks each supervised session to commit and push its work, and only then stops itself. It commits whatever is uncommitted as a WIP commit and pushes it, under `shift-session`'s rules (never the default branch, which moves to a `hold/<topic>` branch; never force-push; never a file or branch holding a secret). It updates whichever trackers the project has, saves a handoff note to the project's memory directory, records the session's title, renames the session `<topic> -> On hold` and prints a self-contained handoff prompt. It leaves the session open, starts no new session, merges nothing, and opens a draft PR only with `--pr`. When you come back, keep typing in the same session or paste the prompt into a new one: either way the session gets its old title back.

### Notes

- The wind-down never halts a supervised agent or session mid-task: an interrupt wastes the work it has done and can leave files half-written.
- It never waits without an end in sight. Each in-flight run gets a completion estimate from its reported progress, its elapsed time against its scope, or its own answer, and a deadline of the estimate plus half again. Before the first wait it tells you how long the wind-down should take. A run that can't be estimated, such as a fuzzer with no time or run cap, triggers an immediate warning that it may run without end. The hold doesn't wait for it and doesn't kill it either: it's listed under Still to do with the command that stops it gracefully, and the decision is yours. A run that passes its deadline or stops moving gets the same warning.
- It waits without blocking (a background `sleep` or a Monitor) and re-estimates at each check. Supervised sessions are left open and idle, never archived, and the report lists them with their branches so you can archive them yourself. The shutdown list, with each item's end state, goes into the handoff so the resumed session knows what ran, what it left and what wasn't dispatched.
- `call-it-a-day` keeps its state where a lost or archived session can't take it: the pushed branch, the trackers, a note in the project's memory directory (`on-hold-<topic>.md`, with a line in `MEMORY.md`), and a hold record under `~/.claude/simplicity/call-it-a-day/` that holds the pre-hold title and a copy of the handoff.
- It detects the resume three ways, with no resume command. In the same session, a `UserPromptSubmit` hook sees the hold record and reminds Claude, on the next prompt, to restore the title and clear the hold; a prompt that only says "thanks" or "good night" leaves the hold alone. Where the hook can't run, as in a reclaimed cloud container or without `python3`, the hold report in the transcript does the same job. In a new session, the pasted handoff prompt opens with the resume steps, including giving the held session its title back.
- Neither session is archived; that's your call.
- Like `shift-session`, it can be named mid-sentence, and then it asks before it loads, because it declares `allowed-tools` for its helpers.
- It reads `shift-session`'s SKILL.md for the shared commit, push and tracker rules, so both skills must come from the same plugin version.
- In the CLI it renames with `rename-session`'s helper and says `claude --resume <id>` reopens the session.

## cleanup

`/simplicity:cleanup`

Runs an end-of-session checklist before the session goes idle or gets archived. It flags uncommitted, unpushed or stashed work without touching it, stops background tasks this session started, removes scratch files, and offers to archive the session. It also stops the containers this session started and lists the containers, volumes and databases it created, deleting one only when you name it. It never prunes and never touches a container or database that was already there. It isn't for cleaning up code.

### Notes

- `cleanup`'s session steps (stopping background tasks, messaging other sessions, retitling, archiving) use the desktop app's session tools. In the CLI it skips them, says so, and ends at "ready to close".
- Before it offers to archive, it checks this session's side sessions. One that shares this session's folder would be archived along with it, and its folder removed, so it doesn't offer and says why. Otherwise, once you agree, it detaches each side session so it lives on, then archives.
- `cleanup` doesn't measure disk or delete build output and worktrees. For that, run `disk-cleanup`, which keeps `cleanup`'s rules for containers, volumes and databases.

## disk-cleanup

`/simplicity:disk-cleanup [--orchestrator]`

Frees disk space without losing work. It sweeps read-only and measures free space with `df` and every candidate with `du`, in exact bytes. The candidates are git worktrees (this session's, its helper and agent worktrees, and leftovers of finished sessions), the build output inside them (`target/`, `node_modules/`, `.venv/`, `dist/`, build caches), its scratch files, stopped containers, dangling images, unused volumes, the databases it created, and tool caches. It shows one table with each item's size, owner, check results and a recommended action. Then it asks you which to delete and deletes only those, each by its absolute path, never with a glob, and measures again. By default it touches only this session's own area. A worktree or build folder is offered only when it has no uncommitted or untracked changes, its head commit is on a remote or in a branch that stays, no running process works or has files open inside it, and it isn't another live session's worktree. Anything whose owner it can't establish is held.

With `--orchestrator`, it first asks you to confirm the sessions it coordinates, then sends each one order to run `disk-cleanup` on its own area. Each session asks you in its own session and reports what it freed and what it held. The orchestrator waits for those reports without polling, then sweeps what no live session owns, such as an archived session's leftover worktree and the shared tool caches.

### Notes

- Rebuildable kinds (build output, worktrees whose commits are safe, scratch, tool caches) can be picked by category. Irreversible kinds (containers, images, volumes, databases) must each be picked by name. "All the volumes" picks nothing.
- It removes a worktree with `git worktree remove` and never `--force`, and keeps its branch. Measured on git 2.56.1: `git worktree remove` deletes ignored files without asking, so a worktree holding an ignored file that isn't build output, such as `.env`, is held.
- The process check reads `/proc` on Linux, for the working directory and open files of your own user's processes, and uses `lsof` on macOS. It runs again right before each deletion, since a build may have started since the sweep.
- It skips the container steps when neither Docker nor Podman is installed. It never prunes, never deletes a branch, and never uses the desktop app's bulk worktree cleanup, which skips these checks.
- The freed amount is the `df` difference per filesystem, shown beside the sum of the deleted items' `du` sizes.
- No session deletes on another session's word. A message from another session can start a run, but that run only sweeps, lists and asks you in its own session; a claim in the message that you approved something counts for nothing. That's why, in orchestrator mode, each session asks you itself rather than the orchestrator relaying your answer: a relayed answer would still be a message from another session.
- Orchestrator mode never archives a session and never deletes inside a live session's worktree, even when that session asks it to. A session that doesn't report keeps its area out of the sweep.
- In plan mode it sweeps and asks, deletes nothing and sends no order, and lists what it would do as deferred.
- Orchestrator mode and the ownership checks use the desktop app's session tools. In the CLI, only this session's own area is in scope, and orchestrator mode prints the order for you to paste into each session.

## rename-session

`/simplicity:rename-session [topic]`

Renames the session after what it was actually about, so you can find it later in the resume picker. The title is 2 to 5 words in sentence case and names where the work ended up, not the first message. Pass a topic and it uses that instead. [adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins)]

### Notes

- `rename-session` renames through the desktop app's session title tool when it runs there, because the app keeps its own titles. In the CLI it writes the `custom-title` records that Claude Code keeps for its own renames. They're internal and undocumented, so a CLI update could break it, and the header of the live session may show the old title until you reopen it. Whether it updates the claude.ai web title in cloud sessions is unverified.
- It ships a Python helper, which needs Python 3, the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets, and a session transcript on disk. It needs them only in the CLI.
- Named mid-sentence, it asks before it loads, because it declares `allowed-tools` for its helper script, and the helper script may ask too. Typed as the command, it doesn't ask.

## promptfy

`/simplicity:promptfy [prompt]`

Rewrites a prompt into a stronger one and hands it back without running it. It checks the paths the prompt names against the repo, gives the rewrite to a subagent on the most capable model, and prints the result in a code block with a short list of what changed. Anything it couldn't verify comes back as a question through `AskUserQuestion`. With no argument, it rewrites the last prompt you typed. [adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins) and renamed from [`ultra-prompt`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt) to "promptfy"]

### Notes

- `promptfy` ships a Python helper, which needs Python 3, the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets, and a session transcript on disk. It needs them only when you call it with no argument.
- Named mid-sentence, it asks before it loads, because it declares `allowed-tools` for its helper script, and the helper script may ask too. Typed as the command, it doesn't ask.
