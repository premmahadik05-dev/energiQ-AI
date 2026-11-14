"""The model-comparison footnote must describe what was deployed and how it did, for the three situations that occur (Fox, Eagle, Peacock)."""
import sys, json
sys.path.insert(0, "/home/claude/pro/tools"); import common
from playwright.sync_api import sync_playwright
ids = {s["key"]: s["id"] for s in json.load(common._req("/societies", token=common.token()))}
cases = [("fox", "24 h", "selected model (Random forest)"), ("eagle", "24 h", "is the selected model at this horizon"), ("peacock", "24 h", "did not beat the best simple baseline")]
ok_all = True
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for key, hz, expect in cases:
        ctx = common.new_ctx(b); ctx.add_init_script(f"sessionStorage.setItem('energiq.activeSociety','{ids[key]}')")
        pg = ctx.new_page(); errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
        pg.goto(common.BASE + "/forecasting"); pg.wait_for_selector("text=Model comparison", timeout=30000); pg.wait_for_timeout(1500)
        card = pg.get_by_role("region", name="Model comparison, 24 hours ahead") if pg.get_by_role("region", name="Model comparison, 24 hours ahead").count() else pg.locator("section:has-text('Model comparison')").first
        txt = card.inner_text()
        ok = expect in txt and not errs
        ok_all &= ok
        foot = [l for l in txt.split("\n") if "cross-validation" in l and ("baseline" in l)]
        print(("PASS " if ok else "FAIL ") + key, "|", (foot[-1] if foot else txt[-300:])[:330].replace("\n", " "), errs[:2])
        card.screenshot(path=f"/home/claude/pro/shots/final/model_choice_{key}.png")
        ctx.close()
    b.close()
sys.exit(0 if ok_all else 1)
