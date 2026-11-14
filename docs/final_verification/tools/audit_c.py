"""Audit C: upload a society through the UI -> process -> train -> forecast -> facilities/buildings -> delete."""
import json, re, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from common import BASE, API, token, new_ctx, _req
S=Path("/home/claude/pro/shots/audit"); res=[]
def rec(i,name,ok,note=""): res.append((i,name,"PASS" if ok else "FAIL",note)); print(f"{'PASS' if ok else 'FAIL'} {i} {name} | {note}",flush=True)
NAME="QA Test Society (synthetic)"
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=new_ctx(b); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e: errs.append(str(e)[:200])); pg.on("console",lambda m: errs.append(m.text[:200]) if m.type=="error" else None)
    pg.goto(BASE+"/society-admin",wait_until="networkidle")
    # validation first: wrong file type
    pg.get_by_label("Society name").fill(NAME); pg.get_by_label("Meter readings CSV").set_input_files({"name":"bad.csv","mimeType":"text/csv","buffer":b"not,a,real\nfile"})
    pg.get_by_role("button",name="Upload and process").click(); pg.wait_for_timeout(2500)
    msgs=pg.locator("[role=alert],[role=status]").all_inner_texts(); rec("C1","a malformed file is refused with a readable reason",any(len(m)>10 for m in msgs),str([m[:150] for m in msgs]))
    # real upload
    pg.get_by_label("Meter readings CSV").set_input_files("/home/claude/pro/run/upload_test/readings.csv")
    pg.get_by_label("Meter mapping CSV (optional)").set_input_files("/home/claude/pro/run/upload_test/mapping.csv")
    pg.get_by_label("Description (optional)").fill("Synthetic test data for QA only")
    pg.get_by_role("button",name="Upload and process").click()
    t0=time.time(); sid=None
    while time.time()-t0<240:
        socs=json.load(_req("/societies",token=token())); m=[s for s in socs if s["name"]==NAME]
        if m and m[0]["status"] in ("ready","evaluated","untrained") : sid=m[0]["id"]; break
        if m and m[0]["status"]=="failed": break
        time.sleep(3)
    soc=[s for s in json.load(_req("/societies",token=token())) if s["name"]==NAME]
    rec("C2","upload + processing job completes and the society is listed",bool(soc),f"{soc[0]['status'] if soc else None} after {time.time()-t0:.0f}s; hours={soc[0]['hours'] if soc else None} valid={soc[0]['valid_hours'] if soc else None} buildings={soc[0]['buildings'] if soc else None}")
    pg.screenshot(path=str(S/"c_after_upload.png"),full_page=True)
    if soc:
        sid=soc[0]["id"]
        d=json.load(_req(f"/societies/{sid}",token=token())); print("   data_card keys:",list(d.get("data_card",{}).keys())[:8])
        fac=json.load(_req(f"/societies/{sid}/facilities",token=token())); print("   facilities:",json.dumps(fac)[:200])
        # train
        pg.goto(BASE+"/society-admin",wait_until="networkidle")
        pg.get_by_role("button",name=re.compile(f"Train models for {re.escape(NAME)}")).click(); t1=time.time(); done=False
        while time.time()-t1<900:
            jobs=json.load(_req("/jobs?limit=5",token=token())); j=[x for x in jobs if x["kind"]=="society_train"]
            if j and j[0]["status"] in ("succeeded","failed"): done=True; break
            time.sleep(10)
        j=j[0] if j else {}
        rec("C3","training job runs to completion",j.get("status")=="succeeded",f"{j.get('status')} in {time.time()-t1:.0f}s; msg={str(j.get('message'))[:80]}; err={str(j.get('error'))[:200]}")
        soc2=json.load(_req(f"/societies/{sid}",token=token()))
        rec("C4","after training the society is forecast-ready with evaluation",bool(soc2.get("forecast_ready")) and bool(soc2.get("has_model")),f"has_model={soc2.get('has_model')} forecast_ready={soc2.get('forecast_ready')}")
        # UI
        ctx2=new_ctx(b); q=ctx2.new_page(); q.on("pageerror",lambda e: errs.append(str(e)[:200]))
        q.goto(BASE+"/forecasting",wait_until="networkidle"); q.get_by_label("Society",exact=True).select_option(label=NAME); q.wait_for_load_state("networkidle"); q.wait_for_timeout(2500)
        txt=q.locator("main").inner_text(); rec("C5","forecasting page shows evaluation and a live forecast for the uploaded society","MAE" in txt and "Next 24 h" in txt or "Predicted" in txt,txt[:140].replace("\n"," | "))
        q.screenshot(path=str(S/"c_forecast_uploaded.png"),full_page=True)
        q.goto(BASE+"/facilities",wait_until="networkidle"); q.wait_for_timeout(1500); ft=q.locator("main").inner_text()
        rec("C6","facilities page charts the mapped lift/pump/street-light meters",q.locator(".recharts-wrapper").count()>=1,f"charts={q.locator('.recharts-wrapper').count()} text={ft[:120]!r}")
        q.screenshot(path=str(S/"c_facilities_uploaded.png"),full_page=True)
        q.goto(BASE+"/buildings",wait_until="networkidle"); q.wait_for_timeout(1000); bt=q.locator("main").inner_text()
        rec("C7","buildings page lists Block A-D with area",all(x in bt for x in ("Block A","Block B","Block C","Block D")),bt[:100].replace("\n"," | "))
        q.goto(BASE+"/alerts",wait_until="networkidle"); q.wait_for_timeout(800)
        rec("C8","alerts computed for the uploaded society (stuck 60 h stretch is a candidate)","Whole-society alerts" in q.locator("main").inner_text(),q.locator("main").inner_text()[200:330].replace("\n"," | "))
        # delete via UI
        pg.goto(BASE+"/society-admin",wait_until="networkidle")
        pg.get_by_role("button",name=f"Delete {NAME}").click(); pg.wait_for_timeout(500)
        dlg=pg.locator("[role=dialog]"); rec("C9a","delete asks for confirmation",dlg.count()==1,dlg.first.inner_text()[:120].replace("\n"," | ") if dlg.count() else "")
        pg.get_by_role("button",name="Cancel").click(); pg.wait_for_timeout(300)
        still=[s for s in json.load(_req("/societies",token=token())) if s["name"]==NAME]; rec("C9b","cancel keeps the society",len(still)==1)
        pg.get_by_role("button",name=f"Delete {NAME}").click(); pg.wait_for_timeout(300)
        inp=pg.locator("[role=dialog] input")
        if inp.count(): inp.first.fill(NAME)
        pg.locator("[role=dialog]").get_by_role("button",name=re.compile("Delete",re.I)).click(); pg.wait_for_timeout(2500)
        gone=[s for s in json.load(_req("/societies",token=token())) if s["name"]==NAME]; rec("C9c","confirmed delete removes the society and its data",len(gone)==0)
    print("page errors:",len(errs),errs[:3]); b.close()
Path("/home/claude/pro/logs/audit_c.json").write_text(json.dumps(res,indent=1))
print("SUMMARY",sum(r[2]=="PASS" for r in res),"pass",sum(r[2]=="FAIL" for r in res),"fail")
