---
name: just-say-it
description: Re-states the session's latest response, the last N responses, or everything said on a given topic as a short numbered list in plain language. Each item is a bold label plus one plain sentence, with no preamble and no new information. Invoked by the user as /simplicity:just-say-it, optionally with a count ("/simplicity:just-say-it 3") or a topic ("/simplicity:just-say-it caching plan"). Use it only when the user names /simplicity:just-say-it or asks for just-say-it by name, including mid-sentence, where the command isn't expanded and reaches the model as text; never on a paraphrase of what it does.
argument-hint: "[N responses | topic]"
license: MIT (see plugin root LICENSE)
compatibility: Claude Code (uses the Claude Code-only argument-hint field).
---

# just-say-it

The user found the earlier output too long or too dense. Give them the same content again, stripped down to what they need. This skill compresses. It doesn't add analysis.

## Scope

Decide what to summarize from `$ARGUMENTS`:

- **Empty, or a number below 1:** your most recent response before this command.
- **A number N:** your last N responses before this command. Summarize them as one list rather than one list per response. If fewer than N exist, use all of them.
- **A number followed by text** (`3 caching`): your last N responses that touched that topic.
- **Anything else:** treat it as a topic, and summarize everything you said about it in this session.

A "response" is one full assistant turn. That includes turns that were mostly tool calls: summarize what they did and found. Earlier `just-say-it` summaries never count, in any of these modes.

If there's nothing to summarize, because nothing precedes the command or nothing matches the topic, say so in one line and stop.

## Output

Write a numbered list and nothing else:

```
1. **Short label** — one plain sentence saying what it is or why it matters.
2. **Short label** — one plain sentence.
```

Follow these rules:

- **No preamble** ("Here's a summary…") and no closing remarks, except the open-decisions line described below.
- **One idea per item.** Each item is a bold label of **at most 4 words**, an em dash, and **one** sentence. For example, "Cache misses" fits the label limit, but "Cache miss for logged-in users" is too long.
- **7 items or fewer.** If there's more, merge related points; don't drop important ones.
- **Keep the original order** when it carried meaning, for example steps or a priority order. Otherwise lead with what matters most.
- **Plain words.** Use short sentences and everyday vocabulary. Drop hedges ("somewhat", "it's worth noting", "of course") and filler. If a technical term has to stay, define it in a few words the first time it appears.
- **Keep what's actionable exact.** File paths, commands, flags, numbers and names stay verbatim, in `code` where they are code.

## Hard limits

- **No new information.** Don't add points, caveats, recommendations or corrections that weren't in the source. If you notice something wrong in the source, you may add one item labelled **Correction** that states it plainly.
- **No tool calls.** Everything you need is already in the conversation.

## Open decisions

Add this line only if the source **explicitly** left decisions to the user: it asked the user something, said "your call" or "I can't decide this for you", or deferred a choice to them. Never turn the summary's own ideas, such as "do all four at once?", into decisions. When the line applies, end with it after the list, keeping the pointer verbatim:

```
Open decisions: <decision one>; <decision two>. Run /simplicity:just-ask to settle them.
```

When nothing is explicitly open, leave the line out entirely.

## Lifecycle

**Encoded-preference, timelessness 9/10, last verified against claude-opus-5-5 (2026-09).** This is a fixed output-format preference. Better models don't make it obsolete, because it corrects a style tendency rather than filling a capability gap. It scores 9 rather than 10 because future models may default to terser output on their own, which would shrink the skill's delta. If it does, re-check it against a baseline "summarize your last response".
