"""Checks on the Windows launchers RUN_PROJECT.bat, STOP_PROJECT.bat and CHECK_ENVIRONMENT.bat.

IMPORTANT - what these tests are and are not.
They are NOT a run on Windows (nothing here can run cmd.exe). They do two things that catch the usual mistakes:

1. Static rules for the files themselves: CRLF line endings, ASCII only, `@echo off`, a move to the folder of the
   file, every `goto` label defined, no ( ) blocks that a folder name such as "Programs (x86)" could break, no
   administrator elevation, nothing destructive.
2. A small interpreter for the few batch commands these files use (if / set / goto / echo / pause / exit and the
   calls to Python). It follows the real text of each file under simulated computers: which Python versions exist,
   whether the launcher succeeds, whether the folder is usable. That proves the control flow: the right Python is
   chosen, the launcher gets the right arguments, the window always pauses before closing, and the exit code and
   the message match what happened.

What this cannot show: how cmd.exe parses a line in an unusual case, SmartScreen, or the real console. Those need a
Windows computer and are listed as NOT TESTED in FINAL_TEST_REPORT.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BATS = ["RUN_PROJECT.bat", "STOP_PROJECT.bat", "CHECK_ENVIRONMENT.bat"]
FAKE_DIR = "C:\\Fake Folder (x86)\\EnergiQ-AI\\"


def read_bat(name: str) -> list[str]:
    raw = (ROOT / name).read_bytes()
    return raw.decode("ascii").split("\r\n")[:-1] if raw.endswith(b"\r\n") else raw.decode("ascii").split("\r\n")


# ======================================================================================== static rules
@pytest.mark.parametrize("name", BATS)
def test_file_is_crlf_and_ascii_only(name):
    raw = (ROOT / name).read_bytes()
    assert raw.isascii(), "non-ASCII characters can be misread by cmd.exe in other code pages"
    assert b"\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "every line must end with CRLF"
    assert raw.endswith(b"\r\n")
    assert b"\t" not in raw


@pytest.mark.parametrize("name", BATS)
def test_file_starts_quietly_and_moves_to_its_own_folder(name):
    lines = [x for x in read_bat(name) if x.strip()]
    assert lines[0].lower() == "@echo off"
    text = "\n".join(lines)
    assert "setlocal EnableExtensions DisableDelayedExpansion" in text  # "!" in a folder name must stay literal
    assert 'cd /d "%~dp0"' in text


@pytest.mark.parametrize("name", BATS)
def test_every_goto_has_a_label_and_labels_are_unique(name):
    lines = read_bat(name)
    labels = [x.strip()[1:].split()[0].lower() for x in lines if x.strip().startswith(":") and not x.strip().startswith("::")]
    assert len(labels) == len(set(labels)), "duplicate label"
    for line in lines:
        for target in re.findall(r"\bgoto\s+:?(\S+)", line, flags=re.I):
            if target.lower() != ":eof":
                assert target.lower().lstrip(":") in labels, f"{name}: goto {target} has no label"


def _strip_quoted_and_escaped(line: str) -> str:
    line = re.sub(r'"[^"]*"', "", line)
    line = re.sub(r"\^.", "", line)
    return re.sub(r"\bin \([^)]*\)", "in X", line)  # the set of a one-line `for` loop


@pytest.mark.parametrize("name", BATS)
def test_no_parenthesised_blocks(name):
    """A ( ) block that expands a path breaks as soon as the folder name contains ")". These files avoid blocks."""
    for line in read_bat(name):
        code = line.strip()
        if code.lower().startswith("rem ") or code.lower() == "rem":
            continue
        assert "(" not in _strip_quoted_and_escaped(code) and ")" not in _strip_quoted_and_escaped(code), f"{name}: {line!r}"


@pytest.mark.parametrize("name", BATS)
def test_rem_lines_have_no_redirection_or_pipe_characters(name):
    for line in read_bat(name):
        if line.strip().lower().startswith("rem"):
            assert not re.search(r"[<>|&]", line), f"{name}: {line!r}"


FORBIDDEN = [
    r"\brunas\b", r"-Verb\s+RunAs", r"\bnet\s+session\b", r"\bpowershell\b", r"\bsetx\b", r"\breg\s+(add|delete)\b",
    r"HKLM", r"\btaskkill\b", r"\bdel\s", r"\berase\b", r"\brmdir\b", r"\brd\s", r"\bformat\b", r"\bcurl\b", r"\bwget\b",
    r"\bbitsadmin\b", r"\bcertutil\b", r"\bschtasks\b", r"\bsc\s+(create|delete|stop)\b",
]


@pytest.mark.parametrize("name", BATS)
def test_no_elevation_no_destructive_or_network_commands(name):
    code = "\n".join(x for x in read_bat(name) if not x.strip().lower().startswith("rem"))
    for pattern in FORBIDDEN:
        assert not re.search(pattern, code, flags=re.I), f"{name}: {pattern}"


@pytest.mark.parametrize("name", BATS)
def test_window_pauses_before_it_closes(name):
    lines = [x.strip().lower() for x in read_bat(name) if x.strip()]
    assert lines[-1].startswith("exit /b")
    assert lines[-2] == "pause"


@pytest.mark.parametrize("name", BATS)
def test_files_it_relies_on_exist(name):
    text = "\n".join(read_bat(name))
    for other in set(re.findall(r"\b(RUN_PROJECT\.bat|STOP_PROJECT\.bat|CHECK_ENVIRONMENT\.bat|run_energiq\.py|START_HERE\.md)\b", text)):
        assert (ROOT / other).is_file(), f"{name} mentions {other}, which does not exist"
    assert "START_PROJECT" not in text


def test_no_secret_or_password_in_the_batch_files():
    for name in BATS:
        text = "\n".join(read_bat(name)).lower()
        assert "password" not in text.replace("passwords", "")  # only the line saying logs never hold passwords
        assert "secret" not in text


# ======================================================================================== interpreter
@dataclass
class Computer:
    """A simulated Windows computer. `py` are the versions the `py -3.x` launcher knows; `python` is what `python` is."""

    py: tuple[str, ...] = ("3.11",)
    python: str | None = None  # e.g. "3.12" or "3.14"; None = no `python` on PATH
    node: str | None = "22.12.0"
    npm: bool = True
    folder_usable: bool = True
    files: tuple[str, ...] = ("run_energiq.py",)
    launcher_rc: int = 0
    no_pause: bool = False  # ENERGIQ_NO_PAUSE=1 in the environment (automated runs)
    calls: list[str] = field(default_factory=list)  # launcher invocations, in order


@dataclass
class Result:
    out: list[str]
    code: int
    paused: bool
    paused_last: bool
    launcher_calls: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.out)


def _python_in_range(version: str | None) -> bool:
    if not version:
        return False
    major, minor = (int(x) for x in version.split(".")[:2])
    return major == 3 and 11 <= minor <= 13


def run_bat(name: str, pc: Computer, args: str = "") -> Result:
    """Follow the real text of a .bat file on the simulated computer."""
    lines = read_bat(name)
    labels = {x.strip()[1:].split()[0].lower(): i for i, x in enumerate(lines) if x.strip().startswith(":") and not x.strip().startswith("::")}
    env: dict[str, str] = {"ENERGIQ_NO_PAUSE": "1"} if pc.no_pause else {}
    state = {"errorlevel": 0}
    out: list[str] = []
    flags = {"paused": False, "paused_last": False, "previous": ""}

    def expand(s: str) -> str:
        s = s.replace("%~dp0", FAKE_DIR).replace("%*", args)

        def var(m: re.Match) -> str:
            n = m.group(1).upper()
            return str(state["errorlevel"]) if n == "ERRORLEVEL" else env.get(n, "")

        return re.sub(r"%([A-Za-z_]+)%", var, s)

    def external(cmd: str) -> tuple[int, str]:
        """Outcome of a program the batch file starts: (errorlevel, printed text)."""
        c = cmd.strip()
        c = re.sub(r"\s*>nul\s*2>nul\s*$", "", c, flags=re.I)
        m = re.match(r"py -(3(?:\.\d+)?) -c ", c)
        if m:
            want = m.group(1)
            ok = any(v == want or (want == "3" and v.startswith("3.")) for v in pc.py)
            return (0 if ok else 9009), ""
        if c.startswith("python --version"):
            return (0, f"Python {pc.python}") if pc.python else (9009, "")
        if c.startswith("python -c "):
            if not pc.python:
                return 9009, ""
            if "(3, 11) <=" in c:  # the version-range check
                return (0 if _python_in_range(pc.python) else 1), ""
            return 0, ""
        if "run_energiq.py" in c:
            pc.calls.append(c)
            return pc.launcher_rc, ""
        if c == "where node":
            return (0, "node.exe") if pc.node else (1, "")
        if c == "where npm":
            return (0, "npm.cmd") if pc.npm else (1, "")
        if c.startswith("node --version"):
            return (0, "v" + pc.node) if pc.node else (9009, "")
        raise AssertionError(f"{name}: the simulator does not know the command {c!r}")

    def say(text: str) -> None:
        out.append(re.sub(r"\^(.)", r"\1", text))

    def exec_stmt(stmt: str, idx: int) -> int | None:
        """Run one statement. Returns the next line index to jump to, ("exit", code) via exception, or None to continue."""
        s = stmt.strip()
        low = s.lower()
        if not s or low.startswith("rem") or low == "@echo off" or low.startswith(("setlocal", "title ")) or s.startswith(":"):
            return None
        m = re.match(r'if\s+(not\s+)?(?:errorlevel\s+(\d+)|defined\s+(\w+)|exist\s+"([^"]*)"|"([^"]*)"\s*==\s*"([^"]*)")\s+(.*)$', s, flags=re.I)
        if m:
            neg, lvl, dfn, ex, a, b, rest = m.groups()
            if lvl is not None:
                cond = state["errorlevel"] >= int(lvl)
            elif dfn is not None:
                cond = bool(env.get(dfn.upper()))
            elif ex is not None:
                cond = ex.replace(FAKE_DIR, "") in pc.files
            else:
                cond = a == b
            if bool(neg) == cond:
                return None
            return exec_stmt(rest, idx)
        if low.startswith("goto"):
            target = s.split(None, 1)[1].lstrip(":").lower()
            if target == "eof":
                raise _Exit(state["errorlevel"])
            return labels[target]
        m = re.match(r'set\s+"([^=]+)=(.*)"$', s, flags=re.I)
        if m:
            env[m.group(1).upper()] = m.group(2)
            return None
        if low.startswith("echo"):
            body = s[4:]
            say("" if body == "." else body[1:] if body.startswith(" ") else body)
            return None
        if low.startswith("cd /d"):
            state["errorlevel"] = 0 if pc.folder_usable else 1
            return None
        if low == "pause":
            flags["paused"] = True
            out.append("<pause>")
            flags["previous"] = "pause"
            return None
        if low.startswith("exit /b"):
            flags["paused_last"] = flags["previous"] == "pause"
            raise _Exit(int(s.split()[-1]))
        m = re.match(r'for /f "delims=" %%N in \(\'(.+?)\'\) do (.*)$', s, flags=re.I)
        if m:
            code, text = external(m.group(1))
            state["errorlevel"] = code
            if code == 0:
                say(m.group(2).replace("%%N", text.lstrip("v")).replace("echo ", "", 1).lstrip())
            return None
        code, printed = external(s)
        state["errorlevel"] = code
        if printed and "--version" in s and ">nul" not in s.lower():
            out.append(printed)
        return None

    class _Exit(Exception):
        def __init__(self, code: int):
            self.code = code

    i, steps = 0, 0
    try:
        while i < len(lines):
            steps += 1
            assert steps < 400, f"{name}: possible endless loop"
            line = lines[i]
            expanded = expand(line) if not line.strip().lower().startswith("rem") else line
            if "%PY%" in line.upper() and "run_energiq.py" in line:
                assert env.get("PY"), f"{name}: the launcher is called with PY undefined"
            kind_before = flags["previous"]
            jump = exec_stmt(expanded, i)
            if flags["previous"] == kind_before and line.strip() and not line.strip().startswith(":") and not line.strip().lower().startswith(("rem", "set", "if")):
                flags["previous"] = "other"
            i = i + 1 if jump is None else jump
        raise AssertionError(f"{name}: ended without 'exit /b'")
    except _Exit as done:
        return Result(out, done.code, bool(flags["paused"]), bool(flags["paused_last"]), list(pc.calls))


# ======================================================================================== RUN_PROJECT.bat
def test_run_picks_python_311_and_forwards_the_options():
    pc = Computer(py=("3.11", "3.12"))
    res = run_bat("RUN_PROJECT.bat", pc, args="--no-browser --reinstall")
    assert len(res.launcher_calls) == 1
    assert res.launcher_calls[0].startswith('py -3.11 "' + FAKE_DIR + 'run_energiq.py"')
    assert res.launcher_calls[0].endswith("--no-browser --reinstall")
    assert res.code == 0 and res.paused_last


@pytest.mark.parametrize("py,expected", [(("3.12",), "py -3.12"), (("3.13",), "py -3.13"), (("3.12", "3.13"), "py -3.12")])
def test_run_falls_back_to_other_supported_versions(py, expected):
    res = run_bat("RUN_PROJECT.bat", Computer(py=py))
    assert res.launcher_calls and res.launcher_calls[0].startswith(expected + " ")


def test_run_uses_plain_python_when_there_is_no_py_launcher():
    res = run_bat("RUN_PROJECT.bat", Computer(py=(), python="3.12"))
    assert res.launcher_calls[0].startswith('python "')


@pytest.mark.parametrize("python", ["3.14", "3.10", None])
def test_run_refuses_unsupported_python_and_says_what_to_do(python):
    pc = Computer(py=(), python=python)
    res = run_bat("RUN_PROJECT.bat", pc)
    assert res.launcher_calls == [] and res.code == 1 and res.paused_last
    assert "3.11, 3.12 or 3.13 was not found" in res.text and "python.org" in res.text and "Add python.exe to PATH" in res.text
    assert ("Another Python version is installed" in res.text) == (python is not None)


def test_run_ignores_a_py_launcher_that_only_has_an_unsupported_version():
    res = run_bat("RUN_PROJECT.bat", Computer(py=("3.9",), python=None))
    assert res.launcher_calls == [] and res.code == 1


def test_run_reports_a_zip_that_was_not_extracted():
    res = run_bat("RUN_PROJECT.bat", Computer(files=()))
    assert res.launcher_calls == [] and res.code == 1 and res.paused_last
    assert "Extract All" in res.text


def test_run_reports_a_folder_cmd_cannot_use():
    res = run_bat("RUN_PROJECT.bat", Computer(folder_usable=False))
    assert res.launcher_calls == [] and res.code == 1 and res.paused_last
    assert "network location" in res.text and "C:\\EnergiQ" in res.text


def test_run_normal_end_does_not_claim_success_or_failure_wrongly():
    res = run_bat("RUN_PROJECT.bat", Computer(launcher_rc=0))
    assert res.code == 0 and "not running in this window any more" in res.text
    assert "error" not in res.text.lower()
    assert "has stopped" not in res.text  # an 'already running' exit must not read as a stop


def test_run_failure_gives_the_code_and_the_next_steps():
    res = run_bat("RUN_PROJECT.bat", Computer(launcher_rc=1))
    assert res.code == 1 and res.paused_last
    for needle in ("code 1", "CHECK_ENVIRONMENT.bat", ".energiq-run", "START_HERE.md", "never contains passwords", "STOP_PROJECT.bat"):
        assert needle in res.text
    assert FAKE_DIR + ".energiq-run" in res.text  # the log folder is named in full


def test_run_cancel_message():
    res = run_bat("RUN_PROJECT.bat", Computer(launcher_rc=130))
    assert res.code == 130 and "Cancelled" in res.text


def test_run_never_calls_the_launcher_twice():
    pc = Computer()
    assert len(run_bat("RUN_PROJECT.bat", pc).launcher_calls) == 1


# ======================================================================================== STOP_PROJECT.bat
def test_stop_calls_the_launcher_with_stop_and_reports_success():
    res = run_bat("STOP_PROJECT.bat", Computer(py=("3.12",)))
    assert len(res.launcher_calls) == 1 and res.launcher_calls[0].endswith("--stop")
    assert res.code == 0 and res.paused_last and "could not be stopped" not in res.text


def test_stop_forwards_a_failure():
    res = run_bat("STOP_PROJECT.bat", Computer(launcher_rc=1))
    assert res.code == 1 and "could not be stopped" in res.text and "Task Manager" in res.text


def test_stop_without_python_explains_how_to_close_the_window():
    res = run_bat("STOP_PROJECT.bat", Computer(py=(), python=None))
    assert res.launcher_calls == [] and res.code == 1 and "Ctrl+C" in res.text and res.paused_last


def test_stop_accepts_any_python_3():
    res = run_bat("STOP_PROJECT.bat", Computer(py=(), python="3.14"))
    assert res.launcher_calls and res.launcher_calls[0].startswith('python "')


# ======================================================================================== CHECK_ENVIRONMENT.bat
def test_check_runs_the_doctor_and_points_to_run_project_when_all_is_well():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer())
    assert res.launcher_calls[0].endswith("--doctor") and res.code == 0 and res.paused_last
    assert "RUN_PROJECT.bat" in res.text


def test_check_forwards_missing_items():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer(launcher_rc=1))
    assert res.code == 1 and "MISSING" in res.text and "RUN_PROJECT.bat to start" not in res.text


def test_check_without_python_still_reports_node_and_npm():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer(py=(), python=None, node="22.12.0", npm=True))
    assert res.launcher_calls == [] and res.code == 1
    assert "[MISSING] Python 3.11, 3.12 or 3.13" in res.text and "Node.js 22.12.0" in res.text and "[FOUND  ] npm" in res.text


def test_check_without_python_node_or_npm():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer(py=(), python=None, node=None, npm=False))
    assert "[MISSING] Node.js" in res.text and "[MISSING] npm" in res.text and res.code == 1 and res.paused_last


def test_check_names_an_unsupported_python_that_is_installed():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer(py=(), python="3.14"))
    assert "Another Python is installed" in res.text and "Python 3.14" in res.text


def test_check_needs_the_project_files():
    res = run_bat("CHECK_ENVIRONMENT.bat", Computer(files=()))
    assert res.launcher_calls == [] and res.code == 1 and "extracted EnergiQ-AI folder" in res.text


# ======================================================================================== automated runs
@pytest.mark.parametrize("name,launcher_rc", [("RUN_PROJECT.bat", 0), ("RUN_PROJECT.bat", 1), ("STOP_PROJECT.bat", 0), ("CHECK_ENVIRONMENT.bat", 0)])
def test_the_final_pause_can_be_skipped_for_automated_runs_and_is_on_by_default(name, launcher_rc):
    interactive = run_bat(name, Computer(launcher_rc=launcher_rc))
    automated = run_bat(name, Computer(launcher_rc=launcher_rc, no_pause=True))
    assert interactive.paused and interactive.paused_last, "a person double-clicking must always get the pause"
    assert not automated.paused and automated.code == interactive.code
