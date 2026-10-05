# Changelog

All notable changes to simplicity are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
follows [Semantic Versioning](https://semver.org/). Version headers here match the
repo's git tags, which follow GitHub's `vX.Y.Z` convention.

## [v0.9.0] - Unreleased

A new command, `/simplicity:shift-session`, hands a session's work to a
fresh child session before the context window bloats, and a plugin hook
suggests it once context use reaches a threshold.

### Added

- **`/simplicity:shift-session [--pr]`.** One shift runs six steps:
  1. **Commits and pushes the work.** It keeps `just-finish-it`'s rules:
     - it never pushes the default branch, and work found there moves to
       a new `shift/<topic>` branch;
     - it never force-pushes;
     - it never stages a file holding a secret;
     - it holds back any branch whose `git diff origin/<default>...<branch>`
       holds one, scanned after the handoff commit.
     It opens a PR only with `--pr`.
  2. **Updates every tracker it finds.** That's the tracker CLAUDE.md
     names, Jira (through the Atlassian MCP), GitHub issues and PRs, the
     task list, and memory files. It skips any that aren't there and says
     so.
  3. **Writes a self-contained handoff prompt.**
  4. **Starts a child session titled "<topic> -> Part N".**
  5. **Renames this session "<topic> -> Handed Off".**
  6. **Runs `/simplicity:cleanup` and archives this session**, or leaves
     it open when anything is pending.
  The title format overrides `rename-session`'s rules for these two
  titles only.
- **How the child starts, by UI:**

  | UI | How | Why |
  |---|---|---|
  | Desktop app, when it offers `start_session` or `hand_off_to_session` | Automatically | The app's own tool descriptions refer to these tools, so some builds have them |
  | Desktop app 2.9939.4 / Claude Code 2.1.284 | A `spawn_task` chip, started with one click | A direct ToolSearch for both tools found neither |
  | CLI, IDE extensions, web without session tools | The handoff prompt is printed, with a suggested `claude "<prompt>"` | No session tools exist there |

  Tried and rejected for the desktop app:
  - `run_scheduled_task` starts a session without a click, but it leaves
    a stored routine behind and runs unattended, where renaming is
    declined.
  - `run_in_terminal` takes one line of ASCII only, and starts a CLI
    session.
  - `move_to_cloud` moves this conversation instead of starting a fresh
    one.
- **Two deliberate departures from a literal reading:**
  - **With a chip, the parent doesn't archive itself.** Archiving a
    session removes its unclicked chip (tested, see Evidence), which would
    lose the handoff. Instead, the handoff's last line asks the child to
    archive the parent once it runs, and the app asks you to approve.
  - **Work on the default branch moves to `shift/<topic>`** rather than
    staying uncommitted, so a child in a fresh worktree can see it. The
    local default branch's extra commits are listed as pending.
- **The context hook**, on `UserPromptSubmit` and `PostToolUse`:
  - **Measurement.** No hook input carries context usage or the model's
    window (checked on Claude Code 2.1.284). So the hook reads the
    transcript's last main-chain assistant usage, the way Claude Code
    counts it: the last non-advisor pass, input plus cache plus output
    tokens. The window comes from the model id.
  - **Firing.** It fires once per 10 points from `SIMPLICITY_SHIFT_THRESHOLD`
    (default 60).
  - **Silence.** It stays silent:
    - below the threshold;
    - in subagents;
    - on the shift command itself;
    - after a handoff;
    - when the threshold is `0` or `off`.
  - **Overrides and failure.** `SIMPLICITY_CONTEXT_WINDOW` overrides the
    window. It needs `python3` on PATH and always exits 0.
  - **Window table.** The 1M ids verified are `claude-opus-5-5` (the
    app's usage tool) and `claude-sonnet-5`, `claude-opus-5`,
    `claude-opus-4-8` (local transcripts above 200,000 tokens). The Fable
    ids and `claude-sonnet-5-5` are listed as 1M unverified.
  - **Source.** The measurement is ported from the maintainer's own
    context-pressure hook.
- **Model invocation stays on.** `disable-model-invocation` would block
  the hook path. A run the hook starts asks once with `AskUserQuestion`
  before it commits, pushes, writes to a tracker or starts anything, then
  runs to the end. Typing the command, or naming it mid-sentence, is the
  go-ahead.
- **Tests and evals.**
  - 57 unit tests for the hook, against a throwaway home directory.
  - 11 seeded evals.
  - A 10-query trigger set.

### Changed

- **`cleanup`** gains a carve-out for `shift-session`, modeled on the
  `just-finish-it` one. Nothing else in it changed.
- **Grader.** `git_argv` now reads a push logged as
  `{"action": "git", "args": "git ..."}`. Comparing main's grader with
  this one on all 8,795 existing check results, 12 change, all from fail
  to pass, and none the other way. All 12 are real pushes the old grader
  missed: 10 in `just-finish-it` eval 1, 2 in eval 4.
- **`run_evals.py`** takes a per-eval `answer`, so an eval can decline an
  `AskUserQuestion`.

### Evidence

- **Unit tests and linters:** pytest (102 tests across the three helpers),
  ruff, `mypy --strict`, `claude plugin validate .`, and CI's
  manifest/evals check, all run locally.
- **Live hook check, 1 run (haiku, `--plugin-dir`, threshold 1%):** the
  model received the hook's text verbatim.
- **Evals, with-skill only, one run per cell.**
  - **Round 1:** 27 runs, 9 evals, on the first draft and the first
    grader: Haiku 45/57, Sonnet 54/57, Opus 51/57. An adversarial review
    of the plan and that round found grader bugs, including three false
    passes in eval 6, and skill gaps. Both were fixed before round 2.
  - **Round 2:** 39 runs, 11 evals. Evals 4 and 10 were rerun after their
    fake keys were replaced, and eval 6 after its seed was fixed.

  | Model | Round 2 |
  |---|---|
  | claude-haiku-4-5 | 60/72 |
  | claude-sonnet-5 | 72/72 |
  | claude-opus-5 | 71/72 |

  - **Opus's miss (eval 9).** It wrote and committed the tests the user
    had asked for, then loaded the skill and asked before pushing. The
    skill itself committed nothing before the answer, but the hook asks
    for the shift before any other work.
  - **Haiku's misses:**
    - It didn't act on the hook's message (evals 9 and 11).
    - It printed the fake `.env` value in its pending list (eval 10).
      The skill forbids this.
    - It left out the chip's archive line (eval 2).
    - It skipped archiving after an automatic start (eval 5).
    - It logged the parent rename in a form the grader can't read
      (eval 7).
    - It had no pending list (eval 10).
  - **Seeds.** Five seeds offer only the chip, as this desktop build
    does. Two keep `start_session` to test the automatic path.
  - **Trigger set,** with SkillArtisan's description optimizer, measuring
    only (3 runs per query, `sonnet`): 9/10.
    - The miss is the bare `/simplicity:shift-session`. The optimizer
      installs the skill on its own, so Claude Code rejects the command
      as unknown before the model sees it.
    - The first measurement had the paraphrase "hand this off to a new
      session" trigger 3/3. The description now names it as not a
      request for the skill, so that query passes partly by construction.
      The other paraphrases held without help.
- **Security scan:** clean for `shift-session` and `cleanup`, with
  gitleaks 8.21.2. The two secret seeds use fake low-entropy values, since
  key-shaped ones trip the scan.

- **Desktop app 2.9939.4 (Claude Code 2.1.284), 2026-10-05: two live
  tests in a throwaway repo** whose `origin` was a local bare repo. The
  plugin was loaded from a local marketplace through that repo's project
  settings.
  - **Chip survival.** A session created a chip (`spawn_task` returned
    its task id), then archived itself. Afterwards there was no chip to
    click. That's why the parent leaves archiving to the child.
  - **A full shift.** The user typed `/simplicity:shift-session` in a
    session with an uncommitted file on `main`, and every step ran:
    - it moved the work to `shift/draft-sandbox-release-notes`,
      committed it and pushed it, with `main` untouched and no PR;
    - it skipped all five trackers and said why;
    - it created the Part 2 chip;
    - it renamed itself "… -> Handed Off" and wrote the handed-off marker;
    - it ran `/simplicity:cleanup` and stayed open for the chip.
    The child renamed itself "… -> Part 2" and archived the parent.
  - **Three fixes came out of the full shift:**
    - **Archive timing.** The child's first archive was refused because
      the parent was still finishing its turn. The archive line now has
      the child wait about 30 seconds (a background `sleep`), then retry,
      up to three tries, before handing it back to the user.
    - **Escaped titles.** The app stores `->` in titles HTML-escaped as
      `-&gt;`. Step 3 now reads `-&gt;` and `→` as `->`, so Part N still
      counts up. The chip list showed the title as "-' Part 2"; the
      session title itself was right.
    - **Step 0 arguments.** Claude Code substitutes `$ARGUMENTS` in the
      skill text, which turned step 0's check into "`` doesn't hold
      `--auto`". Step 0 now quotes the arguments it was given.
  - **Not repeated** after these three wording fixes: the shift itself and the evals.

Not run: the baseline configuration, the trigger set on Haiku and Opus,
the hook-triggered path in the desktop app, and the automatic-start path,
since this app build has no automatic start tool.

## [v0.8.1] - 2026-10-05

The five skills v0.8.0 changed ship current security-scan markers again.

### Fixed

- **Stale `.security-scan-passed` markers.** v0.8.0 edited `what-now`,
  `just-say-it`, `just-ask`, `promptfy` and `rename-session` without
  re-running SkillArtisan's security scan, so each marker's hash no longer
  matched the skill's files and a SkillArtisan audit failed
  `security-scan-marker-current` on all five. A clean scan with gitleaks
  8.21.2 rewrote them.

### Changed

- **The description sentence opens "Use when".** It read "Use it only
  when", which the audit's trigger-framing check doesn't recognise. The
  meaning is unchanged: Claude uses a skill when the user names it, and
  never on a paraphrase.
- **`RELEASING.md` gains a re-scan step** before the changelog is dated,
  so a release can't ship stale markers again.

### Evidence

- **Audit:** SkillArtisan's `audit.py report` on all seven skills passes
  `security-scan-marker-current` and `description-pushy-imperative`.
- **Trigger sets:** re-measured with the reworded descriptions, three runs
  per query on the `sonnet` alias: 50 of 50 queries passed, as in v0.8.0.

Not re-run: the eval suite. Only the opening words of one description
sentence changed in each skill, and the trigger sets cover that sentence.

## [v0.8.0] - 2026-10-05

A command named mid-sentence now runs. Claude Code runs a typed command
only when it starts the message; anywhere else it reaches Claude as plain
text. Five skills can now be loaded by Claude when you name them that way.

### Fixed

- **A command named mid-sentence was reported as not installed.** "Can you
  run `/simplicity:just-ask`?" isn't expanded, and Claude couldn't load a
  skill marked `disable-model-invocation`. It also couldn't see one in its
  skill list, so it told the user the plugin might not be installed.
  `what-now`, `just-say-it`, `just-ask`, `promptfy` and `rename-session`
  drop the flag. Found in a session that asked for two of them
  mid-sentence and was told neither existed.
- **`promptfy` with no argument could rewrite its own request.** Loaded
  from "can you `/simplicity:promptfy` that?", the helper would have
  returned that message as the prompt to rewrite. `last-prompt.py` now
  skips any typed message that names `/promptfy` or
  `/simplicity:promptfy`. Paths and longer names such as `/promptfy-all`
  don't match. Tests cover both cases, and the new ones failed before the
  fix.

### Changed

- **The five skills still fire only when named.** Each description ends
  with one sentence: Claude uses it when you name it, mid-sentence
  included, and never on a paraphrase of what it does.
- **`just-finish-it` keeps `disable-model-invocation`.** It pushes, merges
  and archives, so it runs only when typed as the first thing in a
  message. The README says what to do when Claude says it isn't installed.
- **Named mid-sentence, `promptfy` and `rename-session` ask before they
  load.** Both declare `allowed-tools` for their helper scripts, and a
  skill Claude loads itself asks first when it does. The helper call may
  ask too. Typed as the command, neither asks.
- **Evals.** Each of the five skills gets one eval that names it
  mid-sentence. It reuses the first eval's seed and checks and adds one:
  the skill is loaded through the `Skill` tool. Each also gets a 10-query
  trigger set. With-skill runs pass `--allowedTools Skill`, standing in
  for the user approving the load. The grader drops real `Skill` calls
  from the response before its format checks, because loading a skill
  isn't output the user sees.

### Evidence

- **Headless, before and after:** "can you run `/simplicity:what-now` ?"
  and "please do `/simplicity:just-say-it` for that", with `--plugin-dir`.
  Before, both were answered with "isn't in the skills available". After,
  both loaded the skill. "ok, now `/simplicity:just-finish-it` please"
  still didn't run, and "where are we?" loaded nothing.
- **Evals:** the 19 evals of the five skills, with the skill only, once
  per model on the harness's `haiku`, `sonnet` and `opus` aliases (57
  runs, `--runs 1`). The two mid-sentence evals the first harness blocked
  were re-run after the `--allowedTools` fix.

| Evals | Haiku | Sonnet | Opus | Total |
|---|---|---|---|---|
| existing (typed command) | 81/85 | 85/85 | 85/85 | 251/255 |
| new (named mid-sentence) | 40/41 | 41/41 | 41/41 | 122/123 |

  Haiku's misses on the existing evals are the ones each skill's Lifecycle
  section already records, or a label over four words in `what-now`. Its
  mid-sentence miss: `what-now` numbered the Next list without bold
  labels.
- **Trigger sets:** SkillArtisan's description optimizer, measuring only
  (`--max-iterations 1 --holdout 0`), three runs per query on the `sonnet`
  alias: 50 of 50 queries passed. Every named form triggered, and no
  paraphrase or other skill's name did. The optimizer loads a skill on its
  own, not inside the plugin, so the headless runs above are the
  end-to-end check.

Not run: the baseline configuration, and the trigger sets on Haiku and
Opus. Not checked: the permission prompts in the desktop app.

## [v0.7.2] - 2026-10-03

`rename-session` now works in the desktop app, and its titles are no
longer in ALL CAPS.

### Fixed

- **`rename-session` did nothing visible in the desktop app.** The app
  keeps its own title for each session and never reads the `custom-title`
  records the helper writes, so the helper reported success while the
  sidebar and header kept the old title. The skill now renames through the
  app's session title tool when one exists, and runs the helper only
  elsewhere. Found by running the skill on the session that released it.

### Changed

- **Titles are in sentence case**, like the app's own: "Checkout retry
  bug", not "CHECKOUT RETRY BUG". Names and acronyms keep their own
  capitals. This departs from voidharbor's ALL CAPS rule; the skill's
  Credits section says so.
- The evals and `scripts/grade.py` follow: a title must not be all caps,
  and a passed topic is matched in any capitalisation except ALL CAPS.

### Evidence

- **In the desktop app, one session:** the helper wrote both records and
  the app's title didn't change. The session title tool changed it at
  once, as the app's own session metadata confirmed.
- **Evals:** the two `rename-session` evals, once per model, with and
  without the skill (12 runs, `--runs 1`, on claude-haiku-4-5,
  claude-sonnet-5 and claude-opus-5), graded with this release's grader.

| Config | Haiku | Sonnet | Opus | Total |
|---|---|---|---|---|
| with skill | 5/6 | 6/6 | 6/6 | 17/18 |
| without | 4/6 | 4/6 | 5/6 | 13/18 |

  Every with-skill title was 2 to 5 words in sentence case. Haiku's miss:
  its closing line didn't name the new title. Without the skill, no model
  kept the title to 5 words. The gap to the baseline is smaller than in
  v0.7.0 because models don't write ALL CAPS titles unprompted, and the
  old grader failed them for that.

In the eval harness the session tools are only described, not visible,
and the with-skill runs split: 2 of 6 logged the session title tool and 4
ran the helper. The evals count either as a rename, so they don't show
that the skill picks the tool in the app.

Not checked: the fixed skill end to end in the desktop app. It loads only
after a restart, so the tool path was exercised by hand, not through the
skill. Whether the tool exists in cloud sessions is also unverified.

## [v0.7.1] - 2026-10-03

Fixes what the v0.7.0 benchmark found in `promptfy`, and stops both new
skills from asking permission to run their own helper.

### Changed

- **`promptfy` leaves a tight prompt alone.** Before it calls the
  subagent, it now checks whether the prompt already names verified paths,
  a finish line and its constraints. If so it prints the prompt back as
  typed and changes only what the repo proved wrong. In v0.7.0 every model
  expanded such a prompt.
- **`promptfy` labels its recommendation.** The first option of each
  `AskUserQuestion` question now ends in "(Recommended)", so you can see
  which option is recommended and not only that one is first.
- **No permission prompt for the helpers.** `rename-session` and
  `promptfy` declare `allowed-tools` for their own script and nothing
  else. Without it, `claude -p` denied the rename outright; with it, the
  same call ran with no denial.

The first two changes depart from voidharbor's text. Each skill's Credits
section lists them.

### Evidence

The with-skill evals for both skills, run once per model (15 runs,
`--runs 1`, on claude-haiku-4-5, claude-sonnet-5 and claude-opus-5). No
baseline was rerun: the baseline prompts and the grader didn't change.

| Skill | Haiku | Sonnet | Opus | Total | v0.7.0 total |
|---|---|---|---|---|---|
| `rename-session` | 6/6 | 6/6 | 6/6 | 18/18 | 18/18 |
| `promptfy` | 11/13 | 13/13 | 13/13 | 37/39 | 31/39 |

- The tight-prompt eval went from 5/9 to 9/9.
- The two-footers eval went from 8/12 to 11/12. Sonnet and Opus now label
  the recommended option.
- Two misses remain, both on Haiku. It quoted the project's notes in a
  blockquote on the destructive-prompt eval, which passed 6/6 in v0.7.0.
  And it again wrote both footers into the prompt instead of asking.

One run per cell, so a single miss or pass may be noise.

## [v0.7.0] - 2026-10-03

Two new commands, both adapted from
[voidharbor/claude-plugins](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b) (MIT): `/simplicity:rename-session`
names a session after what it was actually about, and `/simplicity:promptfy`
rewrites a prompt into a stronger one without running it.

### Added

- **`/simplicity:rename-session [topic]`.** Renames the current session to
  a 2 to 5 word ALL CAPS title that names where the work ended up, not the
  first message. A topic passed as an argument is used instead.
- **`/simplicity:promptfy [prompt]`.** Rewrites a prompt and prints it in a
  code block with a short "what changed" list. It never runs the prompt.
  - It checks the paths the prompt names against the repo first.
  - One subagent on the most capable model does the rewrite.
  - Anything it couldn't verify comes back through `AskUserQuestion`.
  - With no argument it rewrites the last prompt typed in the session.
- **Credit.** Both are the work of [voidharbor](https://github.com/voidharbor),
  taken from [voidharbor/claude-plugins@397b270](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b):
  [`rename-session`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/rename-session) and
  [`ultra-prompt`](https://github.com/voidharbor/claude-plugins/tree/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt). `ultra-prompt` ships here renamed
  to `promptfy`. Each skill directory carries voidharbor's MIT `LICENSE`.
- **What changed from upstream.**
  - Both commands became skills (`skills/<name>/SKILL.md` with `scripts/`
    beside it), and both are user-invoked only.
  - The command text is upstream's. Only the command name and the script
    paths changed, and each skill gained Lifecycle and Credits sections.
  - `rename-session.py` and `last-prompt.py` were restructured with the
    same behavior: pathlib, type hints, docstrings, a `main(argv) -> int`
    entry point. Errors now go to stderr with a nonzero exit.
  - `last-prompt.py` skips `/promptfy` and `/simplicity:promptfy` instead
    of upstream's own commands, so a bare `/simplicity:promptfy` doesn't
    rewrite its own name.
- **Unit tests.** 38 pytest cases for the two helpers, run against a
  throwaway home directory:
  `pytest skills/rename-session/tests skills/promptfy/tests -q`.
- **Evals.** Five seeded sessions, wired into `scripts/run_evals.py` and
  `scripts/grade.py`:
  - `rename-session`: a session that pivots from a flaky test to a CI
    matrix migration, and a rename with the topic passed as an argument;
  - `promptfy`: a destructive prompt that must not be run, a bare call
    where the repo has two footers, and a prompt that is already tight.

- **Project scaffolding**, matching EONRaider's other plugin repos:
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull
  request templates, `CODEOWNERS`, Dependabot for GitHub Actions, and a CI
  workflow. CI lints and type-checks the two helpers, runs their unit
  tests on Linux and macOS, and checks that every eval has a seed file
  and one grader check per expectation. It runs no evals.

### Evidence

A single-run benchmark, not the 5-run smoke preset earlier releases used:
each of the five new evals ran once per model, with and without the skill
(30 runs, `--runs 1`, on claude-haiku-4-5, claude-sonnet-5 and
claude-opus-5). One run per cell can't separate a real miss from noise, so
read these as a first look.

| Skill | Config | Haiku | Sonnet | Opus | Total |
|---|---|---|---|---|---|
| `rename-session` | with skill | 6/6 | 6/6 | 6/6 | 18/18 |
| `rename-session` | without | 3/6 | 4/6 | 3/6 | 10/18 |
| `promptfy` | with skill | 10/13 | 10/13 | 11/13 | 31/39 |
| `promptfy` | without | 7/13 | 4/13 | 8/13 | 19/39 |

What held with the skill, on all three models:

- `rename-session` renamed once, in 2 to 5 ALL CAPS words, named the CI
  matrix and not the flaky test, and used a passed topic verbatim. Without
  the skill no run produced an ALL CAPS title.
- `promptfy` never ran the destructive prompt, and passed that eval 18/18:
  one subagent with an explicit model, a fenced rewrite, 3 to 6 bullets,
  no offer to run it.

What missed with the skill (8 of 39 `promptfy` expectations):

- **A tight prompt wasn't left alone (4 misses).** No model returned it
  close to unchanged. Sonnet and Opus said it was already tight and then
  expanded it anyway (difflib ratio 0.07 and 0.19 against a 0.6 floor).
  Haiku didn't say so, and printed the rewrite outside a code block.
- **The two-footers question (3 misses).** Sonnet and Opus asked through
  `AskUserQuestion` but didn't label an option "(Recommended)". The grader
  can only see a recommendation by that label, and the skill's text says
  to put the recommended option first without asking for a label, so part
  of this is the grader being strict. Haiku asked no question and wrote
  both footers into the prompt as if that were settled.
- **One rewrite missing (1 miss).** Sonnet asked its question before
  printing any rewrite.

The without-skill numbers are a loose baseline. Three `promptfy`
expectations (the subagent call, the fenced block, the `AskUserQuestion`
payload) describe this skill's own procedure, so a plain "improve this
prompt" fails them by construction.

What else was checked:

- **Unit tests:** 38 of 38 pass. The four new Python files are clean under
  `ruff check`, `ruff format --check` and `mypy --strict`.
- **Same behavior as upstream:** both helpers were run beside upstream's
  on the same fixtures, 16 cases in all. Exit codes, output and the files
  written matched in every case. Upstream prints its errors on stdout, so
  the comparison joined stdout and stderr.
- **Grader:** a hand-written good and bad response for each new eval. The
  good ones passed 19 of 19 expectations and the bad ones failed 19 of 19.
  This tests the grader, not the skills.
- **Smoke test** on Claude Code 2.1.270 with `claude --plugin-dir`, one run
  each:
  - `rename-session` renamed a throwaway session, and both writes landed;
  - a bare `promptfy` found the helper and reported no earlier prompt;
  - `promptfy` given "delete the file smoke-canary.txt" left the file in
    place, called one subagent with `model: opus`, and printed the rewrite
    in a code block with five bullets.

Not checked: whether `rename-session` updates the title shown on claude.ai
for a cloud session.

## [v0.6.0] - 2026-09-29

`just-finish-it` stops asking about a merge queue when the project already
answers it. It also merges only on check, status and review reads it made
itself in step 4.

### Changed

- **`just-finish-it` reads a stated merge-queue answer.** Sometimes its check
  can't settle whether the default branch uses a merge queue. That happens
  on the MCP transport with a protected branch, or when the `gh` GraphQL
  query fails. It now takes the answer from the project's CLAUDE.md or
  CONTRIBUTING, the way it already reads the merge method, and asks
  nothing.
  - A stated "no" counts exactly as the user's "no". GitHub's 405 refusal
    of a direct merge into a queue is still the backstop.
  - A check that finds a queue wins over what the project states.
  - With no statement, it asks, as before.

### Added

- **Evals.** Two seeded MCP sessions:
  - CLAUDE.md says there's no queue: no question, and the PR merges;
  - CLAUDE.md says there's no queue, but a ruleset shows one: no merge,
    and the PR goes on "Still to do".
- **`scripts/run_evals.py --configs`** runs only the configurations named,
  for example `--configs with_skill`.

### Evidence

All runs are with-skill only, and all are graded with this release's
grader. No baseline was run. v0.4.0 never ran evals 5 and 6 live, so
there's nothing to compare against.

**First pass: 3 runs per model on evals 4–8 (30 runs), before the
check-read fix below.**

| Eval | Sonnet | Opus |
|---|---|---|
| 4: unprotected, no question | 30/30 | 28/30 |
| 5: protected, asks, merges | 23/24 | 22/24 |
| 6: protected, asks, 405 | 20/21 | 19/21 |
| 7: CLAUDE.md says no queue | 17/21 | 21/21 |
| 8: CLAUDE.md says no, ruleset says yes | 20/21 | 21/21 |

Totals: 221/234 expectations (94.4%). The two new behaviors held in every
run:

- eval 7 asked no merge-queue question (6/6);
- eval 8 never merged #44 (6/6).

The misses:

- **Malformed questions.** Two Opus runs of evals 5 and 6 did ask, but
  wrote `AskUserQuestion` JSON with a brace missing, so the grader missed
  the question.
- **A skipped question.** One Sonnet run of eval 6 treated the seed's
  scripted answer as already given, and never asked.
- **Skipped reads.** One Sonnet run of eval 7 merged without calling
  `get_check_runs`, `get_status` or `get_reviews`. It took the results
  from the seed's preloaded output. This led to the check-read fix below.
- **Other misses.** Three Sonnet runs didn't archive, one of them the
  eval 7 run above. One eval 8 run left a pending item without a next
  step. Two Opus runs of eval 4 did push without force, but logged it as a
  `git` action whose args start with `git`, a form the grader doesn't
  parse.

**After the check-read fix: 5 Sonnet runs each on evals 4, 5 and 7 (15
runs).** The score is 122/125 expectations. Every run read check runs,
status and reviews before merging (15/15, against 23/24 merging runs in
the first pass).

- Fifteen runs are too few to show the skip rate changed. They show only
  that it didn't recur.
- Two eval 7 runs didn't archive.
- One eval 4 run wrote the remote-branch delete it was meant to leave to
  the user as an action block in its report.

### Fixed

- **`just-finish-it` merges only on reads made in step 4.** Step 4 now
  says each merge condition comes only from reads made in that step, after
  the recorded push. A result seen earlier in the session, or one the
  model expects a call to return, doesn't count. On the MCP path,
  `get_check_runs`, `get_status` and `get_reviews` are all required before
  `merge_pull_request`.
- **Grader.**
  - A new check requires those three reads before the merge, on evals 5
    and 7.
  - A fenced block holding several JSON actions, one per line, used to
    be dropped whole. Now each action counts.
  - Re-grading the 384 stored `just-finish-it` and `cleanup` runs from
    earlier releases changed 3 of them, all upward. Each had several
    actions in one block.
- **README.** It said the eval harness defaults to 570 runs. `--runs`
  defaults to 1 (126 runs with this release's two new evals); 630 is the
  `--runs 5` smoke preset. The README now also gives `just-finish-it`'s
  argument hint as SKILL.md does, says what `cleanup` skips in the CLI,
  and points to `cleanup`'s trigger set.

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

[Unreleased]: https://github.com/EONRaider/simplicity/compare/v0.9.0...HEAD
[v0.9.0]: https://github.com/EONRaider/simplicity/compare/v0.8.1...v0.9.0
[v0.8.1]: https://github.com/EONRaider/simplicity/compare/v0.8.0...v0.8.1
[v0.8.0]: https://github.com/EONRaider/simplicity/compare/v0.7.2...v0.8.0
[v0.7.2]: https://github.com/EONRaider/simplicity/compare/v0.7.1...v0.7.2
[v0.7.1]: https://github.com/EONRaider/simplicity/compare/v0.7.0...v0.7.1
[v0.7.0]: https://github.com/EONRaider/simplicity/compare/v0.6.0...v0.7.0
[v0.6.0]: https://github.com/EONRaider/simplicity/compare/v0.5.0...v0.6.0
[v0.5.0]: https://github.com/EONRaider/simplicity/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/EONRaider/simplicity/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/EONRaider/simplicity/compare/v0.2.0...v0.3.0
[v0.2.0]: https://github.com/EONRaider/simplicity/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/EONRaider/simplicity/releases/tag/v0.1.0
