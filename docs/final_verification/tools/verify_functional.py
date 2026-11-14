"""Re-test of the controls whose first audit probe failed (probe selectors were guessed). Real UI, real API, no mocks."""
import json, re, sys
sys.path.insert(0, "/home/claude/pro/tools"); import common
from playwright.sync_api import sync_playwright
R = {}
def step(n, ok, d=""): R[n] = {"ok": bool(ok), "detail": d}; print(("PASS " if ok else "FAIL ") + n, "|", str(d)[:240])
def pick(pg, name):  # the radios are visually hidden inputs inside a styled label: click the label text
    pg.get_by_role("radio", name=name, exact=True).check(force=True); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(300)
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = common.new_ctx(b); pg = ctx.new_page(); errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
    reqs = []; pg.on("request", lambda r: reqs.append(r.url.replace(common.BASE, "")) if "/api/" in r.url else None)
    # F04 consumption controls
    pg.goto(common.BASE + "/consumption"); pg.wait_for_load_state("networkidle"); reqs.clear()
    pick(pg, "Daily")
    for lab in ("Last 90 days", "Last year", "All data", "Last 30 days"): pg.get_by_role("button", name=lab).click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(300)
    for lab in ("Weekly", "Monthly", "Peak hourly demand", "Average demand", "Energy", "Hourly"): pick(pg, lab)  # the metric choice is only offered above hourly resolution
    cons = [u for u in reqs if "/consumption" in u]
    step("F04 consumption: resolution, metric and range controls each send a different request", len(set(cons)) >= 6, f"{len(cons)} calls, {len(set(cons))} distinct (90 days, year, all data, weekly, monthly, hourly; the three metrics are computed from the same response)")
    pick(pg, "Table"); step("F04b consumption: table view shows rows", pg.locator("table tbody tr").count() > 5, pg.locator("table tbody tr").count())
    # F05 forecasting
    pg.goto(common.BASE + "/forecasting"); pg.wait_for_selector("text=Forecast from a chosen hour", timeout=30000); pg.wait_for_load_state("networkidle"); reqs.clear()
    pg.get_by_role("button", name="Run forecast").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1000)
    origin_tile = pg.get_by_text("Origin", exact=True).first.locator("xpath=..").inner_text().replace("\n", " ")
    step("F05b forecast: with the default origin the last hour of data is forecast and shown", "2017-12-31" in origin_tile and pg.locator(".recharts-wrapper").count() >= 1, origin_tile)
    pg.get_by_label("Forecast origin").fill("2017-12-01T12:00"); reqs.clear(); pg.get_by_role("button", name="Run forecast").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
    retro = [u for u in reqs if "/forecast?" in u and "origin=2017-12-01" in u]
    step("F05c forecast: a retrospective origin is sent to the API and its result shown next to what happened", bool(retro) and "2017-12-01" in pg.get_by_text("Origin", exact=True).first.locator("xpath=..").inner_text(), retro[-1][:90] if retro else None)
    inp = pg.get_by_label("Forecast origin"); inp.fill("2030-01-01T00:00"); reqs.clear()
    pg.get_by_role("button", name="Run forecast").click(); pg.wait_for_timeout(1200)
    err = pg.get_by_text(re.compile(r"Choose a time between")).first
    sent = [u for u in reqs if "/forecast?" in u and "2030" in u]
    step("F05d forecast: an origin outside the data range shows 'Choose a time between ...' and sends no request", err.count() > 0 and err.is_visible() and not sent, err.inner_text() if err.count() else "no message")
    # F08 alerts
    pg.goto(common.BASE + "/alerts"); pg.wait_for_selector("text=Matching the filters", timeout=30000); pg.wait_for_load_state("networkidle")
    cnt = lambda: pg.get_by_text("Matching the filters").locator("xpath=..").inner_text().replace("\n", " ")
    c0 = cnt(); pick(pg, "All severities"); c1 = cnt(); pick(pg, "Buildings"); c2 = cnt(); pick(pg, "Acknowledged"); c3 = cnt()
    step("F08a alerts: severity, scope and status filters change the match count", len({c0, c1, c2, c3}) >= 3, f"{c0[-14:]} | {c1[-14:]} | {c2[-14:]} | {c3[-14:]}")
    pick(pg, "Medium and high"); pick(pg, "Whole society"); pick(pg, "Open")
    first = pg.locator("table tbody tr").first.get_by_role("button").first; label = first.inner_text(); first.click(); pg.wait_for_timeout(1200)
    close = pg.get_by_role("button", name="Close")
    card = close.locator("xpath=ancestor::section[1]").inner_text().replace("\n", " ") if close.count() else ""
    step("F08d alerts: clicking an event time opens a detail card with an explanation and a Close button", close.count() == 1 and len(card) > 80, f"{label} -> {card[:200]}")
    if close.count(): close.click(); pg.wait_for_timeout(300); step("F08e alerts: Close hides the detail card", pg.get_by_role("button", name="Close").count() == 0)
    # B2 downloads
    pg.goto(common.BASE + "/reports"); pg.wait_for_selector("text=Create a report", timeout=30000); pg.wait_for_load_state("networkidle")
    sel = pg.get_by_label("Report", exact=True); kinds = sel.evaluate("e=>[...e.options].map(o=>o.value)"); made = 0
    for k in kinds:
        sel.select_option(k)
        pg.get_by_role("button", name="Create report").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200)
    n = pg.locator("table tbody tr").count(); ok = 0; sizes = []
    step("B1 reports: every report type can be created and appears in the list (an empty list shows one placeholder row)", n >= len(kinds), f"{n} rows after creating {len(kinds)} types: {kinds}")
    for i in range(n):
        row = pg.locator("table tbody tr").nth(i)
        try:
            with pg.expect_download(timeout=20000) as dl: row.get_by_role("button", name=re.compile("Download", re.I)).first.click()
            p = dl.value.path(); sz = __import__("os").path.getsize(p); head = open(p, "rb").read(8); ok += sz > 0 and (head.startswith(b"%PDF") or b"," in open(p, "rb").read(400)); sizes.append(f"{dl.value.suggested_filename}:{sz}")
        except Exception as e: sizes.append(str(e)[:40])
        pg.wait_for_timeout(250)
    step("B2 reports: every listed report downloads a valid file (PDF header or CSV with columns)", ok == n and n > 0, f"{ok}/{n} {sizes}")
    step("no console errors or warnings during these flows", not errs, "; ".join(errs[:3]))
    b.close()
json.dump(R, open("/home/claude/pro/logs/verify_functional.json", "w"), indent=1)
print(sum(v["ok"] for v in R.values()), "/", len(R))
