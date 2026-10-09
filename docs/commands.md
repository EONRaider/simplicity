# Commands

What each skill does in full, with its requirements, limits and platform differences. The [README](../README.md) has the one-line version.

## Calling a command

- Claude Code runs a typed command only when it starts the message. Named anywhere else ("can you run `/simplicity:what-now`?"), the command reaches Claude as plain text, and Claude loads the skill itself. That works for every skill except `just-finish-it`, which pushes and merges, so it runs only when typed as the first thing in a message. Named mid-sentence, Claude can't load it and may tell you it isn't installed. It is installed: send `/simplicity:just-finish-it` as its own message.
- No skill fires on a paraphrase of what it does, with one exception: `cleanup` can also run when you ask Claude to wrap a session up.
- Three things can act without a typed command. `shift-session`'s hook suggests a shift once the context window is 60% full, and asks you before doing anything. `call-it-a-day`'s hook speaks only in a session you put on hold, to give it its old title back when you come back to it. And `just-move` can schedule a resume that fires into the session after your usage limit resets, but only once you've agreed to it.

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

## shift-session

`/simplicity:shift-session [--pr]`

Hands the session's work to a fresh child session before the context window bloats. It commits and pushes the work, updates whichever trackers the project has (the one named in CLAUDE.md, Jira, GitHub issues and PRs, the task list, memory files), writes a self-contained handoff prompt, and starts the child as `<topic> -> Part 2` (Part 3 on the next shift, and so on). Then it renames this session `<topic> -> Handed Off`, runs `cleanup`, and archives it. It follows `just-finish-it`'s rules: it never pushes to the default branch (work found there moves to a new `shift/<topic>` branch), never force-pushes, never stages a file holding a secret, and holds back any branch whose diff or commit history holds one. It opens a PR only with `--pr`. If anything is pending, the child still gets the work, with the pending list in its handoff, and this session stays open. A plugin hook suggests a shift once context use reaches `SIMPLICITY_SHIFT_THRESHOLD` percent (default 60); a suggested shift asks you once, then runs to the end.

### Notes

- `shift-session` starts the child in the most automatic way the UI allows. If the desktop app offers a tool that starts a session with a prompt (`start_session` or `hand_off_to_session`), it uses that, and archives this session at the end. The app build checked for this release (desktop 2.9939.4, Claude Code 2.1.284) has neither, so there it creates a suggestion chip you start with one click. Archiving a session removes its unclicked chip, so the parent stays open, and the child archives it once it runs; if the parent is still finishing its turn, the child waits and retries, up to three times, before leaving it to you.
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

Puts the session on hold when you stop for the day, so you can pick the same work up later with nothing lost. It commits whatever is uncommitted as a WIP commit and pushes it, under `shift-session`'s rules (never the default branch, which moves to a `hold/<topic>` branch; never force-push; never a file or branch holding a secret). It updates whichever trackers the project has, saves a handoff note to the project's memory directory, records the session's title, renames the session `<topic> -> On hold` and prints a self-contained handoff prompt. It leaves the session open, starts no new session, merges nothing, and opens a draft PR only with `--pr`. When you come back, keep typing in the same session or paste the prompt into a new one: either way the session gets its old title back.

### Notes

- `call-it-a-day` keeps its state where a lost or archived session can't take it: the pushed branch, the trackers, a note in the project's memory directory (`on-hold-<topic>.md`, with a line in `MEMORY.md`), and a hold record under `~/.claude/simplicity/call-it-a-day/` that holds the pre-hold title and a copy of the handoff.
- It detects the resume three ways, with no resume command. In the same session, a `UserPromptSubmit` hook sees the hold record and reminds Claude, on the next prompt, to restore the title and clear the hold; a prompt that only says "thanks" or "good night" leaves the hold alone. Where the hook can't run, as in a reclaimed cloud container or without `python3`, the hold report in the transcript does the same job. In a new session, the pasted handoff prompt opens with the resume steps, including giving the held session its title back.
- Neither session is archived; that's your call.
- Like `shift-session`, it can be named mid-sentence, and then it asks before it loads, because it declares `allowed-tools` for its helpers.
- It reads `shift-session`'s SKILL.md for the shared commit, push and tracker rules, so both skills must come from the same plugin version.
- In the CLI it renames with `rename-session`'s helper and says `claude --resume <id>` reopens the session.

## cleanup

`/simplicity:cleanup`

Runs an end-of-session checklist before the session goes idle or gets archived. It flags uncommitted, unpushed or stashed work without touching it, stops background tasks this session started, removes scratch files, and offers to archive the session. It isn't for cleaning up code.

### Notes

- `cleanup`'s session steps (stopping background tasks, messaging other sessions, retitling, archiving) use the desktop app's session tools. In the CLI it skips them, says so, and ends at "ready to close".

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
