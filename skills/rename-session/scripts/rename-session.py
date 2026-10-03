#!/usr/bin/env python3
"""Original author: voidharbor (https://github.com/voidharbor).

Source: https://github.com/voidharbor/claude-plugins/blob/397b2705f8f83958536721ddc557331bd4d2737b/rename-session/scripts/rename-session.py
License: MIT, Copyright (c) 2026 voidharbor (see the LICENSE file beside this
skill's SKILL.md).
Modified for simplicity: same behavior, restructured to pathlib, full type
hints, Google-style docstrings and a ``main(argv) -> int`` entry point that
reports errors on stderr with a nonzero exit status.

Rename the current Claude Code session.

Usage:
    rename-session.py "NEW TITLE"

Writes the title to the same two places the app itself writes on a rename:

1. a ``{"type":"custom-title",...}`` line appended to the session transcript
   ``.jsonl``;
2. the ``<project>/<session-id>/custom-title.json`` sidecar.

The session is identified by ``$CLAUDE_CODE_SESSION_ID``, never by newest
modification time.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

USAGE = 'usage: rename-session.py "NEW TITLE"'
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


class RenameError(Exception):
    """A rename that cannot proceed; the message is shown to the user."""


def compact(payload: dict[str, str]) -> str:
    """Serialize a record with the app's exact byte format.

    Args:
        payload: The record to serialize.

    Returns:
        The JSON text with no whitespace between separators.
    """
    return json.dumps(payload, separators=(",", ":"))


def find_transcripts(session_id: str) -> list[Path]:
    """Find every transcript on disk for a session.

    Args:
        session_id: The session id, as held by ``$CLAUDE_CODE_SESSION_ID``.

    Returns:
        The matching ``~/.claude/projects/*/<session_id>.jsonl`` paths, sorted.
        Hidden project directories are skipped, as a shell glob would.
    """
    projects = Path.home() / ".claude" / "projects"
    return sorted(
        path
        for path in projects.glob(f"*/{session_id}.jsonl")
        if not path.parent.name.startswith(".")
    )


def resolve_transcript(session_id: str) -> Path:
    """Return the one transcript that belongs to a session.

    Args:
        session_id: The session id to look up.

    Returns:
        The path of the session's transcript.

    Raises:
        RenameError: If zero or several transcripts match.
    """
    paths = find_transcripts(session_id)
    if len(paths) != 1:
        found = [str(path) for path in paths]
        raise RenameError(
            f"expected exactly 1 transcript for {session_id}, "
            f"found {len(paths)}: {found}"
        )
    return paths[0]


def rename(transcript: Path, session_id: str, title: str) -> None:
    """Write the title to the transcript and to its sidecar.

    The transcript is appended to, never rewritten.

    Args:
        transcript: The session's transcript ``.jsonl``.
        session_id: The session id recorded in the transcript line.
        title: The new session title.
    """
    record = {"type": "custom-title", "customTitle": title, "sessionId": session_id}
    with transcript.open("a") as handle:
        handle.write(compact(record) + "\n")
    sidecar_dir = transcript.with_suffix("")
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    with (sidecar_dir / "custom-title.json").open("w") as handle:
        handle.write(compact({"customTitle": title}))


def run(args: Sequence[str]) -> str:
    """Rename the current session.

    Args:
        args: The command-line arguments after the program name.

    Returns:
        The confirmation line to print.

    Raises:
        RenameError: If the title is missing, the session id is unset, or the
            session doesn't have exactly one transcript.
    """
    if not args or not args[0].strip():
        raise RenameError(USAGE)
    title = " ".join(args).strip()
    session_id = os.environ.get(SESSION_ENV)
    if not session_id:
        raise RenameError(
            f"{SESSION_ENV} not set: run this from inside a Claude Code session"
        )
    rename(resolve_transcript(session_id), session_id, title)
    return f"renamed session {session_id[:8]} -> {title}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: The arguments after the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit status: 0 on success, 1 on any error.
    """
    args = sys.argv[1:] if argv is None else argv
    try:
        message = run(args)
    except RenameError as error:
        print(error, file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
