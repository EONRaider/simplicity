"""Tests for rename-session.py.

The script runs as a subprocess against a throwaway HOME, so no real session
is ever renamed. ``test_writes_transcript_line_and_sidecar`` and
``test_no_hardcoded_home_directory`` are ported from voidharbor's
``rename-session/tests/test_bundle_sync.py`` (MIT, Copyright (c) 2026
voidharbor).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "rename-session.py"
SID = "11111111-2222-3333-4444-555555555555"
SEED = '{"type":"user"}\n'
HOME_PATH = re.compile(r"(?:/Users|/home)/(?!<)[A-Za-z0-9._-]+")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a throwaway directory and set the session id."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    return tmp_path


def make_transcript(home: Path, project: str = "demo") -> Path:
    """Create a one-line transcript for SID under a project directory."""
    directory = home / ".claude" / "projects" / project
    directory.mkdir(parents=True)
    transcript = directory / f"{SID}.jsonl"
    transcript.write_text(SEED)
    return transcript


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the script with the current (monkeypatched) environment."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_writes_transcript_line_and_sidecar(home: Path) -> None:
    """The rename is only real if BOTH writes land."""
    transcript = make_transcript(home)

    result = run("CHECKOUT RETRY BUG")

    assert result.returncode == 0, result.stderr
    record = json.loads(transcript.read_text().strip().split("\n")[-1])
    assert record == {
        "type": "custom-title",
        "customTitle": "CHECKOUT RETRY BUG",
        "sessionId": SID,
    }
    sidecar = json.loads((transcript.with_suffix("") / "custom-title.json").read_text())
    assert sidecar == {"customTitle": "CHECKOUT RETRY BUG"}


def test_writes_use_the_exact_compact_format(home: Path) -> None:
    transcript = make_transcript(home)

    result = run("CHECKOUT RETRY BUG")

    assert result.returncode == 0, result.stderr
    line = (
        '{"type":"custom-title","customTitle":"CHECKOUT RETRY BUG",'
        f'"sessionId":"{SID}"}}\n'
    )
    assert transcript.read_text() == SEED + line
    sidecar = transcript.with_suffix("") / "custom-title.json"
    assert sidecar.read_text() == '{"customTitle":"CHECKOUT RETRY BUG"}'


def test_prints_a_one_line_confirmation(home: Path) -> None:
    make_transcript(home)

    result = run("CHECKOUT RETRY BUG")

    assert result.stdout == "renamed session 11111111 -> CHECKOUT RETRY BUG\n"
    assert result.stderr == ""


def test_joins_several_arguments_into_one_title(home: Path) -> None:
    transcript = make_transcript(home)

    result = run("CI", "MATRIX", "MIGRATION")

    assert result.returncode == 0, result.stderr
    record = json.loads(transcript.read_text().splitlines()[-1])
    assert record["customTitle"] == "CI MATRIX MIGRATION"


def test_a_second_rename_appends_and_replaces_the_sidecar(home: Path) -> None:
    transcript = make_transcript(home)

    run("FIRST TITLE")
    run("SECOND TITLE")

    lines = transcript.read_text().splitlines()
    assert len(lines) == 3
    assert [json.loads(line).get("customTitle") for line in lines[1:]] == [
        "FIRST TITLE",
        "SECOND TITLE",
    ]
    sidecar = transcript.with_suffix("") / "custom-title.json"
    assert json.loads(sidecar.read_text()) == {"customTitle": "SECOND TITLE"}


@pytest.mark.parametrize("args", [(), ("",), ("   ",)])
def test_missing_or_empty_title_fails(home: Path, args: tuple[str, ...]) -> None:
    transcript = make_transcript(home)

    result = run(*args)

    assert result.returncode != 0
    assert "usage" in result.stderr
    assert result.stdout == ""
    assert transcript.read_text() == SEED
    assert not transcript.with_suffix("").exists()


def test_unset_session_id_fails(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = make_transcript(home)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

    result = run("CHECKOUT RETRY BUG")

    assert result.returncode != 0
    assert "CLAUDE_CODE_SESSION_ID" in result.stderr
    assert transcript.read_text() == SEED
    assert not transcript.with_suffix("").exists()


def test_no_matching_transcript_fails_and_writes_nothing(home: Path) -> None:
    projects = home / ".claude" / "projects" / "demo"
    projects.mkdir(parents=True)
    other = projects / "99999999-0000-0000-0000-000000000000.jsonl"
    other.write_text(SEED)

    result = run("CHECKOUT RETRY BUG")

    assert result.returncode != 0
    assert "found 0" in result.stderr
    assert other.read_text() == SEED
    assert sorted(path.name for path in projects.iterdir()) == [other.name]


def test_two_matching_transcripts_fail_and_write_nothing(home: Path) -> None:
    first = make_transcript(home, "demo")
    second = make_transcript(home, "demo-worktree")

    result = run("CHECKOUT RETRY BUG")

    assert result.returncode != 0
    assert "found 2" in result.stderr
    for transcript in (first, second):
        assert transcript.read_text() == SEED
        assert not transcript.with_suffix("").exists()


def test_no_hardcoded_home_directory() -> None:
    """The published copy must not leak the author's machine."""
    for path in (SCRIPT, SKILL / "SKILL.md"):
        hits = HOME_PATH.findall(path.read_text())
        assert hits == [], f"{path.name} hardcodes a home directory {hits}"
