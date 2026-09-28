---
name: what-now
description: Takes stock of the current session and reports what has been done, where the current task stands, and the next steps to finish it, as three short lists in which every item is a bold label plus one plain sentence. Invoked by the user as /simplicity:what-now.
disable-model-invocation: true
license: MIT (see plugin root LICENSE)
compatibility: Claude Code (uses the Claude Code-only disable-model-invocation field).
---

# what-now

The user wants to know where the session stands: what's done, what's happening now, and what's left. Give them a snapshot. This is a status report, not new work.

Ignore any arguments. Make no tool calls and ask no questions: the conversation is the only source. After the report, stop. Don't start on the next steps.

## Take stock

Read back through the whole session:

- The user's requests, the plan file, and the task list, if they exist.
- Your tool calls and their results.
- The compaction summary, if the session was compacted. Rebuild what was done from it.

Earlier `what-now` reports never count as work done.

The **current task** is the latest thing the user asked for that isn't finished. If everything they asked for is finished, there is no current task.

## Stay truthful

- Count something as done only if the session shows it: a command succeeded, a commit exists, a test ran green. "Should pass now" isn't proof.
- Work that was changed but never checked goes under Done marked "not yet verified", and checking it becomes a Next step.
- Anything that could have changed since you last saw it (CI, a background task, the working tree) is reported as "last seen …". Don't re-check it.

## Output

Write exactly three sections, with nothing before or after them:

```
**Done**
- **Short label** — one sentence.

**Now**
- **Short label** — one sentence.

**Next**
1. **Short label** — one sentence.
```

- **Done:** what the session finished, in the order it happened. 7 items or fewer. Merge small steps rather than drop important ones.
- **Now:** where the current task stands, in 1–3 items. Name the blocker if there is one. Add an item for a parallel task or a background job that is still running.
- **Next:** the steps that finish the current task, numbered in the order they should happen. 7 items or fewer. When the task is waiting on the user, their step comes first.

Every item in all three lists, Next steps included, is a bold label of **at most 4 words**, an em dash, and **one** sentence.

- **Plain words.** Short sentences, no hedges, no filler.
- **Keep what's actionable exact.** File paths, commands, PR numbers and names stay verbatim, in `code` where they are code.
- **Say when a step is the user's.** A step is the user's only when it needs something only they can give: a decision, an approval, a credential. Start its sentence with "You". If it's a decision, name the options and point to `/simplicity:just-ask` in the same sentence. Everything else is yours to do next.
- **Empty lists.** Nothing done yet: `- Nothing yet.` No current task: one labelled Now item such as `- **All finished** — Nothing you asked for is still open.` Nothing left: `Nothing left to do.` under Next. Never invent steps to fill a list.

## Lifecycle

**Encoded-preference, timelessness 9/10, last verified against claude-opus-5-5 (2026-09).** The three-list status format is a fixed output preference, so better models don't make it obsolete. It scores 9 rather than 10 because future models may produce tight status reports on their own, which would shrink the skill's delta. If that happens, re-check it against a baseline "where are we?".
