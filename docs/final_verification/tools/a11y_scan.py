"""axe-core accessibility scan of every route (signed in), desktop and phone width. Results go to logs/final/a11y.json."""
import sys, json
sys.path.insert(0,"/home/claude/pro/tools")
import common
from playwright.sync_api import sync_playwright
AXE=open("/tmp/claude-0/-home-claude/247b2d3e-c5f9-5fdc-b3ba-90578d09fb30/scratchpad/axe/node_modules/axe-core/axe.min.js").read()
ROUTES=["/","/compare","/consumption","/forecasting","/buildings","/facilities","/cost","/alerts","/recommendations","/reports","/data-sources","/notifications","/jobs","/society-admin","/admin"]
out={}
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for label,vp in (("desktop",(1440,900)),("phone",(390,844))):
        ctx=common.new_ctx(b,viewport=vp); pg=ctx.new_page()
        for r in ROUTES:
            pg.goto(common.BASE+r); pg.wait_for_selector("h1",timeout=30000); pg.wait_for_timeout(2500)
            pg.evaluate(AXE)
            res=pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.length,sample:v.nodes.slice(0,2).map(n=>n.target.join(' ')+' :: '+(n.failureSummary||'').split('\\n').slice(1,3).join(' | '))})))")
            out[f"{label} {r}"]=res
            print(label,r,len(res),[ (v['id'],v['impact'],v['nodes']) for v in res])
        ctx.close()
    # login page (signed out)
    c=b.new_context(viewport={"width":1440,"height":900}); p=c.new_page(); p.goto(common.BASE+"/login"); p.wait_for_selector("h1"); p.evaluate(AXE)
    res=p.evaluate("axe.run(document).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.length})))"); out["desktop /login"]=res; print("login",res)
    b.close()
json.dump(out,open("/home/claude/pro/logs/final/a11y.json","w"),indent=1)
