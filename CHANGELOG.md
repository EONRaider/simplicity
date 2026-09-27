# Changelog

All notable changes to simplicity are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
follows [Semantic Versioning](https://semver.org/). Version headers here match the
repo's git tags, which follow GitHub's `vX.Y.Z` convention.

## [Unreleased]

Both new skills went through SkillArtisan's pipeline: decision gate,
validation, gitleaks scan and audit (`just-finish-it` 17/17, `cleanup`
15/15). Each was benchmarked at the smoke preset (5 runs per configuration)
against a no-skill baseline on Haiku, Sonnet and Opus. The benchmark ran
over seeded session transcripts that end in a live-state snapshot, so no
real repository or PR is touched:

| Skill | Haiku | Sonnet | Opus |
|---|---|---|---|
| `just-finish-it` (with / without) | 95% / 61% | 98% / 70% | 100% / 70% |
| `cleanup` (with / without) | 94% / 60% | 100% / 68% | 99% / 79% |

Without the skill, models committed or stashed unfinished work, unstaged a
secret on their own, merged PRs with red CI or missing reviews, and
archived sessions that still had pending work. The remaining with-skill
misses are concentrated in Haiku. With `just-finish-it`, Haiku reports
"finished" but skips the archive call in 4 of 5 all-green runs, and Haiku
and Sonnet sometimes list an open decision without a "Next" step. With
`cleanup`, Haiku skips the requested handoff message in 3 of 5 runs and
sometimes skips the title proposal.

### Added

- **`just-finish-it`**: a user-invoked skill that ships a session's work.
  It pushes this session's branches, opens missing PRs, waits for CI,
  merges green PRs base-first (never `--admin`, never force-push), syncs
  the local repos, and runs `cleanup`. It archives the session only when
  nothing is pending. Otherwise it ends with a numbered "Still to do" list,
  each item with a concrete next step. Uncommitted work is flagged, never
  committed for you.
- **`cleanup`**: the end-of-session checklist, moved into the plugin from a
  personal skill. It hands the archive decision to `just-finish-it` when
  that skill runs it, and it never repeats a secret's value in its report.
- Evals for both skills (`skills/just-finish-it/evals/`,
  `skills/cleanup/evals/`).

### Changed

- `scripts/run_evals.py` captures the full `stream-json` transcript for
  skills whose actions span several turns. Those runs disallow `Bash` and
  skip user-level settings, so a personal skill can't leak into the
  baseline. `scripts/grade.py` gained action-order and safety checks for
  both new skills.
- The README says eval runs count against your Claude plan's usage limits
  (each one is a `claude -p` call), not API usage.

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
