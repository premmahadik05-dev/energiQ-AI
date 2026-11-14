"""For every chart on every page that has charts: move the mouse across the plot area and check that a tooltip with text appears,
and that each chart frame has a title (nearest heading or aria-label) and some axis text. Desktop width, signed in."""
import sys
sys.path.insert(0, "/home/claude/pro/tools"); import common
from playwright.sync_api import sync_playwright
ROUTES = ["/", "/consumption", "/forecasting", "/compare", "/buildings", "/cost", "/alerts"]
bad = 0; total = 0
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = common.new_ctx(b); pg = ctx.new_page(); errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    for r in ROUTES:
        pg.goto(common.BASE + r, wait_until="networkidle"); pg.wait_for_timeout(1500)
        if r == "/cost":
            pass
        n = pg.locator(".recharts-wrapper").count()
        for i in range(n):
            w = pg.locator(".recharts-wrapper").nth(i); w.scroll_into_view_if_needed(); bb = w.bounding_box()
            if not bb: continue
            total += 1; got = ""
            for fx in (0.35, 0.5, 0.65, 0.8):
                pg.mouse.move(bb["x"] + bb["width"] * fx, bb["y"] + bb["height"] * 0.5); pg.wait_for_timeout(250)
                t = w.locator(".recharts-tooltip-wrapper").inner_text() if w.locator(".recharts-tooltip-wrapper").count() else ""
                if t.strip(): got = t.strip().replace("\n", " ")[:70]; break
            axis = w.locator(".recharts-cartesian-axis-tick-value").count()
            label = w.locator(".recharts-label").count()
            title = w.evaluate("""e => { let n = e.parentElement; for (let k = 0; k < 8 && n; k++, n = n.parentElement) { const a = n.getAttribute('aria-label') || ''; if (a) return a.slice(0, 60); const h = [...n.querySelectorAll('h2, h3, h4, .font-semibold')].find(x => !x.closest('.recharts-wrapper') && x.innerText.trim()); if (h) return h.innerText.trim().slice(0, 60); } return ''; }""")
            ok = bool(got) and axis > 0 and bool(title); bad += (not ok)
            print(("PASS " if ok else "CHECK"), r, f"chart#{i}", "| title:", title or "-", "| tooltip:", got or "-", "| tick labels:", axis, "| axis titles:", label)
    b.close()
print(f"{total - bad} of {total} charts: title, tick labels and a hover tooltip found; console messages: {len(errs)}", errs[:3])
