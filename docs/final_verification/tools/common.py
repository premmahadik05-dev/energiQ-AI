import json, urllib.request, urllib.error
from pathlib import Path
BASE="http://127.0.0.1:5173"; API="http://127.0.0.1:8000/api/v1"
CACHE=Path("/home/claude/pro/run/token.txt")
def _req(path,data=None,token=None,method=None):
    h={"Content-Type":"application/json"}
    if token: h["Authorization"]="Bearer "+token
    return urllib.request.urlopen(urllib.request.Request(API+path,data=json.dumps(data).encode() if data is not None else None,headers=h,method=method))
def token(email="admin@example.com",pw="AdminPass-12345"):
    f=CACHE.with_name("token_"+email.split("@")[0]+".txt")
    if f.exists():
        try: _req("/auth/me",token=f.read_text().strip()); return f.read_text().strip()
        except urllib.error.HTTPError: pass
    t=json.load(_req("/auth/login",{"email":email,"password":pw}))["access_token"]; f.write_text(t); return t
def new_ctx(browser,tok=None,viewport=(1440,900)):
    ctx=browser.new_context(viewport={"width":viewport[0],"height":viewport[1]})
    ctx.add_init_script(f"sessionStorage.setItem('energiq.token','{tok or token()}')"); return ctx
