# Changelog

All notable changes to simplicity are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
follows [Semantic Versioning](https://semver.org/). Version headers here match the
repo's git tags, which follow GitHub's `vX.Y.Z` convention.

## [v0.2.0] - Unreleased

Two new skills, plus an adversarial review of the whole plugin. The review
found merge-safety gaps in the first draft of `just-finish-it`, and found
that the eval harness overstated every skill's effect, including the
v0.1.0 numbers below. Both are fixed here, and all four skills were
re-benchmarked on the corrected harness. That run used the smoke preset (5
runs per configuration) against a no-skill baseline on Haiku, Sonnet and
Opus:

| Skill | Haiku | Sonnet | Opus |
|---|---|---|---|
| `just-ask` (with / without) | 94% / 36% | 100% / 45% | 100% / 53% |
| `just-say-it` (with / without) | 98% / 56% | 98% / 49% | 100% / 41% |
| `just-finish-it` (with / without) | 93% / 66% | 94% / 72% | 100% / 71% |
| `cleanup` (with / without) | 81% / 66% | 98% / 73% | 100% / 82% |

The two older skills keep a large margin. `just-say-it`'s margin is mostly
format compliance: its format is the point of the skill, and its baseline
prompt doesn't ask for that format.

The two new skills keep a smaller but real margin. Without them, models
stashed or committed unfinished work, unstaged a secret on their own,
pushed to `main`, and archived sessions that still had pending work.

The remaining with-skill misses are mostly Haiku:

- With `just-finish-it`, Haiku sometimes skips the final archive call.
- With `cleanup`, Haiku sometimes skips the stop, retitle or handoff steps.
- One Sonnet `just-finish-it` run tried to re-invoke the command mid-run.
- Another Sonnet run declined to merge a newly opened PR whose number the
  seed doesn't give.

### Added

- **`just-finish-it`**: a user-invoked skill that ships a session's work.
  - **Shipping.** It pushes this session's branches, opens missing PRs,
    and waits for CI. It merges a PR only when:
    - every check has passed;
    - GitHub reports the PR as mergeable and clean;
    - no review requests changes;
    - its head is still the SHA that was pushed.

    Stacked PRs go base-first, and each child is brought up to date and
    re-tested before it merges.
  - **Tidying up.** It deletes the merged branches, syncs the local repos
    without touching dirty working trees or worktrees, and runs `cleanup`.
  - **Closing.** It archives the session only when nothing is pending and
    the run wasn't scoped. Otherwise it ends with a numbered "Still to do"
    list, each item with a concrete next step.
  - **What it never does:** use `--admin`, auto-merge or force-push, commit
    uncommitted work, or push to the default branch.
- **`cleanup`**: the end-of-session checklist, moved into the plugin from a
  personal skill.
  - It never repeats a secret's value.
  - It never messages a person without confirmation.
  - It skips steps whose session tools don't exist.
  - When `just-finish-it` runs it, every question goes back to
    `just-finish-it` as a pending item.
- Evals for both skills, and `RELEASING.md` with the tag and marketplace
  steps.

### Changed

- **Eval harness isolation.** Every eval run is now isolated from the
  machine it runs on:
  - no user-level settings, skills or plugins;
  - no MCP servers or claude.ai connectors;
  - `Skill` is the only tool.

  Before, baselines could reach personal skills and connectors with write
  tools, and some runs made real tool calls.
- **Full transcripts.** Runs capture the full `stream-json` transcript and
  retry runs that errored.
- **Baseline prompts.** They no longer tell the model to do what a check
  penalizes. The `just-finish-it` baseline used to say "push everything
  and archive it".
- **Grading.** `scripts/grade.py` now grades behavior, not plugin
  vocabulary:
  - It parses commands instead of keyword-matching: PR targets, push
    refspecs, the current branch, and message recipients.
  - It ignores lookups and tool calls that errored.
  - Format checks accept reasonable variants.
- **Seeds.** They no longer give away the expected outcome.

### Fixed

- **v0.1.0 benchmark.** The v0.1.0 benchmark below was measured on the old
  harness. Its baselines were penalized for harness artifacts: `just-ask`
  baselines found an empty working directory and asked about it. So its
  with/without gaps aren't comparable to the table above.
- **Rounding.** The v0.1.0 Opus `just-ask` baseline was 52%, not 53%.

## [v0.1.0] - 2026-09-27

Initial release. Both skills were built through SkillArtisan's pipeline:
decision gate, validation, gitleaks scan and audit (17/17). Each was
benchmarked at the smoke preset (5 runs per configuration) against a
no-skill baseline on Haiku, Sonnet and Opus, using a deterministic grader
over seeded session transcripts:

| Skill | Haiku | Sonnet | Opus |
|---|---|---|---|
| `just-ask` (with / without) | 88% / 48% | 100% / 46% | 100% / 52% |
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

[v0.2.0]: https://github.com/EONRaider/simplicity/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/EONRaider/simplicity/releases/tag/v0.1.0
