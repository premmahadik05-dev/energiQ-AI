"""Audit the built web interface in a real browser: WCAG 2 A/AA rules (axe-core) and a sweep for broken numbers in the page text.

Starts the real backend (all bundled societies imported) and the built frontend, opens the sign-in and registration pages, signs in as the
administrator, opens every society page, the jobs list and the administration page in Chromium and:

* runs axe-core with the `wcag2a` and `wcag2aa` rule sets (this includes colour contrast, names for controls, image alternatives);
* looks in the visible text for things that should never reach a reader: unrounded floats such as 89.21666666666667, NaN, undefined,
  Infinity and "[object".

Prerequisites (none of them are installed by this script):

    cd frontend && npm ci && npm run build && npm install --no-save axe-core@4.10.2
    pip install playwright==1.63.0 && playwright install chromium

Run from the repository root:  python scripts/ui_audit.py        Exit status 1 when a violation or a leak is found.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
ADMIN_EMAIL, ADMIN_PASSWORD = "admin@example.com", "AdminPass-12345"  # secret-scan: allow (throw-away local instance)
SIGNED_OUT_PAGES = [("sign in", "/login"), ("create account", "/register")]
PAGES = [
    ("society overview", "/"), ("consumption", "/consumption"), ("forecasting", "/forecasting"), ("buildings", "/buildings"),
    ("common facilities", "/facilities"), ("cost and peaks", "/cost"), ("alerts", "/alerts"), ("recommendations", "/recommendations"),
    ("reports", "/reports"), ("data sources", "/data-sources"), ("society admin", "/society-admin"),
    ("jobs", "/jobs"), ("administration", "/admin"),
]
LEAK = re.compile(r"\d+\.\d{5,}|NaN|undefined|\[object|Infinity")
RUN_AXE = """async () => {
  const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
  return r.violations.map(v => ({ id: v.id, impact: v.impact, count: v.nodes.length,
    sample: v.nodes.slice(0, 3).map(n => n.target.join(' ') + ' :: ' + (n.any[0] ? n.any[0].message : '').slice(0, 110)) }));
}"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_servers(tmp: Path, api_port: int, web_port: int) -> tuple[subprocess.Popen, subprocess.Popen]:
    env = {**os.environ, "ENERGIQ_ENV": "dev", "ENERGIQ_DATABASE_URL": f"sqlite:///{tmp / 'audit.db'}", "ENERGIQ_SECRET_KEY": "audit-" + "k" * 48,
           "ENERGIQ_UPLOAD_DIR": str(tmp / "uploads"), "ENERGIQ_MODELS_DIR": str(tmp / "models"), "ENERGIQ_ADMIN_EMAIL": ADMIN_EMAIL,
           "ENERGIQ_ADMIN_PASSWORD": ADMIN_PASSWORD, "ENERGIQ_CORS_ORIGINS": f'["http://127.0.0.1:{web_port}"]', "OMP_NUM_THREADS": "2"}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(api_port)],
                           cwd=REPO, env=env, stdout=(tmp / "api.log").open("w"), stderr=subprocess.STDOUT)
    web = subprocess.Popen(["node", str(REPO / "frontend/node_modules/vite/bin/vite.js"), "preview", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                           cwd=REPO / "frontend", env={**os.environ, "VITE_DEV_PROXY_TARGET": f"http://127.0.0.1:{api_port}"},
                           stdout=(tmp / "web.log").open("w"), stderr=subprocess.STDOUT)
    return api, web


def import_societies(base: str) -> None:
    for _ in range(80):
        try:
            if httpx.get(f"{base}/health/ready", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    token = httpx.post(f"{base}/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json()["access_token"]
    headers = {"authorization": f"Bearer {token}"}
    job = httpx.post(f"{base}/api/v1/admin/societies/import-bundled", headers=headers, timeout=600).json()
    for _ in range(300):
        status = httpx.get(f"{base}/api/v1/jobs/{job['id']}", headers=headers).json()["status"]
        if status in ("succeeded", "failed"):
            break
        time.sleep(2)
    if status != "succeeded":
        raise SystemExit(f"import of the bundled societies ended with status {status}")


def audit_page(page, site: str, name: str, path: str, axe_source: str) -> int:
    page.goto(f"{site}{path}")
    page.wait_for_load_state("networkidle")
    time.sleep(1.2)  # charts animate in and tables fill after the network is idle
    text = page.inner_text("body")
    leaks = [text[max(0, m.start() - 40): m.end() + 20].replace("\n", " ") for m in LEAK.finditer(text)]
    page.evaluate("src => { const s = document.createElement('script'); s.textContent = src; document.head.appendChild(s); }", axe_source)
    violations = page.evaluate(RUN_AXE)
    status = "ok" if not leaks and not violations else "PROBLEM"
    print(f"{status:8} {name}: {len(violations)} axe rule(s) violated, {len(leaks)} text leak(s)")
    for v in violations:
        print(f"           {v['id']} ({v['impact']}, {v['count']} element(s))")
        for sample in v["sample"]:
            print(f"             {sample}")
    for leak in leaks:
        print(f"           text leak: ...{leak}...")
    return len(violations) + len(leaks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--axe", type=Path, default=REPO / "frontend/node_modules/axe-core/axe.min.js", help="path to axe.min.js")
    args = parser.parse_args()
    if not args.axe.is_file():
        raise SystemExit(f"axe-core not found at {args.axe}; run: cd frontend && npm install --no-save axe-core@4.10.2")
    if not (REPO / "frontend/dist/index.html").is_file():
        raise SystemExit("the frontend is not built; run: cd frontend && npm run build")
    axe_source = args.axe.read_text(encoding="utf-8")

    api_port, web_port = free_port(), free_port()
    tmp = Path(tempfile.mkdtemp(prefix="ui_audit_"))
    api, web = start_servers(tmp, api_port, web_port)
    problems = 0
    try:
        import_societies(f"http://127.0.0.1:{api_port}")
        site = f"http://127.0.0.1:{web_port}"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
            for name, path in SIGNED_OUT_PAGES:
                problems += audit_page(page, site, name, path, axe_source)
            page.goto(f"{site}/login")
            page.get_by_label("Email address").fill(ADMIN_EMAIL)
            page.get_by_label("Password", exact=True).fill(ADMIN_PASSWORD)
            page.get_by_role("button", name="Sign in").click()
            page.wait_for_url(f"{site}/")
            for name, path in PAGES:
                problems += audit_page(page, site, name, path, axe_source)
            browser.close()
    finally:
        for proc in (web, api):
            proc.terminate()
    print(f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
