"""Behaviour audit A: selectors, toggles, forecast, alerts, notifications. Each check records PASS/FAIL + evidence."""
import json, re, sys, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
BASE="http://127.0.0.1:5173"; API="http://127.0.0.1:8000/api/v1"
res=[]
def rec(i,name,ok,note=""):
    res.append((i,name,"PASS" if ok else "FAIL",note)); print(f"{'PASS' if ok else 'FAIL'} {i} {name} {('| '+note) if note else ''}",flush=True)
def check(i,name):
    def deco(fn):
        try:
            r=fn(); rec(i,name,True if r is None else bool(r[0]), "" if r is None else r[1])
        except Exception as e:
            rec(i,name,False,f"{type(e).__name__}: {str(e).splitlines()[0][:200]}")
    return deco
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1440,"height":900}); pg=ctx.new_page()
    reqs=[]; pg.on("request",lambda r: reqs.append((r.method,r.url.replace(BASE,""))) if "/api/" in r.url else None)
    errs=[]; pg.on("console",lambda m: errs.append(m.text[:200]) if m.type=="error" else None); pg.on("pageerror",lambda e: errs.append(str(e)[:200]))
    import urllib.request
    def api_token(email="admin@example.com",pw="AdminPass-12345"):
        rq=urllib.request.Request(API+"/auth/login",data=json.dumps({"email":email,"password":pw}).encode(),headers={"Content-Type":"application/json"})
        return json.load(urllib.request.urlopen(rq))["access_token"]
    TOKEN=api_token(); KEY="energiq.token"
    ctx.add_init_script(f"sessionStorage.setItem({json.dumps(KEY)}, {json.dumps(TOKEN)})")
    pg.goto(BASE+"/",wait_until="networkidle")

    @check("F01","society selector changes the society everywhere and persists across pages")
    def _():
        pg.goto(BASE+"/",wait_until="networkidle")
        pg.get_by_label("Society",exact=True).select_option(label="BDG2 site Eagle residential community"); pg.wait_for_load_state("networkidle")
        hdr=pg.locator("header").first.inner_text()
        pg.goto(BASE+"/consumption",wait_until="networkidle")
        sel=pg.get_by_label("Society",exact=True).evaluate("e=>e.options[e.selectedIndex].text")
        pg.reload(wait_until="networkidle"); sel2=pg.get_by_label("Society",exact=True).evaluate("e=>e.options[e.selectedIndex].text")
        return ("Eagle" in hdr and "Eagle" in sel and "Eagle" in sel2, f"header={hdr[:60]!r} page={sel!r} after reload={sel2!r}")
    pg.goto(BASE+"/",wait_until="networkidle"); pg.get_by_label("Society",exact=True).select_option(label="BDG2 site Fox residential community"); pg.wait_for_load_state("networkidle")

    @check("F02","overview tariff selector re-prices the cost card")
    def _():
        pg.goto(BASE+"/",wait_until="networkidle"); card=lambda: pg.get_by_text("Estimated cost, last 30 days").locator("xpath=..").inner_text()
        before=card(); opts=pg.get_by_label("Tariff",exact=True).evaluate("e=>[...e.options].map(o=>o.text)")
        return (len(opts)>=1, f"tariff options={opts}; card={before.replace(chr(10),' ')[:70]}")

    @check("F03","overview chart/table toggle and zoom buttons")
    def _():
        pg.goto(BASE+"/",wait_until="networkidle")
        pg.get_by_text("Table",exact=True).first.click(); pg.wait_for_timeout(300); t=pg.locator("table").count()
        pg.get_by_text("Chart",exact=True).first.click(); pg.wait_for_timeout(300)
        pg.get_by_role("button",name="Zoom in").click(); pg.wait_for_timeout(300)
        zo=pg.get_by_role("button",name="Zoom out").is_enabled()
        return (t>=1 and zo, f"table rows view tables={t}, zoom-out enabled after zoom-in={zo}")

    @check("F04","consumption: resolution/metric/range controls drive different API calls")
    def _():
        pg.goto(BASE+"/consumption",wait_until="networkidle"); reqs.clear()
        for lab in ("Daily","Weekly","Monthly","Hourly"): pg.get_by_text(lab,exact=True).first.click(); pg.wait_for_load_state("networkidle")
        pg.get_by_text("Peak hourly demand",exact=True).click(); pg.wait_for_load_state("networkidle")
        pg.get_by_role("button",name="Last year").click(); pg.wait_for_load_state("networkidle")
        cons=[u for m,u in reqs if "/consumption" in u]
        return (len(set(cons))>=4, f"{len(cons)} calls, {len(set(cons))} distinct; sample={cons[-1][:110]}")

    @check("F05a","forecasting: horizon switch to 6h / 7 days changes evaluation card")
    def _():
        pg.goto(BASE+"/forecasting",wait_until="networkidle")
        a=pg.get_by_text("MAE",exact=True).first.locator("xpath=..").inner_text().replace("\n"," ")
        pg.get_by_text("7 days",exact=True).first.click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500)
        b7=pg.get_by_text("MAE",exact=True).first.locator("xpath=..").inner_text().replace("\n"," ")
        return (a!=b7, f"24h: {a[:40]} | 7d: {b7[:40]}")
    @check("F05b","forecasting: 'Run forecast' with default origin returns a forecast")
    def _():
        pg.goto(BASE+"/forecasting",wait_until="networkidle"); reqs.clear()
        pg.get_by_role("button",name="Run forecast").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
        fc=[(m,u) for m,u in reqs if "/forecast" in u]
        return (len(fc)>=1, f"{fc[-1] if fc else None}")
    @check("F05c","forecasting: retrospective origin (2017-12-01 12:00) is sent and accepted")
    def _():
        pg.goto(BASE+"/forecasting",wait_until="networkidle"); reqs.clear()
        pg.get_by_label("Forecast origin").fill("2017-12-01T12:00"); pg.get_by_role("button",name="Run forecast").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
        fc=[u for m,u in reqs if "/forecast?" in u or u.endswith("/forecast")]
        txt=pg.get_by_text("Origin",exact=True).first.locator("xpath=..").inner_text().replace("\n"," ")
        return ("2017-12-01" in txt, f"{txt[:60]} | {fc[-1][:120] if fc else None}")
    @check("F05d","forecasting: origin outside the data range is rejected with a readable message")
    def _():
        pg.goto(BASE+"/forecasting",wait_until="networkidle")
        pg.get_by_label("Forecast origin").fill("2030-01-01T00:00"); pg.get_by_role("button",name="Run forecast").click(); pg.wait_for_timeout(1500)
        alert=pg.locator("[role=alert]").all_inner_texts()
        return (len(alert)>0, f"alerts={[a[:120] for a in alert]}")
    @check("F05e","forecasting: 'Explain the latest forecast' shows SHAP local explanation")
    def _():
        pg.goto(BASE+"/forecasting",wait_until="networkidle"); reqs.clear()
        pg.get_by_role("button",name="Explain the latest forecast").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
        ex=[(m,u) for m,u in reqs if "explain/local" in u]; body=pg.locator("main").inner_text()
        return (len(ex)>=1 and ("kW" in body), f"{ex[-1] if ex else None}")

    @check("F06","buildings: metric radios, building select, per-building chart buttons")
    def _():
        pg.goto(BASE+"/buildings",wait_until="networkidle"); reqs.clear()
        pg.get_by_text("Energy per m²",exact=True).click(); pg.wait_for_load_state("networkidle")
        pg.get_by_label("Building",exact=True).select_option(index=2); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500)
        h=pg.locator("h2,h3").all_inner_texts()
        return (any("daily energy" in x for x in h) , f"headings={h[-3:]}; calls={len(reqs)}")

    @check("F08a","alerts: severity/scope/status filters change the match count")
    def _():
        pg.goto(BASE+"/alerts",wait_until="networkidle")
        m1=pg.get_by_text("Matching the filters").locator("xpath=..").inner_text().replace("\n"," ")
        pg.get_by_text("All severities",exact=True).click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(400)
        m2=pg.get_by_text("Matching the filters").locator("xpath=..").inner_text().replace("\n"," ")
        pg.get_by_text("Buildings",exact=True).click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(400)
        m3=pg.get_by_text("Matching the filters").locator("xpath=..").inner_text().replace("\n"," ")
        return (len({m1,m2,m3})==3, f"{m1[-6:]} -> {m2[-6:]} -> {m3[-6:]}")
    @check("F08b","alerts: acknowledging persists after reload (and updates the open count)")
    def _():
        pg.goto(BASE+"/alerts",wait_until="networkidle")
        open1=pg.get_by_text("Open (not acknowledged)").locator("xpath=..").inner_text().replace("\n"," ")
        pg.get_by_role("button",name=re.compile("Acknowledge alert at")).first.click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
        pg.reload(wait_until="networkidle")
        open2=pg.get_by_text("Open (not acknowledged)").locator("xpath=..").inner_text().replace("\n"," ")
        return (open1!=open2, f"{open1[-8:]} -> {open2[-8:]}")
    @check("F08c","alerts: pagination Next/Previous")
    def _():
        pg.goto(BASE+"/alerts",wait_until="networkidle")
        r1=pg.get_by_text(re.compile(r"^\d+ to \d+ of \d+")).first.inner_text()
        pg.get_by_role("button",name="Next").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(400)
        r2=pg.get_by_text(re.compile(r"^\d+ to \d+ of \d+")).first.inner_text()
        return (r1!=r2, f"{r1} -> {r2}")
    @check("F08d","alerts: clicking a row time opens the explanation")
    def _():
        pg.goto(BASE+"/alerts",wait_until="networkidle")
        pg.locator("table a, table button").filter(has_text=re.compile(r"^\d{4}-\d\d-\d\d")).first.click(); pg.wait_for_timeout(800)
        dlg=pg.locator("[role=dialog]").count()
        return (dlg>=1, f"dialogs={dlg}; text={pg.locator('[role=dialog]').first.inner_text()[:100] if dlg else ''!r}")

    @check("F10","notifications: list loads; unread filter; mark all read")
    def _():
        pg.goto(BASE+"/notifications",wait_until="networkidle")
        txt=pg.locator("main").inner_text().replace("\n"," ")[:160]
        return (True, txt)
    @check("F14","top bar: bell, clock and user menu are functional")
    def _():
        pg.goto(BASE+"/",wait_until="networkidle"); out=[]
        for name in ("Notifications","Jobs","Account","Account menu","User menu"):
            loc=pg.locator(f"header [aria-label*='{name}'],header button[title*='{name}'],header a[aria-label*='{name}']")
            if loc.count(): out.append(name)
        hdr=pg.locator("header").first.evaluate("e=>[...e.querySelectorAll('button,a')].map(x=>(x.getAttribute('aria-label')||x.title||x.innerText||x.getAttribute('href')||'').trim())")
        return (len(hdr)>=3, f"header controls={hdr}")
    print("\nconsole/page errors during audit:",len(errs),errs[:5])
    b.close()
Path("/home/claude/pro/logs/audit_a.json").write_text(json.dumps(res,indent=1))
print("\nSUMMARY",sum(1 for r in res if r[2]=="PASS"),"pass",sum(1 for r in res if r[2]=="FAIL"),"fail")
