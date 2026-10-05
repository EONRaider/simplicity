---
name: just-ask
description: Sweeps the current session (the user's messages, the plan, the task list, and earlier responses) for every question that is still genuinely open, drops anything answerable without the user, and asks the rest through AskUserQuestion in rounds of up to four, each option carrying a recommendation and the reasoning behind it. Invoked by the user as /simplicity:just-ask, optionally with a focus such as "/simplicity:just-ask database". Use it only when the user names /simplicity:just-ask or asks for just-ask by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[optional focus]"
license: MIT (see plugin root LICENSE)
compatibility: Built for Claude Code, where the AskUserQuestion tool exists. On surfaces without it, falls back to a numbered markdown list carrying the same recommendations and reasoning.
---

# just-ask

Collect every decision the user still owes this session and put them in front of the user in one structured pass. The questions must already be open somewhere in the session. The job is to gather them, not to invent new ones or stress-test the plan.

If `$ARGUMENTS` is non-empty, treat it as a focus: sweep only for questions related to it.

## 1. Sweep

Read back through the whole session and list every candidate question. Look in:

- **The user's messages.** Look for requests with an ambiguous scope, and for things the user said "we'll decide later" about.
- **The plan file**, if plan mode wrote one, and **the task list**, if one exists. Look for TBDs, "open questions" sections, and steps that depend on an unmade choice.
- **Your own earlier responses.** These are where most open questions hide. Look for "I'm not sure whether…", "I'll assume X for now", TODOs left in code you wrote, placeholders, and trade-offs you described without resolving.

Count a silent assumption ("I'll assume UTC unless you say otherwise") as open until the user has confirmed it. Assumptions are the questions users most often wish they'd been asked.

## 2. Filter

Drop a candidate when any of these hold:

- **The session already answers it.** For example, the user replied, or a later message settled it.
- **The code, config or docs answer it**, either as shown in the session or found with a quick read or grep. For example, a `requires-python` line settles "which Python version?", and a `devDependencies` entry settles "which test runner?". Check instead of asking. The user shouldn't have to tell you what's in their own repository.
- **An established project convention or an obvious default covers it**, and getting it wrong would be cheap to fix. Just follow the convention. If it's worth flagging, mention it in the closing summary.

This filter only removes questions of **fact** (what the repo already uses or already says) and cheap conventions. A choice about **behavior** stays open even when one option is the industry standard. That covers what users or callers experience, security trade-offs, data handling, and anything you explicitly listed as undecided. For those, ask, and make the standard option your recommendation. Never settle them silently as "standard practice".

Merge duplicates and near-duplicates into one question. If the user answered part of a compound question, keep only the unanswered part.

If nothing survives, reply with exactly `No open questions.` and stop. With a focus, reply `No open questions about <focus>.` instead, and add how many open questions exist on other topics, if any. Never pad the list with invented or speculative questions to have something to ask. Next-step ideas you could offer, such as "push the commit?" or "scan other files too?", are suggestions, not open questions. Leave them out unless the user left them open. Reply with only that one line.

If more than 8 questions survive, look at the lowest-ranked ones. Where a sensible default exists, turn the question into a stated assumption instead of asking it, and list those assumptions in the closing summary so the user can overrule any of them.

## 3. Rank

Order the survivors by how much each one blocks progress. Rank highest the choices that other work depends on and the ones that are expensive to reverse. Rank lowest the nice-to-haves and the ones that are easy to change later.

## 4. Build each question

Each question must satisfy AskUserQuestion's constraints:

- **`question`**: one clear, self-contained sentence ending in `?`. The user may read it without the surrounding context.
- **`header`**: a topic tag of **12 characters or fewer, counting spaces**, such as `Format`, `Overwrite` or `Timestamps`. Count the characters before sending. For example, `Rate limit response` has 19 characters and is too long, so use `429 handling` instead.
- **`options`**: **2–4 options**, which must be distinct and mutually exclusive unless you set `multiSelect: true` for choices that can combine. If more than 4 real choices exist, offer the 4 strongest and name the rest in the last option's description. The user can still type any of them through "Other".
  - Put the option you recommend **first**, and end its `label` with ` (Recommended)`.
  - Keep each `label` to 1–5 words.
  - In each `description`, say what choosing the option means and why you would or wouldn't pick it. Name the concrete trade-off. "Simpler" is not a reason.
- **Don't add an "Other" option.** The tool adds a free-text "Other" automatically.

Recommend an option on every question. If it's truly a coin-flip, pick one anyway and say in its description that the two are close, and why.

The tool input is one object holding a `questions` array:

```json
{"questions": [{
  "question": "If the export file already exists, what should happen?",
  "header": "Overwrite",
  "multiSelect": false,
  "options": [
    {"label": "Refuse unless --force (Recommended)", "description": "Never destroys a previous export by accident; costs one extra flag on intentional re-runs."},
    {"label": "Overwrite silently", "description": "Easiest for scripted re-runs, but a mistyped path wipes an existing file with no warning."}
  ]
}]}
```

## 5. Ask in rounds

- Send **at most 4 questions per AskUserQuestion call**, most blocking first. The tool rejects a 5th, so hold any extra questions for the next round.
- Before the first call, write at most two short lines and nothing more:
  - the candidates you dropped or turned into assumptions in step 2, each with a few words on why (for example: "Settled already: Python version (pyproject says ≥3.12), Windows (you said Linux/macOS only)")
  - if more rounds follow, a one-line notice, for example: "4 of 7 open questions; a second round follows."
- After each round, apply the answers first. Then re-check the remaining questions, because an answer often settles or reshapes the next ones. Only then ask the next round.

**In plan mode**, AskUserQuestion is the right tool for requirement and approach questions. Never use it to ask whether the plan is approved or ready, because that is ExitPlanMode's job.

## 6. Fallback when AskUserQuestion is unavailable

Present the same content as markdown:

- One numbered item per question, with the header in bold.
- A lettered sub-list of its options. The first option is marked **(Recommended)**, and each option has its reasoning.

Ask the user to reply with answers like `1a, 2c`.

## 7. Close

Once every round is answered, give a short list of the decisions made, one line each. Include any conventions you followed and any assumptions you made in step 2 instead of asking. Then resume the task that was in progress. Don't wait for a separate go-ahead unless the answers changed the task's scope. If no task was in progress, stop after the summary.

## Lifecycle

**Encoded-preference, timelessness 8/10, last verified against claude-opus-5-5 (2026-09).** The procedure itself (sweep, filter, rank, recommend) is a fixed workflow choice that doesn't age with model capability. It scores 8 rather than higher because step 4 encodes AskUserQuestion's current limits: 4 questions per call, 2–4 options, and 12-character headers. Re-verify those limits whenever the tool's schema changes.
