# Notes

Requirements, limits and platform differences for each skill. The [README](../README.md) has the short version of what each one does.

## Calling a command

- Claude Code runs a typed command only when it starts the message. Named anywhere else ("can you run `/simplicity:what-now`?"), the command reaches Claude as plain text, and Claude loads the skill itself. That works for every skill except `just-finish-it`, which pushes and merges, so it runs only when typed as the first thing in a message. Named mid-sentence, Claude can't load it and may tell you it isn't installed. It is installed: send `/simplicity:just-finish-it` as its own message.
- No skill fires on a paraphrase of what it does, with one exception: `cleanup` can also run when you ask Claude to wrap a session up.
- Three things can act without a typed command. `shift-session`'s hook suggests a shift once the context window is 60% full, and asks you before doing anything. `call-it-a-day`'s hook speaks only in a session you put on hold, to give it its old title back when you come back to it. And `just-move` can schedule a resume that fires into the session after your usage limit resets, but only once you've agreed to it.

## just-ask

- `AskUserQuestion` exists only in Claude Code. On other surfaces, `just-ask` falls back to a numbered markdown list with the same recommendations.

## just-move

- `just-move` needs the cloud session tools (`send_later`, `create_trigger`, `update_trigger`, `subscribe_pr_activity`) to schedule a resume and watch PRs. In the CLI, and anywhere else without them, nothing can fire while Claude Code isn't running: it says so, still writes the handoff note, and prints a resume prompt to paste once the limit resets.
- It asks for the reset time shown in `/usage`, unless the session already says it, and repeats it back in UTC.
- The hourly fallback checks a handoff note before it does anything, so it stays quiet while the run is moving, and switches itself off after the 7-day deadline or once the work resumes.
- In plan mode it asks its questions and defers every fix.
- It reads `just-ask`'s and `shift-session`'s SKILL.md files, so all three must come from the same plugin version.

## just-say-it

- `just-say-it` has two modes. Summarizing the session only compresses: it makes no tool calls and adds nothing. Explaining a commit, PR, document or snippet makes read-only calls for that one item (git, the GitHub MCP server or `gh`, a fetch tool, or a connector), and adds only plain-word definitions, never opinions or a review.
- If you want terser output in every session, set an output style or a CLAUDE.md instruction instead.

## just-finish-it

- `just-finish-it` needs `git`, plus an authenticated `gh` or the GitHub MCP server's tools (cloud sessions often have only the MCP server).
- On the MCP path it can't always see a merge queue. If the default branch is protected and the server's `governance` toolset doesn't show one, it takes the answer your CLAUDE.md or CONTRIBUTING states, and asks you only when neither says, once per run. If GitHub then refuses the merge because of a queue, the PR goes on "Still to do" for you to enqueue.
- The MCP server has no branch-delete tool, so a merged branch the repo doesn't auto-delete goes on the "Still to do" list.
- Archiving uses the desktop app's session tools. In the CLI it stops at "ready to close".

## shift-session

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

- `call-it-a-day` keeps its state where a lost or archived session can't take it: the pushed branch, the trackers, a note in the project's memory directory (`on-hold-<topic>.md`, with a line in `MEMORY.md`), and a hold record under `~/.claude/simplicity/call-it-a-day/` that holds the pre-hold title and a copy of the handoff.
- It detects the resume three ways, with no resume command. In the same session, a `UserPromptSubmit` hook sees the hold record and reminds Claude, on the next prompt, to restore the title and clear the hold; a prompt that only says "thanks" or "good night" leaves the hold alone. Where the hook can't run, as in a reclaimed cloud container or without `python3`, the hold report in the transcript does the same job. In a new session, the pasted handoff prompt opens with the resume steps, including giving the held session its title back.
- Neither session is archived; that's your call.
- Like `shift-session`, it can be named mid-sentence, and then it asks before it loads, because it declares `allowed-tools` for its helpers.
- It reads `shift-session`'s SKILL.md for the shared commit, push and tracker rules, so both skills must come from the same plugin version.
- In the CLI it renames with `rename-session`'s helper and says `claude --resume <id>` reopens the session.

## cleanup

- `cleanup`'s session steps (stopping background tasks, messaging other sessions, retitling, archiving) use the desktop app's session tools. In the CLI it skips them, says so, and ends at "ready to close".

## rename-session

- `rename-session` renames through the desktop app's session title tool when it runs there, because the app keeps its own titles. In the CLI it writes the `custom-title` records that Claude Code keeps for its own renames. They're internal and undocumented, so a CLI update could break it, and the header of the live session may show the old title until you reopen it. Whether it updates the claude.ai web title in cloud sessions is unverified.
- It ships a Python helper, which needs Python 3, the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets, and a session transcript on disk. It needs them only in the CLI.
- Named mid-sentence, it asks before it loads, because it declares `allowed-tools` for its helper script, and the helper script may ask too. Typed as the command, it doesn't ask.

## promptfy

- `promptfy` ships a Python helper, which needs Python 3, the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets, and a session transcript on disk. It needs them only when you call it with no argument.
- Named mid-sentence, it asks before it loads, because it declares `allowed-tools` for its helper script, and the helper script may ask too. Typed as the command, it doesn't ask.
