---
name: just-say-it
description: Re-states the session's latest response, the last N responses, or everything said on a given topic as a short numbered list in plain language. It can also explain a commit, a pull request, a document (a file path, a URL, or a doc reached through a connected tool) or a pasted snippet of text, in short, plain words with no technical jargon. Each item is a bold label plus one plain sentence, with no preamble. Invoked by the user as /simplicity:just-say-it, optionally with a count ("/simplicity:just-say-it 3"), a topic ("/simplicity:just-say-it caching plan"), or something to explain ("/simplicity:just-say-it a1b2c3d", "/simplicity:just-say-it #16", "/simplicity:just-say-it docs/backups.md"). Use when the user names /simplicity:just-say-it or asks for just-say-it by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[N responses | topic | commit | #PR | file or URL | text]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code (uses the Claude Code-only argument-hint field). Explaining a commit needs git; a PR needs the GitHub MCP server's tools or an authenticated gh; a URL or connected doc needs a fetch tool or that connector. Re-stating the session needs nothing.
---

# just-say-it

The user wants something said plainly. There are two modes:

- **Summarize** (the default): the user found your earlier output too long or too dense. Give them the same content again, stripped down to what they need. This mode compresses. It doesn't add analysis.
- **Explain**: the user points at a commit, a pull request, a document or a pasted snippet. Say what it is and what it does, in plain words, for someone who doesn't write code.

## Scope

Decide the mode and the source from `$ARGUMENTS`. Check these rules in order, and use the first that matches:

1. **Empty, or a number below 1:** summarize your most recent response before this command.
2. **A whole number from 1 to 999:** summarize your last N responses before this command, as one list rather than one list per response. If fewer than N exist, use all of them. A bare number always means this, never a PR: `#16` is the PR.
3. **A number followed by text** (`3 caching`): summarize your last N responses that touched that topic.
4. **A pasted snippet:** the argument spans several lines, sits in a code fence or in quotes, or runs past 30 words. Explain that text.
5. **A URL:** a GitHub `…/pull/<n>` URL is a PR, and a `…/commit/<sha>` URL is a commit. Any other URL is a document.
6. **A PR:** `#16`, `PR 16`, `PR #16` or `pr#16`, in the current repository.
7. **A commit:** a single word of 7 to 40 hexadecimal characters (`0-9`, `a-f`) that includes at least one digit, or a bare number of 7 to 40 digits. Check that it resolves (`git cat-file -e <sha>^{commit}`). If it doesn't, go on to rule 9.
8. **A file:** a single word that starts with `/`, `./`, `../` or `~/`, contains a `/`, or ends in a file extension such as `.md`. It's a document. If no such file exists, say so in one line and stop.
9. **Anything else:** a topic. Summarize everything you said about it in this session.

A bare number from 1,000 up to 6 digits matches none of these. Say in one line that a PR number needs a `#`, and that a count up to 999 means your last N responses, then stop.

A "response" is one full assistant turn. That includes turns that were mostly tool calls: summarize what they did and found. Earlier `just-say-it` lists never count as a source, in any mode.

If there's nothing to summarize, because nothing precedes the command or nothing matches the topic, say so in one line and stop.

## Explain: fetch the source

Get the source text with read-only calls, and only for the item the user named:

- **Commit:** `git show --stat <sha>`, then `git show <sha>` for the diff when the message alone doesn't say what changed.
- **PR:** the GitHub MCP server's `pull_request_read` (`get`, then `get_diff` or `get_files` when needed). Use `gh pr view <n>` and `gh pr diff <n>` only where `gh` exists. Cloud sessions often have only the MCP server.
- **Document:** a local file with the Read tool. A URL with the fetch tool you have. A doc behind a connected tool, such as a Confluence page or a Google Doc, with that connector's read tool. If nothing can reach it, say so in one line and stop.
- **Snippet:** none. The text is already in the argument.

If a fetch fails, say so in one line and stop. Never edit, comment, review or change anything you fetched.

## Output

Write a numbered list and nothing else:

```
1. **Short label** — one plain sentence saying what it is or why it matters.
2. **Short label** — one plain sentence.
```

Follow these rules in both modes:

- **No preamble** ("Here's a summary…") and no closing remarks, except the open-decisions line described below.
- **One idea per item.** Each item is a bold label of **at most 4 words**, an em dash, and **one** sentence. For example, "Cache misses" fits the label limit, but "Cache miss for logged-in users" is too long.
- **7 items or fewer.** If there's more, merge related points; don't drop important ones.
- **Keep the original order** when it carried meaning, for example steps or a priority order. Otherwise lead with what matters most.
- **Plain words.** Use short sentences and everyday vocabulary. Drop hedges ("somewhat", "it's worth noting", "of course") and filler. If a technical term has to stay, define it in a few words the first time it appears.
- **Keep what's actionable exact.** File paths, commands, flags, numbers and names stay verbatim, in `code` where they are code.

In explain mode, also:

- **No jargon at all.** Write for someone who has never written code. Say what the change does for the people who use the thing ("a slow network moment no longer fails the nightly backup"), not how it's built. Replace each technical term with everyday words. When a name has to appear, such as a product, a file or a setting, say in a few words what it is.
- **Start with what it is**: "This commit…", "This pull request…", "This document…", "This text…". Put it in the first item's sentence, not as a preamble.

## Hard limits

**In summarize mode:**

- **No new information.** Don't add points, caveats, recommendations or corrections that weren't in the source. If you notice something wrong in the source, you may add one item labelled **Correction** that states it plainly.
- **No tool calls.** Everything you need is already in the conversation.

**In explain mode**, these two limits are relaxed on purpose, and only this far:

- **Tool calls:** only the read-only fetches above, and only for the item the user named.
- **New information:** only what the source itself says, put into plain words, plus the few-word definitions that make it readable. No opinions, review, recommendations, risks or corrections of your own: explain the item, don't judge it.

## Open decisions

This line is for summarize mode only. Explain mode never adds it.

Add this line only if the source **explicitly** left decisions to the user: it asked the user something, said "your call" or "I can't decide this for you", or deferred a choice to them. Never turn the summary's own ideas, such as "do all four at once?", into decisions. When the line applies, end with it after the list, keeping the pointer verbatim:

```
Open decisions: <decision one>; <decision two>. Run /simplicity:just-ask to settle them.
```

When nothing is explicitly open, leave the line out entirely.

## Lifecycle

**Encoded-preference, timelessness 8/10, last verified against claude-opus-5-5 (2026-09) for summarize mode; explain mode not yet verified with evals (2026-10).** This is a fixed output-format preference. Better models don't make it obsolete, because it corrects a style tendency rather than filling a capability gap. It scores 8 rather than 9 now that explain mode leans on outside tools, such as git, the GitHub MCP server or `gh`, and connectors, whose names and inputs change. Future models may also default to terser output on their own, which would shrink the skill's delta. If they do, re-check it against a baseline "summarize your last response" and "explain this commit in plain words".
