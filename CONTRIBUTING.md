# Contributing to simplicity

Thanks for helping. Bug reports, skill fixes and documentation corrections are all welcome.

## Before you start

- For anything larger than a small fix, open an issue first so the approach can be agreed.
- Security problems go through [private reporting](SECURITY.md), not public issues.
- By contributing you agree that your work is released under the [MIT license](LICENSE) and
  that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

You need Python 3.10 or later and Claude Code.

```bash
git clone https://github.com/EONRaider/simplicity.git
cd simplicity
python3 -m pip install pytest ruff mypy
```

Run the checks CI runs:

```bash
pytest skills/rename-session/tests skills/promptfy/tests skills/shift-session/tests skills/call-it-a-day/tests -q
ruff check skills/*/scripts skills/*/tests
ruff format --check skills/*/scripts skills/*/tests
mypy --strict skills/*/scripts/*.py skills/*/tests/*.py
```

Try the plugin from your checkout, in any project:

```bash
claude --plugin-dir /path/to/simplicity
```

Validate the plugin manifest:

```bash
claude plugin validate .
```

## Ground rules

1. **A skill is one `SKILL.md`.** Each lives in `skills/<name>/`, with its evals in `evals/`
   and, if it needs code, its helpers in `scripts/` and their tests in `tests/`.
2. **Skills that act are conservative.** Nothing commits, discards, force-pushes, bypasses a
   check or messages a person on its own. When in doubt a skill reports and asks.
3. **Helper scripts use the standard library only**, and are tested against a throwaway home
   directory. A test never reads or writes a real session.
4. **Changes to a skill come with evals.** Add or update a seeded session in
   `skills/<name>/evals/` and its checks in `scripts/grade.py`. Checks grade behavior, not
   vocabulary, and a baseline prompt never names the plugin.
5. **Report evidence honestly.** The CHANGELOG says what was run, how many times, and what
   missed. "Not run" is an acceptable answer; an unstated one is not.
6. **Credit travels with adapted work.** Code or text taken from someone else keeps its
   license file, a provenance header, and a credit in the skill, the README and the CHANGELOG.

## Running the evals

Each skill ships seeded session transcripts and expectations in `skills/<name>/evals/`: 64
evals across the ten skills. `cleanup` also ships a 20-query trigger set for its description
(`skills/cleanup/evals/trigger_eval_set.json`), and the eight skills you can name mid-sentence
ship a 10-query set each that checks they run when named and stay quiet when paraphrased.

To reproduce the benchmark in the CHANGELOG, run the commands below. Each run is a `claude -p`
call, so it counts against your Claude plan's usage limits, or bills your API key if one is
configured. Every eval runs with and without the skill on Haiku, Sonnet and Opus, so
`--runs 5` (the smoke preset the CHANGELOG uses) is 1,920 runs. `--runs` defaults to 1 (384
runs); `--skills`, `--models`, `--evals` and `--configs` narrow the set.

```bash
python3 scripts/run_evals.py --iteration my-run --runs 5
python3 scripts/grade.py .eval-workspace/*/my-run-*
```

Use a fresh iteration name: runs that already have a result are skipped, so an old name only
resumes. Then aggregate each iteration directory with `scripts/eval_loop.py aggregate` from
[SkillArtisan](https://github.com/EONRaider/SkillArtisan).

Every run is isolated from the machine it runs on:

- It skips user-level settings, skills and plugins (`--setting-sources project,local`).
- It skips MCP servers and claude.ai connectors (`--strict-mcp-config`).
- The only tool it can call is `Skill`, and a with-skill run may load a skill without asking,
  as if you had approved the prompt. `call-it-a-day`'s and `just-move`'s runs can also call
  the read-only `Read`, since those skills read other skills' SKILL.md files.

The `just-finish-it`, `cleanup`, `rename-session`, `promptfy`, `shift-session`,
`call-it-a-day` and `just-move` seeds end with a "Live state" snapshot that stands in for the
repos and PRs. The model logs every command it would run as a JSON block, and the grader
checks those blocks for order and safety. No real repository, PR or session is touched.

The four Python helpers also have unit tests: the `pytest` command under [Setup](#setup).
They run against a throwaway home directory and cost nothing.

## Pull requests

- Branch from `main`; `main` is protected and takes changes only through pull requests.
- Keep a PR to one change. Add a CHANGELOG entry when users would notice the change.
- CI must pass.

Releases are cut by the maintainer; see [RELEASING.md](RELEASING.md).
