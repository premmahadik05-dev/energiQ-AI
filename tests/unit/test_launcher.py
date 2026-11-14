"""Unit tests for run_energiq.py, the launcher that RUN_PROJECT.bat / run_project.sh run.

Everything here uses a temporary run folder and mocked process lookups, so no server is started and nothing in the
real .energiq-run folder is touched. The Windows branches are exercised by switching IS_WIN and mocking `tasklist` /
`taskkill`; they have NOT been run on a real Windows machine (see FINAL_TEST_REPORT.md).
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "run_energiq.py"


@pytest.fixture()
def L(tmp_path, monkeypatch):
    """The launcher module, loaded fresh, with its run folder redirected to a temporary directory."""
    spec = importlib.util.spec_from_file_location("run_energiq_under_test", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    run = tmp_path / ".energiq-run"
    monkeypatch.setattr(mod, "RUN_DIR", run)
    monkeypatch.setattr(mod, "STATE_FILE", run / "state.json")
    monkeypatch.setattr(mod, "CRED_FILE", run / "admin_login.txt")
    monkeypatch.setattr(mod, "SECRET_FILE", run / "secret_key.txt")
    monkeypatch.setattr(mod, "ROOT", tmp_path)  # no data/energiq.db here, so the "legacy install" branch is off
    for var in ("ENERGIQ_ADMIN_EMAIL", "ENERGIQ_ADMIN_PASSWORD", "ENERGIQ_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield mod
    sys.modules.pop(spec.name, None)


def _alive_pid() -> int:
    return os.getpid()  # this test process is certainly running


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid  # finished and reaped, so no process has this id now


# --------------------------------------------------------------------------- admin password and signing key
def test_generated_password_meets_the_server_policy(L):
    for _ in range(50):
        pw = L.new_password()
        assert len(pw) >= 12
        assert any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)
    assert len({L.new_password() for _ in range(20)}) == 20  # not a constant


def test_first_run_creates_a_random_password_and_keeps_it(L):
    email, pw, shown = L.admin_credentials()
    assert email == L.ADMIN_EMAIL and pw == shown
    assert pw != L.LEGACY_ADMIN_PASSWORD
    assert L.CRED_FILE.read_text().splitlines() == [f"email={email}", f"password={pw}"]
    assert L.admin_credentials() == (email, pw, pw)  # second start reuses the saved login


def test_credentials_from_the_environment_win_and_are_not_written(L, monkeypatch):
    monkeypatch.setenv("ENERGIQ_ADMIN_EMAIL", "teacher@example.org")
    monkeypatch.setenv("ENERGIQ_ADMIN_PASSWORD", "My-Own-Password-1")
    email, pw, shown = L.admin_credentials()
    assert (email, pw) == ("teacher@example.org", "My-Own-Password-1")
    assert "My-Own-Password-1" not in shown  # the window says where it came from instead of printing it
    assert not L.CRED_FILE.exists()


def test_existing_database_from_the_first_launcher_keeps_its_old_login(L, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "energiq.db").write_bytes(b"")
    _, pw, _ = L.admin_credentials()
    assert pw == L.LEGACY_ADMIN_PASSWORD  # otherwise the admin could no longer sign in to the old database


def test_signing_key_is_random_persistent_and_never_the_public_dev_key(L):
    from backend.app.config import DEV_SECRET

    key = L.signing_key()
    assert len(key) >= 32 and key != DEV_SECRET
    assert L.signing_key() == key  # logins survive a restart
    assert L.SECRET_FILE.read_text() == key


def test_a_too_short_saved_key_is_replaced(L):
    L.RUN_DIR.mkdir()
    L.SECRET_FILE.write_text("short")
    assert len(L.signing_key()) >= 32


def test_signing_key_from_the_environment_is_used_as_is(L, monkeypatch):
    monkeypatch.setenv("ENERGIQ_SECRET_KEY", "k" * 40)
    assert L.signing_key() == "k" * 40
    assert not L.SECRET_FILE.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_secret_files_are_private_on_posix(L):
    L.admin_credentials()
    L.signing_key()
    assert oct(L.CRED_FILE.stat().st_mode & 0o777) == "0o600"
    assert oct(L.SECRET_FILE.stat().st_mode & 0o777) == "0o600"


# --------------------------------------------------------------------------- process lookup
def test_pid_alive_on_posix(L, monkeypatch):
    monkeypatch.setattr(L, "IS_WIN", False)
    assert L.pid_alive(_alive_pid())
    assert not L.pid_alive(_dead_pid())
    assert not L.pid_alive(0) and not L.pid_alive(-5)


def test_pid_alive_on_windows_reads_tasklist_and_never_signals_the_process(L, monkeypatch):
    """os.kill(pid, 0) would terminate a process on Windows, so the Windows branch must use tasklist only."""
    monkeypatch.setattr(L, "IS_WIN", True)
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        listing = '"python.exe","4242","Console","1","55,000 K"\r\n' if "4242" in cmd[2] else "INFO: No tasks are running which match the specified criteria.\r\n"
        return SimpleNamespace(stdout=listing, returncode=0)

    monkeypatch.setattr(L.subprocess, "run", fake_run)
    monkeypatch.setattr(L.os, "kill", lambda *a: pytest.fail("os.kill must not be used on Windows"))
    assert L.pid_alive(4242) is True
    assert L.pid_alive(999) is False
    assert seen[0][0] == "tasklist" and "PID eq 4242" in seen[0]


def test_pid_alive_on_windows_survives_a_missing_tasklist(L, monkeypatch):
    monkeypatch.setattr(L, "IS_WIN", True)

    def boom(*a, **kw):
        raise OSError("tasklist not found")

    monkeypatch.setattr(L.subprocess, "run", boom)
    assert L.pid_alive(4242) is False


def test_kill_tree_on_windows_uses_taskkill_with_tree_flag(L, monkeypatch):
    monkeypatch.setattr(L, "IS_WIN", True)
    calls = []
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0))
    L.kill_tree(777)
    assert calls == [["taskkill", "/PID", "777", "/T", "/F"]]
    L.kill_tree(0)
    assert len(calls) == 1  # pid 0 is ignored


# --------------------------------------------------------------------------- one instance at a time
def test_state_round_trip_and_garbage_is_ignored(L):
    assert L.read_state() is None
    L.write_state({"launcher_pid": 5, "phase": "running"})
    assert L.read_state() == {"launcher_pid": 5, "phase": "running"}
    L.STATE_FILE.write_text("not json")
    assert L.read_state() is None
    L.STATE_FILE.write_text("[1, 2]")
    assert L.read_state() is None  # valid JSON of the wrong shape


def test_first_launcher_claims_and_a_second_is_refused(L, monkeypatch):
    monkeypatch.setattr(L, "backend_answers", lambda port: True)
    mine = {"launcher_pid": _alive_pid(), "phase": "starting", "started_at": time.time()}
    assert L.claim_instance(mine) is True
    assert L.claim_instance({"launcher_pid": 1, "phase": "starting", "started_at": time.time()}) is False
    assert L.read_state()["launcher_pid"] == mine["launcher_pid"]  # the second one did not overwrite the first


def test_a_stale_record_from_a_crashed_launcher_is_replaced(L):
    L.write_state({"launcher_pid": _dead_pid(), "phase": "running", "backend_port": 8000})
    assert L.existing_instance() is None
    assert not L.STATE_FILE.exists()
    assert L.claim_instance({"launcher_pid": _alive_pid(), "phase": "starting", "started_at": time.time()}) is True


def test_a_launcher_that_never_finished_starting_is_treated_as_dead(L):
    L.write_state({"launcher_pid": _alive_pid(), "phase": "starting", "started_at": time.time() - L.STARTING_GRACE_S - 5})
    assert L.existing_instance() is None


def test_a_live_launcher_whose_backend_stopped_answering_is_not_reported_running(L, monkeypatch):
    monkeypatch.setattr(L, "backend_answers", lambda port: False)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    L.write_state({"launcher_pid": _alive_pid(), "phase": "running", "backend_port": 8000})
    assert L.existing_instance() is None


def test_a_healthy_running_instance_is_reported(L, monkeypatch):
    monkeypatch.setattr(L, "backend_answers", lambda port: True)
    st = {"launcher_pid": _alive_pid(), "phase": "running", "backend_port": 8000}
    L.write_state(st)
    assert L.existing_instance() == st


def test_clear_state_only_removes_its_own_record(L):
    L.write_state({"launcher_pid": 111})
    L.clear_state(only_pid=222)  # another launcher's cleanup must not delete this record
    assert L.STATE_FILE.exists()
    L.clear_state(only_pid=111)
    assert not L.STATE_FILE.exists()
    L.clear_state()  # removing a missing file is not an error


# --------------------------------------------------------------------------- stop
def test_stop_without_an_instance_is_a_clean_no_op(L, capsys):
    assert L.stop_instance() == 0
    assert "Nothing to stop" in capsys.readouterr().out


def _running_state(L, **extra):
    st = {"frontend_pid": 10, "backend_pid": 20, "launcher_pid": 30, "backend_port": 8000, "frontend_port": 5173, "phase": "running"}
    st.update(extra)
    L.write_state(st)
    return st


class _Clock:
    """A fake clock so that waiting loops finish instantly and deterministically."""

    def __init__(self, L, monkeypatch):
        self.now = 1000.0
        self.slept = []
        monkeypatch.setattr(L.time, "time", lambda: self.now)
        monkeypatch.setattr(L.time, "sleep", lambda s: (self.slept.append(s), setattr(self, "now", self.now + s)))


def test_stop_asks_the_running_window_to_exit_on_its_own_first(L, monkeypatch, capsys):
    """The normal case: the launcher window sees the 'stopping' record, shuts its servers down and exits with code 0."""
    alive, killed = {10, 20, 30}, []
    _running_state(L)
    clock = _Clock(L, monkeypatch)
    monkeypatch.setattr(L, "pid_alive", lambda p: p in alive)
    monkeypatch.setattr(L, "backend_answers", lambda port: 20 in alive)
    monkeypatch.setattr(L, "web_answers", lambda port: 10 in alive)
    monkeypatch.setattr(L, "kill_tree", lambda p: killed.append(p))
    real_sleep = L.time.sleep

    def window_reacts(s):  # one second later the launcher window has shut everything down
        real_sleep(s)
        if clock.now >= 1001.0:
            alive.clear()

    monkeypatch.setattr(L.time, "sleep", window_reacts)
    assert L.stop_instance() == 0
    assert killed == []  # nothing had to be force-killed, so that window ends without an error code
    assert "shut the servers down and closed" in capsys.readouterr().out
    assert not L.STATE_FILE.exists()


def test_stop_ends_servers_before_the_launcher_when_the_window_does_not_react(L, monkeypatch):
    order, alive = [], {10, 20, 30}
    _running_state(L)
    _Clock(L, monkeypatch)
    monkeypatch.setattr(L, "pid_alive", lambda p: p in alive)
    monkeypatch.setattr(L, "backend_answers", lambda port: 20 in alive)
    monkeypatch.setattr(L, "web_answers", lambda port: 10 in alive)
    monkeypatch.setattr(L, "kill_tree", lambda p: (order.append(p), alive.discard(p)))
    assert L.stop_instance() == 0
    assert order == [10, 20, 30]  # web app, backend, then the launcher that supervises them
    assert not L.STATE_FILE.exists()


def test_stop_does_not_kill_a_server_number_that_was_freed_and_reused_during_a_clean_shutdown(L, monkeypatch):
    """After the window exits, the old backend number may belong to an unrelated program: it must not be killed."""
    killed, alive = [], {10, 20, 30}
    _running_state(L)
    clock = _Clock(L, monkeypatch)
    monkeypatch.setattr(L, "kill_tree", lambda p: killed.append(p))
    monkeypatch.setattr(L, "pid_alive", lambda p: p in alive)
    answering = {"on": True}
    monkeypatch.setattr(L, "backend_answers", lambda port: answering["on"])
    monkeypatch.setattr(L, "web_answers", lambda port: answering["on"])
    real_sleep = L.time.sleep

    def window_reacts(s):
        real_sleep(s)
        if clock.now >= 1001.0:
            answering["on"] = False
            alive.discard(30)  # the launcher is gone; 10 and 20 are now (pretend) unrelated programs

    monkeypatch.setattr(L.time, "sleep", window_reacts)
    assert L.stop_instance() == 0
    assert killed == []


def test_stop_reports_a_process_that_refuses_to_die(L, monkeypatch, capsys):
    _running_state(L, frontend_pid=0, launcher_pid=0)
    monkeypatch.setattr(L, "pid_alive", lambda p: p == 20)
    monkeypatch.setattr(L, "backend_answers", lambda port: True)
    monkeypatch.setattr(L, "web_answers", lambda port: False)
    monkeypatch.setattr(L, "kill_tree", lambda p: None)
    clock = iter(range(1000))
    monkeypatch.setattr(L.time, "time", lambda: next(clock))
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    assert L.stop_instance() == 1
    assert "Could not stop" in capsys.readouterr().out


def test_stop_never_kills_a_process_that_only_reused_a_recorded_number(L, monkeypatch, capsys):
    """After a crash the recorded ids can belong to unrelated programs. Nothing from EnergiQ answers, so nothing is killed."""
    killed = []
    _running_state(L)
    monkeypatch.setattr(L, "pid_alive", lambda p: True)  # all three numbers are in use by someone
    monkeypatch.setattr(L, "backend_answers", lambda port: False)
    monkeypatch.setattr(L, "web_answers", lambda port: False)
    monkeypatch.setattr(L, "kill_tree", lambda p: killed.append(p))
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    assert L.stop_instance() == 0
    assert killed == []
    assert "Left process" in capsys.readouterr().out
    assert not L.STATE_FILE.exists()  # the stale record is still removed


def test_stop_during_start_up_ends_the_launcher(L, monkeypatch):
    """While packages install the launcher has no servers yet; stop must still end it."""
    killed, alive = [], {30}
    L.write_state({"launcher_pid": 30, "phase": "starting", "started_at": L.time.time(), "backend_port": 8000, "frontend_port": 5173})
    monkeypatch.setattr(L, "pid_alive", lambda p: p in alive)
    monkeypatch.setattr(L, "backend_answers", lambda port: False)
    monkeypatch.setattr(L, "web_answers", lambda port: False)
    monkeypatch.setattr(L, "kill_tree", lambda p: (killed.append(p), alive.discard(p)))
    _Clock(L, monkeypatch)
    assert L.stop_instance() == 0
    assert killed == [30]


def test_stop_marks_the_record_so_the_launcher_window_can_tell_a_stop_from_a_crash(L, monkeypatch):
    seen, alive = [], {10, 20, 30}
    _running_state(L)
    _Clock(L, monkeypatch)
    assert not L.stop_requested()  # a normal running instance: a vanished server would be a crash
    assert not L.stop_marked()
    monkeypatch.setattr(L, "pid_alive", lambda p: p in alive)
    monkeypatch.setattr(L, "backend_answers", lambda port: True)
    monkeypatch.setattr(L, "web_answers", lambda port: True)

    def fake_kill(pid):
        seen.append(L.stop_requested() and L.stop_marked())  # what the launcher window would see when its server dies
        alive.discard(pid)

    monkeypatch.setattr(L, "kill_tree", fake_kill)
    assert L.stop_instance() == 0
    assert seen == [True, True, True]
    assert L.stop_requested()  # and once the record is cleared there is nothing left to be a crash of


# --------------------------------------------------------------------------- readiness must be real
def test_readiness_predicates_accept_only_the_energiq_answers(L):
    ok_body = '{"status":"ok","database":"up","environment":"dev"}'
    assert L.backend_ready(200, ok_body)
    assert not L.backend_ready(503, '{"status":"unavailable","database":"down"}')  # database down is not ready
    assert not L.backend_ready(200, "<html>some other program</html>")
    assert not L.backend_ready(404, "")
    assert L.backend_is_ours(503, '{"status":"unavailable","database":"down"}')  # ours, but not ready
    assert not L.backend_is_ours(200, "<html></html>")
    assert L.web_ready(200, "<title>EnergiQ AI</title>")
    assert not L.web_ready(200, "<title>Another app</title>")
    assert not L.web_ready(404, "EnergiQ")


class _FakeChild:
    def __init__(self, alive=True):
        self._alive, self.name, self.log = alive, "backend", Path("backend.log")
        self.proc = SimpleNamespace(returncode=1)

    def alive(self):
        return self._alive


def test_wait_for_returns_when_the_answer_is_acceptable(L, monkeypatch):
    monkeypatch.setattr(L, "probe", lambda url, timeout=3: (200, '{"database":"up"}'))
    L.wait_for("http://x/health/ready", [_FakeChild()], 5, "backend", ok=L.backend_ready)


def test_wait_for_does_not_trust_another_program_answering_on_the_port(L, monkeypatch, capsys):
    """A different program on the port answers 200 with its own page: that must not count as 'ready'."""
    monkeypatch.setattr(L, "probe", lambda url, timeout=3: (200, "<html>someone else</html>"))
    clock = iter(range(0, 1000, 2))
    monkeypatch.setattr(L.time, "time", lambda: next(clock))
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit):
        L.wait_for("http://x/health/ready", [_FakeChild()], 10, "backend", ok=L.backend_ready)
    assert "did not become ready" in capsys.readouterr().out


def test_wait_for_reports_a_server_that_died_even_if_something_answers(L, monkeypatch, capsys, tmp_path):
    log = tmp_path / "backend.log"
    log.write_text("Address already in use\n")
    child = _FakeChild(alive=False)
    child.log = log
    monkeypatch.setattr(L, "probe", lambda url, timeout=3: (200, '{"database":"up"}'))  # the OTHER program's answer
    with pytest.raises(SystemExit):
        L.wait_for("http://x/health/ready", [child], 5, "backend", ok=L.backend_ready)
    out = capsys.readouterr().out
    assert "stopped while starting" in out and "Address already in use" in out


# --------------------------------------------------------------------------- launcher.log and secrets
def test_launcher_log_records_the_run_but_never_the_password(L, capsys):
    L.start_log("start")
    L.say("  Sign in with: admin@example.com   /   Eq-secret-1234", log_msg="  Sign in with: admin@example.com   /   (password shown in the window only)")
    L.say("[EnergiQ] something else")
    log = (L.RUN_DIR / "launcher.log").read_text(encoding="utf-8")
    assert "Eq-secret-1234" not in log
    assert "password shown in the window only" in log and "something else" in log and "start" in log
    assert "Eq-secret-1234" in capsys.readouterr().out  # the window still shows it: that is how the user signs in
    L._LOG_FH.close()
    L._LOG_FH = None


def test_launcher_log_is_rotated_when_it_grows(L):
    L.RUN_DIR.mkdir()
    (L.RUN_DIR / "launcher.log").write_text("x" * 600_000, encoding="utf-8")
    L.start_log("start")
    assert (L.RUN_DIR / "launcher.log.1").exists()
    assert (L.RUN_DIR / "launcher.log").stat().st_size < 10_000
    L._LOG_FH.close()
    L._LOG_FH = None


def test_fail_points_to_the_logs_and_exits(L, capsys):
    L.start_log("start")
    with pytest.raises(SystemExit) as exc:
        L.fail("something broke")
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "STOPPED: something broke" in out and "launcher.log" in out
    L._LOG_FH.close()
    L._LOG_FH = None


def test_say_survives_a_console_that_cannot_print_the_character(L, monkeypatch, capsys):
    calls = []

    def flaky_print(text, flush=False):
        calls.append(text)
        if len(calls) == 1:
            raise UnicodeEncodeError("charmap", text, 0, 1, "cannot encode")

    monkeypatch.setattr("builtins.print", flaky_print)
    L.say("caf\u00e9 \u2713")  # must not raise
    assert len(calls) == 2 and calls[1].isascii()


# --------------------------------------------------------------------------- database step
REPO = LAUNCHER.parent


def test_database_step_creates_the_database_and_reports_it(L, monkeypatch, tmp_path):
    monkeypatch.setattr(L, "ROOT", REPO)
    L.RUN_DIR.mkdir()
    env = dict(os.environ, ENERGIQ_ENV="dev", ENERGIQ_DATABASE_URL=f"sqlite:///{tmp_path / 'fresh.db'}")
    msg = L.prepare_database(Path(sys.executable), env)
    assert "tables" in msg and "user account" in msg
    assert int(msg.split("(")[1].split(",")[1].split()[0]) >= 10  # the schema was really created
    assert (tmp_path / "fresh.db").exists()


def test_database_step_explains_an_unusable_database(L, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(L, "ROOT", REPO)
    L.RUN_DIR.mkdir()
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the database folder should be")
    env = dict(os.environ, ENERGIQ_ENV="dev", ENERGIQ_DATABASE_URL=f"sqlite:///{blocker / 'x.db'}")
    with pytest.raises(SystemExit):
        L.prepare_database(Path(sys.executable), env)
    out = capsys.readouterr().out
    assert "database could not be prepared" in out and "OneDrive" in out
    assert re.search(r"Reason: \S*Error", out), out  # the window gets the one-line reason ...
    assert 'File "' not in out and "Traceback" not in out  # the window gets the reason, the log gets the trace
    assert "database.log" in out


def test_error_line_picks_the_line_that_names_the_error(L, tmp_path):
    log = tmp_path / "x.log"
    log.write_text('Traceback (most recent call last):\n  File "a.py", line 1, in <module>\n    boom()\n'
                   "sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file\n"
                   "(Background on this error at: https://sqlalche.me/e/21/e3q8)\n")
    assert "unable to open database file" in L.error_line(log)
    log.write_text("just one line\n")
    assert L.error_line(log) == "just one line"
    log.write_text("")
    assert "empty" in L.error_line(log)


def test_database_step_explains_a_folder_that_cannot_be_written(L, monkeypatch, capsys, tmp_path):
    (tmp_path / "data").write_text("a file where the data folder should be")  # mkdir / write fails
    monkeypatch.setattr(L, "ROOT", tmp_path)
    L.RUN_DIR.mkdir()
    with pytest.raises(SystemExit):
        L.prepare_database(Path(sys.executable), dict(os.environ))
    assert "cannot be written to" in capsys.readouterr().out


# --------------------------------------------------------------------------- notes about the computer
def test_long_windows_paths_and_sync_folders_are_noted(L, monkeypatch):
    monkeypatch.setattr(L, "IS_WIN", True)
    monkeypatch.setattr(L, "smart_app_control_state", lambda: None)
    monkeypatch.setattr(L, "ROOT", Path("C:/Users/someone/OneDrive/Documents/" + "folder/" * 12 + "EnergiQ-AI"))
    notes = " | ".join(L.environment_notes())
    assert "path is long" in notes and "cloud-sync" in notes
    monkeypatch.setattr(L, "ROOT", Path("C:/EnergiQ/EnergiQ-AI"))
    assert L.environment_notes() == []


def test_smart_app_control_is_read_from_the_registry_without_admin_rights(L, monkeypatch):
    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake = SimpleNamespace(HKEY_LOCAL_MACHINE=0, OpenKey=lambda root, path: FakeKey(), QueryValueEx=lambda key, name: (1, 4))
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(L, "IS_WIN", True)
    assert L.smart_app_control_state() == 1
    assert any("Smart App Control" in n for n in L.environment_notes())
    monkeypatch.setattr(L, "IS_WIN", False)
    assert L.smart_app_control_state() is None  # not Windows: no registry, no note


def test_smart_app_control_unreadable_is_not_an_error(L, monkeypatch):
    def boom(root, path):
        raise OSError("key not found")

    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(HKEY_LOCAL_MACHINE=0, OpenKey=boom, QueryValueEx=None))
    monkeypatch.setattr(L, "IS_WIN", True)
    assert L.smart_app_control_state() is None


def test_doctor_reports_writable_folder_and_database(L, monkeypatch, capsys):
    monkeypatch.setattr(L, "ROOT", REPO)
    monkeypatch.setattr(L, "FRONTEND", REPO / "frontend")
    monkeypatch.setattr(L, "VENV", REPO / ".venv-not-here")
    monkeypatch.setattr(L, "existing_instance", lambda: None)
    L.doctor()
    out = capsys.readouterr().out
    assert "Project folder is writable" in out and "Database" in out


# --------------------------------------------------------------------------- environment checks
def test_node_version_parsing(L, monkeypatch):
    monkeypatch.setattr(L.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="v26.13.0\n"))
    assert L.node_version("node") == (26, 13)
    monkeypatch.setattr(L.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="garbage"))
    assert L.node_version("node") is None

    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(L.subprocess, "run", missing)
    assert L.node_version("node") is None


def test_too_old_node_stops_with_a_clear_message(L, monkeypatch, capsys):
    monkeypatch.setattr(L.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(L, "node_version", lambda n: (18, 20))
    with pytest.raises(SystemExit):
        L.check_node()
    assert "too old" in capsys.readouterr().out


def test_missing_node_explains_how_to_install_it(L, monkeypatch, capsys):
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit):
        L.check_node()
    assert "nodejs.org" in capsys.readouterr().out


def test_unsupported_python_is_refused_with_the_supported_range(L, monkeypatch, capsys):
    monkeypatch.setattr(L.sys, "version_info", (3, 9, 0, "final", 0))
    with pytest.raises(SystemExit):
        L.check_python()
    assert "3.11" in capsys.readouterr().out


def test_busy_port_is_skipped_unless_the_user_chose_it(L, monkeypatch):
    busy = {8000, 8001}
    monkeypatch.setattr(L, "port_free", lambda p: p not in busy)
    assert L.pick_port(8000, "backend", explicit=False) == 8002
    assert L.pick_port(9000, "web app", explicit=False) == 9000
    with pytest.raises(SystemExit):
        L.pick_port(8000, "backend", explicit=True)


def test_checksum_helper_follows_the_file_content(L, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("energiq")
    first = L.sha256_of(f)
    assert len(first) == 64 and L.sha256_of(f) == first
    f.write_text("energiq2")
    assert L.sha256_of(f) != first  # this is what makes "install only when requirements changed" work
