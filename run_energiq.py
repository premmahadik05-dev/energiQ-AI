#!/usr/bin/env python3
"""EnergiQ AI - one-command local launcher (standard library only).

What it does, in order:
  1. checks Python (3.11-3.13) and Node.js (20.19 or newer);
  2. creates ./.venv and installs requirements.txt (first run, or when the file changes);
  3. runs `npm ci` in ./frontend (first run, or when package-lock.json changes);
  4. creates / checks the database (./data/energiq.db, SQLite) and reports the result;
  5. starts the FastAPI backend and the Vite dev server on 127.0.0.1, and waits until BOTH really answer
     (the backend must report its database as up; the web app must serve the EnergiQ page and reach the
     backend through its proxy), signs in as the local admin and imports the bundled societies once
     (skip with --no-import);
  6. opens the app in your browser and keeps running until you press Ctrl+C.

Everything is local: both servers listen on 127.0.0.1 only, and the data lives in
./data/energiq.db (SQLite). Logs are written to ./.energiq-run/ (launcher.log, backend.log, frontend.log,
pip-install.log, npm-install.log, database.log). The administrator password is never written to launcher.log.

Usage:  python run_energiq.py [--no-import] [--no-browser] [--check] [--reinstall]
                              [--backend-port N] [--frontend-port N]
        python run_energiq.py --status      is it running, and where?
        python run_energiq.py --stop        stop a running instance (backend and web app)
        python run_energiq.py --doctor      check the computer and the installation; changes nothing

Only one instance runs at a time: starting a second one reports the address of the first instead of opening
duplicate servers. The running instance is recorded in ./.energiq-run/state.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
RUN_DIR = ROOT / ".energiq-run"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"

SUPPORTED_PY = ((3, 11), (3, 13))
MIN_NODE = (20, 19)

ADMIN_EMAIL = "admin@example.com"
# Installs made with the first version of this launcher were created with this password and have no credentials
# file; it is used only to keep signing in to such an existing database. New installs get their own random password.
LEGACY_ADMIN_PASSWORD = "EnergiQ-Local-2026"  # nosec B105 - legacy local-only installs, see admin_credentials()
CRED_FILE = RUN_DIR / "admin_login.txt"
SECRET_FILE = RUN_DIR / "secret_key.txt"

STATE_FILE = RUN_DIR / "state.json"
STARTING_GRACE_S = 15 * 60  # a launcher that has not reported "running" after this long is treated as dead
GRACEFUL_STOP_S = 20  # how long STOP waits for the launcher window to shut its servers down itself

REQ_MARK = VENV / ".energiq_requirements.sha256"
LOCK_MARK = FRONTEND / "node_modules" / ".energiq_lock.sha256"


# --------------------------------------------------------------------------- output helpers
_LOG_FH = None  # launcher.log, opened by start_log()


def start_log(mode: str) -> None:
    """Append everything this launcher prints to .energiq-run/launcher.log (the password is never written there)."""
    global _LOG_FH
    try:
        RUN_DIR.mkdir(exist_ok=True)
        log = RUN_DIR / "launcher.log"
        if log.exists() and log.stat().st_size > 512_000:
            os.replace(log, RUN_DIR / "launcher.log.1")
        _LOG_FH = log.open("a", encoding="utf-8", errors="replace")
        _LOG_FH.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {mode}  pid {os.getpid()}  "
                      f"Python {sys.version.split()[0]}  {sys.platform}  folder {ROOT} =====\n")
        _LOG_FH.flush()
    except OSError:
        _LOG_FH = None


def _to_log(text: str) -> None:
    if _LOG_FH is not None:
        try:
            _LOG_FH.write(text + "\n")
            _LOG_FH.flush()
        except (OSError, ValueError):
            pass


def say(msg: str = "", log_msg: str | None = None) -> None:
    """Print to the window and, when a log is open, to launcher.log (log_msg replaces the text there)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:  # an old Windows console code page: never crash over a character
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)
    _to_log(msg if log_msg is None else log_msg)


def step(msg: str) -> None:
    say(f"\n[EnergiQ] {msg}")


def fail(msg: str, code: int = 1) -> NoReturn:
    say(f"\n[EnergiQ] STOPPED: {msg}")
    if _LOG_FH is not None:
        say(f"  Logs for troubleshooting are in the {RUN_DIR.name} folder (launcher.log and the others).")
    sys.exit(code)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tail(path: Path, n: int = 25) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return "(no log)"


# --------------------------------------------------------------------------- environment checks
def check_python() -> None:
    cur = sys.version_info[:2]
    lo, hi = SUPPORTED_PY
    if not (lo <= cur <= hi):
        fail(
            f"This launcher is running on Python {cur[0]}.{cur[1]}, but EnergiQ AI supports "
            f"{lo[0]}.{lo[1]} to {hi[0]}.{hi[1]}.\n"
            "  Install Python 3.11 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'),\n"
            "  then run this again."
        )


def node_version(node: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        major, minor, *_ = out.lstrip("v").split(".")
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check_node() -> tuple[str, str]:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        fail(
            "Node.js was not found on your PATH.\n"
            "  Install the LTS version from https://nodejs.org/ (version 22 recommended), close this\n"
            "  window, open a new one and run this again."
        )
    ver = node_version(node)
    if ver is None:
        fail("Node.js is installed but could not be started. Reinstall it from https://nodejs.org/.")
    if ver < MIN_NODE:
        fail(f"Node.js {ver[0]}.{ver[1]} is too old; the frontend needs {MIN_NODE[0]}.{MIN_NODE[1]} or newer. "
             "Install the current LTS from https://nodejs.org/.")
    return node, npm


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0 if IS_WIN else 1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_port(preferred: int, label: str, explicit: bool) -> int:
    if port_free(preferred):
        return preferred
    if explicit:
        fail(f"Port {preferred} ({label}) is already in use. Close the program using it or pick another port.")
    for p in range(preferred + 1, preferred + 20):
        if port_free(p):
            say(f"  Port {preferred} is busy, using {p} for the {label}.")
            return p
    fail(f"No free port found near {preferred} for the {label}.")


def smart_app_control_state() -> int | None:
    """Windows Smart App Control: 0 off, 1 on, 2 evaluation mode; None when it cannot be read (not Windows, or no such value).
    Reading needs no administrator rights. Used only for an advisory note, never to block anything."""
    if not IS_WIN:
        return None
    try:
        import winreg  # type: ignore[import-not-found]  # Windows only

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as key:
            value, _ = winreg.QueryValueEx(key, "VerifiedAndReputablePolicyState")
        return int(value)
    except (OSError, ImportError, ValueError):
        return None


def environment_notes() -> list[str]:
    """Things that are not errors but often explain a later failure (shown as NOTE, never stop the start)."""
    notes: list[str] = []
    here = str(ROOT)
    if IS_WIN and len(here) > 80:
        notes.append(f"The project folder path is long ({len(here)} characters). Windows limits paths to 260 characters and the web "
                     "packages use deep folders. If the install fails, move the project to a short path such as C:\\EnergiQ.")
    if any(name in here.lower() for name in ("onedrive", "dropbox", "google drive")):
        notes.append("The project is inside a cloud-sync folder. Sync tools can lock files during the install; a plain folder "
                     "such as C:\\EnergiQ is safer.")
    if smart_app_control_state() in (1, 2):
        notes.append("Windows Smart App Control is on. It can block unsigned programs that Python or web packages bring. "
                     "If Windows shows a 'blocked' message, see START_HERE.md (section 'When something goes wrong').")
    return notes


# --------------------------------------------------------------------------- one-time setup
def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def run_logged(cmd: list[str], log: Path, cwd: Path, what: str) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as fh:
        rc = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        fail(f"{what} failed (exit code {rc}). Last lines of {log}:\n\n{tail(log)}\n\n"
             "  Check your internet connection and try again.")


def ensure_backend_env(reinstall: bool) -> Path:
    req = ROOT / "requirements.txt"
    if not req.is_file():
        fail("requirements.txt not found. Run this launcher from the EnergiQ-AI project folder.")
    if reinstall and VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
    py = venv_python()
    if py.exists():
        got = subprocess.run([str(py), "-c", "import sys;print('%d.%d'%sys.version_info[:2])"],
                             capture_output=True, text=True).stdout.strip()
        want = f"{sys.version_info.major}.{sys.version_info.minor}"
        if got != want:
            say(f"  The existing .venv uses Python {got or '?'}, rebuilding it for {want}.")
            shutil.rmtree(VENV, ignore_errors=True)
    if not py.exists():
        step("Creating the Python environment (.venv) ...")
        try:
            venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
        except Exception as exc:  # noqa: BLE001
            fail(f"Could not create .venv: {exc}")
    digest = sha256_of(req)
    if REQ_MARK.exists() and REQ_MARK.read_text().strip() == digest:
        say("  Python packages: already installed.")
        return py
    step("Installing Python packages (first run takes a few minutes) ...")
    log = RUN_DIR / "pip-install.log"
    run_logged([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)], log, ROOT,
               "Installing Python packages")
    REQ_MARK.write_text(digest)
    return py


def ensure_frontend_deps(npm: str, reinstall: bool) -> None:
    lock = FRONTEND / "package-lock.json"
    if not lock.is_file():
        fail("frontend/package-lock.json not found. Run this launcher from the EnergiQ-AI project folder.")
    if reinstall:
        shutil.rmtree(FRONTEND / "node_modules", ignore_errors=True)
    digest = sha256_of(lock)
    if LOCK_MARK.exists() and LOCK_MARK.read_text().strip() == digest:
        say("  Frontend packages: already installed.")
        return
    step("Installing frontend packages with npm (first run takes a few minutes) ...")
    log = RUN_DIR / "npm-install.log"
    run_logged([npm, "ci", "--no-audit", "--no-fund"], log, FRONTEND, "Installing frontend packages")
    LOCK_MARK.write_text(digest)


DB_SNIPPET = r"""
from sqlalchemy import inspect, text
from backend.app.config import Settings
from backend.app.db import Database
settings = Settings()
db = Database(settings.database_url)
db.create_all()
with db.session() as session:
    session.execute(text("SELECT 1"))
    users = session.execute(text("SELECT count(*) FROM users")).scalar()
print("DB_OK", len(inspect(db.engine).get_table_names()), users)
"""


def error_line(path: Path) -> str:
    """The line of a log that names the error (for example 'sqlite3.OperationalError: unable to open database file')."""
    lines = [x.strip() for x in tail(path, 80).splitlines() if x.strip()]
    for line in reversed(lines):
        if ("Error" in line or "Exception" in line) and not line.startswith(("File ", "Background on")):
            return line
    return lines[-1] if lines else "(the log is empty)"


def prepare_database(py: Path, env: dict[str, str]) -> str:
    """Create or check the database before any server starts, so a problem is reported here in plain words.
    Returns a one-line outcome. SQLite (the default) is a single file, data/energiq.db."""
    data = ROOT / "data"
    try:
        data.mkdir(exist_ok=True)
        probe_file = data / ".write_test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        fail(f"The folder {data} cannot be written to ({exc}).\n"
             "  Do not run EnergiQ AI from inside the ZIP, from Program Files, or from a read-only or protected location.\n"
             "  Extract the ZIP to a normal folder such as C:\\EnergiQ and run it from there.")
    existed = (data / "energiq.db").exists()
    log = RUN_DIR / "database.log"
    with log.open("wb") as fh:
        rc = subprocess.run([str(py), "-c", DB_SNIPPET], cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
    out = tail(log, 60)
    marker = [line for line in out.splitlines() if line.startswith("DB_OK ")]
    if rc != 0 or not marker:
        fail("The database could not be prepared.\n"
             f"  Reason: {error_line(log)}\n\n"
             "  Common causes: the folder is read-only, the disk is full, or a sync tool (OneDrive) or an antivirus has\n"
             f"  locked data{os.sep}energiq.db. Close other programs that use the project folder and try again.\n"
             f"  Full details: {log}")
    _, tables, users = marker[-1].split()
    where = env.get("ENERGIQ_DATABASE_URL")
    place = "the database you configured in ENERGIQ_DATABASE_URL" if where else f"data{os.sep}energiq.db"
    state = "ready" if existed else "created"
    return f"{state} ({place}, {tables} tables, {users} user account(s))"


# --------------------------------------------------------------------------- process handling
class Child:
    def __init__(self, name: str, cmd: list[str], cwd: Path, env: dict[str, str], log: Path):
        self.name, self.log = name, log
        log.parent.mkdir(parents=True, exist_ok=True)
        self._fh = log.open("wb")
        kw: dict = {}
        if IS_WIN:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kw["start_new_session"] = True
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=self._fh, stderr=subprocess.STDOUT, **kw)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                if IS_WIN:  # kill the whole tree (npm.cmd -> node -> vite)
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                                   capture_output=True, timeout=20)
                else:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except (OSError, subprocess.SubprocessError):
                self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    if not IS_WIN:
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                    else:
                        self.proc.kill()
                except OSError:
                    pass
        self._fh.close()


# --------------------------------------------------------------------------- HTTP helpers
# Local calls must never go through a system / corporate proxy (common on Windows), so use an opener without one.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method: str, url: str, body: dict | None = None, token: str | None = None, timeout: float = 15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with OPENER.open(req, timeout=timeout) as r:  # local URL only
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def probe(url: str, timeout: float = 3) -> tuple[int, str] | None:
    """(HTTP status, body text) of a local URL, or None when nothing answers."""
    try:
        with OPENER.open(url, timeout=timeout) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(200_000).decode("utf-8", "replace")
        except (OSError, ValueError):
            body = ""
        return exc.code, body
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def backend_ready(status: int, body: str) -> bool:
    """/health/ready of the EnergiQ backend with its database reachable."""
    return status == 200 and '"database"' in body and '"up"' in body


def backend_is_ours(status: int, body: str) -> bool:
    """Whatever answers is the EnergiQ backend, even if its database is momentarily down (503)."""
    return status in (200, 503) and '"database"' in body


def web_ready(status: int, body: str) -> bool:
    """The Vite dev server is serving the EnergiQ page (not some other program on that port)."""
    return status == 200 and "EnergiQ" in body


def wait_for(url: str, children: list[Child], seconds: int, what: str, ok=None) -> None:
    """Wait until `url` answers acceptably. `ok(status, body)` decides; the default accepts anything below HTTP 500.
    A child that has stopped is reported at once, before any answer is trusted (it could come from another program)."""
    accept = ok or (lambda status, body: status < 500)
    deadline = time.time() + seconds
    while time.time() < deadline:
        for c in children:
            if not c.alive():
                fail(f"The {c.name} stopped while starting (exit code {c.proc.returncode}). "
                     f"Last lines of {c.log}:\n\n{tail(c.log)}")
        res = probe(url)
        if res is not None and accept(*res):
            for c in children:  # it must still be running after it answered, or the answer was not from it
                if not c.alive():
                    fail(f"The {c.name} stopped while starting (exit code {c.proc.returncode}). "
                         f"Last lines of {c.log}:\n\n{tail(c.log)}")
            return
        time.sleep(1)
    fail(f"The {what} did not become ready within {seconds} s. See the logs in {RUN_DIR}.")


def admin_login(api: str, email: str, password: str) -> tuple[str | None, str]:
    """(token, note). token is None when the account exists with another password or the server cannot be asked."""
    try:
        _, tok = http("POST", f"{api}/auth/login", {"email": email, "password": password})
        return tok["access_token"], ""
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return None, "wrong-password"
        return None, f"sign-in failed (HTTP {exc.code})"
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        return None, f"sign-in failed ({exc})"


def import_societies(api: str, token: str) -> str:
    """Import the bundled societies if none exist. Returns a one-line outcome."""
    _, socs = http("GET", f"{api}/societies", token=token)
    if socs:
        return f"nothing to do - {len(socs)} societies are already loaded"
    _, job = http("POST", f"{api}/admin/societies/import-bundled", token=token)
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(2)
        _, j = http("GET", f"{api}/jobs/{job['id']}", token=token)
        if j["status"] == "succeeded":
            n = len((j.get("result") or {}).get("imported", []))
            return f"done - {n} societies imported"
        if j["status"] == "failed":
            return f"failed - {j.get('error') or 'unknown error'} (you can retry from Society admin in the app)"
    return "still running after 10 minutes - check Society admin in the app"


# --------------------------------------------------------------------------- admin account of this installation
def new_password() -> str:
    """16+ characters with letters, digits and a symbol, so it satisfies the server's password policy."""
    return f"Eq-{secrets.token_urlsafe(9)}-{secrets.randbelow(9000) + 1000}"


def admin_credentials() -> tuple[str, str, str]:
    """(email, password, what to print). Nothing secret is shipped in the ZIP: every installation makes its own.

    Order: ENERGIQ_ADMIN_EMAIL / ENERGIQ_ADMIN_PASSWORD from the environment; the file this launcher saved on the
    first run (.energiq-run/admin_login.txt); the legacy password for a database made by the first launcher
    version; otherwise a new random password, saved to that file and shown in the window.
    """
    env_email, env_pw = os.environ.get("ENERGIQ_ADMIN_EMAIL"), os.environ.get("ENERGIQ_ADMIN_PASSWORD")
    if env_pw:
        return env_email or ADMIN_EMAIL, env_pw, "the password you set in ENERGIQ_ADMIN_PASSWORD"
    try:
        lines = CRED_FILE.read_text(encoding="utf-8").splitlines()
        saved = dict(line.split("=", 1) for line in lines if "=" in line)
        if saved.get("email") and saved.get("password"):
            return saved["email"], saved["password"], saved["password"]
    except OSError:
        pass
    if (ROOT / "data" / "energiq.db").exists():
        return env_email or ADMIN_EMAIL, LEGACY_ADMIN_PASSWORD, LEGACY_ADMIN_PASSWORD
    email, pw = env_email or ADMIN_EMAIL, new_password()
    try:
        RUN_DIR.mkdir(exist_ok=True)
        CRED_FILE.write_text(f"email={email}\npassword={pw}\n", encoding="utf-8")
        if not IS_WIN:
            CRED_FILE.chmod(0o600)
    except OSError:
        pass  # the password is still shown in the window
    return email, pw, pw


def signing_key() -> str:
    """The key that signs sign-in tokens: random per installation and kept in .energiq-run, so logins survive a restart.
    The built-in development key is public (it is in the source), so it is never used by this launcher."""
    env_key = os.environ.get("ENERGIQ_SECRET_KEY")
    if env_key:
        return env_key
    try:
        saved = SECRET_FILE.read_text(encoding="utf-8").strip()
        if len(saved) >= 32:
            return saved
    except OSError:
        pass
    key = secrets.token_urlsafe(48)
    try:
        RUN_DIR.mkdir(exist_ok=True)
        SECRET_FILE.write_text(key, encoding="utf-8")
        if not IS_WIN:
            SECRET_FILE.chmod(0o600)
    except OSError:
        pass  # still random for this run; sessions just end when the launcher restarts
    return key


# --------------------------------------------------------------------------- one instance at a time
def pid_alive(pid: int) -> bool:
    """Is a process with this id running? (On Windows os.kill(pid, 0) would TERMINATE it, so tasklist is used instead.)"""
    if pid <= 0:
        return False
    if IS_WIN:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_state() -> dict | None:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_state(state: dict) -> None:
    RUN_DIR.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def clear_state(only_pid: int | None = None) -> None:
    """Remove the state file (only if it belongs to `only_pid`, so one launcher never deletes another's record)."""
    st = read_state()
    if only_pid is not None and st is not None and st.get("launcher_pid") != only_pid:
        return
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def backend_answers(port: int) -> bool:
    res = probe(f"http://127.0.0.1:{port}/health/ready")
    return res is not None and backend_is_ours(*res)


def web_answers(port: int) -> bool:
    res = probe(f"http://127.0.0.1:{port}/")
    return res is not None and web_ready(*res)


def existing_instance() -> dict | None:
    """The state of a live instance, or None (a stale record left by a crash or a closed window is removed)."""
    st = read_state()
    if st is None:
        return None
    pid = int(st.get("launcher_pid") or 0)
    if pid_alive(pid):
        if st.get("phase") == "starting":
            if time.time() - float(st.get("started_at") or 0) < STARTING_GRACE_S:
                return st
        else:
            for attempt in range(3):  # a busy backend may need a moment before it answers
                if backend_answers(int(st.get("backend_port") or 0)):
                    return st
                if attempt < 2:
                    time.sleep(1)
    clear_state()
    return None


def claim_instance(state: dict) -> bool:
    """Atomically record this launcher as THE instance. False if another live launcher holds it."""
    RUN_DIR.mkdir(exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(STATE_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if existing_instance() is not None:
                return False
            continue  # the record was stale and has been removed: try once more
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(state, indent=1))
        return True
    return False


def kill_tree(pid: int) -> None:
    if pid <= 0:
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        return
    try:  # children run in their own session, so the group id equals the pid
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def stop_marked() -> bool:
    """True while STOP_PROJECT is stopping this instance (the record says so)."""
    recorded = read_state()
    return recorded is not None and recorded.get("phase") == "stopping"


def stop_requested() -> bool:
    """True once STOP_PROJECT has begun or the record is gone: a server that vanishes then is not a crash."""
    return read_state() is None or stop_marked()


def stop_instance() -> int:
    """Stop the web app, the backend and the launcher recorded in state.json, and nothing else.

    A process id alone can be reused by an unrelated program after a crash, so a recorded server is stopped only if
    something that is verifiably EnergiQ still answers on its recorded port; the launcher only if it is alive and
    either one of its servers answers or it is still within its start-up time.
    """
    st = read_state()
    if st is None:
        say("[EnergiQ] No running instance is recorded. Nothing to stop.")
        say("  (If a server window is still open, close that window or press Ctrl+C in it.)")
        return 0
    say("[EnergiQ] Stopping EnergiQ AI ...")
    be_pid, fe_pid, ln_pid = (int(st.get(k) or 0) for k in ("backend_pid", "frontend_pid", "launcher_pid"))
    be_up = bool(st.get("backend_port")) and backend_answers(int(st["backend_port"]))
    fe_up = bool(st.get("frontend_port")) and web_answers(int(st["frontend_port"]))
    starting = st.get("phase") == "starting" and time.time() - float(st.get("started_at") or 0) < STARTING_GRACE_S
    owned = {
        "web app": (fe_pid, fe_up or (starting and ln_pid > 0 and pid_alive(ln_pid))),
        "backend": (be_pid, be_up or (starting and ln_pid > 0 and pid_alive(ln_pid))),
        "launcher": (ln_pid, be_up or fe_up or starting),
    }
    try:  # tell the launcher window that this is a requested stop, not a crash
        write_state({**st, "phase": "stopping"})
    except OSError:
        pass
    stopped: list[int] = []
    if not starting and ln_pid > 0 and owned["launcher"][1] and pid_alive(ln_pid):
        # The launcher window is running normally: let it shut its own servers down and exit with code 0, so that
        # window ends cleanly instead of reporting a crash. Anything still alive afterwards is stopped below.
        say("  Asking the EnergiQ window to shut down ...")
        deadline = time.time() + GRACEFUL_STOP_S
        while time.time() < deadline and pid_alive(ln_pid):
            time.sleep(0.5)
        if not pid_alive(ln_pid):
            say("  The EnergiQ window shut the servers down and closed.")
        # re-check what still belongs to EnergiQ: after a clean shutdown the recorded server numbers may be free for reuse
        be_up = bool(st.get("backend_port")) and backend_answers(int(st["backend_port"]))
        fe_up = bool(st.get("frontend_port")) and web_answers(int(st["frontend_port"]))
        owned["web app"], owned["backend"] = (fe_pid, fe_up), (be_pid, be_up)
    for label, (pid, ours) in owned.items():  # servers first, then the launcher that supervises them
        if not pid or not pid_alive(pid):
            continue
        if not ours:
            say(f"  Left process {pid} alone: it is recorded as the {label} but nothing from EnergiQ answers any more, "
                "so it may be an unrelated program that reused the number.")
            continue
        kill_tree(pid)
        stopped.append(pid)
        say(f"  Stopped the {label} (process {pid}).")
    deadline = time.time() + 15
    while time.time() < deadline and any(pid_alive(p) for p in stopped):
        time.sleep(0.5)
    left = [p for p in stopped if pid_alive(p)]
    clear_state()
    if left:
        say(f"[EnergiQ] Could not stop process(es) {', '.join(map(str, left))}. Close their windows or end them in Task Manager.")
        return 1
    say("[EnergiQ] Stopped. Your data is kept in data/energiq.db.")
    return 0


def print_status() -> int:
    st = existing_instance()
    if st is None:
        say("[EnergiQ] EnergiQ AI is not running.")
        return 1
    if st.get("phase") == "starting":
        say("[EnergiQ] EnergiQ AI is starting in another window. Wait for it to print the address.")
        return 0
    say(f"[EnergiQ] EnergiQ AI is running:  http://127.0.0.1:{st['frontend_port']}")
    say(f"  Backend / API documentation:    http://127.0.0.1:{st['backend_port']}/docs")
    return 0


def doctor() -> int:
    """Report on the computer and the installation without installing or changing anything. Exit code 1 if something blocks a start."""
    problems = 0

    def row(ok: bool | None, what: str, detail: str = "") -> None:
        nonlocal problems
        tag = {True: "OK     ", False: "MISSING", None: "NOTE   "}[ok]
        if ok is False:
            problems += 1
        say(f"  [{tag}] {what}" + (f" - {detail}" if detail else ""))

    cur, (lo, hi) = sys.version_info[:2], SUPPORTED_PY
    row(lo <= cur <= hi, f"Python {cur[0]}.{cur[1]}", "supported" if lo <= cur <= hi else f"needs {lo[0]}.{lo[1]} to {hi[0]}.{hi[1]}")
    node, npm = shutil.which("node"), shutil.which("npm")
    ver = node_version(node) if node else None
    row(bool(ver and ver >= MIN_NODE), "Node.js" + (f" {ver[0]}.{ver[1]}" if ver else ""), f"needs {MIN_NODE[0]}.{MIN_NODE[1]} or newer" if not (ver and ver >= MIN_NODE) else "supported")
    row(bool(npm), "npm", "" if npm else "comes with Node.js")
    req, lock = ROOT / "requirements.txt", FRONTEND / "package-lock.json"
    row(req.is_file() and lock.is_file(), "Project files (requirements.txt, frontend/package-lock.json)", "" if req.is_file() and lock.is_file() else "run this from the EnergiQ-AI folder")
    py = venv_python()
    row(None, "Python environment (.venv)", "found" if py.exists() else "not created yet; RUN_PROJECT creates it")
    if py.exists() and req.is_file():
        done = REQ_MARK.exists() and REQ_MARK.read_text().strip() == sha256_of(req)
        row(None, "Python packages", "installed" if done else "will be installed on the next start")
    if lock.is_file():
        done = LOCK_MARK.exists() and LOCK_MARK.read_text().strip() == sha256_of(lock)
        row(None, "Frontend packages", "installed" if done else "will be installed on the next start")
    bundled = ROOT / "data" / "society" / "processed" / "societies.json"
    row(bundled.is_file(), "Bundled community data", "" if bundled.is_file() else "data/society/processed is missing; the ZIP may be incomplete")
    try:
        (ROOT / "data").mkdir(exist_ok=True)
        probe_file = ROOT / "data" / ".write_test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        row(True, "Project folder is writable", "")
    except OSError as exc:
        row(False, "Project folder is writable", f"{exc}; extract the ZIP to a normal folder such as C:\\EnergiQ")
    db_file = ROOT / "data" / "energiq.db"
    row(None, "Database", "data/energiq.db exists and is kept between runs" if db_file.exists() else "will be created on the first start")
    try:
        free_gb = shutil.disk_usage(ROOT).free / 1e9
        row(free_gb >= 3, f"Free disk space {free_gb:.1f} GB", "" if free_gb >= 3 else "about 3 GB are needed for the first install")
    except OSError:
        row(None, "Free disk space", "could not be read")
    for note in environment_notes():
        row(None, "Note", note)
    st = existing_instance()
    if st:
        row(None, "EnergiQ AI is already running", f"http://127.0.0.1:{st.get('frontend_port')}")
    else:
        for port, label in ((8000, "backend"), (5173, "web app")):
            row(None, f"Port {port} ({label})", "free" if port_free(port) else "in use by another program; the launcher will pick the next free port")
    say("")
    say("[EnergiQ] " + ("Everything needed is present." if problems == 0 else f"{problems} item(s) need attention (marked MISSING)."))
    return 0 if problems == 0 else 1


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Run EnergiQ AI locally with one command.")
    ap.add_argument("--no-import", action="store_true", help="do not auto-import the bundled societies")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--check", action="store_true", help="check requirements and install packages, then exit")
    ap.add_argument("--reinstall", action="store_true", help="delete .venv and node_modules and install again")
    ap.add_argument("--status", action="store_true", help="say whether EnergiQ AI is running and where")
    ap.add_argument("--stop", action="store_true", help="stop a running instance")
    ap.add_argument("--doctor", action="store_true", help="check the computer and the installation; changes nothing")
    ap.add_argument("--backend-port", type=int, default=None)
    ap.add_argument("--frontend-port", type=int, default=None)
    args = ap.parse_args()

    signal.signal(signal.SIGINT, signal.default_int_handler)  # Ctrl+C -> KeyboardInterrupt, even if the parent ignored it
    if hasattr(signal, "SIGTERM"):  # `kill`/closing the window behaves like Ctrl+C
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    try:  # keep the Windows console from crashing on odd characters
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if args.stop:
        if RUN_DIR.exists():
            start_log("stop")
        return stop_instance()
    if args.status:
        return print_status()
    say("=" * 64)
    say("  EnergiQ AI - local launcher")
    say("=" * 64)
    if args.doctor:
        say("\n[EnergiQ] Checking your computer and the installation ...")
        return doctor()
    start_log("check" if args.check else "start")

    live = existing_instance()
    if live is not None and not args.check:
        if live.get("phase") == "stopping":
            say("\n[EnergiQ] EnergiQ AI is being stopped right now. Run it again in a few seconds.")
        elif live.get("phase") == "starting":
            say("\n[EnergiQ] EnergiQ AI is already starting in another window. Wait for that window to print the address.")
        else:
            url = f"http://127.0.0.1:{live['frontend_port']}"
            say(f"\n[EnergiQ] EnergiQ AI is already running:  {url}")
            say("  No second copy was started. To restart it, run STOP_PROJECT first.")
            if not args.no_browser:
                webbrowser.open(url)
        return 0

    step("Checking your computer ...")
    check_python()
    say(f"  Python {sys.version_info.major}.{sys.version_info.minor}: OK")
    node, npm = check_node()
    say(f"  Node.js {'.'.join(map(str, node_version(node) or ()))}: OK")
    for note in environment_notes():
        say(f"  NOTE: {note}")
    RUN_DIR.mkdir(exist_ok=True)

    py = ensure_backend_env(args.reinstall)
    ensure_frontend_deps(npm, args.reinstall)
    if args.check:
        say("\n[EnergiQ] Check complete. Everything needed is installed.")
        return 0

    be_port = pick_port(args.backend_port or 8000, "backend", args.backend_port is not None)
    fe_port = pick_port(args.frontend_port or 5173, "web app", args.frontend_port is not None)

    email, password, shown_password = admin_credentials()

    env = dict(os.environ)
    env.update({
        "ENERGIQ_ENV": "dev",
        "ENERGIQ_ADMIN_EMAIL": email,
        "ENERGIQ_ADMIN_PASSWORD": password,
        "ENERGIQ_SECRET_KEY": signing_key(),
        "PYTHONUNBUFFERED": "1",
        "VITE_DEV_PROXY_TARGET": f"http://127.0.0.1:{be_port}",
    })

    children: list[Child] = []
    state = {"launcher_pid": os.getpid(), "phase": "starting", "started_at": time.time(), "backend_port": be_port, "frontend_port": fe_port}
    if not claim_instance(state):
        say("\n[EnergiQ] EnergiQ AI was just started by another window. No second copy was started.")
        return 0

    def shutdown() -> None:
        for c in reversed(children):
            c.stop()
        clear_state(only_pid=os.getpid())

    try:
        step("Preparing the database ...")
        say("  Database: " + prepare_database(py, env))

        step("Starting the backend ...")
        children.append(Child(
            "backend",
            [str(py), "-m", "uvicorn", "backend.app.main:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(be_port)],
            ROOT, env, RUN_DIR / "backend.log"))
        state["backend_pid"] = children[-1].proc.pid
        write_state(state)
        wait_for(f"http://127.0.0.1:{be_port}/health/ready", children, 90, "backend", ok=backend_ready)
        say("  Backend: ready (answers, database up)")

        step("Starting the web app ...")
        children.append(Child(
            "web app",
            [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(fe_port), "--strictPort"],
            FRONTEND, env, RUN_DIR / "frontend.log"))
        state["frontend_pid"] = children[-1].proc.pid
        write_state(state)
        wait_for(f"http://127.0.0.1:{fe_port}/", children, 90, "web app", ok=web_ready)
        # the path the browser uses: web app -> its proxy -> backend. If this fails the page would open but show errors.
        wait_for(f"http://127.0.0.1:{fe_port}/health/ready", children, 30, "connection between the web app and the backend",
                 ok=backend_ready)
        say("  Web app: ready (serves the EnergiQ page and reaches the backend)")

        api = f"http://127.0.0.1:{be_port}/api/v1"
        token, login_note = admin_login(api, email, password)
        if not args.no_import:
            step("Loading the bundled societies (first run only) ...")
            if token is None:
                say("  Import: skipped - the admin account already exists with a different password. "
                    "Sign in yourself and use Society admin in the app." if login_note == "wrong-password" else f"  Import: skipped - {login_note}.")
            else:
                try:
                    say("  Import: " + import_societies(api, token))
                except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
                    say(f"  Import: skipped ({exc}). You can import from Society admin in the app.")

        url = f"http://127.0.0.1:{fe_port}"
        state["phase"] = "running"
        write_state(state)
        say("\n" + "=" * 64)
        say(f"  EnergiQ AI is running:  {url}")
        if token is None and login_note == "wrong-password":
            say(f"  Sign in with:           the {email} password you chose earlier for this installation")
        else:
            # the password goes to the window only; launcher.log gets a placeholder
            say(f"  Sign in with:           {email}   /   {shown_password}",
                log_msg=f"  Sign in with:           {email}   /   (password shown in the window only)")
            if CRED_FILE.exists() and shown_password == password and password != LEGACY_ADMIN_PASSWORD:
                say(f"  (This password is unique to this installation and is saved in {CRED_FILE.relative_to(ROOT)}.)")
        say(f"  API documentation:      http://127.0.0.1:{be_port}/docs")
        say("  Keep this window open while you use the app. To stop: press Ctrl+C here, or run STOP_PROJECT.bat.")
        say(f"  Logs for troubleshooting: {RUN_DIR.name}{os.sep}launcher.log, backend.log, frontend.log")
        say("=" * 64)
        if not args.no_browser:
            try:
                opened = webbrowser.open(url)
            except Exception:  # noqa: BLE001 - no browser must never stop the app
                opened = False
            if not opened:
                say(f"  Your browser could not be opened automatically. Open this address yourself: {url}")

        while True:
            if stop_marked():  # STOP_PROJECT.bat asked this window to shut down
                say("\n[EnergiQ] EnergiQ AI was stopped with STOP_PROJECT.bat.")
                return 0
            for c in children:
                if not c.alive():
                    if stop_requested():
                        say("\n[EnergiQ] EnergiQ AI was stopped with STOP_PROJECT.bat.")
                        return 0
                    say(f"\n[EnergiQ] The {c.name} stopped unexpectedly (exit code {c.proc.returncode}). "
                        f"Last lines of {c.log}:\n\n{tail(c.log)}")
                    return 1
            time.sleep(1.0)
    except KeyboardInterrupt:
        say("\n[EnergiQ] Stopping ...")
        return 0
    finally:
        started = bool(children)
        shutdown()
        if started:
            say("[EnergiQ] Stopped. Your data is kept in data/energiq.db.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\n[EnergiQ] Cancelled. Run it again any time; setup continues where it stopped.")
        sys.exit(130)
