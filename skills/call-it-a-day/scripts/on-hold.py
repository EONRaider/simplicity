#!/usr/bin/env python3
"""Keep the hold record for /simplicity:call-it-a-day, and spot the resume.

``call-it-a-day`` puts a session on hold: it pushes the work, saves a handoff
note and renames the session ``<topic> -> On hold``. This script keeps the one
piece of state that lives outside the repo and the memory directory: a hold
record per session, at ``~/.claude/simplicity/call-it-a-day/<session id>.json``.
The record holds the session's pre-hold title, its topic, the hold time and a
copy of the handoff note, so the title can be restored on resume even if the
memory note is gone.

Subcommands (the session id defaults to ``$CLAUDE_CODE_SESSION_ID``):

``hold --title T --topic P [--handoff FILE] [--session ID]``
    Write the record. If one already exists, the session was on hold already,
    so its pre-hold title is kept rather than replaced by the ``On hold`` one.
``show [--session ID]``
    Print the record as JSON; exit 1 when there is none.
``resume [--session ID]``
    Delete the record and print the pre-hold title to restore; exit 1 when
    there is none.
``title [--session ID]``
    Print the session's current CLI title, the last ``custom-title`` record in
    its transcript; exit 1 when it has none. The desktop app keeps its own
    titles, so there the skill reads the title with the app's tool instead.

With no subcommand it runs as a ``UserPromptSubmit`` hook. When the prompting
session has a hold record, and the prompt isn't another ``call-it-a-day`` run,
it adds a note to the model's context: the user is back, so rename the session
to its pre-hold title and clear the hold, unless the message is only an
acknowledgement. The note repeats on every prompt until the hold is cleared.
Every hook path exits 0: a hook that can't read its state stays silent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
SKILL_NAME = "call-it-a-day"
UNSAFE_ID = re.compile(r"[^A-Za-z0-9_-]")
HANDOFF_LIMIT = 256 * 1024
SCRIPT = Path(__file__).resolve()
RENAME_HELPER = SCRIPT.parents[2] / "rename-session" / "scripts" / "rename-session.py"


class HoldError(Exception):
    """A subcommand that cannot proceed; the message is shown to the user."""


def record_dir() -> Path:
    """Return the directory that holds every session's hold record.

    It lives under the home directory, never ``$CLAUDE_PLUGIN_DATA``, because
    the skill's own shell may not see that variable while the hook does.
    """
    return Path.home() / ".claude" / "simplicity" / SKILL_NAME


def record_file(session_id: str) -> Path:
    """Return the hold record for a session.

    Args:
        session_id: The session id; characters unsafe in a file name become
            underscores.

    Returns:
        ``~/.claude/simplicity/call-it-a-day/<id>.json``.
    """
    safe = UNSAFE_ID.sub("_", session_id)[:200] or "session"
    return record_dir() / f"{safe}.json"


def load(session_id: str) -> dict[str, Any] | None:
    """Return a session's hold record, or None when it has none or it's unreadable."""
    try:
        data = json.loads(record_file(session_id).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("title"), str):
        return None
    return data


def save(session_id: str, record: Mapping[str, Any]) -> Path:
    """Write a session's hold record atomically.

    Args:
        session_id: The session the record belongs to.
        record: The record to write.

    Returns:
        The record file written.
    """
    path = record_file(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    os.replace(handle.name, path)
    return path


def read_handoff(path: str | None) -> tuple[str | None, str | None]:
    """Read the handoff note to copy into the record.

    Args:
        path: The note's path, or None when no note was given.

    Returns:
        (absolute path, text), both None when no note was given.

    Raises:
        HoldError: If the note can't be read or is larger than 256 KiB.
    """
    if path is None:
        return None, None
    note = Path(path).expanduser()
    try:
        text = note.read_text()
    except OSError as error:
        raise HoldError(f"can't read the handoff note {note}: {error}") from error
    if len(text.encode()) > HANDOFF_LIMIT:
        raise HoldError(f"the handoff note {note} is larger than 256 KiB")
    return str(note.resolve()), text


def hold(
    session_id: str, title: str, topic: str, handoff: str | None, now: datetime
) -> tuple[Path, dict[str, Any]]:
    """Record that a session is on hold.

    A session put on hold twice keeps the pre-hold title from the first time,
    since its current title is by then ``<topic> -> On hold``.

    Args:
        session_id: The session going on hold.
        title: Its title before the hold.
        topic: The topic of its ``<topic> -> On hold`` title.
        handoff: The path of the handoff note, if there is one.
        now: The time of the hold.

    Returns:
        The record file and the record written.

    Raises:
        HoldError: If the title or topic is blank, or the note is unreadable.
    """
    if not title.strip() or not topic.strip():
        raise HoldError("--title and --topic must not be blank")
    note, text = read_handoff(handoff)
    previous = load(session_id)
    record: dict[str, Any] = {
        "session_id": session_id,
        "title": previous["title"] if previous else title.strip(),
        "topic": topic.strip(),
        "on_hold_title": f"{topic.strip()} -> On hold",
        "held_at": now.isoformat(timespec="seconds"),
        "handoff_path": note,
        "handoff": text,
    }
    return save(session_id, record), record


def resume(session_id: str) -> str:
    """Clear a session's hold.

    Args:
        session_id: The session being resumed.

    Returns:
        The pre-hold title to restore.

    Raises:
        HoldError: If the session has no hold record.
    """
    record = load(session_id)
    if record is None:
        raise HoldError(f"session {session_id} has no hold record")
    record_file(session_id).unlink(missing_ok=True)
    return str(record["title"])


def cli_title(session_id: str) -> str | None:
    """Return a CLI session's current title from its transcript.

    Args:
        session_id: The session to read.

    Returns:
        The ``customTitle`` of the last ``custom-title`` record in the
        session's ``~/.claude/projects/*/<id>.jsonl``, or None when there is
        no such record, or not exactly one transcript.
    """
    projects = Path.home() / ".claude" / "projects"
    paths = [
        path
        for path in projects.glob(f"*/{session_id}.jsonl")
        if not path.parent.name.startswith(".")
    ]
    if len(paths) != 1:
        return None
    title = None
    try:
        with paths[0].open("rb") as handle:
            for line in handle:
                if b'"custom-title"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "custom-title":
                    continue
                value = entry.get("customTitle")
                if isinstance(value, str):
                    title = value
    except OSError:
        return None
    return title


def message(record: Mapping[str, Any]) -> str:
    """Return the note the hook adds to the context of a session on hold."""
    title = str(record["title"])
    held = str(record.get("on_hold_title") or "<topic> -> On hold")
    rename = f"python3 {shlex.quote(str(RENAME_HELPER))} {shlex.quote(title)}"
    clear = f"python3 {shlex.quote(str(SCRIPT))} resume"
    note = record.get("handoff_path")
    note_line = (
        f" Then delete the handoff note {note} and its line in the memory "
        "index, since the branch and the trackers now carry the state."
        if note
        else ""
    )
    return (
        f"simplicity: this session was put on hold by /simplicity:call-it-a-day "
        f"at {record.get('held_at', 'an earlier time')} and is titled "
        f"{json.dumps(held)}. If the user's message only acknowledges the hold "
        "(such as 'thanks' or 'good night') or asks about it, answer and leave "
        "the hold in place. Otherwise the user is back and the work resumes: "
        "before anything else, rename this session to its pre-hold title "
        f'{json.dumps(title)} (the session title tool with "self" in the '
        f"desktop app; in the CLI run {rename}; not /simplicity:rename-session, "
        "which rewrites titles), then clear the hold with "
        f"{clear}.{note_line} Don't commit, push or run call-it-a-day for "
        "this; then carry on with the user's request."
    )


def evaluate(payload: Mapping[str, Any]) -> str | None:
    """Decide what, if anything, a hook call adds to the context.

    Args:
        payload: The parsed hook input.

    Returns:
        The hook's stdout JSON, or None to stay silent.
    """
    if payload.get("hook_event_name") != "UserPromptSubmit" or payload.get("agent_id"):
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and SKILL_NAME in prompt:
        return None
    record = load(session_id)
    if record is None:
        return None
    output = {"hookEventName": "UserPromptSubmit", "additionalContext": message(record)}
    return json.dumps({"hookSpecificOutput": output})


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the subcommands."""
    top = argparse.ArgumentParser(prog="on-hold.py", description=__doc__.split("\n")[0])
    sub = top.add_subparsers(dest="command", required=True)
    for name in ("hold", "show", "resume", "title"):
        command = sub.add_parser(name)
        command.add_argument("--session", default=os.environ.get(SESSION_ENV, ""))
        if name == "hold":
            command.add_argument("--title", required=True)
            command.add_argument("--topic", required=True)
            command.add_argument("--handoff")
    return top


def run(args: Sequence[str]) -> str:
    """Run one subcommand.

    Args:
        args: The command-line arguments after the program name.

    Returns:
        The text to print.

    Raises:
        HoldError: If the session id is unknown or the subcommand fails.
    """
    ns = parser().parse_args(list(args))
    session_id = str(ns.session).strip()
    if not session_id:
        raise HoldError(
            f"{SESSION_ENV} not set: pass --session or run inside Claude Code"
        )
    if ns.command == "hold":
        now = datetime.now(timezone.utc).astimezone()
        path, record = hold(session_id, ns.title, ns.topic, ns.handoff, now)
        return f"on hold: {path} (pre-hold title {json.dumps(record['title'])})"
    if ns.command == "show":
        found = load(session_id)
        if found is None:
            raise HoldError(f"session {session_id} has no hold record")
        return json.dumps(found, indent=2)
    if ns.command == "resume":
        return resume(session_id)
    title = cli_title(session_id)
    if title is None:
        raise HoldError(f"session {session_id} has no CLI title")
    return title


def main(argv: Sequence[str] | None = None) -> int:
    """Run a subcommand, or the hook when there is none.

    Args:
        argv: The arguments after the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        0 on success and on every hook path, 1 when a subcommand fails, 2 on a
        usage error.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        try:
            print(run(args))
        except HoldError as error:
            print(f"on-hold.py: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        output = evaluate(payload) if isinstance(payload, dict) else None
    except Exception as error:  # noqa: BLE001 - a hook must never break the session
        print(f"call-it-a-day hold check: {error}", file=sys.stderr)
        return 0
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
