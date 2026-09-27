---
name: just-finish-it
description: Finalizes the work of an implementation session. Pushes this session's branches, opens any missing pull requests, waits for CI, merges the PRs whose checks pass, syncs the local repositories, runs /simplicity:cleanup, and archives the session when nothing is left pending. When something is still pending (failing CI, missing review, uncommitted work, unfinished tasks), it merges what it safely can, skips archiving, and ends with a report of what remains and the suggested next step for each item. Invoked by the user as /simplicity:just-finish-it at the end of a session or mid-session, optionally scoped to specific PRs or a repository ("/simplicity:just-finish-it 42 57").
disable-model-invocation: true
argument-hint: "[PR numbers | repo path]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git and an authenticated GitHub CLI (gh). Archiving uses the desktop app's session tools; in the CLI the skill stops at "ready to close" instead.
---

# just-finish-it

The user wants this session's work shipped and the session closed. Invoking the command is their go-ahead to push, open PRs, and merge PRs whose checks pass, all within the scope set in step 1. It is **not** a go-ahead to commit uncommitted work, merge anything with failing or missing checks, bypass branch protection, or touch work from outside this session.

Work through the steps in order. Keep a running **pending list** from the first step on. Anything that stops a step from finishing cleanly goes on it, and the pending list decides step 7.

## 1. Scope

List every repository, branch and PR this session created, committed to, or pushed, plus any PR the user named in this session. If `$ARGUMENTS` names PR numbers or a repository path, narrow the scope to those.

Leave out:

- branches and PRs by other people, and ones this session never touched, even if they are open in the same repo;
- the default branch itself. Never push straight to it. Commits made on it this session go on the pending list with the suggestion to move them to a branch.

For each repository in scope, record `git status --short`, `git stash list`, and every in-scope branch with its PR number, if it has one. Then show the scope to the user in a short table (repo, branch, PR, state) before anything leaves the machine. Don't wait for approval unless the scope surprised you. The user already asked for this.

## 2. Take stock of what's unfinished

Before shipping anything, collect everything in the session that isn't done. Put each item on the pending list:

- **Uncommitted or stashed changes.** Never commit, stash, or discard them yourself. Note the files and what they seem to be.
- **Tasks.** Include task-list items that aren't completed, unchecked steps in the plan file, and things the user asked for that were never done.
- **Loose ends in your own responses.** Include TODOs you left in code, placeholders, "I'll come back to this", and tests you skipped or said you would add.
- **Open decisions** the user still owes you. List them. Don't ask them here.

A branch whose work is clearly half-done, such as one with failing local tests or a task still in progress, stays in scope for pushing so the work isn't lost. Don't open a PR for it, or leave its PR as a draft, and put it on the pending list.

## 3. Push and open PRs

For each in-scope branch that has commits and isn't marked half-done:

1. Push it: `git push -u origin <branch>`. Never force-push. If the push is rejected because the remote moved, put the branch on the pending list instead of rebasing on your own.
2. If it has no PR, open one with `gh pr create`. Base it on the default branch, or on its parent branch if it's stacked. Take the title and body from the commits and the session's own account of the change, and follow any PR conventions in the project's CLAUDE.md.
3. Record the head SHA you pushed. The merge in step 4 checks it.

## 4. Wait for CI, then merge what's green

For each PR in scope, base-first when PRs are stacked:

1. **Read its state:** `gh pr view <n> --json isDraft,mergeable,mergeStateStatus,reviewDecision,headRefOid,baseRefName,statusCheckRollup`. Prefer the host's PR-status tools when they exist.
2. **Wait for checks** with `gh pr checks <n> --watch --fail-fast`, running it in the background and letting it notify you when done. Stop waiting after about 20 minutes and mark the PR pending with the note "CI still running".
3. **Merge only when all of these hold:**
   - every required check passed;
   - it isn't a draft;
   - `reviewDecision` isn't `REVIEW_REQUIRED` or `CHANGES_REQUESTED`;
   - `mergeable` isn't `CONFLICTING`;
   - the head SHA still matches the one you recorded.

   Then run `gh pr merge <n> --<method> --delete-branch --match-head-commit <sha>`.
4. **Otherwise, don't merge.** Put it on the pending list with the exact reason, such as the failing check's name, "awaiting review", "conflicts with main", or "draft".

**Merge method.** Use the method the project's CLAUDE.md or CONTRIBUTING names. If there's none, check `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`. When only one method is allowed, use it. When several are, ask once for the whole run, with squash as the recommended option.

**No checks reported.** Wait two minutes, since checks can take a moment to register. If the repository has no CI at all (no `.github/workflows/` and no checks on its recently merged PRs), merge and say "merged without CI: repo has none" in the report. If it has CI but nothing ran for this PR, that's pending.

**Never** use `--admin`, never enable auto-merge, never re-run or skip a failing check to get it green, and never edit code during this skill to fix CI. A red PR is pending. Fixing it is a suggestion for the report, not something to do now.

**Stacked PRs.** After a base PR merges, confirm the child PR was retargeted to the default branch and is still mergeable. Then continue with it. If it now conflicts, that's pending, with the suggestion to rebase it.

## 5. Sync local repositories

For each repository where something merged:

- `git fetch --prune`, then fast-forward the default branch with `git pull --ff-only`.
- If the current branch was merged and deleted, switch to the default branch.
- Delete merged local branches with `git branch -d`. After a squash or rebase merge, `-d` refuses because the merged commits have new hashes. In that case only, use `-D`, and only if `gh pr view <n> --json state,headRefOid` shows `MERGED` with a head SHA equal to the local branch tip, so nothing local is lost. Otherwise leave the branch and mention it.
- If this session runs inside a worktree the app created, leave that worktree alone. Archiving cleans it up.

## 6. Run cleanup

Invoke `/simplicity:cleanup` and follow its checklist, with one change: stop after its summary and don't ask about archiving, because step 7 decides that. Add anything cleanup flags to the pending list, such as a background task you couldn't stop or a file that looks like a secret.

## 7. Report, then archive or stop

Write the report first. The user needs to see it whether or not the session gets archived.

**Shipped.** One line per PR: number, title, and "merged", "opened", or "pushed". Mention each repository that was synced.

**If the pending list is empty**, say the session is finished. Then archive it with the host's session-archive tool. The invocation already counts as consent, so don't ask again. If no archive tool exists, as in the CLI, say it's ready to close and stop.

**If anything is pending, don't archive.** An archived session would hide the list the user needs. End with:

```
Still to do
1. <what> — <why it's blocked>. Next: <the concrete action, a command where one fits>.
2. ...

Suggested order: <the item that unblocks the most first, as a short sequence>. Then run /simplicity:just-finish-it again.
```

Follow these rules for the list:

- One line per item, most blocking first. Keep numbers, check names, file paths and commands exact.
- Each **Next** is something the user can do right now. Examples: "`gh run view <id> --log-failed`, then fix `test_parse`", "request review from @owner", "commit `src/api.py` to `feat/x`, or discard it", "answer the open questions with /simplicity:just-ask".
- Group items only when one action clears several.

## Lifecycle

**Encoded-preference, timelessness 7/10, last verified against claude-opus-5-5 (2026-09).** The workflow order and its safety rules (merge only on green, never commit for the user, archive only when nothing is pending) are fixed preferences that don't age with model capability. It scores 7 rather than higher because steps 3–5 encode today's `gh` flags and PR fields (`mergeStateStatus`, `--match-head-commit`), and step 7 depends on the desktop app's archive tool. Re-verify those whenever `gh` or the session tools change.
