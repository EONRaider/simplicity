# simplicity

simplicity is a Claude Code plugin of ten small skills for long sessions. They ask every open question at once, re-state a long response in plain language, tell you where the task stands, rewrite a prompt, rename the session, prepare it to run unattended, and close the work out: hand it to a fresh session, put it on hold for the day, or push, merge and archive it. Nothing acts unless you ask: you type a command or name it in a sentence.

## Install

```bash
claude plugin marketplace add EONRaider/claude-plugins
claude plugin install simplicity@eonraider
```

For local development, load the plugin straight from a clone:

```bash
claude --plugin-dir /path/to/simplicity
```

## Commands

| Command | What it does |
|---|---|
| [`/simplicity:just-ask [focus]`](docs/commands.md#just-ask) | Collects every question still open in the session and asks them all at once, each option with a recommendation. |
| [`/simplicity:just-move [focus]`](docs/commands.md#just-move) | Gets the session ready to run on its own for as long as possible, including across usage-limit resets. |
| [`/simplicity:just-say-it [N \| topic \| commit \| #PR \| file or URL \| text]`](docs/commands.md#just-say-it) | Re-states recent responses, or explains a commit, PR, document or snippet, as a short numbered list in plain language. |
| [`/simplicity:what-now`](docs/commands.md#what-now) | Takes stock of the session and lists what's done, where the current task stands, and the next steps to finish it. |
| [`/simplicity:just-finish-it [PR numbers \| repo path]`](docs/commands.md#just-finish-it) | Ships the session's work and closes it: pushes, merges the PRs whose CI is green, cleans up and archives the session. |
| [`/simplicity:shift-session [--pr]`](docs/commands.md#shift-session) | Hands the session's work to a fresh child session before the context window bloats. |
| [`/simplicity:call-it-a-day [--pr]`](docs/commands.md#call-it-a-day) | Puts the session on hold when you stop for the day, so you can pick the same work up later with nothing lost. |
| [`/simplicity:cleanup`](docs/commands.md#cleanup) | Runs an end-of-session checklist before the session goes idle or gets archived. |
| [`/simplicity:rename-session [topic]`](docs/commands.md#rename-session) | Renames the session after what it was actually about, so you can find it later in the resume picker. |
| [`/simplicity:promptfy [prompt]`](docs/commands.md#promptfy) | Rewrites a prompt into a stronger one and hands it back without running it. |

Each command links to its full description in [docs/commands.md](docs/commands.md), along with its requirements, the differences between the desktop app, the CLI and cloud sessions, and the hook settings. To run the evals, see [CONTRIBUTING.md](CONTRIBUTING.md#running-the-evals).

## Credits

`rename-session` and `promptfy` are adapted from [voidharbor](https://github.com/voidharbor)'s [claude-plugins](https://github.com/voidharbor/claude-plugins), at commit [`397b270`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b), under the MIT license. `rename-session` comes from [`rename-session`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/rename-session) and keeps its name. `promptfy` comes from [`ultra-prompt`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt), which ships here under the new name. Each skill's `SKILL.md` lists what changed from the original.

## License

[MIT](LICENSE). `rename-session` and `promptfy` carry voidharbor's MIT license and copyright notice in their own directories: [skills/rename-session/LICENSE](skills/rename-session/LICENSE) and [skills/promptfy/LICENSE](skills/promptfy/LICENSE).
