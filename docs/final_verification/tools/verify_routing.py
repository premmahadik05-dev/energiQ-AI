"""Routing behaviour after the react-router 7 upgrade: guard redirect, return-to-page after sign-in, back/forward, deep links, 404, sign-out."""
import json
from playwright.sync_api import sync_playwright
BASE="http://127.0.0.1:5173"; R={}
def step(n,ok,d=""):
    R[n]={"ok":bool(ok),"detail":d}; print(("PASS " if ok else "FAIL ")+n,d)
with sync_playwright() as pw:
    b=pw.chromium.launch(); ctx=b.new_context(viewport={"width":1440,"height":900}); pg=ctx.new_page()
    errs=[]
    pg.on("console",lambda m: errs.append(m.text) if m.type in("error","warning") else None)
    pg.on("pageerror",lambda e: errs.append("PAGEERROR "+str(e)))
    pg.goto(BASE+"/cost"); pg.wait_for_url("**/login*",timeout=15000)
    step("signed-out visit to /cost redirects to /login", "/login" in pg.url, pg.url)
    pg.get_by_label("Email address").fill("admin@example.com"); pg.get_by_label("Password",exact=True).fill("AdminPass-12345")
    pg.get_by_role("button",name="Sign in").click(); pg.wait_for_url(lambda u:"/login" not in u,timeout=15000)
    step("after sign-in the original page (/cost) is reopened", pg.url.rstrip("/").endswith("/cost"), pg.url)
    pg.wait_for_selector("h1",timeout=15000)
    step("page title follows the route", pg.title()=="Cost and peaks · EnergiQ AI", pg.title())
    nav=pg.get_by_role("navigation")
    pg.get_by_role("link",name="Compare communities").first.click(); pg.wait_for_url("**/compare"); pg.wait_for_selector("h1:has-text('Compare communities')")
    pg.get_by_role("link",name="Forecasting").first.click(); pg.wait_for_url("**/forecasting"); pg.wait_for_selector("h1:has-text('Forecasting')")
    pg.go_back(); pg.wait_for_url("**/compare")
    step("browser Back returns to /compare", pg.locator("h1").first.inner_text()=="Compare communities")
    pg.go_forward(); pg.wait_for_url("**/forecasting")
    step("browser Forward returns to /forecasting", pg.locator("h1").first.inner_text()=="Forecasting")
    pg.reload(); pg.wait_for_selector("h1:has-text('Forecasting')",timeout=20000)
    step("reload keeps the session and the page", "/forecasting" in pg.url)
    pg.goto(BASE+"/no/such/page"); pg.wait_for_selector("h1:has-text('Page not found')",timeout=15000)
    step("unknown URL shows the 404 page inside the app", True, pg.title())
    pg.get_by_role("link",name="Society overview").first.click(); pg.wait_for_selector("h1:has-text('Society overview')")
    step("404 page links back to the app", True)
    pg.get_by_role("button",name="Account menu for admin@example.com").click(); pg.get_by_role("button",name="Sign out").click(); pg.wait_for_url("**/login*",timeout=15000)
    step("sign-out lands on /login", "/login" in pg.url)
    pg.goto(BASE+"/alerts"); pg.wait_for_url("**/login*",timeout=15000)
    step("after sign-out protected pages are closed again", "/login" in pg.url)
    unexpected=[e for e in errs if "401" not in e]
    step("no unexpected console errors (401 from the signed-out probe excluded)", not unexpected, "; ".join(unexpected[:3]))
    b.close()
json.dump(R,open("logs/verify_routing.json","w"),indent=1); print(sum(v["ok"] for v in R.values()),"/",len(R))
