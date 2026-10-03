# Security policy

## Supported versions

Only the latest released version receives security fixes.

## Reporting a vulnerability

Please do not open a public issue. Report privately through GitHub:
[Report a vulnerability](https://github.com/EONRaider/simplicity/security/advisories/new).

Include what you found, how to reproduce it, and the plugin and Claude Code versions. You can
expect a first reply within seven days. Once a fix is released the advisory is published and
you are credited, unless you ask not to be.

## What counts

simplicity is a set of skills: instructions that Claude follows with your session's tools, plus
two small Python helpers. Problems of particular interest:

- a skill that pushes, merges, deletes or archives something its documentation says it never
  touches, such as `just-finish-it` using `--admin`, force-pushing, or pushing to the default
  branch;
- a skill that repeats a credential it found into the transcript, or sends a message to a
  person without confirmation;
- `rename-session.py` writing anywhere other than the current session's transcript and its
  `custom-title.json` sidecar;
- `last-prompt.py` writing anything at all, or reading outside `~/.claude/projects`;
- a way to make either helper run code taken from a transcript or a title.

A skill is guidance to a model, not a security boundary: the session's own permission settings
decide what can actually run. A skill that gives a poor answer, or a model that ignores a
skill's instruction once, is a bug, not a vulnerability; please file it as a normal issue.
