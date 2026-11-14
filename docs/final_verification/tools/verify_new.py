import sys, json
sys.path.insert(0,"/home/claude/pro/tools")
import common
from playwright.sync_api import sync_playwright
OUT="/home/claude/pro/shots/new/"
res={}
with sync_playwright() as pw:
    b=pw.chromium.launch()
    ctx=common.new_ctx(b)
    pg=ctx.new_page()
    errs=[]
    pg.on("console",lambda m: errs.append(m.text) if m.type in("error","warning") else None)
    pg.on("pageerror",lambda e: errs.append("PAGEERROR "+str(e)))
    # compare
    pg.goto(common.BASE+"/compare"); pg.wait_for_selector("text=All figures",timeout=20000); pg.wait_for_timeout(800)
    pg.screenshot(path=OUT+"compare.png",full_page=True)
    res["compare_rows"]=pg.locator("table tbody tr").count()
    # forecasting error analysis
    pg.goto(common.BASE+"/forecasting"); pg.wait_for_selector("text=Forecast error analysis",timeout=30000); pg.wait_for_timeout(1500)
    pg.get_by_text("Forecast error analysis").first.scroll_into_view_if_needed()
    pg.screenshot(path=OUT+"forecast_full.png",full_page=True)
    res["ea_kpi"]=pg.locator("text=Average error (bias)").count()
    # cost + tariff
    pg.goto(common.BASE+"/cost"); pg.wait_for_selector("text=Add a tariff",timeout=30000); pg.wait_for_timeout(1000)
    pg.screenshot(path=OUT+"cost_full.png",full_page=True)
    # peaks
    pg.get_by_role("tab",name="Peak demand").click(); pg.wait_for_selector("text=Load duration curve",timeout=30000); pg.wait_for_timeout(1500)
    pg.screenshot(path=OUT+"peaks_full.png",full_page=True)
    res["errors"]=errs[:10]
    b.close()
print(json.dumps(res,indent=1))
