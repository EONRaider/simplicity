## What changed

## Why

## Credit

<!-- Code or text adapted from someone else: name them, link the source at a pinned commit, and state the license. Otherwise write "None". -->

## How it was checked

- [ ] `pytest skills/rename-session/tests skills/promptfy/tests skills/shift-session/tests skills/call-it-a-day/tests -q` passes
- [ ] `ruff check`, `ruff format --check` and `mypy --strict` pass on the helper scripts and their tests
- [ ] `claude plugin validate .` passes
- [ ] Evals run for the skills this touches, with the run count and pass rates stated (or "not run")
- [ ] CHANGELOG.md updated (user-visible changes)
