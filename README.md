# simplicity

Two small, user-invoked Claude Code skills for long sessions. Neither one fires on its own. You call them when you need them.

| Command | What it does |
|---|---|
| `/simplicity:just-ask [focus]` | Sweeps the session (your messages, the plan, the task list and Claude's own earlier responses) for every question that's still open. It drops anything the repo or the conversation already answers, then asks the rest through `AskUserQuestion` in rounds of up to four. Every option has a recommendation and the reasoning behind it. |
| `/simplicity:just-say-it [N \| topic]` | Re-states the last response, the last N responses, or everything said on a topic as a short numbered list: a bold label plus one plain sentence per item. It adds no preamble and no new information. If the content leaves decisions open, it ends by pointing you to `just-ask`. |

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
- `just-say-it` only compresses. If you want terser output in every session, set an output style or a CLAUDE.md instruction instead.

## Evals

Each skill ships seeded session transcripts and expectations in `skills/<name>/evals/`. To reproduce the benchmark in the CHANGELOG (this uses real API usage):

```bash
python3 scripts/run_evals.py --iteration iteration-1 --runs 5
python3 scripts/grade.py .eval-workspace/*/iteration-1-*
```

Then aggregate each iteration directory with SkillArtisan's `scripts/eval_loop.py aggregate`.

## License

[MIT](LICENSE)
