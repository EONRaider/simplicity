# Changelog

All notable changes to simplicity are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
follows [Semantic Versioning](https://semver.org/). Version headers here match the
repo's git tags, which follow GitHub's `vX.Y.Z` convention.

## [Unreleased]

## [v0.1.0] - 2026-09-27

Initial release. Both skills were built through SkillArtisan's pipeline:
decision gate, validation, gitleaks scan and audit (17/17). Each was
benchmarked at the smoke preset (5 runs per configuration) against a
no-skill baseline on Haiku, Sonnet and Opus, using a deterministic grader
over seeded session transcripts:

| Skill | Haiku | Sonnet | Opus |
|---|---|---|---|
| `just-ask` (with / without) | 88% / 48% | 100% / 46% | 100% / 53% |
| `just-say-it` (with / without) | 97% / 53% | 97% / 50% | 98% / 40% |

Haiku's remaining `just-ask` misses are formatting only: an occasional
header over 12 characters, or a markdown fallback triggered by the headless
harness.

### Added

- **`just-ask`**: a user-invoked skill that sweeps the session for open
  questions, filters out anything answerable without the user, and asks the
  rest through `AskUserQuestion` in rounds of up to four. Every option carries
  a recommendation and its reasoning, and a markdown fallback covers surfaces
  without the tool.
- **`just-say-it`**: a user-invoked skill that re-states the latest
  response, the last N responses, or a topic as a short plain-language
  numbered list, with a hand-off line to `just-ask` when decisions are left
  open.
- An eval set per skill (`skills/*/evals/`) with seeded session transcripts,
  plus the harness that runs and grades it (`scripts/run_evals.py`, `scripts/grade.py`).
