#!/usr/bin/env python3
"""Original author: voidharbor (https://github.com/voidharbor).

Source: https://github.com/voidharbor/claude-plugins/blob/397b2705f8f83958536721ddc557331bd4d2737b/ultra-prompt/scripts/last-prompt.py
License: MIT, Copyright (c) 2026 voidharbor (see the LICENSE file beside this
skill's SKILL.md).
Modified for simplicity: the skipped meta-commands are now /promptfy and
/simplicity:promptfy (upstream skipped its own commands, ultra-prompt among
them), and a typed message that names either one anywhere is skipped too;
otherwise the same behavior, restructured to pathlib, full type hints,
Google-style docstrings and a ``main(argv) -> int`` entry point that reports
errors on stderr with a nonzero exit status.

Print the last prompt(s) the user actually typed, read verbatim from the
transcript.

Usage:
    python3 last-prompt.py                 # last prompt, this session
    python3 last-prompt.py -n 5            # last 5 prompts, this session
    python3 last-prompt.py --all           # last prompt from ANY session
    python3 last-prompt.py --all -n 5      # last 5 across all sessions
    python3 last-prompt.py --session <id>  # a specific session

Why this exists rather than just scrolling back: after a long session the
context gets summarized, and the verbatim wording of what was asked can be gone
from what the model can see. The .jsonl on disk still has it exactly as typed.

What counts as "a prompt": anything the user sent by hand, including slash
commands (shown as "/name args"). Deliberately NOT counted: tool results,
system-injected messages, subagent chatter, command stdout, and promptfy
itself, typed as a command or named anywhere in a message -- otherwise a bare
/simplicity:promptfy would just report /simplicity:promptfy.

Transcripts are only ever read, never written.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import typing
from collections.abc import Sequence
from pathlib import Path

SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

# Tail sizes to try in order. Transcripts reach 55MB+ and a single prompt can
# sit behind a lot of tool output, so grow the window instead of guessing one
# size. None reads the whole file.
TAIL_STEPS: tuple[int | None, ...] = (1_000_000, 8_000_000, None)

# With --all, only the newest transcripts are searched.
MAX_SESSIONS = 40

SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)

# Wrappers the CLI writes into the user stream that the user never typed.
NOISE_TAGS = ("<local-command-stdout>", "<local-command-stderr>", "<bash-stdout>")

# Meta-commands that ask about the last prompt. Reporting one as the answer
# would just echo the question back. A plugin skill is recorded under its
# namespaced name, so both forms are listed.
SELF_COMMANDS = frozenset({"/promptfy", "/simplicity:promptfy"})

# Either meta-command typed as plain text. A command named mid-sentence isn't
# expanded, so the model invokes the skill itself and the message reaches the
# transcript as typed. It asks for the rewrite; it is never the prompt to
# rewrite. The lookarounds keep paths ("skills/promptfy/") and longer names
# ("/promptfy-all") from matching.
SELF_MENTION = re.compile(r"(?<![\w/:.-])/(?:simplicity:)?promptfy(?![\w-])")

Record = dict[str, typing.Any]


class Prompt(typing.NamedTuple):
    """One prompt the user typed.

    Attributes:
        timestamp: The record's ISO-8601 timestamp, or "" when it has none.
        session: The id of the session the prompt was sent in.
        text: The prompt as typed.
    """

    timestamp: str
    session: str
    text: str


class LookupFailure(Exception):
    """A lookup that cannot proceed; the message is shown to the user."""


def projects_dir() -> Path:
    """Return the directory Claude Code keeps session transcripts under."""
    return Path.home() / ".claude" / "projects"


def visible(paths: Sequence[Path]) -> list[Path]:
    """Drop transcripts in hidden directories or with hidden names.

    Args:
        paths: The candidate transcript paths.

    Returns:
        The paths a shell glob would have matched.
    """
    return [
        path
        for path in paths
        if not path.name.startswith(".") and not path.parent.name.startswith(".")
    ]


def read_records(path: Path, nbytes: int | None) -> list[Record]:
    """Parse JSONL records from the tail of a transcript.

    Args:
        path: The transcript to read.
        nbytes: How many trailing bytes to read. None reads the whole file.

    Returns:
        The parsed records, oldest first. A truncated first line is expected,
        and corrupt lines are skipped rather than fatal.

    Raises:
        OSError: If the transcript cannot be read.
    """
    size = path.stat().st_size
    with path.open("rb") as handle:
        if nbytes is not None and size > nbytes:
            handle.seek(size - nbytes)
            handle.readline()  # drop the partial line we probably landed in
        data = handle.read()
    records: list[Record] = []
    for raw_line in data.split(b"\n"):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def raw_text(record: Record) -> str | None:
    """Flatten a user record's content to text.

    Args:
        record: A transcript record of type "user".

    Returns:
        The record's text, or None if the record is not typed input.
    """
    message = record.get("message") or {}
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            # A tool_result anywhere means this record is the harness talking,
            # not the user.
            if block.get("type") == "tool_result":
                return None
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts) if parts else None
    return None


def as_prompt(record: Record) -> str | None:
    """Extract the prompt the user typed from a transcript record.

    Slash commands are normalised to "/name args" so they read the way they
    were typed.

    Args:
        record: Any transcript record.

    Returns:
        The prompt text, or None if the record is not a typed prompt.
    """
    if record.get("type") != "user":
        return None
    if record.get("isSidechain") or record.get("isMeta"):
        return None

    text = raw_text(record)
    if text is None:
        return None

    if any(tag in text for tag in NOISE_TAGS):
        return None

    name = COMMAND_NAME.search(text)
    if name:
        command = name.group(1).strip()
        if command in SELF_COMMANDS:
            return None  # never report the meta-command itself as the answer
        args_match = COMMAND_ARGS.search(text)
        args = args_match.group(1).strip() if args_match else ""
        return f"{command} {args}".strip()

    text = SYSTEM_REMINDER.sub("", text).strip()
    if SELF_MENTION.search(text):
        return None  # a typed request for promptfy, not the prompt to rewrite
    return text or None


def prompts_from(path: Path, want: int, session_id: str) -> list[Prompt]:
    """Collect the newest prompts from one transcript.

    The tail window grows until enough prompts are found or the whole file has
    been read.

    Args:
        path: The transcript to read.
        want: How many prompts to return at most.
        session_id: The session id to label each prompt with.

    Returns:
        Up to ``want`` prompts, newest first. Empty if the file is unreadable.
    """
    found: list[Prompt] = []
    for nbytes in TAIL_STEPS:
        try:
            records = read_records(path, nbytes)
        except OSError:
            return []
        found = []
        for record in reversed(records):
            text = as_prompt(record)
            if text:
                timestamp = str(record.get("timestamp") or "")
                found.append(Prompt(timestamp, session_id, text))
                if len(found) >= want:
                    return found
        # Whole file already read, or the tail covered the whole file anyway.
        if nbytes is None or path.stat().st_size <= nbytes:
            return found
    return found


def when(timestamp: str) -> str:
    """Render a timestamp as a clock time plus its age.

    Args:
        timestamp: An ISO-8601 UTC stamp, or "" when unknown.

    Returns:
        Text such as "12:09 PM, 42 minutes ago". An unparseable stamp is
        returned unchanged.
    """
    if not timestamp:
        return "unknown time"
    try:
        local = datetime.datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).astimezone()
    except ValueError:
        return timestamp
    delta = datetime.datetime.now(datetime.timezone.utc) - local.astimezone(
        datetime.timezone.utc
    )
    secs = int(delta.total_seconds())
    if secs < 90:
        ago = f"{max(secs, 0)} seconds ago"
    elif secs < 5400:
        ago = f"{secs // 60} minutes ago"
    elif secs < 172800:
        ago = f"{secs // 3600} hours ago"
    else:
        ago = f"{secs // 86400} days ago"
    stamp = local.strftime("%-I:%M %p")
    if secs >= 43200:
        stamp = local.strftime("%a %-d %b, %-I:%M %p")
    return f"{stamp}, {ago}"


def mtime(path: Path) -> float:
    """Return a file's modification time, or 0.0 if it has vanished."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def across_sessions(want: int) -> list[Prompt]:
    """Collect the newest prompts across every session on disk.

    Args:
        want: How many prompts to return at most.

    Returns:
        Up to ``want`` prompts, newest first.

    Raises:
        LookupFailure: If no transcript exists at all.
    """
    projects = projects_dir()
    paths = visible(list(projects.glob("*/*.jsonl")))
    if not paths:
        raise LookupFailure(f"No transcripts found under {projects}.")
    # Newest files first, and stop early: a prompt cannot be newer than its
    # file.
    paths.sort(key=mtime, reverse=True)
    collected: list[Prompt] = []
    for path in paths[:MAX_SESSIONS]:
        collected.extend(prompts_from(path, want, path.stem))
    collected.sort(key=lambda prompt: prompt.timestamp, reverse=True)
    return collected[:want]


def in_session(session_id: str, want: int) -> list[Prompt]:
    """Collect the newest prompts from one session.

    Args:
        session_id: The session to read. "" when it could not be determined.
        want: How many prompts to return at most.

    Returns:
        Up to ``want`` prompts, newest first.

    Raises:
        LookupFailure: If the session id is unknown or has no transcript.
    """
    if not session_id:
        raise LookupFailure(
            f"Could not tell which session this is: {SESSION_ENV} is not set.\n"
            "Re-run with --session <id>, or use --all to search every session."
        )
    matches = visible(sorted(projects_dir().glob(f"*/{session_id}.jsonl")))
    if not matches:
        raise LookupFailure(
            f"No transcript on disk for session {session_id}.\n"
            "Use --all to search every session instead."
        )
    return prompts_from(matches[0], want, session_id)


def render(rows: Sequence[Prompt], scope: str, show_session: bool) -> str:
    """Format the prompts for printing.

    Args:
        rows: The prompts to print, newest first.
        scope: A phrase naming where they were searched for.
        show_session: Whether to label each prompt with its session id.

    Returns:
        The text to print.
    """
    label = "Last prompt" if len(rows) == 1 else f"Last {len(rows)} prompts"
    lines = [f"{label} sent, {scope}:"]
    for row in rows:
        head = when(row.timestamp)
        if show_session:
            head += f"  [session {row.session[:8]}]"
        lines.extend(["", f"--- {head} ---", row.text])
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: The arguments after the program name. None reads ``sys.argv``.

    Returns:
        The parsed options: ``n``, ``all`` and ``session``.
    """
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "-n", type=int, default=1, help="how many prompts back (default 1)"
    )
    parser.add_argument(
        "--all", action="store_true", help="search every session, not just this one"
    )
    parser.add_argument("--session", help="a specific session id")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: The arguments after the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit status: 0 when the lookup ran, including when it found
        no earlier prompt, and 1 when the session or its transcript could not
        be found.
    """
    args = parse_args(argv)
    want = max(1, int(args.n))
    session_id = str(args.session or os.environ.get(SESSION_ENV, ""))
    search_all = bool(args.all)

    try:
        if search_all:
            rows = across_sessions(want)
            scope = "across all sessions"
        else:
            rows = in_session(session_id, want)
            scope = f"this session ({session_id[:8]})"
    except LookupFailure as error:
        print(error, file=sys.stderr)
        return 1

    if not rows:
        print(
            f"No earlier prompt found {scope} -- "
            "this looks like the first thing sent here."
        )
        return 0

    print(render(rows, scope, search_all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
