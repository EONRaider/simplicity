---
name: speed-up
description: Shortens the path to the current session's objectives without changing them. Maps the remaining work as a dependency tree (what each task waits on, which files it writes, which user decisions it needs) and finds the safe speed-ups: tasks that can start earlier, independent tasks that can run in parallel as sub-agents, waits such as CI that can overlap other work, and tasks already done. It never moves a task ahead of what it depends on, never lets two parallel workers write the same file, and never starts anything that waits on a user decision. It has the proposal reviewed (by the advisor tool when the session has one, otherwise an adversarial sub-agent), asks through AskUserQuestion, and only after the user's yes applies the new task list and notifies the orchestrator, parent or sibling sessions affected by the change, when they exist. It never commits, pushes, discards, bypasses a check, changes permission settings or messages a person. In plan mode it analyses, reviews and asks, and defers applying and notifying. Invoked by the user as /simplicity:speed-up, optionally with a focus such as "/simplicity:speed-up tests". The everyday phrases "speed this up", "go faster" and "can we parallelize" are not requests for this skill. Use when the user names /simplicity:speed-up or asks for speed-up by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[optional focus]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs AskUserQuestion; without it, the approval falls back to a markdown list, as in just-ask. Reads just-ask's and call-it-a-day's SKILL.md from the same plugin. Reviews with the advisor tool when the session has one, otherwise with a sub-agent through Agent; without either it says the proposal is unreviewed and still asks. Applies the list with the host's task tools (update_plan in the desktop app, TaskCreate/TaskUpdate or TodoWrite in the CLI); without them it prints the list as the plan of record. Notifies with SendMessage or the session tools' send_message where they exist; without them it names who should be told and sends nothing.
---

# speed-up

The user wants this session to reach its current objectives sooner. Keep the objectives exactly as they are and change only the order and concurrency of the work that's left: start what's ready, run what's independent side by side, overlap waits with other work, and drop what's already done. Every change must be safe, reviewed, and agreed by the user before anything moves.

How this differs from its neighbours:

- `/simplicity:what-now` reports where the work stands. This skill changes the order of what's left.
- `/simplicity:just-move` prepares the session to run without the user. This skill makes the same work finish sooner.
- `/simplicity:just-finish-it` ships the work and closes the session. This skill never ships anything.

Like every simplicity skill it is conservative. It never commits, pushes, discards, stashes, bypasses a check, changes permission settings or messages a person. It messages only sessions and agents, and only after the user's yes. When unsure, it reports and asks. Never repeat a secret's value anywhere, including the proposal and the messages.

## 0. Before you start

**Read just-ask.** Read `${CLAUDE_SKILL_DIR}/../just-ask/SKILL.md` with the Read tool now. Don't load it with the Skill tool, which would start a separate run. Step 5 asks the way just-ask's steps 4 to 6 say.

**Read call-it-a-day's step 1.** Read `${CLAUDE_SKILL_DIR}/../call-it-a-day/SKILL.md` with the Read tool, for two things only: the **Inventory** list in its step 1, which says how to find what a session supervises, and its rule for messaging a session mid-turn (`SendMessage`, or `send_message` with priority `next`, never `now`). Follow nothing else in that file: this skill commits, pushes, stops, waits on and renames nothing.

**Focus.** The arguments this run was given: "$ARGUMENTS". When they're non-empty, treat them as a focus: sweep only the items related to it, plus every item they depend on and every item that depends on them. A focus never hides a dependency. When they're empty, take the whole session.

**Plan mode.** If the session is in plan mode, still run steps 1 to 5: reading, analysing, the review and the question are safe there. Skip step 6. List the task-list update and each message you would send under **Deferred** in the report, and say that running `/simplicity:speed-up` again after plan mode ends applies them. Don't refuse to run.

**The task list stays as it is until step 6.** Don't write the session's task list before the user's yes, not even to track this skill's own steps. In the desktop app the `update_plan` list is the session's work list, and replacing it with this skill's steps would change the work before the user agreed. Where the host asks for an `update_plan` call each turn, send only `advance` or `start` on the existing list, never a new `items` list.

**Tools.** Check once which of these the session has: the task tools (`update_plan` in the desktop app; `TaskCreate`, `TaskUpdate`, `TaskList` or `TodoWrite` in the CLI), the session tools (`list_sessions`, `get_session`, `send_message`, `ListAgents`, `SendMessage`) and the advisor tool. Any of them may be deferred: look them up with ToolSearch before deciding one is missing.

## 1. Take stock

**Objectives.** Write down what the user asked this session to achieve, in their words where possible. These are fixed. This skill never adds, drops or redefines one.

**The current list.** Use the task list from the task tools. Without one, use the plan in the transcript: a plan file, or a numbered plan in an earlier response. Without either, build the list from the objectives and the remaining work the transcript names. Say which source you used.

**The dependency table.** Write it out in full, one row per open item:

| id | item | status | depends on | writes | waits on | needs user decision | owner |
|---|---|---|---|---|---|---|---|

- **depends on**: every item that must finish first. Reading something another item writes is a dependency.
- **writes**: everything the item changes, not only source files: generated files, lockfiles, the git index of a checkout, a branch, a database or schema, a port, a container. When you can't tell what an item writes, write `unknown`.
- **waits on**: a tool, a CI run, a long command, a reply or any other outside result.
- **needs user decision**: the open decision it depends on, if any.
- **owner**: this session, a sub-agent's id, or another session's id.

Keep each item's existing id and wording. The proposal and the applied list reuse them, so the user can follow what moved.

**Parties.** Find who would need to know about a change, using only what the host's tools return in this run:

- **Below this session**: what it supervises, found the way call-it-a-day's Inventory says: sub-agents and workflows it started, the `list_sessions {"linked": true}` rows whose `startedBy` is this session, sessions it created with `create_session`, and the teammates `ListAgents` lists.
- **Above this session**: in the desktop app, `get_session("self")`'s `parentSessionId` when it's present and `detached` isn't true, and the session that started this one in `list_sessions {"linked": true}`.

A session or agent counts as a party only when a tool returned its id in this run. A name in the transcript or in a memory note that no tool confirms isn't a party: report it as "named, not confirmed, not messaged". People are never parties.

## 2. Find the safe speed-ups

Look for four kinds of change:

- **Start earlier**: an item whose inputs all exist already, waiting behind work it doesn't depend on.
- **Run in parallel**: independent items that can run side by side as sub-agents through the Agent tool.
- **Overlap a wait**: independent work that can go on while CI, a long command or a reply is pending.
- **Drop**: an item that's already done, or that exactly duplicates another.

Every change must pass all of these rules. They are hard rules: a change that breaks one is left out, not softened.

1. **Order.** An item never moves ahead of anything it depends on, directly or through other items.
2. **One writer per resource.** No two items in a parallel group write the same file or other resource from the table's **writes** column. An item whose writes are `unknown` never joins a group. Two workers in the same checkout never both run git write commands: workers in a parallel group don't commit, and the session commits after the group ends, as it would have anyway.
3. **Decisions first.** Nothing that needs a user decision starts, moves earlier, joins a group or is handed to a worker before the user has decided. It keeps its place and is listed as waiting on that decision. Name the open decision in the proposal and point to `/simplicity:just-ask` for it. Never fold it into step 5's question.
4. **Session-bound work stays in the session.** An item that needs AskUserQuestion, a permission prompt, the session's MCP connectors or this session's own context is never handed to a sub-agent.
5. **A wait is left undisturbed.** Work that overlaps a CI run never pushes to the branch that CI is checking, and work that overlaps a long command never writes what that command reads.
6. **Other owners' items move only by message.** An item another session or agent owns is never done here. Its owner is told in step 6.
7. **Drops need evidence.** Drop an item only when the session shows it done, or when it duplicates another item exactly. Otherwise it stays.
8. **Same objectives.** The new list reaches every objective the old one did. Splitting an item is fine; adding scope isn't.
9. **At most 3 sub-agents at once** in one parallel group. A session that already runs more is left as it is.

When you aren't sure a rule holds, leave the change out and name it under **Unchanged** with the doubt.

If no change survives, say so with the reason, skip steps 3 to 6, and end with step 7's report: nothing changed, nobody was notified. Check that conclusion against each item whose inputs already exist before you settle on it.

## 3. Write the proposal

Write the whole proposal in the conversation now, before the review. The advisor reads the conversation and takes no input, so it can only review what's written here.

- **New list**: every open item in its new order, with its id and wording. Write a parallel group as one item that names its members, such as "Parallel: T3 Add the export button + T5 Write the CSV docs".
- **Changes**: one line per change: what moved, grouped or was dropped, what it saves (a wait removed, a serial step overlapped; minutes only where the session gives a duration), and the table rows that make it safe.
- **Unchanged**: every change you considered and left out, with the rule or the doubt that kept it out. Include each item waiting on a user decision.
- **Parties to notify**: each party with what it would be told, or "No supervised or supervising parties found."

## 4. Review

Have the proposal checked before the user sees the question.

- **With the advisor.** If a tool named `advisor` is in the tool list or ToolSearch finds it, call it now.
- **Without it**, spawn exactly one read-only review sub-agent with the Agent tool. It's the only Agent call this skill makes before the user's yes. Tell it that it may read files but must not edit anything, run a git write command or message anyone. Give it the objectives, the dependency table and the proposal, then this brief, word for word: "Find the dependency this reordering breaks, the file two workers would both write, the step that silently assumes a decision. Name each with the table row it comes from; say 'none found' for each you can't find."
- **With neither**, say the proposal is unreviewed, and still go on to step 5.

Fix every finding you confirm by moving that change to **Unchanged**. Never fix one by weakening a rule. Under **Review**, record who reviewed, each finding, and what changed in response. Review again only if a fix added a new change.

## 5. Ask

Show the reviewed proposal, then ask one question through AskUserQuestion, built as just-ask's step 4 says:

- **question**: "Apply this reordered task list?", or "Apply this reordered task list, and notify <the parties' names>?" when there are parties.
- **header**: `Speed-up`
- **options**: "Apply it (Recommended)", whose description says what changes and who is told, and "Keep current order", whose description says nothing changes and nobody is told.

Without AskUserQuestion, use just-ask's step 6 markdown fallback. In plan mode, ask the same question about the proposal, never about the plan's approval.

Then stop and wait for the answer. Nothing before this point writes to the task list, starts a worker or sends a message.

- **"Apply it"**: go to step 6.
- **"Keep current order"**: end with "Nothing changed. Nobody was notified."
- **Edits typed as "Other"**: apply them to the proposal, check the rules again on what changed, and ask again.

## 6. Apply, then notify

Only after the user said yes. Skip this step in plan mode.

1. **Check that nothing moved.** Read the task list and the parties' state again. If an item finished, moved or changed owner since step 1, say so, redo steps 2 to 5 for the part it touches, and ask again.
2. **Apply the new list**, keeping each item's id and wording:
   - in the desktop app, one `update_plan` call with the whole list and `scope: "continuation"`. It takes at most 12 items: past 12, fold the trailing items into one "Remaining: T<n> to T<m>" item, and keep the full list in the report;
   - in the CLI, `TaskCreate` or `TaskUpdate` for each item in the new order, or one `TodoWrite`;
   - with no task tools, print the new list as the plan of record.
3. **Notify each party that exists and is affected**: a parent, orchestrator or project-manager session whose tracked order or finish time changed, and a session or agent that owns a moved item or waits on one. Use `SendMessage` for an agent or teammate, and `send_message` with priority `next` for a session, never `now`, which interrupts it. Send each party one message:

   > From session `<this session's id>` ("<its title>"): the user approved a reordered task list for <the objective>. Moved: <item>, now <its new position>, was <its old one>, because <its input is ready, or a wait now overlaps>. Now in parallel: <the group>. What you do differently: <a concrete action, such as "start T4 now; its input is at <path or SHA>">, or "nothing, for your information". Finish your current task first; this doesn't interrupt it.

   The message only reorders. It never asks the recipient to stop, hold, wind down, commit or push. Skip a party that's not affected. Never invent an id and never message a person. When step 1 found no parties, say "No supervised or supervising parties found." and send nothing.
4. **Hand back.** The session carries on with its work in the new order, starting each parallel group under rules 2 and 9.

A step that fails goes in the report with the reason. It doesn't stop the rest.

## 7. Report

Write it as normal markdown:

- **Applied**: the new list as applied, or **Deferred** in plan mode, with each change and message that waits.
- **Parallel groups**: each group and what it runs.
- **Unchanged**: each change left out, and why.
- **Review**: the reviewer, each finding and what changed, or "unreviewed".
- **Notified**: each party, the tool and the priority, or "No supervised or supervising parties found."

End with one line: "Objectives unchanged."

## Lifecycle

**Encoded-preference, timelessness 6/10, last verified against claude-sonnet-5-5 (2026-11) with seeded evals.** "Change only order and concurrency, never the objectives, and only after the user agrees" is a fixed preference. It scores 6 because it leans on the host's task tools (`update_plan`'s 12-item limit and `scope`), session-list and message tools, on the advisor tool, and on the Agent tool. Re-check step 0, step 1's parties and step 6 whenever those change, and re-check step 0's pointers whenever just-ask's steps or call-it-a-day's step 1 are renumbered.
