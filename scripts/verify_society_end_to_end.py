"""Run the raw-data verification AGAINST A LIVE API, in one command.

    python scripts/verify_society_end_to_end.py                 # throw-away API + the bundled societies + verify + write the report
    python scripts/verify_society_end_to_end.py --check-subset  # also compare the shipped subset with the full official file (needs the full files)

What it does: starts the application's API as a separate process with an empty temporary database, signs in as the temporary administrator, imports the bundled
societies through the normal admin endpoint (the same path a user takes) and then runs scripts/verify_society_raw_data.py against that API. The verifier is a
separate program; this wrapper only starts and stops the server and passes the address and the temporary credentials through the environment.
Nothing is written to your own database. Extra arguments are passed to the verifier.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "verify-admin@example.com"
PASSWORD = "Aa1-" + secrets.token_urlsafe(18)       # a new random password for every run; it exists only in this process and in the throw-away database


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _call(url: str, token: str | None = None, body: dict | None = None, timeout: int = 600, method: str | None = None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - always http://127.0.0.1:<port> of the server started above  # nosec B310
        return json.loads(r.read())


def main() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = Path(tempfile.mkdtemp(prefix="energiq_verify_"))
    env = {**os.environ, "ENERGIQ_ENV": "dev", "ENERGIQ_DATABASE_URL": f"sqlite:///{tmp / 'verify.db'}", "ENERGIQ_SECRET_KEY": "verify-" + "k" * 48, "ENERGIQ_UPLOAD_DIR": str(tmp / "u"),
           "ENERGIQ_MODELS_DIR": str(tmp / "m"), "ENERGIQ_ADMIN_EMAIL": EMAIL, "ENERGIQ_ADMIN_PASSWORD": PASSWORD, "OMP_NUM_THREADS": "2"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                              stdout=open(tmp / "server.log", "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(f"{base}/health/ready", timeout=2) as r:  # noqa: S310 - local server started above  # nosec B310
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        token = _call(f"{base}/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD})["access_token"]
        job = _call(f"{base}/api/v1/admin/societies/import-bundled", token, method="POST")
        for _ in range(600):
            st = _call(f"{base}/api/v1/jobs/{job['id']}", token)
            if st["status"] in ("succeeded", "failed"):
                break
            time.sleep(2)
        print(f"bundled import: {st['status']}", flush=True)
        if st["status"] != "succeeded":
            print(st, file=sys.stderr)
            return 1
        run_env = {**os.environ, "ENERGIQ_VERIFY_EMAIL": EMAIL, "ENERGIQ_VERIFY_PASSWORD": PASSWORD}
        return subprocess.call([sys.executable, str(ROOT / "scripts/verify_society_raw_data.py"), "--api-url", base, *sys.argv[1:]], env=run_env)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
