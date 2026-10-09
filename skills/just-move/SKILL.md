---
name: just-move
description: Prepares the current session to run unattended for as long as possible, including across usage-limit resets. Sweeps the session for open decisions (reusing just-ask) and for blockers that would stop the run partway, such as permission prompts, missing credentials or tools, disk, unwatched PRs, missing check-ins and context headroom, and asks every question up front through AskUserQuestion. After the user agrees, it fixes what it can: it subscribes to PRs, schedules a resume for after the usage limit resets with an hourly fallback that switches itself off, and writes a handoff note to the project's memory directory. It ends with a readiness report. It never commits, pushes, discards, bypasses a check, changes permission settings or messages a person. In plan mode it asks its questions and defers every fix. Invoked by the user as /simplicity:just-move, optionally with a focus such as "/simplicity:just-move migration". The everyday phrases "just move on" and "keep going without me" are not requests for this skill. Use when the user names /simplicity:just-move or asks for just-move by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[optional focus]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs AskUserQuestion; without it, the questions fall back to a numbered markdown list, as in just-ask. Reads just-ask's and shift-session's SKILL.md from the same plugin. Scheduling a resume and watching PRs use send_later, create_trigger, update_trigger and subscribe_pr_activity, which exist only in Claude Code cloud sessions; on other surfaces those blockers are reported, not fixed, and the resume prompt is printed instead.
---

# just-move

The user is about to leave this session running on its own. Find everything that would stop the run before it's finished, and settle it now, while the user is still here. Every question goes to the user in one structured pass. Every fix waits for the user's yes.

How this differs from its neighbours:

- `/simplicity:just-ask` asks the session's open questions. This skill asks them too, by following just-ask, and adds the blockers and the resume plan an unattended run needs.
- `/simplicity:call-it-a-day` pauses the work. This skill keeps it going.
- `/simplicity:shift-session` hands the work to a new session. This skill keeps it in this one.

Like every simplicity skill it is conservative. It never commits, pushes, discards, stashes, bypasses a check, changes permission settings or messages a person on its own. When unsure, it reports and asks. Never repeat a secret's value anywhere, including the questions, the handoff note and the report.

## 0. Before you start

**Read just-ask.** Read `${CLAUDE_SKILL_DIR}/../just-ask/SKILL.md` with the Read tool now. Don't load it with the Skill tool, which would start a separate run. Wherever a step below says "just-ask's step N", follow that step as it's written there, with the changes listed here. Where the two disagree, this file wins.

**Focus.** The arguments this run was given: "$ARGUMENTS". When they're non-empty, treat them as a focus: sweep only the work, decisions and blockers related to it. When they're empty, check the whole session.

**Plan mode.** If the session is in plan mode, still run steps 1 to 4: sweeping and asking are safe there, as just-ask's step 5 says. Skip step 5. Every fix that changes something outside the conversation counts as an action and is deferred: a trigger, a PR subscription, the handoff note. List each deferred fix in the report, and say that running `/simplicity:just-move` again after plan mode ends applies them. Don't refuse to run, the way shift-session and call-it-a-day do in plan mode.

**Surface.** Check once whether this session has `send_later`, `create_trigger`, `update_trigger` and `subscribe_pr_activity`. They may be deferred tools: look them up with ToolSearch before deciding they're missing. With them, this is a **trigger surface** (a Claude Code cloud session). Without them, it isn't, and step 3 changes as described there.

## 1. Sweep for open decisions

Follow just-ask's steps 1 to 4: sweep, filter, rank, and build each question. Don't ask yet. Step 4 asks these questions together with the blocker and resume questions. Read the session with one more question in mind: what would the run stop to ask the user, hours from now, if nobody settled it first? That counts as open even when nobody has asked it yet, as long as the work the user set out needs it decided. For example, the next task says "pick a library", or a deploy step needs a target.

If nothing is open, don't stop the way just-ask does. Go on to step 2.

## 2. Check for blockers

Check only what you can see from inside the session. Use read-only commands and the session's own tools, and never change anything here. For each check, note whether it's a blocker, whether you can fix it after the user agrees, and the exact fix otherwise.

| Check | How to see it | Fix |
|---|---|---|
| **Permission mode** | `get_session` (session tools) or the session's settings. A mode that prompts for edits or commands stalls an unattended run. | Report only. Never change permission settings. Name the mode that fits, such as `acceptEdits` or `auto`, and where the user sets it. |
| **Likely permission prompts** | The commands and tools the remaining work needs, against the allow rules that are visible. | Report each command that would prompt. The user approves it now or adds an allow rule. |
| **Network** | Earlier refusals in this session (403, a denied host), and the hosts the remaining work needs. | Report the host and that the environment's network policy must allow it. |
| **Credentials and CLI tools** | `command -v <tool>`, `gh auth status`, and whether a needed environment variable is set: check presence only, as in `test -n "$VAR"`. Never print a value. | Report what's missing and how to provide it. |
| **Disk** | `df -h` on the working directory, and how much the remaining work will write. | Report it when space is low. Never delete files to make room. |
| **PR activity** | The open PRs this session drives, and whether this session is subscribed to them. | On a trigger surface: subscribe with `subscribe_pr_activity`, after the user agrees. |
| **Check-ins** | `list_triggers`, for any check-in that already fires into this session. | Step 3's resume plan covers it. Don't duplicate an existing check-in. |
| **Context headroom** | `get_session`'s context usage, or the shift-session hook's last message. | Report how much is left. The shift-session hook asks the user before it shifts, and that question would stall the run. So when the run looks likely to reach its threshold (60% by default), offer the choice now: shift before the user leaves, or the user sets `SIMPLICITY_SHIFT_THRESHOLD=off` for this run. Never set it yourself. |
| **Uncommitted work** | `git status --short` in each repo the session touched. | Report it. The run commits as the user's task says; this skill commits nothing. |

Put every blocker you can fix into step 4 as a yes/no question. Put every blocker you can't fix into the report.

## 3. Plan for usage-limit pauses

A long unattended run will probably hit the user's Claude plan usage limit, and once it does, nothing more can run until the limit resets. So everything here is set up now, before any pause.

**Reset time.** If the session already states when the usage limit resets, use that. Otherwise, add a question for step 4: ask for the reset time shown in `/usage`, including its time zone. `/usage` shows local time. Convert it to UTC in RFC3339 form, and in the question or the closing summary, repeat both times back so the user can catch a mistake. If the user doesn't know the time, rely on the hourly fallback alone: skip guard 1 below, and set the deadline to the time you arm the fallback plus 7 days.

**The deadline** is the reset time plus 7 days. A weekly limit can last that long, and past the deadline nothing keeps firing.

**On a trigger surface**, add one yes/no question for step 4: schedule the resume, both parts bound to this session.

- **One-shot resume.** `send_later` with `at` set to a few minutes after the reset. It switches itself off after it fires. Its prompt carries guards 3 and 4 below, so it does nothing when no pause happened, or when the work is already running or done.
- **Hourly fallback.** A self-bound `create_trigger` with `cron_expression: "0 * * * *"`, in case the reset time was wrong or a weekly limit applies. A cron trigger can't switch itself off, and its prompt can't change after it's armed. So its prompt carries every guard, checked in order:

  > This is just-move's hourly fallback for the unattended run in this session (fallback `<fallback id>`). Check, in order, and stop at the first that applies:
  > 1. Before `<reset UTC>`: end this turn and do nothing.
  > 2. After `<deadline UTC>`: call `update_trigger` with `trigger_id: "<fallback id>"` and `enabled: false`, then stop.
  > 3. Read the handoff note at `<note path>`. If there's a new commit or a task update since the latest checkpoint it records, or another turn is already working on the run: end this turn without action.
  > 4. If the note says the task is done: switch this fallback off as in 2, then stop.
  > 5. Otherwise, the run was paused: continue from the note's **Next step**, and switch this fallback off as in 2 as soon as the work is running again.

  `create_trigger` returns the fallback's id only after the trigger exists. So arm it with `<fallback id>` replaced by the words "this fallback", then put the real id into the handoff note and the report. A firing that can't tell its own id looks it up with `list_triggers`, by its name: "just-move fallback: <topic>".
- **The one-shot's prompt** is the same text without the fallback's guards 1 and 2: guard 3, guard 4 (with "switch the hourly fallback `<fallback id>` off" in place of "this fallback"), then 5.

Write every `<…>` with its real value, never a placeholder. Report both trigger ids. Once the work is running again after a pause, the resumed turn switches the fallback off with `update_trigger enabled=false`; deleting it is optional.

**Not on a trigger surface** (the local CLI, or any session without these tools): nothing can fire while Claude Code isn't running. Say plainly that automatic resume isn't available here. In step 5 still write the handoff note, and in step 6 print a ready-to-paste resume prompt. Don't try local scheduling: it fires only while the process is alive.

## 4. Ask

Put every question in one queue: the open decisions from step 1, the yes/no fix questions from step 2, and the reset-time and resume questions from step 3. Rank them by just-ask's step 3, then ask them by its steps 4 to 6: rounds of at most 4, the recommended option first with ` (Recommended)` in its label, headers of 12 characters or fewer, no "Other" option, and the markdown fallback when AskUserQuestion is missing. For a fix, recommend "yes" unless it's risky to apply right now, and say why in its description.

Apply the answers after each round, as just-ask says, before the next round.

## 5. Apply what the user agreed to

Skip this step in plan mode: everything here is deferred.

Do only what the user said yes to, in this order:

1. **Subscribe** to each agreed PR with `subscribe_pr_activity`.
2. **Write the handoff note.** Read `${CLAUDE_SKILL_DIR}/../shift-session/SKILL.md` with the Read tool, and write the note with its step 3 sections: **Goal**, **Done**, **Pending**, **Repository state**, **Next step** and **Context**. Add a **Checkpoint** line: the time, the latest commit SHA in each repo, and the task list's state. Name any uncommitted work, but never commit it. Save the note in the project's memory directory as `just-move-<topic-slug>.md`, following the session's memory rules, and add a one-line pointer to the memory index if it keeps one, as call-it-a-day does with its note. Start the note with this line, so an unrelated session that reads its memory leaves it alone: "Unattended run since <date>, from session `<id>` ("<title>"). Use this note only to resume this run after a pause, or when the user asks to continue this work." When there's no memory directory, write the note to a scratch file and say so.
3. **Arm the resume** (trigger surface only): the one-shot, then the fallback, as step 3 describes, with the note's real path in both prompts. Then write the fallback's id into the note.

A step that fails goes in the report as not set up, with the reason. It doesn't stop the rest.

## 6. Readiness report

Write it as normal markdown:

- **Settled**: the decisions made, one line each, including assumptions you made instead of asking.
- **Set up**: each PR subscription, and the one-shot and fallback with their trigger ids, or "not available on this surface".
- **Deferred**: in plan mode, every fix you'd have applied.
- **Usage limit**: the reset time (local and UTC), the deadline (UTC), and the handoff note's path.
- **Still open**: each blocker you couldn't fix, with its exact fix for the user.

When this isn't a trigger surface, add "Automatic resume isn't available here. After the limit resets, paste this into this session or a new one:", followed by the resume prompt in a fenced code block. The resume prompt is the handoff note's text, opening with the line "Continue the unattended run described below. First check whether the work already moved on since its checkpoint."

End with one line: "Clear to run." when nothing in **Still open** would stop the run, or "Not clear to run: <the first blocker>." when something would.

## During the run

These rules stay in effect after the report:

- **Refresh the handoff note at each checkpoint**: after each commit, finished task or meaningful step. Update **Done**, **Pending**, **Next step** and the **Checkpoint** line. Writing the note commits nothing.
- **After a resume**, once the work is running again, switch the fallback off with `update_trigger enabled=false`.
- **When the task is done**, switch the fallback off, mark the note done, and delete the note and its index line if the user's task is fully shipped.

## Lifecycle

**Encoded-preference, timelessness 5/10, not yet verified with evals (2026-10).** "Ask everything before the user leaves, fix only on their yes" is a fixed workflow preference, and better models don't make it obsolete. It scores 5 because the resume plan leans on Claude Code's remote trigger tools (`send_later`, `create_trigger`, `update_trigger`), on the cloud session tools that report the permission mode and context usage, and on how plan usage limits reset. Re-check step 3 whenever those tools or limits change. Re-check step 0's and step 5's pointers whenever just-ask's or shift-session's steps are renumbered.
