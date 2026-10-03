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
pytest skills/rename-session/tests skills/promptfy/tests -q
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

Each run is a `claude -p` call, so it counts against your Claude plan's usage limits. See the
Evals section of the [README](README.md) for the commands and the run counts.

## Pull requests

- Branch from `main`; `main` is protected and takes changes only through pull requests.
- Keep a PR to one change. Add a CHANGELOG entry when users would notice the change.
- CI must pass.

Releases are cut by the maintainer; see [RELEASING.md](RELEASING.md).
