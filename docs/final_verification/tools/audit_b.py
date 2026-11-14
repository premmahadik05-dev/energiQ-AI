"""Behaviour audit B: reports (create + download + validate files), auth flows, admin pages, role guards."""
import json, re, csv, io, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from common import BASE, API, token, new_ctx, _req
res=[]
def rec(i,name,ok,note=""):
    res.append((i,name,"PASS" if ok else "FAIL",note)); print(f"{'PASS' if ok else 'FAIL'} {i} {name} | {note}",flush=True)
DL=Path("/home/claude/pro/run/downloads"); DL.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=new_ctx(b); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e: errs.append(str(e)[:200])); pg.on("console",lambda m: errs.append(m.text[:200]) if m.type=="error" else None)
    # ---------- Reports
    pg.goto(BASE+"/reports",wait_until="networkidle")
    kinds=pg.get_by_label("Report",exact=True).evaluate("e=>[...e.options].map(o=>[o.value,o.text])")
    print("report kinds:",kinds)
    for val,text in kinds:
        try:
            pg.get_by_label("Report",exact=True).select_option(val)
            pg.get_by_role("button",name="Create report").click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
            rows=pg.locator("table tbody tr").count()
            rec("B1",f"report '{text}' created and listed",rows>=1,f"rows in list={rows}")
        except Exception as e: rec("B1",f"report '{text}' created",False,str(e).splitlines()[0][:150])
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(800)
    n=pg.locator("table tbody tr").count(); rec("B1b","reports persist after reload",n>=len(kinds),f"{n} rows")
    for i in range(n):
        row=pg.locator("table tbody tr").nth(i); label=row.inner_text().replace("\n"," | ")[:90]
        btn=row.get_by_role("button",name=re.compile("Download",re.I)).first
        if btn.count()==0: btn=row.locator("a,button").last
        try:
            with pg.expect_download(timeout=20000) as dl: btn.click()
            d=dl.value; path=DL/d.suggested_filename; d.save_as(path); data=path.read_bytes()
            kind="PDF" if data[:4]==b"%PDF" else "CSV" if path.suffix==".csv" else path.suffix
            ok=len(data)>500
            note=f"{d.suggested_filename} {len(data):,} bytes"
            if data[:4]==b"%PDF":
                ok=ok and data.rstrip().endswith(b"%%EOF"); note+=f" pdf-eof={data.rstrip().endswith(b'%%EOF')}"
            elif path.suffix==".csv":
                rows_=list(csv.reader(io.StringIO(data.decode("utf-8-sig")))); ok=ok and len(rows_)>2 and len(set(len(r) for r in rows_[1:50]))==1
                note+=f" csv rows={len(rows_)} cols={len(rows_[0])} header={rows_[0][:4]}"
            rec("B2",f"download valid: {label}",ok,note)
        except Exception as e: rec("B2",f"download: {label}",False,str(e).splitlines()[0][:150])
    # ---------- Auth
    c2=b.new_context(viewport={"width":1440,"height":900}); a=c2.new_page(); a.goto(BASE+"/",wait_until="networkidle")
    rec("B3a","unauthenticated visit redirects to sign-in","/login" in a.url,a.url)
    a.get_by_label("Email address").fill("admin@example.com"); a.get_by_label("Password",exact=True).fill("wrong-password-1"); a.get_by_role("button",name="Sign in").click(); a.wait_for_timeout(1200)
    msg=a.locator("[role=alert]").all_inner_texts(); rec("B3b","wrong password shows a clear error",any("Invalid" in m or "incorrect" in m.lower() for m in msg),str(msg)[:120])
    a.get_by_label("Email address").fill(""); a.get_by_role("button",name="Sign in").click(); a.wait_for_timeout(500)
    rec("B3c","empty form is validated client-side",a.get_by_text(re.compile("required|enter",re.I)).count()>0,a.locator("form").inner_text()[:100].replace("\n"," "))
    a.goto(BASE+"/register",wait_until="networkidle"); email=f"qa.{abs(hash(str(res)))%10**6}@example.com"
    a.get_by_label("Full name (optional)").fill("QA Analyst"); a.get_by_label("Email address").fill(email)
    a.get_by_label("Password",exact=True).fill("short"); a.get_by_label("Confirm password",exact=True).fill("short"); a.get_by_role("button",name=re.compile("Create account|Register",re.I)).click(); a.wait_for_timeout(600)
    rec("B3d","weak password rejected on register",a.get_by_text(re.compile("10|character|letters",re.I)).count()>0 and "/register" in a.url,a.url)
    a.get_by_label("Password",exact=True).fill("Analyst-Pass-2026"); a.get_by_label("Confirm password",exact=True).fill("Analyst-Pass-2026"); a.get_by_role("button",name=re.compile("Create account|Register",re.I)).click(); a.wait_for_load_state("networkidle"); a.wait_for_timeout(1500)
    rec("B3e","valid registration signs in and opens the overview","/register" not in a.url and "/login" not in a.url,a.url)
    a.goto(BASE+"/admin",wait_until="networkidle"); rec("B3f","analyst cannot open /admin (role guard)","Administration" not in a.locator("main").inner_text(),a.locator("main").inner_text()[:80].replace("\n"," "))
    a.goto(BASE+"/society-admin",wait_until="networkidle"); rec("B3g","analyst cannot open /society-admin","Society administration" not in a.locator("main").inner_text(),a.locator("main").inner_text()[:80].replace("\n"," "))
    nav=a.locator("nav").inner_text(); rec("B3h","analyst nav hides admin items","Admin" not in nav.split("System")[-1] and "Society admin" not in nav,nav.replace("\n"," | ")[-90:])
    try:
        a.get_by_role("button",name=re.compile("Account menu")).click(); a.get_by_role("button",name="Sign out").click(); a.wait_for_load_state("networkidle"); a.wait_for_timeout(800)
        rec("B3i","sign out returns to /login and clears the session","/login" in a.url and a.evaluate("sessionStorage.getItem('energiq.token')") is None,a.url)
    except Exception as e: rec("B3i","sign out",False,str(e).splitlines()[0][:150])
    # ---------- Admin pages
    pg.goto(BASE+"/admin",wait_until="networkidle")
    for tab in ("Users","Audit log","System"):
        pg.get_by_role("tab",name=tab).click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500)
        txt=pg.locator("main").inner_text().replace("\n"," | ")
        rec("B4",f"admin tab '{tab}' loads data",len(txt)>150 and "error" not in txt.lower()[:200],txt[60:170])
    pg.get_by_role("tab",name="Users").click(); pg.wait_for_timeout(400)
    sel=pg.locator("select").filter(has=pg.locator("option[value=analyst]")); cnt=sel.count()
    rec("B4b","admin can see other users with role selectors",cnt>=1,f"{cnt} role selectors (own account should be protected)")
    pg.goto(BASE+"/jobs",wait_until="networkidle"); jt=pg.locator("table").inner_text().replace("\n"," | ")[:200]; rec("B5","jobs page lists the import job",("society_import" in jt or "import" in jt.lower()),jt[:140])
    print("console/page errors:",len(errs),errs[:4]); b.close()
Path("/home/claude/pro/logs/audit_b.json").write_text(json.dumps(res,indent=1))
print("SUMMARY",sum(r[2]=="PASS" for r in res),"pass",sum(r[2]=="FAIL" for r in res),"fail")
