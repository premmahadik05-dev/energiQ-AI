import json
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE="http://127.0.0.1:5173"
ROUTES=["/","/consumption","/forecasting","/buildings","/facilities","/cost","/alerts","/recommendations","/reports","/data-sources","/notifications","/jobs","/society-admin","/admin"]
out={}
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1440,"height":900}).new_page()
    pg.goto(BASE+"/login",wait_until="networkidle")
    pg.get_by_label("Email address").fill("admin@example.com"); pg.get_by_label("Password",exact=True).fill("AdminPass-12345")
    pg.get_by_role("button",name="Sign in").click(); pg.wait_for_url(lambda u:"/login" not in u); pg.wait_for_load_state("networkidle")
    for r in ROUTES:
        pg.goto(BASE+r,wait_until="networkidle"); pg.wait_for_timeout(800)
        out[r]=pg.evaluate("""()=>{
          const t=e=>(e.getAttribute('aria-label')||e.innerText||e.value||'').trim().replace(/\\s+/g,' ').slice(0,50);
          const main=document.querySelector('main')||document.body;
          return {
           headings:[...main.querySelectorAll('h1,h2,h3')].map(e=>e.innerText.trim().slice(0,60)),
           buttons:[...main.querySelectorAll('button')].map(e=>t(e)+(e.disabled?' [disabled]':'')),
           links:[...main.querySelectorAll('a[href]')].map(e=>t(e)+' -> '+e.getAttribute('href')).slice(0,25),
           fields:[...main.querySelectorAll('input,select,textarea')].map(e=>`${e.tagName.toLowerCase()}:${e.type||''}:${(e.labels&&e.labels[0]?e.labels[0].innerText:e.getAttribute('aria-label')||e.name||'').trim().slice(0,40)}`)}}""")
    b.close()
Path("/home/claude/pro/logs/inventory.json").write_text(json.dumps(out,indent=1))
for r,v in out.items():
    print(f"\n### {r}\n H: {' | '.join(v['headings'])[:300]}\n B({len(v['buttons'])}): {' | '.join(dict.fromkeys(v['buttons']))[:420]}\n F: {' | '.join(v['fields'])[:300]}")
