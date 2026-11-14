"""Check a running EnergiQ AI that was started from an extracted ZIP.   python check_running.py <extracted EnergiQ-AI folder>

Reads the ports from <folder>/.energiq-run/state.json and the generated password from admin_login.txt (the password is never printed).
Checks: health through the web app's proxy, sign-in, the societies, a live forecast for each, the old shared password is refused,
13 pages in a real browser (heading, window title, no console or HTTP errors), and that no log file contains the password.
"""
import json
import sys
import urllib.request
from pathlib import Path

root = Path(sys.argv[1]).resolve()
run = root / ".energiq-run"
state = json.loads((run / "state.json").read_text())
fe, be = state["frontend_port"], state["backend_port"]
kv = dict(line.split("=", 1) for line in (run / "admin_login.txt").read_text().split() if "=" in line)
email, pwd = kv["email"], kv["password"]
print(f"state: phase={state['phase']} web app :{fe} backend :{be}; admin_login.txt has a generated password: {'EnergiQ-Local-2026' not in pwd and len(pwd) >= 12}")
fails = 0


def req(base, path, data=None, tok=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=h)
    return json.load(urllib.request.urlopen(r, timeout=30))


health = req(f"http://127.0.0.1:{fe}", "/health/ready")
print("health through the web app's proxy:", health)
fails += not (health.get("status") == "ok" and health.get("database") == "up")
api = f"http://127.0.0.1:{be}/api/v1"
tok = req(api, "/auth/login", {"email": email, "password": pwd})["access_token"]
socs = req(api, "/societies", tok=tok)
print("societies:", len(socs), sorted(s["key"] for s in socs))
fails += len(socs) != 7
good = 0
for s in socs:
    f = req(api, f"/societies/{s['id']}/forecast", tok=tok)
    pts = f.get("points") or f.get("forecast") or []
    ok = bool(pts) and (all(p["lower"] <= p["forecast"] <= p["upper"] and p["forecast"] >= 0 for p in pts) if "lower" in pts[0] else True)
    print(f"  {s['key']}: forecast points {len(pts)} {'ok' if ok else 'CHECK'}")
    good += ok
print("live forecasts ok:", good, "of", len(socs))
fails += good != len(socs)
try:
    req(api, "/auth/login", {"email": email, "password": "EnergiQ-Local-2026"})
    print("OLD SHARED PASSWORD ACCEPTED (bad)")
    fails += 1
except Exception as exc:  # noqa: BLE001
    print("old shared password refused:", getattr(exc, "code", exc))
    fails += getattr(exc, "code", None) != 401

leaks = [p.name for p in run.glob("*.log*") if pwd in p.read_text(errors="replace")]
print("log files containing the password:", leaks or "none")
fails += bool(leaks)

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = f"http://127.0.0.1:{fe}"
routes = [("/", "Society overview"), ("/compare", "Compare communities"), ("/consumption", "Consumption"), ("/forecasting", "Forecasting"),
          ("/buildings", "Buildings"), ("/cost", "Cost and peak demand"), ("/alerts", "Alerts"), ("/recommendations", "Recommendations"),
          ("/reports", "Reports"), ("/data-sources", "Data sources"), ("/society-admin", "Society administration"), ("/admin", "Administration"),
          ("/jobs", "Jobs")]
bad, errs = 0, []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    pg.on("console", lambda m: errs.append(m.text[:150]) if m.type in ("error", "warning") else None)
    pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url[-80:]}") if r.status >= 400 else None)
    pg.goto(BASE + "/login", wait_until="networkidle")
    pg.get_by_label("Email address").fill(email)
    pg.get_by_label("Password", exact=True).fill(pwd)
    pg.get_by_role("button", name="Sign in").click()
    pg.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    for r, h1 in routes:
        pg.goto(BASE + r, wait_until="networkidle")
        pg.wait_for_timeout(900)
        got = [e.inner_text() for e in pg.locator("h1").all()][:1]
        ok = got == [h1] and pg.locator("main").inner_text().strip() != ""
        bad += not ok
        print("PASS" if ok else "FAIL", r, got, pg.title())
    b.close()
print("pages failed:", bad, "| console/HTTP problems:", errs[:5] or "none")
fails += bad + bool(errs)
print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails} problem(s))")
sys.exit(1 if fails else 0)
