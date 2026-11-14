"""Final crawl (after react-router 7): log in through the UI, visit every route at three viewports, record console/page/network errors,
horizontal overflow, broken images, chart counts; save full-page screenshots. Read-only (no destructive clicks)."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173"
OUT = Path("/home/claude/pro/shots/final")
ROUTES = ["/", "/consumption", "/forecasting", "/compare", "/buildings", "/facilities", "/cost", "/alerts", "/recommendations",
          "/reports", "/data-sources", "/notifications", "/jobs", "/society-admin", "/admin", "/does-not-exist"]
VIEWPORTS = {"desktop": (1440, 900), "tablet": (820, 1180), "mobile": (390, 844)}
only = sys.argv[1:] or list(VIEWPORTS)

results = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for vp in only:
        w, h = VIEWPORTS[vp]
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        page = ctx.new_page()
        cur = {"console": [], "pageerror": [], "http": [], "failed": []}
        page.on("console", lambda m, c=cur: c["console"].append(f"{m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e, c=cur: c["pageerror"].append(str(e)[:300]))
        page.on("response", lambda r, c=cur: c["http"].append(f"{r.status} {r.request.method} {r.url.replace(BASE, '')[:140]}") if r.status >= 400 else None)
        page.on("requestfailed", lambda r, c=cur: c["failed"].append(f"{r.method} {r.url.replace(BASE, '')[:140]} {r.failure}"))
        page.goto(BASE + "/login", wait_until="networkidle")
        page.screenshot(path=str(OUT / f"{vp}__login.png"))
        page.get_by_label("Email address").fill("admin@example.com")
        page.get_by_label("Password", exact=True).fill("AdminPass-12345")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        page.wait_for_load_state("networkidle")
        for r in ROUTES:
            for k in cur: cur[k].clear()
            page.goto(BASE + r, wait_until="networkidle")
            page.wait_for_timeout(1200)
            info = page.evaluate("""() => ({
              title: document.title,
              h1: [...document.querySelectorAll('h1')].map(e => e.innerText.trim()).slice(0, 2),
              overflowX: document.documentElement.scrollWidth - window.innerWidth,
              buttons: document.querySelectorAll('button').length,
              links: document.querySelectorAll('a[href]').length,
              inputs: document.querySelectorAll('input,select,textarea').length,
              charts: document.querySelectorAll('.recharts-wrapper').length,
              tables: document.querySelectorAll('table').length,
              brokenImgs: [...document.images].filter(i => i.complete && i.naturalWidth === 0).length,
              images: document.images.length,
              emptyStates: [...document.querySelectorAll('[role=status],[role=alert]')].map(e => e.innerText.trim().slice(0, 90)).slice(0, 4),
              bodyText: document.body.innerText.length })""")
            name = r.strip("/").replace("/", "_") or "overview"
            page.screenshot(path=str(OUT / f"{vp}__{name}.png"), full_page=True)
            results.append({"viewport": vp, "route": r, **info, **{k: list(v) for k, v in cur.items()}})
        ctx.close()
    b.close()
Path("/home/claude/pro/logs/crawl_final.json").write_text(json.dumps(results, indent=1))
for x in results:
    flags = []
    if x["overflowX"] > 0: flags.append(f"overflowX+{x['overflowX']}")
    if x["brokenImgs"]: flags.append(f"brokenImgs={x['brokenImgs']}")
    if x["console"]: flags.append(f"console={len(x['console'])}")
    if x["pageerror"]: flags.append(f"pageerror={len(x['pageerror'])}")
    if x["http"]: flags.append(f"http={len(x['http'])}")
    if x["failed"]: flags.append(f"reqfailed={len(x['failed'])}")
    print(f"{x['viewport']:8} {x['route']:18} charts={x['charts']} tables={x['tables']} btn={x['buttons']} h1={x['h1'][:1]} {' '.join(flags)}")
