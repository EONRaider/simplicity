# simplicity

Small Claude Code skills for long sessions. The three `just-*` commands never fire on their own. You call them when you need them. `cleanup` can also run when you ask Claude to wrap a session up.

| Command | What it does |
|---|---|
| `/simplicity:just-ask [focus]` | Sweeps the session (your messages, the plan, the task list and Claude's own earlier responses) for every question that's still open. It drops anything the repo or the conversation already answers, then asks the rest through `AskUserQuestion` in rounds of up to four. Every option has a recommendation and the reasoning behind it. |
| `/simplicity:just-say-it [N \| topic]` | Re-states the last response, the last N responses, or everything said on a topic as a short numbered list: a bold label plus one plain sentence per item. It adds no preamble and no new information. If the content leaves decisions open, it ends by pointing you to `just-ask`. |
| `/simplicity:just-finish-it [PR numbers \| repo]` | Ships the session's work and closes it. It pushes this session's branches, opens any missing PRs, waits for CI, and merges the PRs whose checks pass, base-first for stacked PRs. It never uses `--admin`, force-pushes, or commits work for you. Then it syncs your local repos, runs `cleanup`, and archives the session. If anything is still pending (red CI, a missing review, uncommitted work, unfinished tasks), it skips archiving and ends with a numbered "Still to do" list, each item with its next step. |
| `/simplicity:cleanup` | An end-of-session checklist. It flags uncommitted, unpushed or stashed work without touching it, stops background tasks this session started, removes scratch files, and offers to archive the session. |

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

- `AskUserQuestion` exists only in Claude Code. On other surfaces, `just-ask` falls back to a numbered markdown list with the same recommendations.
- `just-finish-it` needs `git` and an authenticated `gh`. Archiving uses the desktop app's session tools. In the CLI it stops at "ready to close".
- `just-say-it` only compresses. If you want terser output in every session, set an output style or a CLAUDE.md instruction instead.

## Evals

Each skill ships seeded session transcripts and expectations in `skills/<name>/evals/`. To reproduce the benchmark in the CHANGELOG (each run is a `claude -p` call, so it counts against your Claude plan's usage limits):

```bash
python3 scripts/run_evals.py --iteration iteration-1 --runs 5
python3 scripts/grade.py .eval-workspace/*/iteration-1-*
```

Then aggregate each iteration directory with SkillArtisan's `scripts/eval_loop.py aggregate`.

The `just-finish-it` and `cleanup` evals never touch a real repository. Each seed ends with a "Live state" snapshot, `Bash` is disallowed, and the model logs every command it would run as a JSON block, which the grader checks for order and safety. These runs also skip user-level settings (`--setting-sources project,local`), so a personal skill such as a `~/.claude/skills/cleanup` can't leak into the baseline.

## License

[MIT](LICENSE)
