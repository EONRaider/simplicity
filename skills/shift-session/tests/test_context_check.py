"""Tests for context-check.py, the shift-session hook.

Every test runs against a throwaway HOME and a transcript built for it, and
``CLAUDE_PLUGIN_DATA`` is cleared, so no real session or plugin state is read
or written. The pure functions are loaded with importlib; the hook as a whole
runs as a subprocess, the way Claude Code runs it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
import typing
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "context-check.py"
SID = "11111111-2222-3333-4444-555555555555"

Record = dict[str, typing.Any]


def load() -> types.ModuleType:
    """Import the hook script as a module."""
    spec = importlib.util.spec_from_file_location("context_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = load()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a throwaway directory and clear the hook's env vars."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (
        "CLAUDE_PLUGIN_DATA",
        "SIMPLICITY_SHIFT_THRESHOLD",
        "SIMPLICITY_CONTEXT_WINDOW",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def assistant(tokens: int, model: str = "claude-sonnet-4-6", **extra: object) -> Record:
    """Build an assistant entry whose usage adds up to ``tokens``."""
    record: Record = {
        "type": "assistant",
        "isSidechain": False,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": 2,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": tokens - 2,
                "output_tokens": 0,
            },
        },
    }
    record.update(extra)
    return record


def write(home: Path, *records: Record) -> Path:
    """Write a transcript under the throwaway home."""
    path = home / ".claude" / "projects" / "demo" / f"{SID}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def hook(transcript: Path, event: str = "UserPromptSubmit", **extra: object) -> str:
    """Run the hook as a subprocess and return its stdout."""
    payload: Record = {
        "session_id": SID,
        "transcript_path": str(transcript),
        "hook_event_name": event,
    }
    payload.update(extra)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# ---------- threshold ----------


def test_threshold_defaults_to_60() -> None:
    assert cc.threshold({}) == 60


def test_threshold_env_override() -> None:
    assert cc.threshold({"SIMPLICITY_SHIFT_THRESHOLD": "45"}) == 45


@pytest.mark.parametrize("raw", ["", "abc", "101", "-5", "60.5"])
def test_threshold_rejects_bad_values(raw: str) -> None:
    assert cc.threshold({"SIMPLICITY_SHIFT_THRESHOLD": raw}) == 60


@pytest.mark.parametrize("raw", ["0", "off", "OFF", " off "])
def test_threshold_off_switch(raw: str) -> None:
    assert cc.threshold({"SIMPLICITY_SHIFT_THRESHOLD": raw}) == 0


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(0, 0), (59, 0), (60, 1), (61, 1), (69, 1), (70, 2), (85, 3), (100, 5)],
)
def test_band_below_at_and_above_default(percent: int, expected: int) -> None:
    assert cc.band(percent, 60) == expected


def test_band_follows_override() -> None:
    assert cc.band(44, 45) == 0
    assert cc.band(45, 45) == 1
    assert cc.band(60, 45) == 2


# ---------- window ----------


@pytest.mark.parametrize(
    ("model", "window"),
    [
        ("claude-opus-5-5", 1_000_000),
        ("claude-fable-5-1", 1_000_000),
        ("claude-opus-4-7", 1_000_000),
        ("claude-opus-6-0", 1_000_000),
        ("claude-sonnet-4-6[1m]", 1_000_000),
        ("claude-sonnet-4-6", 200_000),
        ("claude-haiku-4-5-20251001", 200_000),
        ("claude-opus-4-6", 200_000),
        ("claude-sonnet-5-20260101", 1_000_000),
        ("claude-opus-4-8-20251120", 1_000_000),
        (None, 200_000),
    ],
)
def test_window_from_model(model: str | None, window: int) -> None:
    assert cc.window_for(model, 1000, {}) == window


def test_window_grows_when_tokens_prove_it() -> None:
    assert cc.window_for("claude-sonnet-4-6", 250_000, {}) == 1_000_000


def test_window_env_override() -> None:
    env = {"SIMPLICITY_CONTEXT_WINDOW": "500000"}
    assert cc.window_for("claude-opus-5-5", 1000, env) == 500_000
    assert (
        cc.window_for("claude-opus-5-5", 1000, {"SIMPLICITY_CONTEXT_WINDOW": "x"})
        == 1_000_000
    )


# ---------- measurement ----------


def test_tokens_sum_all_four_fields() -> None:
    usage = {
        "input_tokens": 1,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 100,
        "output_tokens": 1000,
    }
    assert cc.context_tokens(usage) == 1111


def test_tokens_use_last_main_pass_not_advisor_sum() -> None:
    usage = {
        "input_tokens": 4,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 200_000,
        "output_tokens": 10,
        "iterations": [
            {
                "type": "message",
                "input_tokens": 2,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 100_000,
                "output_tokens": 5,
            },
            {
                "type": "advisor_message",
                "input_tokens": 9,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 9,
                "output_tokens": 9,
            },
            {
                "type": "message",
                "input_tokens": 2,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 100_100,
                "output_tokens": 5,
            },
        ],
    }
    assert cc.context_tokens(usage) == 100_107


def test_tokens_reject_malformed_usage() -> None:
    assert cc.context_tokens({"input_tokens": "lots"}) is None
    assert cc.context_tokens({"input_tokens": True}) is None


def test_last_usage_skips_sidechain_and_synthetic(home: Path) -> None:
    path = write(
        home,
        assistant(50_000),
        assistant(190_000, isSidechain=True),
        assistant(180_000, model="<synthetic>"),
        {"type": "user", "message": {"content": "x" * 5000}},
    )
    assert cc.last_usage(path) == (50_000, "claude-sonnet-4-6")


def test_last_usage_reads_across_chunks(home: Path) -> None:
    path = write(
        home, assistant(42_000), {"type": "user", "message": {"content": "y" * 9000}}
    )
    assert cc.last_usage(path, chunk=512) == (42_000, "claude-sonnet-4-6")


def test_last_usage_missing_or_empty(home: Path) -> None:
    assert cc.last_usage(home / "nope.jsonl") is None
    assert cc.last_usage(write(home, {"type": "user"})) is None


# ---------- the hook end to end ----------


def test_silent_below_threshold(home: Path) -> None:
    assert hook(write(home, assistant(119_000))) == ""


def test_fires_at_default_threshold(home: Path) -> None:
    out = json.loads(hook(write(home, assistant(120_000))))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "UserPromptSubmit"
    assert "60%" in spec["additionalContext"]
    assert "shift-session" in spec["additionalContext"]
    assert "--auto" in spec["additionalContext"]
    assert "Before you continue" in spec["additionalContext"]


def test_fires_above_threshold_on_post_tool_use(home: Path) -> None:
    out = json.loads(hook(write(home, assistant(150_000)), event="PostToolUse"))
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "75%" in out["hookSpecificOutput"]["additionalContext"]


def test_env_override_changes_when_it_fires(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(home, assistant(100_000))
    assert hook(path) == ""
    monkeypatch.setenv("SIMPLICITY_SHIFT_THRESHOLD", "50")
    assert "50% shift threshold" in hook(path)


def test_one_model_window_from_transcript(home: Path) -> None:
    assert hook(write(home, assistant(150_000, model="claude-opus-5-5"))) == ""


def test_fires_once_per_band_then_rearms(home: Path) -> None:
    path = write(home, assistant(121_000))
    assert hook(path) != ""
    assert hook(path) == ""
    assert hook(write(home, assistant(130_000))) == ""
    assert hook(write(home, assistant(141_000))) != ""
    assert hook(write(home, assistant(20_000))) == ""
    assert hook(write(home, assistant(121_000))) != ""


def test_state_lives_under_home_or_plugin_data(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook(write(home, assistant(121_000)))
    assert (home / ".claude" / "simplicity" / "shift-session" / f"{SID}.json").is_file()
    data = home / "plugin-data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    hook(write(home, assistant(121_000)))
    assert (data / "shift-session" / f"{SID}.json").is_file()


def test_silent_for_subagents_and_other_events(home: Path) -> None:
    path = write(home, assistant(190_000))
    assert hook(path, agent_id="abc") == ""
    assert hook(path, event="Stop") == ""


@pytest.mark.parametrize(
    "stdin", ["", "not json", "[]", '{"hook_event_name": "UserPromptSubmit"}']
)
def test_bad_input_never_fails(home: Path, stdin: str) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_missing_transcript_is_silent(home: Path) -> None:
    assert hook(home / "missing.jsonl") == ""


def test_off_switch_silences_the_hook(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMPLICITY_SHIFT_THRESHOLD", "off")
    assert hook(write(home, assistant(190_000))) == ""


def test_silent_on_the_shift_command_itself(home: Path) -> None:
    path = write(home, assistant(150_000))
    assert hook(path, prompt="  /simplicity:shift-session --pr") == ""
    assert hook(path, prompt="keep going") != ""


def test_silent_after_handoff_marker(home: Path) -> None:
    path = write(home, assistant(121_000))
    cc.mark_handed_off(SID)
    marker = home / ".claude" / "simplicity" / "shift-session" / f"{SID}.handed-off"
    assert marker.is_file()
    assert hook(path) == ""
    assert hook(write(home, assistant(190_000))) == ""


def test_mark_handed_off_cli_uses_session_env(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--mark-handed-off"],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (
        home / ".claude" / "simplicity" / "shift-session" / f"{SID}.handed-off"
    ).is_file()
    assert hook(write(home, assistant(150_000))) == ""


def test_mark_handed_off_cli_needs_a_session(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--mark-handed-off"],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert not (home / ".claude" / "simplicity").exists()
