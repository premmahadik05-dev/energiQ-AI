"""Fixtures that start a REAL server process (uvicorn) on a free port with a temporary SQLite database."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
ADMIN = ("admin@example.com", "AdminPass-12345")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    port = free_port()
    env = {**os.environ, "ENERGIQ_ENV": "dev", "ENERGIQ_DATABASE_URL": f"sqlite:///{(tmp / 'e2e.db').as_posix()}",
           "ENERGIQ_SECRET_KEY": "e2e-" + "k" * 48, "ENERGIQ_UPLOAD_DIR": str(tmp / "uploads"), "ENERGIQ_MODELS_DIR": str(tmp / "models"),
           "ENERGIQ_ADMIN_EMAIL": ADMIN[0], "ENERGIQ_ADMIN_PASSWORD": ADMIN[1], "ENERGIQ_CORS_ORIGINS": '["http://127.0.0.1:4173","http://localhost:4173"]',
           "ENERGIQ_LOGIN_PER_MINUTE": "1000", "ENERGIQ_REGISTER_PER_HOUR": "1000", "OMP_NUM_THREADS": "2"}
    log = (tmp / "server.log").open("w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:create_app", "--factory", "--port", str(port), "--host", "127.0.0.1"],
                            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health/ready", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("server did not become ready:\n" + (tmp / "server.log").read_text()[-2000:])
        yield {"base": base, "port": port, "log": tmp / "server.log"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
