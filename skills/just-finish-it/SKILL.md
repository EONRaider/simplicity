---
name: just-finish-it
description: Finalizes the work of an implementation session. Pushes this session's branches, opens any missing pull requests, waits for CI, merges the PRs whose checks pass, deletes their merged branches, syncs the local repositories, runs /simplicity:cleanup, and archives the session when nothing is left pending. When something is still pending (failing CI, missing review, uncommitted work, unfinished tasks), it merges what it safely can, skips archiving, and ends with a report of what remains and the suggested next step for each item. Invoked by the user as /simplicity:just-finish-it at the end of a session or mid-session, optionally scoped to specific PRs or a repository ("/simplicity:just-finish-it 42 57").
disable-model-invocation: true
argument-hint: "[PR numbers | repo path]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git, plus an authenticated GitHub CLI (gh) or the GitHub MCP server's tools. Archiving uses the desktop app's session tools; in the CLI the skill stops at "ready to close" instead.
---

# just-finish-it

The user wants this session's work shipped and the session closed. Invoking the command is their go-ahead to push, open PRs, merge PRs whose checks pass, and delete the branches of merged PRs, all within the scope set in step 1. It is **not** a go-ahead to commit uncommitted work, merge anything with failing checks or missing reviews, bypass branch protection, or touch work from outside this session.

If the session is in plan mode, stop and say that this command pushes and merges, so it can't run in plan mode.

Work through the steps in order. Keep a running **pending list** from the first step on. Anything that stops a step from finishing cleanly goes on it, and the pending list decides step 7. Never repeat a secret's value anywhere, including the pending list.

## Transport: gh or the GitHub MCP server

Use `gh` when it's installed and `gh auth status` succeeds. Otherwise use the GitHub MCP server's tools, usually named `mcp__github__<tool>`. Cloud sessions, such as Claude Code on the web, often have only those. If neither exists, or the remote isn't GitHub, do step 3's pushes only, and put PR creation and merging for that repository on the pending list. Pick the transport once per repository in step 1, and show it in the scope table.

The steps below name `gh` commands. On the MCP path, make the matching call from this table instead. Take `owner` and `repo` from `git remote get-url origin`. The table was checked against github-mcp-server v1.12.2; before relying on a parameter, check that the loaded tool's schema has it.

| `gh` call | GitHub MCP call |
|---|---|
| `gh repo view --json nameWithOwner,defaultBranchRef` | `search_repositories` with `query: "repo:<owner>/<repo>"`. Read `default_branch` from the one result. |
| `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed` | No tool returns the allowed merge methods. See step 1's merge-method rule. |
| `gh api graphql` for `repository.mergeQueue` (step 1) | `list_branches` with `perPage: 100`. Read `protected` on the default branch. If it's loaded, also `repository_ruleset_read` with `level: "repository"`, `method: "get_rules_for_branch"`, `branch: "<default>"`. See "Merge queue" below. |
| `gh pr create` | `create_pull_request` with `owner`, `repo`, `title`, `head`, `base` and `body`. |
| `gh pr checks <n> --watch`, then `--json name,bucket` | `pull_request_read` with `method: "get_check_runs"` and again with `method: "get_status"`. There is no watch: re-read about once a minute, with the same 20-minute limit. |
| `gh pr view <n> --json state,isDraft,mergeable,mergeStateStatus,headRefOid` | `pull_request_read` with `method: "get"`. Read `state`, `draft`, `merged`, `mergeable_state`, `head.sha` and `base.ref`. |
| `gh pr view <n> --json reviewDecision,latestReviews` | `pull_request_read` with `method: "get_reviews"` and `perPage: 100`. |
| `gh pr merge <n> --<method> --match-head-commit <sha>` | `merge_pull_request` with `pullNumber`, `merge_method` and `expectedHeadSha: "<sha>"`. |
| `--delete-branch` | No MCP tool deletes a branch. See "Branch deletion" below. |
| `gh pr update-branch <n>` | `update_pull_request_branch` with `expectedHeadSha` set to the PR's current head. |

The MCP results use REST field names, so step 4's merge conditions translate like this:

- **Checks.** A check run passes when its `status` is `completed` and its `conclusion` is `success`, `neutral` or `skipped`. Any other conclusion is a failure. The combined status passes when its `state` is `success`. A combined status with `total_count` 0 has no statuses at all, so it counts as passing even though its `state` reads `pending`. Page through check runs when `total_count` is larger than the page. If both `get_check_runs` and `get_status` return `total_count` 0, that's "no checks reported", and step 4's rule for it applies. To see whether recently merged PRs had checks, call `list_pull_requests` with `state: "closed"`, `base: "<default>"` and `sort: "updated"`, then `get_check_runs` on the most recent ones that have a `merged_at`. Before `merge_pull_request`, call `get_check_runs`, `get_status` and `get_reviews` for that PR in step 4, even when you think you know the answer.
- **Mergeability.** `get` returns neither `mergeable` nor `reviewDecision`. Require `mergeable_state` to be `clean` or `has_hooks`, the lowercase REST forms of `CLEAN` and `HAS_HOOKS`; either one means the PR is mergeable. `blocked` covers a missing required review. If `mergeable_state` is missing or `unknown`, GitHub is still computing it: wait a few seconds and read it again.
- **Changes requested.** From `get_reviews`, find each reviewer's standing verdict: their latest `APPROVED`, `CHANGES_REQUESTED` or `DISMISSED` review. A later `COMMENTED` review doesn't clear an earlier `CHANGES_REQUESTED`. Don't merge while any reviewer stands at `CHANGES_REQUESTED`.
- **Head SHA.** Immediately before `merge_pull_request`, call `get` again and compare `head.sha` with the SHA you recorded. On a mismatch, don't merge: the PR is pending with "head moved". Also pass the recorded SHA as `expectedHeadSha`, so GitHub refuses the merge if the head moves after that read. If the loaded `merge_pull_request` has no `expectedHeadSha` parameter, the re-read is the only guard. That leaves a check-then-act race the `gh` path doesn't have, because GitHub itself checks `--match-head-commit`. Say so in the report.
- **Merged.** Only `merged: true` from `get` counts as merged.
- **Merge queue.** No MCP tool reads a merge queue directly. Work it out from what the tools can read:
  - Call `list_branches` with `perPage: 100`, and page until the default branch appears. If its `protected` is `false`, it has no merge queue. A queue can only come from classic branch protection or a repository ruleset, and either one sets `protected` to `true`. If the branch never appears, treat it as protected.
  - If it's protected and `repository_ruleset_read` is loaded, look for a rule of type `merge_queue`. If there is one, the repository uses a merge queue.
  - In every other case, take the answer the project's CLAUDE.md or CONTRIBUTING states, or ask the user, both as step 1 says. That includes a protected branch whose rulesets show no queue: a queue set in classic branch protection doesn't show up in `repository_ruleset_read`. Nothing else in the default toolsets tells them apart. `get` reports `mergeable_state: clean` on a branch that requires a queue.
  - GitHub refuses a direct merge into a branch that requires a queue. `merge_pull_request` then fails with a 405 whose message includes "Changes must be made through the merge queue". But that only happens for a caller who can't bypass the rule. For a caller who can, the same call merges and skips the queue. That covers an admin on the ruleset's bypass list, and any admin when classic protection doesn't include administrators. So the refusal is a backstop, not a check, and the question stays unless the project states the answer.
  - If `merge_pull_request` fails with an error that mentions the merge queue, the repository uses one. Put that PR and the repository's remaining PRs on the pending list with "repo uses a merge queue: enqueue it yourself". Don't retry.
  - `repository_ruleset_read` is in the server's `governance` toolset, which is off by default. Loading it lets you find a ruleset queue without asking, but it can't rule out a classic one. On GitHub's remote server, send the header `X-MCP-Toolsets: default,governance`. To add just this read tool, since the toolset also holds write tools, send `X-MCP-Toolsets: default` with `X-MCP-Tools: repository_ruleset_read`. On the local server, pass `--toolsets default,governance` or set `GITHUB_TOOLSETS=default,governance`. Hosts that bring their own GitHub tools, such as Claude Code on the web, may not let you change them.
- **Branch deletion.** After a merge, run `git ls-remote --exit-code --heads origin <branch>`. If the branch is gone, the repository's auto-delete-head-branches setting removed it; say so in the report. If it's still there, leave it and put it on the pending list with the next step `git push origin --delete <branch>`.

Every safety rule in this skill holds on both transports: merge only with every check green, the PR mergeable and clean, no changes requested, and the head SHA unchanged. Never bypass branch protection, enable auto-merge, or force-push, by any route.

## 1. Scope and repo facts

**In scope** are the branches this session created, committed to, or pushed, and their PRs. A PR someone else opened is in scope only when `$ARGUMENTS` names it. A mention earlier in the conversation isn't enough. If `$ARGUMENTS` names PR numbers or a repository path, narrow the scope to those. If a bare PR number could belong to more than one repository in scope, ask which.

Never push to a repository's default branch. Commits made on it this session go on the pending list, with the suggestion to move them to a branch.

For each repository in scope, settle these facts now, before anything waits on CI:

- **Transport.** Pick `gh` or the GitHub MCP server, as the Transport section says.
- **Owner and default branch.** Run `gh repo view --json nameWithOwner,defaultBranchRef`. Pass `-R <owner/repo>` to every `gh pr` command from here on. PR numbers are per repository, and `-R` also keeps `gh pr merge --delete-branch` from touching local branches or worktrees (step 4). On MCP, pass `owner` and `repo` to every call.
- **Merge method.** Use the method the project's CLAUDE.md or CONTRIBUTING names. Otherwise check `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`. When only one method is allowed, use it. When several are, or on MCP, where the allowed methods can't be read, ask now, in one question covering every such repository, with squash as the recommended option.
- **Merge queue.** On `gh`, run `gh api graphql -f query='query($owner:String!,$repo:String!,$branch:String!){repository(owner:$owner,name:$repo){mergeQueue(branch:$branch){id}}}' -f owner=<owner> -f repo=<repo> -f branch=<default>`. A non-null `mergeQueue` means the repository uses one, whether it comes from a ruleset or classic branch protection. The REST branch-rules API shows only rulesets, so it can miss a queue. On MCP, follow the Transport section's "Merge queue" bullet. If the repository uses a merge queue, don't merge anything in it. Put its PRs on the pending list with "repo uses a merge queue: enqueue it yourself". The check can fail to settle it. That happens when the MCP tools can't tell, or when the `gh` query fails, for example because a proxy blocks GraphQL. Then, if the project's CLAUDE.md or CONTRIBUTING states whether the default branch uses a merge queue, take that answer, the way the merge method is read, and don't ask. A stated "no" counts exactly as the user's "no" below, with the same backstop and no more. A check that finds a queue always wins over what the project states. Otherwise, ask whether the repository uses a merge queue. Put the question in the same round as the merge method, one question per repository, and recommend neither answer, since you can't tell. If the user says it does, or doesn't answer, treat it as a merge queue. If they say it doesn't, carry on. Step 4 still catches GitHub's refusal.

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
3. **Merge only when all of these hold.** Judge each condition only from the reads made in items 1 and 2, after the push you recorded. A result seen earlier in the session, or one you expect a call to return, doesn't count.
   - every check's `bucket` is `pass` or `skipping`, whether the check is required or not;
   - `state` is `OPEN` and `isDraft` is false;
   - `mergeable` is `MERGEABLE`, and `mergeStateStatus` is `CLEAN` or `HAS_HOOKS`;
   - `reviewDecision` isn't `REVIEW_REQUIRED` or `CHANGES_REQUESTED`, and no entry in `latestReviews` has state `CHANGES_REQUESTED`;
   - `headRefOid` still matches the SHA you recorded.

   Then run `gh pr merge <n> -R <owner/repo> --<method> --delete-branch --match-head-commit <sha>`. With `-R`, `--delete-branch` deletes only the remote branch. Step 5 handles local branches. On MCP, re-read the head SHA first and handle the remote branch as the Transport section says.
4. **Confirm the merge.** Read `gh pr view <n> -R <owner/repo> --json state` afterwards. Only `MERGED` counts as merged. If the command failed or the state is anything else, put the PR on the pending list with the error. Don't retry with other flags. If `gh pr merge` added the PR to a merge queue instead, that isn't a merge: report it as queued. An error that mentions the merge queue means the repository has one. Stop merging there, as the Transport section's "Merge queue" bullet says.
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

**Encoded-preference, timelessness 7/10, last verified against claude-opus-5-5, gh 2.101.0 and github-mcp-server v1.12.2 (2026-09), with GitHub's merge-queue behavior measured on 2026-09-28.** The workflow order and its safety rules (merge only on green, never commit for the user, archive only when nothing is pending) are fixed preferences that don't age with model capability. It scores 7 rather than higher because steps 1–5 encode today's `gh` behavior: `-R` turning `--delete-branch` remote-only, `pr checks` exit codes and buckets, `mergeStateStatus` values, and the GraphQL `mergeQueue` field for merge queues. The Transport section also depends on the GitHub MCP server's tool surface: its tool names and parameters, the REST field names it returns, and which toolsets are on by default. It also depends on GitHub itself: the `protected` flag covering every source of a merge queue, and the 405 that refuses a direct merge into a queue. Step 7 depends on the desktop app's archive tool. Re-verify those whenever `gh`, the GitHub MCP server or the session tools change.
