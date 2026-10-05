#!/usr/bin/env python3
"""Suggest a session shift once context use reaches a threshold.

A plugin hook for ``UserPromptSubmit`` and ``PostToolUse``. It reads the hook
input on stdin, works out how full the session's context window is from the
transcript at ``transcript_path``, and, when use reaches the threshold, prints a
``hookSpecificOutput.additionalContext`` line asking the model to suggest
``/simplicity:shift-session``. Below the threshold it prints nothing.

Why the transcript: no hook input carries context usage or the model's window
size (checked on Claude Code 2.1.284; only the status line sees them). The
transcript's last main-chain assistant entry carries ``message.usage`` and
``message.model``, so this script sums the usage and maps the model to its
window.

The measurement is ported from the maintainer's own context-pressure hook,
which in turn ports Claude Code's own count:

- **Which entry.** The last ``type: assistant`` entry that isn't a sidechain,
  isn't ``isUnmetered`` and whose model isn't ``<synthetic>``.
- **Which pass.** A response that called a server-side tool such as
  ``advisor`` lists several passes in ``usage.iterations``, and the top-level
  numbers add them up, so one advisor call roughly doubles them. The count
  uses the last pass that isn't an ``advisor_message`` or ``compaction``, and
  falls back to the top level when there is no valid pass.
- **What sum.** Input, cache-read, cache-creation and output tokens.

The threshold is ``SIMPLICITY_SHIFT_THRESHOLD`` (a percent, default 60; ``0``
or ``off`` turns the hook off). The window is ``SIMPLICITY_CONTEXT_WINDOW``
when set, else read from the model id, with any ``-YYYYMMDD`` date suffix
dropped. Verified 1M ids: ``claude-opus-5-5`` (the app's usage tool reported a
1,000,000-token window), and ``claude-sonnet-5``, ``claude-opus-5`` and
``claude-opus-4-8`` (local transcripts held more than 200,000 tokens). The
Fable ids and ``claude-sonnet-5-5`` are listed as 1M without that check. Any
other id counts as 200,000 until the tokens in context exceed that.
A suggestion fires once per 10-point band at or above the threshold (60, 70,
80, ...), so declining one doesn't silence the next. When use drops below a
band again, after a compaction for instance, the band re-arms.

The hook stays silent on the prompt that runs ``/simplicity:shift-session``,
and for good once a shift has handed the session off: the skill runs
``context-check.py --mark-handed-off``, which writes
``~/.claude/simplicity/shift-session/<session id>.handed-off``. The session id
comes from ``$CLAUDE_CODE_SESSION_ID``, which matches the hook input's
``session_id`` in a normal session.

State is one small JSON file per session under ``$CLAUDE_PLUGIN_DATA`` when
the plugin host sets it, else under ``~/.claude/simplicity/shift-session``.
Every path exits 0: a hook that can't measure stays silent rather than
blocking the session.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

THRESHOLD_ENV = "SIMPLICITY_SHIFT_THRESHOLD"
WINDOW_ENV = "SIMPLICITY_CONTEXT_WINDOW"
DEFAULT_THRESHOLD = 60
BAND_STEP = 10
SMALL_WINDOW = 200_000
LARGE_WINDOW = 1_000_000
READ_BUDGET_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 1 << 20
EVENTS = ("UserPromptSubmit", "PostToolUse")

USAGE_FIELDS = (
    "input_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "output_tokens",
)
SKIPPED_PASSES = frozenset({"advisor_message", "compaction"})
CONTEXT_PASSES = frozenset({"message", "fallback_message"})
SYNTHETIC_MODEL = "<synthetic>"

LARGE_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
    }
)
OPUS_VERSION = re.compile(r"^claude-opus-(\d+)-(\d+)")
UNSAFE_ID = re.compile(r"[^A-Za-z0-9_-]")
DATE_SUFFIX = re.compile(r"-\d{8}$")
COMMAND = "/simplicity:shift-session"
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
OFF = 0


def threshold(env: Mapping[str, str]) -> int:
    """Return the threshold percent.

    Args:
        env: The environment to read ``SIMPLICITY_SHIFT_THRESHOLD`` from.

    Returns:
        0 (off) when the env value is ``0`` or ``off``, the env value when it
        is a whole number from 1 to 100, else 60.
    """
    raw = env.get(THRESHOLD_ENV, "").strip().lower()
    if raw in ("0", "off"):
        return OFF
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_THRESHOLD
    return value if 1 <= value <= 100 else DEFAULT_THRESHOLD


def window_for(model: str | None, tokens: int, env: Mapping[str, str]) -> int:
    """Return the context window, in tokens, the session runs with.

    Args:
        model: The ``message.model`` of the last assistant entry, if any.
        tokens: The tokens in context now. More than 200,000 proves a 1M window.
        env: The environment to read ``SIMPLICITY_CONTEXT_WINDOW`` from.

    Returns:
        The env override when it is a positive whole number. Otherwise
        1,000,000 for ids ending in ``[1m]``, for the 1M models in
        ``LARGE_MODELS``, for Opus 4.7 and later, and whenever ``tokens``
        already exceeds 200,000; else 200,000.
    """
    raw = env.get(WINDOW_ENV, "").strip()
    try:
        override = int(raw)
    except ValueError:
        override = 0
    if override > 0:
        return override
    name = (model or "").lower()
    base = DATE_SUFFIX.sub("", name.removesuffix("[1m]"))
    match = OPUS_VERSION.match(base)
    version = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    large_opus = version >= (4, 7)
    if name.endswith("[1m]") or base in LARGE_MODELS or large_opus:
        return LARGE_WINDOW
    return LARGE_WINDOW if tokens > SMALL_WINDOW else SMALL_WINDOW


def is_count(value: object) -> bool:
    """Return whether a value is a token count: a non-negative int, not a bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def context_pass(usage: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the pass whose numbers are the context, or None for the top level.

    Args:
        usage: A ``message.usage`` object.

    Returns:
        The last ``usage.iterations`` element that isn't an advisor or
        compaction pass, when it is a valid main-model pass with a nonzero
        input side; else None.
    """
    passes = usage.get("iterations")
    if not isinstance(passes, list):
        return None
    chosen = next(
        (
            p
            for p in reversed(passes)
            if not (isinstance(p, dict) and p.get("type") in SKIPPED_PASSES)
        ),
        None,
    )
    if not isinstance(chosen, dict) or chosen.get("type") not in CONTEXT_PASSES:
        return None
    if not all(is_count(chosen.get(key)) for key in USAGE_FIELDS):
        return None
    if sum(chosen[key] for key in USAGE_FIELDS[:3]) <= 0:
        return None
    return chosen


def context_tokens(usage: Mapping[str, Any]) -> int | None:
    """Return the tokens in context according to one ``message.usage``.

    Args:
        usage: A ``message.usage`` object.

    Returns:
        Input, cache-read, cache-creation and output tokens of the main
        model's last pass, missing keys counting as 0, or None when a present
        key isn't a token count.
    """
    top: dict[str, int] = {}
    for key in USAGE_FIELDS:
        value = usage.get(key, 0)
        if not is_count(value):
            return None
        top[key] = value
    source: Mapping[str, Any] = top
    if sum(top[key] for key in USAGE_FIELDS[:3]) > 0:
        source = context_pass(usage) or top
    return sum(int(source[key]) for key in USAGE_FIELDS)


def read_line(line: bytes) -> tuple[int, str | None] | None:
    """Return (tokens, model) for a usable assistant line, else None.

    Args:
        line: One raw transcript line.

    Returns:
        The line's context tokens and model, or None when the line isn't a
        usable main-chain assistant entry.
    """
    if b'"assistant"' not in line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return None
    if entry.get("isSidechain") is True or entry.get("isUnmetered") is True:
        return None
    message = entry.get("message")
    if not isinstance(message, dict) or message.get("model") == SYNTHETIC_MODEL:
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    tokens = context_tokens(usage)
    if tokens is None:
        return None
    model = message.get("model")
    return tokens, model if isinstance(model, str) else None


def last_usage(
    path: Path, budget: int = READ_BUDGET_BYTES, chunk: int = CHUNK_BYTES
) -> tuple[int, str | None] | None:
    """Scan a transcript backward for the last usable assistant entry.

    Only lines that contain ``"assistant"`` are parsed, so a large tool
    result between that entry and the end of the file is skipped cheaply.

    Args:
        path: The transcript ``.jsonl``.
        budget: The most bytes to read before giving up.
        chunk: The size of each backward read.

    Returns:
        (tokens, model) for the entry, or None when the file is missing or
        holds no usable entry within the budget.
    """
    try:
        with path.open("rb") as handle:
            pos = handle.seek(0, os.SEEK_END)
            read = 0
            carry = b""
            while pos > 0 and read < budget:
                size = min(chunk, pos, budget - read)
                pos -= size
                handle.seek(pos)
                parts = (handle.read(size) + carry).split(b"\n")
                read += size
                carry = parts[0]
                for line in reversed(parts[1:]):
                    found = read_line(line)
                    if found:
                        return found
            return read_line(carry) if pos == 0 else None
    except OSError:
        return None


def band(percent: int, limit: int) -> int:
    """Return the band a percent falls in: 0 below the threshold, then 1, 2, ...

    Args:
        percent: Context use, in percent of the window.
        limit: The threshold percent.

    Returns:
        0 below ``limit``, 1 from ``limit``, 2 from ``limit + 10``, and so on.
    """
    return 0 if percent < limit else 1 + (percent - limit) // BAND_STEP


def state_file(session_id: str, env: Mapping[str, str]) -> Path:
    """Return the state file for a session.

    Args:
        session_id: The hook input's ``session_id``.
        env: The environment to read ``CLAUDE_PLUGIN_DATA`` from.

    Returns:
        ``<data>/shift-session/<id>.json``, where ``<data>`` is
        ``$CLAUDE_PLUGIN_DATA`` or ``~/.claude/simplicity``.
    """
    data = env.get("CLAUDE_PLUGIN_DATA") or str(Path.home() / ".claude" / "simplicity")
    safe = UNSAFE_ID.sub("_", session_id)[:200] or "session"
    return Path(data) / "shift-session" / f"{safe}.json"


def stored_band(path: Path) -> int:
    """Return the band last stored for a session, 0 when there is none."""
    try:
        value = json.loads(path.read_text()).get("band", 0)
    except (OSError, ValueError, AttributeError):
        return 0
    return value if is_count(value) else 0


def store_band(path: Path, value: int) -> None:
    """Write a session's band atomically. A failure to write is ignored."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump({"band": value}, handle)
        os.replace(handle.name, path)
    except OSError:
        pass


def marker_file(session_id: str) -> Path:
    """Return the file whose presence means a session was handed off.

    It lives under the home directory, never ``$CLAUDE_PLUGIN_DATA``, because
    the skill's own shell may not see that variable.
    """
    safe = UNSAFE_ID.sub("_", session_id)[:200] or "session"
    base = Path.home() / ".claude" / "simplicity" / "shift-session"
    return base / f"{safe}.handed-off"


def mark_handed_off(session_id: str) -> Path:
    """Record that a session was handed off, so the hook stays silent in it.

    Args:
        session_id: The session to mark.

    Returns:
        The marker file written.
    """
    path = marker_file(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("handed off\n")
    return path


def message(tokens: int, window: int, percent: int, limit: int) -> str:
    """Return the text added to the model's context when a band is crossed."""
    return (
        f"simplicity: this session's context is about {percent}% full "
        f"({tokens:,} of {window:,} tokens), at or above the "
        f"{limit}% shift threshold. Before you continue with the user's "
        "request, invoke the simplicity:shift-session skill with the argument "
        "--auto, unless a shift is already running. It asks the user once "
        "before it commits, pushes or hands off anything. If the app's own "
        "usage tool reports the context below the threshold, skip this and "
        "say nothing about it."
    )


def evaluate(payload: Mapping[str, Any], env: Mapping[str, str]) -> str | None:
    """Decide what, if anything, a hook call adds to the context.

    Args:
        payload: The parsed hook input.
        env: The process environment.

    Returns:
        The hook's stdout JSON, or None to stay silent.
    """
    event = payload.get("hook_event_name")
    if event not in EVENTS or payload.get("agent_id"):
        return None
    session_id = payload.get("session_id")
    transcript = payload.get("transcript_path")
    if not isinstance(session_id, str) or not isinstance(transcript, str):
        return None
    limit = threshold(env)
    prompt = payload.get("prompt")
    if limit == OFF or marker_file(session_id).exists():
        return None
    if isinstance(prompt, str) and prompt.lstrip().startswith(COMMAND):
        return None
    found = last_usage(Path(transcript))
    if found is None:
        return None
    tokens, model = found
    window = window_for(model, tokens, env)
    percent = tokens * 100 // window
    now = band(percent, limit)
    path = state_file(session_id, env)
    before = stored_band(path)
    if now != before:
        store_band(path, now)
    if now <= before:
        return None
    text = message(tokens, window, percent, limit)
    output = {"hookEventName": event, "additionalContext": text}
    return json.dumps({"hookSpecificOutput": output})


def main(argv: list[str] | None = None) -> int:
    """Run the hook: read stdin, maybe print a suggestion, always exit 0.

    With ``--mark-handed-off [session_id]`` it marks the session (default
    ``$CLAUDE_CODE_SESSION_ID``) as handed off instead, and exits 1 when no
    session id is known.
    """
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--mark-handed-off":
        session_id = args[1] if len(args) > 1 else os.environ.get(SESSION_ENV, "")
        if not session_id:
            print(f"--mark-handed-off: {SESSION_ENV} not set", file=sys.stderr)
            return 1
        print(f"marked {mark_handed_off(session_id)}")
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        output = evaluate(payload, os.environ) if isinstance(payload, dict) else None
    except Exception as error:  # noqa: BLE001 - a hook must never break the session
        print(f"shift-session context check: {error}", file=sys.stderr)
        return 0
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
