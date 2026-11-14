"""Browser end-to-end test: a real Chromium drives the built React app, which talks to a real uvicorn server.

Needs a built frontend (``cd frontend && npm ci && npm run build``) and Playwright's Chromium. When either is missing
the test is *skipped with that reason*; it is never faked. The app is served by ``vite preview`` (which proxies /api to
the backend, exactly like nginx does in the Docker image).

What it proves: a new person can register, read the society overview and its forecast, acknowledge an alert and create and
download a PDF report through the user interface, that every number shown comes from API responses, that the removed
single-meter pages are gone, and that no 5xx responses and no browser console errors occur along the way.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
SHOTS = REPO / "docs" / "screenshots" / "e2e"
PASSWORD = "Correct-Horse-42"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def web(server):
    """`vite preview` of the built bundle, proxying /api and /health to the e2e backend."""
    if not (FRONTEND / "dist" / "index.html").is_file():
        pytest.skip("frontend/dist is missing: run `npm ci && npm run build` in frontend/")
    node = shutil.which("node")
    if node is None or not (FRONTEND / "node_modules" / "vite").is_dir():
        pytest.skip("Node.js or frontend/node_modules is missing: run `npm ci` in frontend/")
    port = free_port()
    env = {**os.environ, "VITE_DEV_PROXY_TARGET": server["base"]}
    proc = subprocess.Popen([node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"), "preview", "--port", str(port), "--strictPort", "--host", "127.0.0.1"],
                            cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(base, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("vite preview did not start")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser():
    with pw_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - any launch failure means "no browser here"
            pytest.skip(f"Chromium could not be started: {exc}")
        yield b
        b.close()


def _ensure_societies(base: str, admin: tuple[str, str]) -> None:
    """The administrator imports the bundled societies once per server (a no-op when another test already did).

    The credentials come from the `server` fixture: importing them with ``from conftest import ADMIN`` depended on which
    of the several conftest.py files pytest had registered under the name "conftest", i.e. on the collection order.
    """
    api = "/api/v1"
    with httpx.Client(base_url=base, timeout=180) as c:
        token = c.post(f"{api}/auth/login", json={"email": admin[0], "password": admin[1]}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        if c.get(f"{api}/societies", headers=h).json():
            return
        job = c.post(f"{api}/admin/societies/import-bundled", headers=h).json()
        for _ in range(600):
            status = c.get(f"{api}/jobs/{job['id']}", headers=h).json()["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.5)
        assert status == "succeeded", f"import of the bundled societies ended with status {status}"


def test_new_user_completes_the_society_workflow_in_the_browser(server, web, browser):
    _ensure_societies(server["base"], server["admin"])
    SHOTS.mkdir(parents=True, exist_ok=True)
    page = browser.new_context(viewport={"width": 1366, "height": 850}).new_page()
    try:
        _workflow(web, page)
    except Exception:
        page.screenshot(path=str(SHOTS / "FAILURE.png"), full_page=True)
        print("\nPAGE TEXT AT FAILURE:\n" + page.inner_text("body")[:1500])
        raise


def _workflow(web, page):
    console_errors: list[str] = []
    server_errors: list[str] = []
    api_calls: list[str] = []
    bodies: dict[str, dict] = {}   # last JSON body per "METHOD path", to compare what the screen shows with what the API sent
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

    def on_response(r):
        if "/api/" not in r.url:
            return
        path = r.url.split("/api/v1/")[-1].split("?")[0]
        api_calls.append(f"{r.request.method} {r.status} {path}")
        if r.status >= 500:
            server_errors.append(f"{r.status} {r.url}")
        if r.status < 300 and "json" in (r.headers.get("content-type") or ""):
            try:
                bodies[f"{r.request.method} {path}"] = r.json()
            except Exception:  # noqa: BLE001 - e.g. a response body that was already discarded on navigation
                pass

    page.on("response", on_response)
    page.set_default_timeout(15_000)

    # --- register through the form (client-side validation first: a weak password is refused in the browser)
    page.goto(f"{web}/register")
    page.get_by_label("Email address").fill("ui-user@example.com")
    page.get_by_label("Password", exact=True).fill("short")
    page.get_by_label("Confirm password", exact=True).fill("short")
    page.get_by_role("button", name="Create account").click()
    assert page.get_by_text("10-128 characters").first.is_visible()
    assert not any("auth/register" in c for c in api_calls), "a weak password must be refused before any request is sent"
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill("Different-Password-1")
    page.get_by_role("button", name="Create account").click()
    assert page.get_by_text("Passwords do not match.").is_visible()
    assert not any("auth/register" in c for c in api_calls), "a mismatching confirmation must be refused before any request is sent"
    page.get_by_label("Confirm password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url(lambda u: "/register" not in u and "/login" not in u, timeout=20_000)
    page.screenshot(path=str(SHOTS / "01_after_register.png"))

    # --- the removed single-meter section: no heading, no links, and the old addresses lead to the not-found page
    nav = page.get_by_role("navigation", name="Main")
    nav.get_by_text("System", exact=True).wait_for()
    assert nav.get_by_text("Single-meter tools").count() == 0
    for gone in ("Dashboard", "Datasets", "Models", "Anomalies", "Explainability", "Optimisation", "Benchmark"):
        assert nav.get_by_role("link", name=gone, exact=True).count() == 0, gone
    page.goto(f"{web}/datasets")
    page.get_by_role("heading", name=re.compile("not found", re.I)).wait_for()
    page.goto(f"{web}/")

    # --- overview of the Fox community: the tiles must show the numbers the API sent
    page.get_by_role("heading", name="Society overview").first.wait_for()
    societies = bodies["GET societies"]
    fox = next(s for s in societies if s["key"] == "fox")
    page.get_by_role("combobox", name="Society", exact=True).select_option(str(fox["id"]))
    page.get_by_text("Energy, last 7 days").first.wait_for()
    ov = bodies[f"GET societies/{fox['id']}/overview"]
    week = ov["windows"]["last_7d"]["energy_kwh"]
    pw_sync.expect(page.locator(".card", has_text="Energy, last 7 days").first).to_contain_text(f"{week:,.0f}")  # waits for the render
    if fox["forecast_ready"]:
        peak = ov["forecast"]["peak_kw"]
        pw_sync.expect(page.locator(".card", has_text="Predicted peak demand").first).to_contain_text(f"{peak:,.0f}")
    page.screenshot(path=str(SHOTS / "02_overview.png"))

    # --- alerts: acknowledge the first open one; the PATCH goes out and the button turns into "Reopen"
    nav.get_by_role("link", name="Alerts", exact=True).click()
    page.get_by_text("Alert timeline").first.wait_for()
    page.get_by_role("button", name=re.compile(r"^Acknowledge alert at")).first.click()
    page.get_by_role("button", name=re.compile(r"^Reopen alert at")).first.wait_for()
    page.screenshot(path=str(SHOTS / "03_alerts.png"))

    # --- reports: create the default report as a PDF and download it
    nav.get_by_role("link", name="Reports", exact=True).click()
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/reports"), timeout=60_000) as created:
        page.get_by_role("button", name="Create report").click()
    assert created.value.status == 201
    new_title = created.value.json()["title"]
    download_button = page.get_by_role("button", name=f"Download {new_title}").first
    download_button.wait_for()
    with page.expect_download() as dl:
        download_button.click()
    assert dl.value.suggested_filename.endswith(".pdf") and Path(dl.value.path()).read_bytes().startswith(b"%PDF-"), "the downloaded file must be a real PDF"
    page.screenshot(path=str(SHOTS / "04_reports.png"))

    # --- everything went through the API and nothing broke
    assert any(c.startswith("POST 201") and "auth/register" in c for c in api_calls)
    assert any(c.startswith("PATCH 200") and "/anomalies/" in c for c in api_calls)
    assert any(c.startswith("POST 201") and c.endswith("/reports") for c in api_calls)
    assert not any("/datasets" in c or c.endswith("/models") for c in api_calls), "the removed pages must not call their old API routes"
    assert not server_errors, server_errors
    assert not console_errors, console_errors
