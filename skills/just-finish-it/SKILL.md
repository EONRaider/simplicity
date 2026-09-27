---
name: just-finish-it
description: Finalizes the work of an implementation session. Pushes this session's branches, opens any missing pull requests, waits for CI, merges the PRs whose checks pass, deletes their merged branches, syncs the local repositories, runs /simplicity:cleanup, and archives the session when nothing is left pending. When something is still pending (failing CI, missing review, uncommitted work, unfinished tasks), it merges what it safely can, skips archiving, and ends with a report of what remains and the suggested next step for each item. Invoked by the user as /simplicity:just-finish-it at the end of a session or mid-session, optionally scoped to specific PRs or a repository ("/simplicity:just-finish-it 42 57").
disable-model-invocation: true
argument-hint: "[PR numbers | repo path]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git and an authenticated GitHub CLI (gh). Archiving uses the desktop app's session tools; in the CLI the skill stops at "ready to close" instead.
---

# just-finish-it

The user wants this session's work shipped and the session closed. Invoking the command is their go-ahead to push, open PRs, merge PRs whose checks pass, and delete the branches of merged PRs, all within the scope set in step 1. It is **not** a go-ahead to commit uncommitted work, merge anything with failing checks or missing reviews, bypass branch protection, or touch work from outside this session.

If the session is in plan mode, stop and say that this command pushes and merges, so it can't run in plan mode.

Work through the steps in order. Keep a running **pending list** from the first step on. Anything that stops a step from finishing cleanly goes on it, and the pending list decides step 7. Never repeat a secret's value anywhere, including the pending list.

## 1. Scope and repo facts

**In scope** are the branches this session created, committed to, or pushed, and their PRs. A PR someone else opened is in scope only when `$ARGUMENTS` names it. A mention earlier in the conversation isn't enough. If `$ARGUMENTS` names PR numbers or a repository path, narrow the scope to those. If a bare PR number could belong to more than one repository in scope, ask which.

Never push to a repository's default branch. Commits made on it this session go on the pending list, with the suggestion to move them to a branch.

For each repository in scope, settle these facts now, before anything waits on CI:

- **Owner and default branch.** Run `gh repo view --json nameWithOwner,defaultBranchRef`. Pass `-R <owner/repo>` to every `gh pr` command from here on. PR numbers are per repository, and `-R` also keeps `gh pr merge --delete-branch` from touching local branches or worktrees (step 4).
- **Is GitHub usable?** Check `gh auth status`. If gh is missing or unauthenticated, or the remote isn't GitHub, do step 3's pushes only. PR creation and merging for that repo go on the pending list.
- **Merge method.** Use the method the project's CLAUDE.md or CONTRIBUTING names. Otherwise check `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`. When only one method is allowed, use it. When several are, ask now, in one question covering every such repository, with squash as the recommended option.
- **Merge queue.** Check `gh api repos/<owner/repo>/rules/branches/<default>` for a rule of type `merge_queue`. If there is one, don't merge anything in that repository. Put its PRs on the pending list with "repo uses a merge queue: enqueue it yourself".

Also record, per repository, `git status --short`, `git stash list`, `git worktree list`, and every in-scope branch with its PR number, if it has one. Then show the scope as a short table (repo, branch, PR, state) before anything leaves the machine. Don't wait for approval unless the scope surprised you. The user already asked for this.

If nothing is in scope, say so, run step 6, and stop without archiving.

## 2. Take stock of what's unfinished

Before shipping anything, collect everything in the session that isn't done. Put each item on the pending list:

- **Uncommitted or stashed changes.** Never commit, stash, or discard them yourself. Note the files and what they seem to be. A branch with uncommitted changes in its working tree is **dirty**. Don't merge its PR, and don't switch or delete it later.
- **Unpushed work outside the scope.** This covers session branches that `$ARGUMENTS` left out of scope but that have commits not on their remote.
- **Tasks.** Include task-list items that aren't completed, and things the user asked for that were never done. Count a plan step as pending only if its work is actually missing, not just because its checkbox was never ticked.
- **Loose ends in your own responses.** Include TODOs you left in code, placeholders, "I'll come back to this", and tests you skipped or said you would add.
- **Open decisions** the user still owes you. List them. Don't ask them here.
- **Secrets in commits.** For each in-scope branch, read `git diff <default>...<branch>`. Look for added files or lines that hold credentials: `.env` files, keys, tokens, and connection strings with passwords. If one does, don't push that branch. Put it on the pending list with the file and the kind of secret, never the value.

A branch whose work is clearly half-done is **half-done**. That covers a branch with failing local tests, or one whose task is still in progress. Push it in step 3 so the work isn't lost, but don't open a PR for it and don't merge an existing one. Put it on the pending list.

## 3. Push and open PRs

For each in-scope branch that has commits, isn't the default branch, and wasn't held back for a secret:

1. Push it: `git push -u origin <branch>`. Never force-push. If the push is rejected because the remote moved, put the branch on the pending list instead of rebasing on your own.
2. If it has no PR and isn't half-done, open one with `gh pr create -R <owner/repo>`. Base it on the default branch, or on its parent branch if it's stacked. Take the title and body from the commits and the session's own account of the change, and follow any PR conventions in the project's CLAUDE.md.
3. Record the head SHA you pushed. The merge in step 4 checks it.

## 4. Wait for CI, then merge what's green

For each PR in scope that isn't half-done, doesn't belong to a dirty branch, and isn't blocked by a merge queue, work base-first when PRs are stacked:

1. **Wait for checks.** Run `gh pr checks <n> -R <owner/repo> --watch` in the background and let it notify you when it's done. It exits 0 when every check passed, 1 when one failed, and 8 while checks are still pending. If it says "no checks reported", see below. Stop waiting after about 20 minutes: stop the watch, and mark the PR pending with the note "CI still running".
2. **Read the final state:**
   - `gh pr checks <n> -R <owner/repo> --json name,bucket`
   - `gh pr view <n> -R <owner/repo> --json state,isDraft,mergeable,mergeStateStatus,reviewDecision,latestReviews,headRefOid`

   If `mergeable` or `mergeStateStatus` is `UNKNOWN`, GitHub is still computing it. Wait a few seconds and read it again.
3. **Merge only when all of these hold:**
   - every check's `bucket` is `pass` or `skipping`, whether the check is required or not;
   - `state` is `OPEN` and `isDraft` is false;
   - `mergeable` is `MERGEABLE`, and `mergeStateStatus` is `CLEAN` or `HAS_HOOKS`;
   - `reviewDecision` isn't `REVIEW_REQUIRED` or `CHANGES_REQUESTED`, and no entry in `latestReviews` has state `CHANGES_REQUESTED`;
   - `headRefOid` still matches the SHA you recorded.

   Then run `gh pr merge <n> -R <owner/repo> --<method> --delete-branch --match-head-commit <sha>`. With `-R`, `--delete-branch` deletes only the remote branch. Step 5 handles local branches.
4. **Confirm the merge.** Read `gh pr view <n> -R <owner/repo> --json state` afterwards. Only `MERGED` counts as merged. If the command failed or the state is anything else, put the PR on the pending list with the error. Don't retry with other flags.
5. **Otherwise, don't merge.** Put the PR on the pending list with the exact reason, such as the failing check's name, "awaiting review", "changes requested by @x", "conflicts with main", "behind main", or "draft".

**No checks reported.** Wait two minutes, since checks can take a moment to register. If the repository has no CI at all (no `.github/workflows/` and no checks on its recently merged PRs), merge and say "merged without CI: repo has none" in the report. If it has CI but nothing ran for this PR, that's pending.

**Never** use `--admin`, never enable auto-merge, never re-run or skip a failing check to get it green, and never edit code during this skill to fix CI. A red PR is pending. Fixing it is a suggestion for the report, not something to do now.

**Stacked PRs.** After a base PR merges, confirm the child PR was retargeted to the default branch. Its checks ran against the old base, so bring it up to date with `gh pr update-branch <n> -R <owner/repo>`. Record the new head SHA and go back to item 1 for it. If the update conflicts, put the child on the pending list with the suggestion to rebase it.

## 5. Sync local repositories

For each repository where something merged:

- Run `git fetch --prune origin`.
- **Update the default branch without disturbing anyone's work.**
  - If no worktree has it checked out, run `git fetch origin <default>:<default>`.
  - If a clean worktree has it checked out, run `git -C <that worktree> pull --ff-only`.
  - If that worktree is dirty, leave it and mention it.
- **Switch branches only in the main checkout, and only when it's clean.** If its current branch was just merged, run `git switch <default>`. Never switch branches inside a worktree the app created for this session. Archiving cleans that worktree up.
- **Delete only the local branches of PRs merged in step 4.** Skip any branch that is checked out in a worktree. Use `git branch -d` first. After a squash or rebase merge, `-d` refuses because the merged commits have new hashes. In that case only, use `-D`, and only if every local commit made it into the merge:
  1. Fetch the PR's final head with `git fetch origin pull/<n>/head`. GitHub keeps this ref after the branch is deleted.
  2. Check `git merge-base --is-ancestor <branch> FETCH_HEAD`. It succeeds when the local tip is the merged head or behind it, for example after `update-branch`.

  If it fails, keep the branch and put it on the pending list: it has local commits that weren't merged.

## 6. Run cleanup

Invoke `/simplicity:cleanup` and follow its checklist, with these changes, since this skill decides what happens next:

- Wherever cleanup says to ask the user, add the item to the pending list instead.
- Skip its closing offer to archive.
- Send no messages to people. Session-to-session handoffs the user asked for are fine.

Add anything cleanup flags to the pending list.

## 7. Report, then archive or stop

Write the report first. The user needs to see it whether or not the session gets archived. Write it as normal markdown, not inside a code block.

**Shipped.** One line per PR: number, title, and "merged", "opened", or "pushed". Mention each repository that was synced and each branch that was deleted.

**Archive only when all of these hold:**
- the pending list is empty;
- `$ARGUMENTS` was empty;
- something was in scope;
- nothing in the conversation says the user will keep working in this session.

Invoking this command is the user's explicit agreement to archive in that case, so don't ask again. Say the session is finished, then archive it with the host's session-archive tool as your very last action. If no archive tool exists, as in the CLI, say it's ready to close and stop.

**Otherwise, don't archive.** Say why in one line, for example "Session left open: 3 items still to do". When items are pending, end with a **Still to do** heading followed by a numbered list, one item per line:

1. **What's blocked**: why it's blocked. **Next:** the concrete action, with a command where one fits.
2. …

Then add one line starting "Suggested order:", putting the item that unblocks the most first, and finish with "Then run /simplicity:just-finish-it again."

Follow these rules for the list:

- Most blocking first. Keep numbers, check names, file paths and commands exact.
- Every item has a **Next:** the user can do right now. That includes open decisions, whose next step is "answer it with /simplicity:just-ask". Other examples: "`gh run view <id> --log-failed`, then fix `test_parse`", "request review from @owner", "commit `src/api.py` to `feat/x`, or discard it".
- Group items only when one action clears several.

## Lifecycle

**Encoded-preference, timelessness 7/10, last verified against claude-opus-5-5 and gh 2.101.0 (2026-09).** The workflow order and its safety rules (merge only on green, never commit for the user, archive only when nothing is pending) are fixed preferences that don't age with model capability. It scores 7 rather than higher because steps 1–5 encode today's `gh` behavior: `-R` turning `--delete-branch` remote-only, `pr checks` exit codes and buckets, `mergeStateStatus` values, and the branch-rules API for merge queues. Step 7 also depends on the desktop app's archive tool. Re-verify those whenever `gh` or the session tools change.
