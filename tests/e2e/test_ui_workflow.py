"""Browser end-to-end test: a real Chromium drives the built React app, which talks to a real uvicorn server.

Needs a built frontend (``cd frontend && npm ci && npm run build``) and Playwright's Chromium. When either is missing
the test is *skipped with that reason*; it is never faked. The app is served by ``vite preview`` (which proxies /api to
the backend, exactly like nginx does in the Docker image).

What it proves: a new person can register, load data, train a model, make a forecast, run anomaly detection and ask for a
cheapest-window schedule through the user interface, and that every number shown comes from API responses (no 5xx
responses and no browser console errors occur along the way).
"""
from __future__ import annotations

import os
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


def test_new_user_completes_the_main_workflow_in_the_browser(web, browser):
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
    page.get_by_label("E-mail").fill("ui-user@example.com")
    page.get_by_label("Password").fill("short")
    page.get_by_role("button", name="Create account").click()
    assert page.get_by_text("10-128 characters").first.is_visible()
    assert not any("auth/register" in c for c in api_calls), "a weak password must be refused before any request is sent"
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url(lambda u: "/register" not in u and "/login" not in u, timeout=20_000)
    page.screenshot(path=str(SHOTS / "01_after_register.png"))

    # --- data: bundled sample dataset (real hourly UCI readings, 8,760 hours)
    page.get_by_role("link", name="Datasets").first.click()
    page.get_by_role("button", name="Load bundled sample dataset").click()
    # the app opens the new dataset's detail page; its summary line is built from the API record
    page.get_by_text("valid of 8,760 hours").first.wait_for(timeout=60_000)
    ds = next(v for k, v in bodies.items() if k.startswith("GET datasets/") and isinstance(v, dict) and v.get("hours") == 8760)
    assert ds["status"] == "ready" and page.get_by_text(f"{ds['valid_hours']:,} valid of 8,760 hours").first.is_visible()
    page.screenshot(path=str(SHOTS / "02_dataset_ready.png"))

    # --- train a real model (production XGBoost parameters; takes tens of seconds)
    page.get_by_role("link", name="Models").first.click()
    page.get_by_role("button", name="Train a new model").click()
    page.get_by_text("Hold-out accuracy:").first.wait_for(timeout=240_000)
    models = bodies["GET models"]
    assert len(models) == 1 and models[0]["is_active"]
    mae_1h = models[0]["evaluation"]["horizons"]["1"]["metrics"]["xgboost"]["mae"]
    assert page.get_by_role("cell", name=f"{mae_1h:.3f}").first.is_visible(), "the 1-hour MAE on screen must be the one the API returned"
    page.screenshot(path=str(SHOTS / "03_model_trained.png"))

    # --- forecast: the saved forecast card must appear, and its peak must be the peak of the API's points
    page.get_by_role("link", name="Forecast").first.click()
    page.get_by_role("button", name="Create forecast").click()
    page.get_by_text("Forecast peak").first.wait_for(timeout=60_000)
    fc = bodies["POST forecasts"]
    assert len(fc["points"]) == 24
    peak = max(p["kw"] for p in fc["points"])
    assert page.get_by_text(f"{peak:.2f} kW").first.is_visible(), "the forecast peak on screen must be the maximum of the 24 API points"
    page.screenshot(path=str(SHOTS / "04_forecast.png"))

    # --- anomalies: run detection and wait for the summary tiles that only exist after a finished run
    page.get_by_role("link", name="Anomalies").first.click()
    page.get_by_role("button", name="Run detection").click()
    page.get_by_text("Events found").first.wait_for(timeout=120_000)
    summary = bodies["GET anomalies/summary"]
    assert summary["run"] is not None
    page.screenshot(path=str(SHOTS / "05_anomalies.png"))

    # --- everything went through the API and nothing broke
    assert any(c.startswith("POST 201") and "auth/register" in c for c in api_calls)
    assert any(c.startswith("POST 202") and "datasets/sample" in c for c in api_calls)
    assert any(c.startswith("POST 202") and c.endswith("/train") for c in api_calls)
    assert any(c.startswith("POST 201") and c.endswith("forecasts") for c in api_calls)
    assert any(c.startswith("POST 202") and "anomalies/run" in c for c in api_calls)
    assert not server_errors, server_errors
    assert not console_errors, console_errors
