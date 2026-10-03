"""Tests for last-prompt.py.

The script runs as a subprocess against a throwaway HOME holding a transcript
built for each test, so no real session is ever read.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "last-prompt.py"
SID = "11111111-2222-3333-4444-555555555555"
OTHER_SID = "99999999-0000-0000-0000-000000000000"
HOME_PATH = re.compile(r"(?:/Users|/home)/(?!<)[A-Za-z0-9._-]+")

Record = dict[str, typing.Any]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a throwaway directory and set the session id."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    return tmp_path


def user(content: object, minute: int = 0, **extra: object) -> Record:
    """Build a user record with a timestamp ``minute`` minutes into the hour."""
    record: Record = {
        "type": "user",
        "timestamp": f"2026-10-03T12:{minute:02d}:00.000Z",
        "message": {"role": "user", "content": content},
    }
    record.update(extra)
    return record


def command(name: str, args: str = "", minute: int = 0) -> Record:
    """Build the record Claude Code writes for a typed slash command."""
    text = (
        f"<command-message>{name.lstrip('/')}</command-message>\n"
        f"<command-name>{name}</command-name>\n"
        f"<command-args>{args}</command-args>"
    )
    return user(text, minute)


def assistant(text: str) -> Record:
    """Build an assistant record."""
    content = [{"type": "text", "text": text}]
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def write_transcript(
    home: Path, records: list[Record], sid: str = SID, project: str = "demo"
) -> Path:
    """Write records as a session transcript under a project directory."""
    directory = home / ".claude" / "projects" / project
    directory.mkdir(parents=True, exist_ok=True)
    transcript = directory / f"{sid}.jsonl"
    transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
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


def prompts(stdout: str) -> list[str]:
    """Return the prompt bodies from the script's output, newest first."""
    bodies: list[str] = []
    for chunk in re.split(r"^--- .* ---$", stdout, flags=re.MULTILINE)[1:]:
        bodies.append(chunk.strip("\n"))
    return bodies


def test_returns_the_last_typed_prompt(home: Path) -> None:
    write_transcript(
        home,
        [
            user("add a dark mode toggle", 1),
            assistant("Done."),
            user("fix the footer", 2),
            assistant("Which one?"),
        ],
    )

    result = run()

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Last prompt sent, this session (11111111):\n")
    assert prompts(result.stdout) == ["fix the footer"]


def test_reads_text_blocks_as_typed_input(home: Path) -> None:
    blocks = [{"type": "text", "text": "fix the "}, {"type": "text", "text": "footer"}]
    write_transcript(home, [user(blocks, 1)])

    assert prompts(run().stdout) == ["fix the footer"]


@pytest.mark.parametrize("name", ["/promptfy", "/simplicity:promptfy"])
def test_skips_promptfy_itself(home: Path, name: str) -> None:
    write_transcript(
        home,
        [user("fix the footer", 1), command(name, "", 2), command(name, "x", 3)],
    )

    assert prompts(run().stdout) == ["fix the footer"]


def test_filters_tool_results(home: Path) -> None:
    result_block = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    mixed = [{"type": "text", "text": "not typed"}, result_block]
    write_transcript(
        home, [user("fix the footer", 1), user([result_block], 2), user(mixed, 3)]
    )

    assert prompts(run().stdout) == ["fix the footer"]


def test_strips_system_reminders(home: Path) -> None:
    reminder = "<system-reminder>\nToday is Saturday.\n</system-reminder>"
    write_transcript(
        home,
        [
            user(f"{reminder}\nfix the footer\n{reminder}", 1),
            user(reminder, 2),
        ],
    )

    assert prompts(run().stdout) == ["fix the footer"]


@pytest.mark.parametrize(
    "wrapper",
    [
        "<local-command-stdout>Compacted</local-command-stdout>",
        "<local-command-stderr>Error: no such model</local-command-stderr>",
        "<bash-stdout>total 0</bash-stdout>",
    ],
)
def test_filters_local_command_output(home: Path, wrapper: str) -> None:
    write_transcript(home, [user("fix the footer", 1), user(wrapper, 2)])

    assert prompts(run().stdout) == ["fix the footer"]


def test_filters_sidechain_and_meta_records(home: Path) -> None:
    write_transcript(
        home,
        [
            user("fix the footer", 1),
            user("You are rewriting a prompt.", 2, isSidechain=True),
            user("Caveat: the messages below were generated.", 3, isMeta=True),
        ],
    )

    assert prompts(run().stdout) == ["fix the footer"]


def test_renders_slash_commands_as_typed(home: Path) -> None:
    write_transcript(
        home,
        [
            command("/simplicity:just-say-it", "3", 1),
            command("/compact", "", 2),
        ],
    )

    assert prompts(run("-n", "2").stdout) == ["/compact", "/simplicity:just-say-it 3"]


def test_n_returns_that_many_prompts_newest_first(home: Path) -> None:
    write_transcript(home, [user(f"prompt {i}", i) for i in range(1, 6)])

    result = run("-n", "3")

    assert result.stdout.startswith("Last 3 prompts sent, this session (11111111):\n")
    assert prompts(result.stdout) == ["prompt 5", "prompt 4", "prompt 3"]


def test_n_larger_than_the_session_returns_what_exists(home: Path) -> None:
    write_transcript(home, [user("only one", 1)])

    assert prompts(run("-n", "5").stdout) == ["only one"]


def test_no_earlier_prompt_is_handled_cleanly(home: Path) -> None:
    write_transcript(home, [command("/simplicity:promptfy", "", 1), assistant("Hm.")])

    result = run()

    assert result.returncode == 0
    assert result.stdout.startswith("No earlier prompt found this session (11111111)")
    assert result.stderr == ""


def test_finds_a_prompt_behind_more_output_than_the_first_tail(home: Path) -> None:
    write_transcript(home, [user("fix the footer", 1), assistant("x" * 1_200_000)])

    assert prompts(run().stdout) == ["fix the footer"]


def test_skips_corrupt_lines(home: Path) -> None:
    transcript = write_transcript(home, [user("fix the footer", 1)])
    with transcript.open("a") as handle:
        handle.write('{"type":"user","message":\n[1, 2]\n"text"\n')

    assert prompts(run().stdout) == ["fix the footer"]


def test_session_flag_reads_that_session(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_transcript(home, [user("this session", 1)])
    write_transcript(home, [user("the other session", 2)], sid=OTHER_SID)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

    result = run("--session", OTHER_SID)

    assert result.returncode == 0, result.stderr
    assert prompts(result.stdout) == ["the other session"]


def test_all_searches_every_session(home: Path) -> None:
    write_transcript(home, [user("older", 1)], project="one")
    write_transcript(home, [user("newer", 2)], sid=OTHER_SID, project="two")

    result = run("--all", "-n", "2")

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Last 2 prompts sent, across all sessions:\n")
    assert prompts(result.stdout) == ["newer", "older"]
    assert "[session 99999999]" in result.stdout


def test_unset_session_id_fails(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_transcript(home, [user("fix the footer", 1)])
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

    result = run()

    assert result.returncode == 1
    assert "CLAUDE_CODE_SESSION_ID is not set" in result.stderr
    assert result.stdout == ""


def test_missing_transcript_fails(home: Path) -> None:
    result = run()

    assert result.returncode == 1
    assert f"No transcript on disk for session {SID}" in result.stderr
    assert result.stdout == ""


def test_all_without_any_transcript_fails(home: Path) -> None:
    result = run("--all")

    assert result.returncode == 1
    assert "No transcripts found" in result.stderr


@pytest.mark.parametrize("args", [(), ("-n", "3"), ("--all",), ("--session", SID)])
def test_never_writes_to_the_transcript(home: Path, args: tuple[str, ...]) -> None:
    transcript = write_transcript(
        home, [user("fix the footer", 1), command("/simplicity:promptfy", "", 2)]
    )
    before = (transcript.read_bytes(), transcript.stat().st_mtime_ns)
    tree = sorted(str(path) for path in home.rglob("*"))

    result = run(*args)

    assert result.returncode == 0, result.stderr
    assert (transcript.read_bytes(), transcript.stat().st_mtime_ns) == before
    assert sorted(str(path) for path in home.rglob("*")) == tree


def test_no_hardcoded_home_directory() -> None:
    """The published copy must not leak the author's machine."""
    for path in (SCRIPT, SKILL / "SKILL.md"):
        hits = HOME_PATH.findall(path.read_text())
        assert hits == [], f"{path.name} hardcodes a home directory {hits}"
