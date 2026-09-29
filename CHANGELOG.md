# Changelog

All notable changes to simplicity are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
follows [Semantic Versioning](https://semver.org/). Version headers here match the
repo's git tags, which follow GitHub's `vX.Y.Z` convention.

## [Unreleased]

### Fixed

- **README.** It said the eval harness defaults to 570 runs. `--runs`
  defaults to 1 (114 runs); 570 is the `--runs 5` smoke preset. The
  README now also gives `just-finish-it`'s argument hint as SKILL.md does,
  says what `cleanup` skips in the CLI, and points to `cleanup`'s trigger
  set.

## [v0.5.0] - 2026-09-28

A new command, `/simplicity:what-now`, gives a status snapshot of the
session. It was built through SkillArtisan's pipeline:

- decision gate, with no existing skill covering it;
- `validate.py`;
- gitleaks scan;
- `audit.py`, 21/21.

It was then benchmarked at the smoke preset (5 runs per configuration)
against a no-skill baseline on Haiku, Sonnet and Opus:

| Skill | Haiku | Sonnet | Opus |
|---|---|---|---|
| `what-now` (with / without) | 84% / 48% | 96% / 56% | 99% / 52% |

These numbers come from a second pass.

- **Corrected baselines.** The first grading pass scored the baselines at
  28–32%, because its content checks only read named sections. A
  baseline that answered in prose failed them even when the facts were
  right. The content checks now read the whole response when a section is
  missing, and the table uses the corrected scores.
- **Two SKILL.md fixes.** The first run exposed two gaps, fixed before the
  with-skill runs were repeated:
  - a finished session's Now item had no label;
  - the user's decision wasn't placed first under Next.

  Haiku went from 74% to 84%. The baseline runs were shared across both
  passes.

Most of the margin is format compliance, as with `just-say-it`. The
baseline prompt ("Where are we? What's done, where does the task stand,
and what's next?") asks for the content but not the format. Without the
skill, models mostly report the right facts, in prose or loose lists. The
skill's content wins are narrower:

- In a finished session it never invents next steps (15/15 runs vs 11/15).
- It always flags a fix that was never tested (15/15 vs 13/15).

The remaining with-skill misses:

- Haiku sometimes leaves the bold labels off numbered Next steps.
- Sonnet and Opus sometimes go over the 4-word label limit on the user's
  decision step ("You decide dead-letter vs. drop").

### Added

- **`what-now`**: a user-invoked skill that takes stock of the session and
  prints three lists. **Done** is what the session finished, **Now** is
  where the current task stands, and **Next** is the numbered steps that
  finish it. Each item is a bold label plus one sentence.
  - It makes no tool calls. It counts work as done only when the session
    shows it done. It marks a fix that was never tested as not yet
    verified, and it reports CI, background tasks and the working tree as
    "last seen".
  - A step is the user's only when it needs a decision, an approval or a
    credential. That step starts with "You", comes first when the task is
    waiting on it, and points decisions to `/simplicity:just-ask`.
  - It never invents steps to fill an empty list.
- **Evals.** Three seeded sessions for `what-now`: a task in progress with
  an untested fix, a finished task, and a task blocked on the user's
  decision. `scripts/grade.py` and `scripts/run_evals.py` now cover the
  new skill.
  - Section headers accept reasonable variants.
  - Content checks read the whole response when a section is missing, so
    a baseline that writes prose is graded on what it says and loses
    points only on the format checks.

  The README's full-benchmark count goes from 480 to 570 runs.

## [v0.4.0] - 2026-09-28

`just-finish-it` can now merge over the GitHub MCP server without the
`governance` toolset. v0.3.0 left every PR pending there with "couldn't
verify merge queue", which is the normal case in Claude Code on the web.
This release also fixes a merge-queue check that missed queues set in
classic branch protection, on both transports. No benchmark was re-run.
The new and changed evals have been checked against synthetic good and bad
responses only, not against live model runs.

### Changed

- **Merge queues on the MCP path.** The skill now works out the queue state
  from what the default toolsets can read, and asks when they can't tell.
  - `list_branches` gives the default branch's `protected` flag. When it's
    `false`, the branch has no merge queue, so the skill merges without
    asking.
  - When the branch is protected and `repository_ruleset_read` is loaded,
    a `merge_queue` rule still means pending, as before.
  - Otherwise the skill asks once whether the repo uses a merge queue. It
    asks in the same round as the merge-method question and recommends
    neither answer. "Yes", or no answer, means pending. "No" means it
    merges, with `expectedHeadSha` as before.
  - If GitHub then refuses the merge because of a queue, the PR goes on
    "Still to do" with "repo uses a merge queue: enqueue it yourself". The
    skill doesn't retry.
- **The question stays even though GitHub refuses queue bypasses.** GitHub
  refuses a direct API merge into a queue-required branch, but only for a
  caller who can't bypass the rule. For a caller who can, the same call
  merges and skips the queue. No default MCP tool reports whether the caller
  can bypass.
- **Enabling `governance`.** SKILL.md now names the exact settings.
  - Remote server: the header `X-MCP-Toolsets: default,governance`. To add
    only the read tool, send `X-MCP-Toolsets: default` with
    `X-MCP-Tools: repository_ruleset_read`.
  - Local binary: `--toolsets default,governance`, or
    `GITHUB_TOOLSETS=default,governance`.
  - Loading it lets the skill confirm a ruleset queue without asking. It
    can't rule out a classic-protection queue, so a protected branch with no
    ruleset queue still gets the question.

### Fixed

- **Classic-protection merge queues.** The `gh` path checked
  `GET /repos/{owner}/{repo}/rules/branches/{branch}`, which returns ruleset
  rules only. A queue set in classic branch protection returned `[]`, so the
  skill would have gone ahead and run `gh pr merge`. On a queue branch, that
  command adds the PR to the queue instead of merging it. The check now
  reads GraphQL `repository.mergeQueue(branch:)`, which is non-null for
  either kind of queue. If that query fails, as it can behind a proxy that
  pins GraphQL operations, the skill asks.
- **Queued isn't merged.** If `gh pr merge` reports that it queued the PR,
  the skill reports it as queued, not merged.

### Evidence

Measured on 2026-09-28 against a throwaway public org repo, as an org owner,
with `PUT /repos/{owner}/{repo}/pulls/{n}/merge` and `sha` set. That is the
call `merge_pull_request` makes (github-mcp-server v1.12.2,
`pkg/github/pullrequests.go`).

| Setup on `main` | `mergeable_state` | GraphQL `mergeQueue` | `protected` | Merge result |
|---|---|---|---|---|
| Repo ruleset `merge_queue`, empty bypass list | `clean` | non-null | `true` | 405 `Repository rule violations found` / `Changes must be made through the merge queue` |
| Same ruleset, admin role bypass `always` | `clean` | non-null | `true` | 200, merged, queue skipped |
| Classic "Require merge queue", admins not included | `clean` | non-null | `true` | 200, merged, queue skipped |
| Same, admins included (`enforce_admins`) | `clean` | non-null | `true` | 405 `Changes must be made through the merge queue` |
| No protection | `clean` | `null` | `false` | 200, merged |

`rules/branches` returned `[]` under classic protection in both classic
rows. An org-level ruleset with a `merge_queue` rule was rejected with a
422. In GitHub's REST schema, for both github.com and GHEC, `merge_queue` is
a valid rule only in repository rulesets, not org or enterprise ones.

Sources:

- GitHub Docs, [Merging a pull request with a merge queue](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request-with-a-merge-queue)
  says administrators can merge directly, bypassing branch protections,
  "if allowed by branch protection settings". It also says `gh pr merge`
  adds the PR to the queue on a branch that requires one.
- GitHub REST, [Get rules for a branch](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch)
  describes returning active ruleset rules. It doesn't mention classic
  protection.
- GitHub REST, [List branches](https://docs.github.com/en/rest/branches/branches#list-branches):
  `protected` covers "branch protections or rulesets".
- github-mcp-server v1.12.2: `governance` isn't a default toolset
  (`pkg/github/tools.go`). The remote-server headers are in
  `docs/remote-server.md`, and `--toolsets` and `GITHUB_TOOLSETS` are in the
  README.
- Claude Code docs, [cloud environments](https://code.claude.com/docs/en/cloud-environments)
  say cloud sessions ship built-in GitHub tools. The docs don't say whether
  their toolsets can be changed.

### Evals

- `session-mcp-no-gh.md` (eval 4) now returns `main` unprotected from
  `list_branches`. A new check requires no merge-queue question.
- `session-mcp-ask-queue.md` (eval 5): `main` is protected and there's no
  `governance`. The run must ask before merging, recommend neither answer,
  then merge with `expectedHeadSha`.
- `session-mcp-queue-refused.md` (eval 6): the user says there's no queue,
  but GitHub returns the 405. The run must call `merge_pull_request` once,
  report the PR for the user to enqueue, and not archive.
- The README's full-benchmark count goes from 420 to 480 runs.

## [v0.3.0] - 2026-09-27

`just-finish-it` now works without `gh`, through the GitHub MCP server.
`cleanup` now recognizes a false "unpushed commits" count from a harness
Stop hook. No benchmark was re-run for this release, to save plan usage.
The v0.2.0 numbers below were measured before these changes. The two new
evals have been checked against synthetic good and bad responses
only, not against live model runs. Re-grading all 180 stored v0.2.0 runs
of `cleanup` and `just-finish-it` with the updated grader gave identical
scores.

### Added

- **`just-finish-it` over the GitHub MCP server.** It uses `gh` when that
  exists and is authenticated. Otherwise it uses the GitHub MCP tools
  (`mcp__github__*`), which cloud sessions often have instead. If neither
  exists, it pushes and reports.
  - A mapping table gives the MCP call for every `gh` call the skill
    makes. It was checked against github-mcp-server v1.12.2's own tool
    schemas.
  - Every safety rule is the same on both transports: merge only with all
    checks green, the PR mergeable and clean, no changes requested, and
    the head SHA unchanged. It never uses admin, auto-merge or
    force-push.
  - Before merging, it re-reads the PR's head SHA and passes it as
    `expectedHeadSha`. If a server's `merge_pull_request` lacks that
    parameter, the report says the re-read leaves a check-then-act race
    that `gh`'s `--match-head-commit` doesn't have.
  - The MCP server exposes neither a repo's allowed merge methods nor its
    auto-delete setting. Unless the project's docs name a merge method,
    the skill asks for one. After a merge, it checks with
    `git ls-remote` whether the branch was auto-deleted. If not, the
    branch goes on "Still to do" with `git push origin --delete <branch>`.
  - The merge-queue check needs `repository_ruleset_read`, which is in the
    server's `governance` toolset, off by default. Without it, the queue
    state is unknown, so the PR stays pending with "couldn't verify merge
    queue". It is never merged blind.
- **`cleanup` and Stop-hook unpushed counts.** Some Stop hooks compare
  `HEAD` with `origin/<branch>` only, so they also count commits that
  another remote ref already holds. Step 1 now checks with
  `git rev-list HEAD --not --remotes --count`, reports "nothing at risk"
  when that is 0, and never pushes, resets or moves the branch to quiet
  the hook.
- **Evals.** One new seed per skill, with grader checks:
  - `session-mcp-no-gh.md`: MCP calls in order, and a head-SHA re-read
    right before the merge.
  - `session-hook-false-unpushed.md`: no push or reset, and the report
    explains the count.

  The README's full-benchmark count goes from 360 to 420 runs.

### Changed

- `just-finish-it`'s `compatibility` field, the README notes and its
  Lifecycle section now name the GitHub MCP server. The Lifecycle section
  now says to re-verify the skill when the MCP server's tool surface
  changes.

## [v0.2.0] - 2026-09-27

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
  - It no longer triggers on the bare word "cleanup", and its description
    says it isn't for cleaning up code. The 20-query trigger set for the
    description optimizer is in `skills/cleanup/evals/trigger_eval_set.json`.
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

[Unreleased]: https://github.com/EONRaider/simplicity/compare/v0.5.0...HEAD
[v0.5.0]: https://github.com/EONRaider/simplicity/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/EONRaider/simplicity/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/EONRaider/simplicity/compare/v0.2.0...v0.3.0
[v0.2.0]: https://github.com/EONRaider/simplicity/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/EONRaider/simplicity/releases/tag/v0.1.0
