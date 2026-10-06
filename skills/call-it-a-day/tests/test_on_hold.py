"""Tests for on-hold.py, call-it-a-day's hold record and resume hook.

Every test runs against a throwaway HOME, so no real session, transcript or
hold record is read or written. The functions are loaded with importlib; the
hook and the subcommands also run as a subprocess, the way Claude Code and the
skill run them.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
import typing
from datetime import datetime, timezone
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "on-hold.py"
SID = "11111111-2222-3333-4444-555555555555"
NOW = datetime(2026, 10, 6, 18, 30, tzinfo=timezone.utc)

Record = dict[str, typing.Any]


def load() -> types.ModuleType:
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("on_hold", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oh = load()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a throwaway directory and clear the session id."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return tmp_path


def run(
    home: Path, *args: str, stdin: str = "", session: str | None = SID
) -> subprocess.CompletedProcess[str]:
    """Run the script as a subprocess with the throwaway HOME."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
    env["HOME"] = str(home)
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def hook_input(prompt: str = "morning, let's continue", **extra: object) -> str:
    """Build a UserPromptSubmit hook input for the test session."""
    payload: Record = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": SID,
        "transcript_path": "/nonexistent.jsonl",
        "prompt": prompt,
    }
    payload.update(extra)
    return json.dumps(payload)


def transcript(home: Path, *records: Record, session: str = SID) -> Path:
    """Write a session transcript under the throwaway home."""
    path = home / ".claude" / "projects" / "-home-me-code" / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


# ---------- record paths ----------
def test_record_file_lives_under_home(home: Path) -> None:
    assert (
        oh.record_file(SID)
        == home / ".claude" / "simplicity" / "call-it-a-day" / f"{SID}.json"
    )


def test_record_file_sanitizes_the_session_id(home: Path) -> None:
    path = oh.record_file("../../etc/passwd")
    assert path.parent == oh.record_dir()
    assert path.name == "______etc_passwd.json"


def test_record_file_of_an_empty_id_has_a_name(home: Path) -> None:
    assert oh.record_file("").name == "session.json"


# ---------- hold ----------
def test_hold_writes_the_record(home: Path) -> None:
    path, record = oh.hold(SID, "CSV importer", "CSV importer", None, NOW)
    assert path.is_file()
    saved = json.loads(path.read_text())
    assert saved == record
    assert saved["title"] == "CSV importer"
    assert saved["on_hold_title"] == "CSV importer -> On hold"
    assert saved["held_at"] == "2026-10-06T18:30:00+00:00"
    assert saved["handoff"] is None and saved["handoff_path"] is None


def test_hold_strips_whitespace(home: Path) -> None:
    _, record = oh.hold(SID, "  CSV importer ", " CSV importer\n", None, NOW)
    assert record["title"] == "CSV importer"
    assert record["on_hold_title"] == "CSV importer -> On hold"


def test_hold_copies_the_handoff_note(home: Path) -> None:
    note = home / "memory" / "on-hold-csv-importer.md"
    note.parent.mkdir()
    note.write_text("## Goal\nImport CSVs.\n")
    _, record = oh.hold(SID, "CSV importer", "CSV importer", str(note), NOW)
    assert record["handoff_path"] == str(note.resolve())
    assert record["handoff"] == "## Goal\nImport CSVs.\n"


def test_hold_keeps_the_first_pre_hold_title(home: Path) -> None:
    oh.hold(SID, "CSV importer -> Part 2", "CSV importer", None, NOW)
    _, record = oh.hold(SID, "CSV importer -> On hold", "CSV importer", None, NOW)
    assert record["title"] == "CSV importer -> Part 2"


def test_hold_replaces_an_unreadable_record(home: Path) -> None:
    path = oh.record_file(SID)
    path.parent.mkdir(parents=True)
    path.write_text("not json")
    _, record = oh.hold(SID, "CSV importer", "CSV importer", None, NOW)
    assert record["title"] == "CSV importer"


@pytest.mark.parametrize(("title", "topic"), [("", "x"), ("x", "  "), (" ", "")])
def test_hold_refuses_a_blank_title_or_topic(
    home: Path, title: str, topic: str
) -> None:
    with pytest.raises(oh.HoldError):
        oh.hold(SID, title, topic, None, NOW)
    assert not oh.record_file(SID).exists()


def test_hold_refuses_a_missing_note(home: Path) -> None:
    with pytest.raises(oh.HoldError, match="can't read"):
        oh.hold(SID, "t", "t", str(home / "missing.md"), NOW)
    assert not oh.record_file(SID).exists()


def test_hold_refuses_a_huge_note(home: Path) -> None:
    note = home / "big.md"
    note.write_text("x" * (oh.HANDOFF_LIMIT + 1))
    with pytest.raises(oh.HoldError, match="256 KiB"):
        oh.hold(SID, "t", "t", str(note), NOW)


def test_save_leaves_no_temp_files(home: Path) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    assert [p.name for p in oh.record_dir().iterdir()] == [f"{SID}.json"]


# ---------- load and resume ----------
def test_load_without_a_record_is_none(home: Path) -> None:
    assert oh.load(SID) is None


@pytest.mark.parametrize("content", ["[]", '{"title": 3}', "{}", "garbage"])
def test_load_of_a_bad_record_is_none(home: Path, content: str) -> None:
    path = oh.record_file(SID)
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert oh.load(SID) is None


def test_resume_returns_the_title_and_clears_the_record(home: Path) -> None:
    oh.hold(SID, "CSV importer", "CSV importer", None, NOW)
    assert oh.resume(SID) == "CSV importer"
    assert not oh.record_file(SID).exists()


def test_resume_without_a_record_fails(home: Path) -> None:
    with pytest.raises(oh.HoldError, match="no hold record"):
        oh.resume(SID)


def test_resume_leaves_other_sessions_alone(home: Path) -> None:
    other = "99999999-0000-0000-0000-000000000000"
    oh.hold(SID, "a", "a", None, NOW)
    oh.hold(other, "b", "b", None, NOW)
    oh.resume(SID)
    assert oh.load(other) is not None


# ---------- CLI title ----------
def test_cli_title_reads_the_last_custom_title(home: Path) -> None:
    transcript(
        home,
        {"type": "user", "message": {"content": "custom-title"}},
        {"type": "custom-title", "customTitle": "First", "sessionId": SID},
        {"type": "assistant", "message": {}},
        {"type": "custom-title", "customTitle": "CSV importer", "sessionId": SID},
    )
    assert oh.cli_title(SID) == "CSV importer"


def test_cli_title_without_a_title_is_none(home: Path) -> None:
    transcript(home, {"type": "user", "message": {"content": "hi"}})
    assert oh.cli_title(SID) is None


def test_cli_title_without_a_transcript_is_none(home: Path) -> None:
    assert oh.cli_title(SID) is None


def test_cli_title_with_two_transcripts_is_none(home: Path) -> None:
    transcript(home, {"type": "custom-title", "customTitle": "A"})
    other = home / ".claude" / "projects" / "-other" / f"{SID}.jsonl"
    other.parent.mkdir(parents=True)
    other.write_text(json.dumps({"type": "custom-title", "customTitle": "B"}) + "\n")
    assert oh.cli_title(SID) is None


def test_cli_title_skips_hidden_projects(home: Path) -> None:
    transcript(home, {"type": "custom-title", "customTitle": "Visible"})
    hidden = home / ".claude" / "projects" / ".trash" / f"{SID}.jsonl"
    hidden.parent.mkdir(parents=True)
    hidden.write_text(
        json.dumps({"type": "custom-title", "customTitle": "Hidden"}) + "\n"
    )
    assert oh.cli_title(SID) == "Visible"


def test_cli_title_skips_bad_lines(home: Path) -> None:
    path = transcript(home, {"type": "custom-title", "customTitle": "Good"})
    with path.open("a") as handle:
        handle.write('{"type": "custom-title", broken\n')
        handle.write('["custom-title"]\n')
        handle.write(json.dumps({"type": "custom-title", "customTitle": 5}) + "\n")
    assert oh.cli_title(SID) == "Good"


# ---------- hook ----------
def test_hook_is_silent_without_a_record(home: Path) -> None:
    assert oh.evaluate(json.loads(hook_input())) is None


def test_hook_reports_the_hold(home: Path) -> None:
    oh.hold(SID, "CSV importer -> Part 2", "CSV importer", None, NOW)
    out = json.loads(oh.evaluate(json.loads(hook_input())))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "UserPromptSubmit"
    text = spec["additionalContext"]
    assert '"CSV importer -> Part 2"' in text
    assert '"CSV importer -> On hold"' in text
    assert "rename-session.py" in text
    assert f"{oh.SCRIPT} resume" in text or "on-hold.py resume" in text
    assert "acknowledges" in text
    assert "handoff note" not in text


def test_hook_names_the_note_to_delete(home: Path) -> None:
    note = home / "on-hold-csv.md"
    note.write_text("handoff")
    oh.hold(SID, "CSV importer", "CSV importer", str(note), NOW)
    text = json.loads(oh.evaluate(json.loads(hook_input())))["hookSpecificOutput"][
        "additionalContext"
    ]
    assert str(note.resolve()) in text


def test_hook_quotes_titles_for_the_shell(home: Path) -> None:
    oh.hold(SID, "Bob's $HOME `fix`", "Bob's fix", None, NOW)
    text = oh.message(oh.load(SID))
    assert "'Bob'\"'\"'s $HOME `fix`'" in text


@pytest.mark.parametrize(
    "prompt",
    [
        "/simplicity:call-it-a-day",
        "/simplicity:call-it-a-day --pr",
        "ok run call-it-a-day again",
    ],
)
def test_hook_is_silent_on_another_hold(home: Path, prompt: str) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    assert oh.evaluate(json.loads(hook_input(prompt))) is None


def test_hook_is_silent_in_subagents(home: Path) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    assert oh.evaluate(json.loads(hook_input(agent_id="a1"))) is None


@pytest.mark.parametrize("event", ["PostToolUse", "SessionStart", None])
def test_hook_is_silent_on_other_events(home: Path, event: str | None) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    assert oh.evaluate(json.loads(hook_input(hook_event_name=event))) is None


@pytest.mark.parametrize("session", [None, "", 7])
def test_hook_is_silent_without_a_session(home: Path, session: object) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    assert oh.evaluate(json.loads(hook_input(session_id=session))) is None


def test_hook_ignores_other_sessions(home: Path) -> None:
    oh.hold("someone-else", "t", "t", None, NOW)
    assert oh.evaluate(json.loads(hook_input())) is None


def test_hook_works_without_a_prompt_field(home: Path) -> None:
    oh.hold(SID, "t", "t", None, NOW)
    payload = json.loads(hook_input())
    del payload["prompt"]
    assert oh.evaluate(payload) is not None


# ---------- as a subprocess ----------
def test_main_hook_prints_nothing_without_a_record(home: Path) -> None:
    proc = run(home, stdin=hook_input())
    assert proc.returncode == 0 and proc.stdout == ""


def test_main_hook_prints_the_note(home: Path) -> None:
    oh.hold(SID, "CSV importer", "CSV importer", None, NOW)
    proc = run(home, stdin=hook_input())
    assert proc.returncode == 0
    assert (
        "CSV importer"
        in json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    )


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]", "null"])
def test_main_hook_survives_bad_input(home: Path, stdin: str) -> None:
    proc = run(home, stdin=stdin)
    assert proc.returncode == 0 and proc.stdout == ""


def test_main_hold_show_resume_round_trip(home: Path) -> None:
    note = home / "note.md"
    note.write_text("## Goal\nship it\n")
    proc = run(
        home,
        "hold",
        "--title",
        "CSV importer",
        "--topic",
        "CSV importer",
        "--handoff",
        str(note),
    )
    assert proc.returncode == 0, proc.stderr
    assert "on hold:" in proc.stdout
    shown = run(home, "show")
    assert shown.returncode == 0
    assert json.loads(shown.stdout)["handoff"] == "## Goal\nship it\n"
    resumed = run(home, "resume")
    assert resumed.returncode == 0 and resumed.stdout.strip() == "CSV importer"
    assert run(home, "show").returncode == 1


def test_main_session_flag_overrides_the_env(home: Path) -> None:
    proc = run(home, "hold", "--title", "t", "--topic", "t", "--session", "other-id")
    assert proc.returncode == 0
    assert oh.load("other-id") is not None
    assert oh.load(SID) is None


def test_main_without_a_session_id_fails(home: Path) -> None:
    proc = run(home, "hold", "--title", "t", "--topic", "t", session=None)
    assert proc.returncode == 1
    assert "CLAUDE_CODE_SESSION_ID" in proc.stderr
    assert not oh.record_dir().exists()


def test_main_resume_without_a_record_fails(home: Path) -> None:
    proc = run(home, "resume")
    assert proc.returncode == 1 and "no hold record" in proc.stderr


def test_main_title(home: Path) -> None:
    transcript(home, {"type": "custom-title", "customTitle": "CSV importer"})
    proc = run(home, "title")
    assert proc.returncode == 0 and proc.stdout.strip() == "CSV importer"


def test_main_title_without_one_fails(home: Path) -> None:
    proc = run(home, "title")
    assert proc.returncode == 1


def test_main_bad_hold_fails_cleanly(home: Path) -> None:
    proc = run(
        home, "hold", "--title", "t", "--topic", "t", "--handoff", str(home / "nope.md")
    )
    assert proc.returncode == 1 and "can't read" in proc.stderr


def test_main_usage_error_exits_2(home: Path) -> None:
    proc = run(home, "frobnicate")
    assert proc.returncode == 2


def test_main_in_process_returns_status(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    assert oh.main(["resume"]) == 1
    assert oh.main(["hold", "--title", "t", "--topic", "t"]) == 0
    assert oh.main(["resume"]) == 0


def test_rename_helper_path_points_at_rename_session() -> None:
    assert oh.RENAME_HELPER.is_file()
