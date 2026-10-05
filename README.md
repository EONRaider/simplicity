# simplicity

Small Claude Code skills for long sessions. None of them fires on its own. You call them when you need them, by typing the command or by naming it in a sentence. `cleanup` can also run when you ask Claude to wrap a session up.

| Command | What it does |
|---|---|
| `/simplicity:just-ask [focus]` | Sweeps the session (your messages, the plan, the task list and Claude's own earlier responses) for every question that's still open. It drops anything the repo or the conversation already answers, then asks the rest through `AskUserQuestion` in rounds of up to four. Every option has a recommendation and the reasoning behind it. |
| `/simplicity:just-say-it [N \| topic]` | Re-states the last response, the last N responses, or everything said on a topic as a short numbered list: a bold label plus one plain sentence per item. It adds no preamble and no new information. If the content leaves decisions open, it ends by pointing you to `just-ask`. |
| `/simplicity:what-now` | Takes stock of the session and gives three short lists: what's done, where the current task stands, and the next steps to finish it. Each item is a bold label plus one plain sentence. It makes no tool calls and counts work as done only when the session shows it done, so a fix that was never tested is marked unverified. A step that needs you, such as a decision, says so. |
| `/simplicity:just-finish-it [PR numbers \| repo path]` | Ships the session's work and closes it. It pushes this session's branches, opens any missing PRs, waits for CI, and merges the PRs whose checks all pass, base-first for stacked PRs. It then deletes the merged branches, remote and local, syncs your local repos, runs `cleanup`, and archives the session. It never uses `--admin`, auto-merge or force-push, never commits work for you, and never pushes to the default branch. If anything is still pending (red CI, a missing review, uncommitted work, unfinished tasks), or if you scoped the run, it skips archiving. It ends with a numbered "Still to do" list, each item with its next step. |
| `/simplicity:cleanup` | An end-of-session checklist. It flags uncommitted, unpushed or stashed work without touching it, stops background tasks this session started, removes scratch files, and offers to archive the session. It isn't for cleaning up code. |
| `/simplicity:rename-session [topic]` | Renames the session after what it was actually about, so you can find it later in the resume picker. The title is 2 to 5 words in sentence case and names where the work ended up, not the first message. Pass a topic and it uses that instead. [adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins)] |
| `/simplicity:promptfy [prompt]` | Rewrites a prompt into a stronger one and hands it back. It never runs the prompt. It checks the paths the prompt names against the repo, gives the rewrite to a subagent on the most capable model, and prints the result in a code block with a short list of what changed. Anything it couldn't verify comes back as a question through `AskUserQuestion`. With no argument, it rewrites the last prompt you typed. [adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins) and renamed from [`ultra-prompt`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt) to "promptfy"] |

## Install

```bash
claude plugin marketplace add EONRaider/claude-plugins
claude plugin install simplicity@eonraider
```

For local development, load the plugin straight from a clone:

```bash
claude --plugin-dir /path/to/simplicity
```

## Notes

- Claude Code runs a typed command only when it starts the message. Named anywhere else ("can you run `/simplicity:what-now`?"), the command reaches Claude as plain text, and Claude loads the skill itself. That works for every skill except `just-finish-it`, which pushes and merges, so it runs only when typed as the first thing in a message. Named mid-sentence, Claude can't load it and may tell you it isn't installed. It is installed: send `/simplicity:just-finish-it` as its own message.
- `AskUserQuestion` exists only in Claude Code. On other surfaces, `just-ask` falls back to a numbered markdown list with the same recommendations.
- `just-finish-it` needs `git`, plus an authenticated `gh` or the GitHub MCP server's tools (cloud sessions often have only the MCP server). On the MCP path it can't always see a merge queue. If the default branch is protected and the server's `governance` toolset doesn't show one, it takes the answer your CLAUDE.md or CONTRIBUTING states, and asks you only when neither says, once per run. If GitHub then refuses the merge because of a queue, the PR goes on "Still to do" for you to enqueue. The MCP server has no branch-delete tool, so a merged branch the repo doesn't auto-delete goes on the "Still to do" list. Archiving uses the desktop app's session tools. In the CLI it stops at "ready to close".
- `cleanup`'s session steps (stopping background tasks, messaging other sessions, retitling, archiving) use the desktop app's session tools. In the CLI it skips them, says so, and ends at "ready to close".
- `just-say-it` only compresses. If you want terser output in every session, set an output style or a CLAUDE.md instruction instead.
- `rename-session` and `promptfy` ship Python helpers. They need Python 3, the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets, and a session transcript on disk. `rename-session` needs them only in the CLI, and `promptfy` only when you call it with no argument.
- Named mid-sentence, `rename-session` and `promptfy` ask before they load, because they declare `allowed-tools` for their helper scripts, and the helper script may ask too. Typed as the command, neither asks.
- `rename-session` renames through the desktop app's session title tool when it runs there, because the app keeps its own titles. In the CLI it writes the `custom-title` records that Claude Code keeps for its own renames. They're internal and undocumented, so a CLI update could break it, and the header of the live session may show the old title until you reopen it. Whether it updates the claude.ai web title in cloud sessions is unverified.

## Evals

Each skill ships seeded session transcripts and expectations in `skills/<name>/evals/`: 31 evals across the seven skills. `cleanup` also ships a 20-query trigger set for its description (`skills/cleanup/evals/trigger_eval_set.json`), and the five skills you can name mid-sentence ship a 10-query set each that checks they run when named and stay quiet when paraphrased. To reproduce the benchmark in the CHANGELOG, run the commands below. Each run is a `claude -p` call, so it counts against your Claude plan's usage limits, or bills your API key if one is configured. Every eval runs with and without the skill on Haiku, Sonnet and Opus, so `--runs 5` (the smoke preset the CHANGELOG uses) is 930 runs. `--runs` defaults to 1 (186 runs); `--skills`, `--models`, `--evals` and `--configs` narrow the set.

```bash
python3 scripts/run_evals.py --iteration my-run --runs 5
python3 scripts/grade.py .eval-workspace/*/my-run-*
```

Use a fresh iteration name: runs that already have a result are skipped, so an old name only resumes. Then aggregate each iteration directory with `scripts/eval_loop.py aggregate` from [SkillArtisan](https://github.com/EONRaider/SkillArtisan).

Every run is isolated from the machine it runs on:

- It skips user-level settings, skills and plugins (`--setting-sources project,local`).
- It skips MCP servers and claude.ai connectors (`--strict-mcp-config`).
- The only tool it can call is `Skill`, and a with-skill run may load a skill without asking, as if you had approved the prompt.

The `just-finish-it`, `cleanup`, `rename-session` and `promptfy` seeds end with a "Live state" snapshot that stands in for the repos and PRs. The model logs every command it would run as a JSON block, and the grader checks those blocks for order and safety. No real repository, PR or session is touched.

The two Python helpers also have unit tests. They run against a throwaway home directory and cost nothing:

```bash
pytest skills/rename-session/tests skills/promptfy/tests -q
```

## Credits

`rename-session` and `promptfy` are adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins), at commit [`397b270`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b), under the MIT license. `rename-session` comes from [`rename-session`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/rename-session) and keeps its name. `promptfy` comes from [`ultra-prompt`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt), which ships here under the new name. Each skill's `SKILL.md` lists what changed from the original.

## License

[MIT](LICENSE). `rename-session` and `promptfy` carry voidharbor's MIT license and copyright notice in their own directories: [skills/rename-session/LICENSE](skills/rename-session/LICENSE) and [skills/promptfy/LICENSE](skills/promptfy/LICENSE).
