## Summary

<!-- What this changes and why, in a few sentences. -->

## Changes

-

## Credit

<!-- Code or text adapted from someone else: name them, link the source at a pinned commit, and state the license. Otherwise write "None". -->

## Verification

<!-- Tick what you ran and paste the result. Leave a box empty rather than tick something that didn't run. -->

- [ ] `pytest skills/rename-session/tests skills/promptfy/tests -q`
- [ ] `claude plugin validate .`
- [ ] Evals for the skills this touches (`scripts/run_evals.py`, then `scripts/grade.py`), with the run count and pass rates
- [ ] Smoke test with `claude --plugin-dir .`

## Release

<!-- Only for a release PR. See RELEASING.md. -->

- [ ] `version` bumped in `.claude-plugin/plugin.json`
- [ ] CHANGELOG entry dated, compare links updated
