import sys, json
sys.path.insert(0,"/home/claude/pro/tools")
import common
from playwright.sync_api import sync_playwright
OUT="/home/claude/pro/shots/new/"
# clean slate: remove tariffs left by an earlier run
_t=common.token()
for t in json.load(common._req("/tariffs",token=_t)):
    if not t["is_demo"]: common._req(f"/tariffs/{t['id']}",token=_t,method="DELETE")
R={}
def step(name,ok,detail=""):
    R[name]={"ok":bool(ok),"detail":detail}; print(("PASS " if ok else "FAIL ")+name, detail)
with sync_playwright() as pw:
    b=pw.chromium.launch(); ctx=common.new_ctx(b); pg=ctx.new_page()
    errs=[]
    pg.on("console",lambda m: errs.append(m.text) if m.type in("error","warning") else None)
    pg.on("pageerror",lambda e: errs.append("PAGEERROR "+str(e)))
    pg.goto(common.BASE+"/cost"); pg.wait_for_selector("text=Add a tariff",timeout=30000)
    form=pg.get_by_role("form",name="Add a tariff")
    # 1 empty submit shows validation, nothing is created
    form.get_by_role("button",name="Save tariff").click()
    step("empty submit shows field errors", form.get_by_text("Give the tariff a name").is_visible() and form.get_by_text("The rate must be a number").is_visible())
    n_before=pg.locator("table").first.locator("tbody tr").count()
    # 2 invalid number
    form.get_by_label("Name", exact=True).fill("Home bill")
    form.get_by_label("Rate (INR per kWh)", exact=True).fill("-3")
    form.get_by_role("button",name="Save tariff").click()
    step("negative rate rejected", form.get_by_text("The rate must be a number").is_visible())
    # 3 valid flat INR
    form.get_by_label("Rate (INR per kWh)", exact=True).fill("7.5")
    form.get_by_label("Fixed charge per day (INR)").fill("12")
    step("preview appears for valid rates", pg.get_by_text("Rate by hour of day (preview of what will be saved)").is_visible())
    pg.screenshot(path=OUT+"tariff_form_filled.png",full_page=True)
    form.get_by_role("button",name="Save tariff").click()
    pg.wait_for_selector("text=Tariff \"Home bill\" saved and selected.",timeout=10000)
    pg.wait_for_timeout(1500)
    step("saved tariff listed and in use", pg.get_by_role("row",name="Home bill").count()==1 and "In use" in pg.get_by_role("row",name="Home bill").inner_text())
    # cost now in INR with Indian grouping
    pg.wait_for_selector("text=Estimated cost",timeout=15000); pg.wait_for_timeout(1200)
    kpi=pg.locator("text=Estimated cost").first.locator("xpath=..").inner_text()
    step("cost figure uses rupees", "₹" in kpi, kpi.replace("\n"," | "))
    pg.screenshot(path=OUT+"cost_inr.png",full_page=True)
    # 4 duplicate name
    form.get_by_label("Name", exact=True).fill("Home bill"); form.get_by_label("Rate (INR per kWh)", exact=True).fill("5")
    form.get_by_role("button",name="Save tariff").click()
    pg.wait_for_timeout(800)
    step("duplicate name rejected by server", form.get_by_text("You already have a tariff with this name").is_visible())
    # 5 peak window
    form.get_by_label("Name", exact=True).fill("Time of day")
    form.get_by_text("Peak and off-peak").click()
    form.get_by_label("Off-peak rate (INR per kWh)").fill("5")
    form.get_by_label("Peak rate (INR per kWh)", exact=True).fill("9")
    form.get_by_label("Peak starts at hour").fill("18"); form.get_by_label("Peak ends before hour").fill("18")
    form.get_by_role("button",name="Save tariff").click()
    step("window with equal start/end rejected", form.get_by_text("different hour").is_visible())
    form.get_by_label("Peak ends before hour").fill("22")
    form.get_by_role("button",name="Save tariff").click()
    pg.wait_for_selector("text=Tariff \"Time of day\" saved and selected.",timeout=10000); pg.wait_for_timeout(1200)
    row=pg.get_by_role("row",name="Time of day").inner_text()
    step("peak tariff stored with 5 to 9 range", "5 to 9" in row.replace("\n"," "), row.replace("\n"," | "))
    # 6 cost differs between tariffs
    # 7 delete the one in use -> falls back to demo
    pg.get_by_role("button",name="Delete tariff Time of day").click()
    pg.get_by_role("dialog").get_by_role("button",name="Delete tariff").click()
    pg.wait_for_selector("text=Tariff \"Time of day\" deleted.",timeout=10000); pg.wait_for_timeout(1200)
    step("deleted, list updated", pg.get_by_role("row",name="Time of day").count()==0)
    step("selection fell back to demo", "In use" in pg.get_by_role("row",name="DEMO tariff").inner_text())
    pg.get_by_role("button",name="Delete tariff Home bill").click()
    pg.get_by_role("dialog").get_by_role("button",name="Cancel").click()
    step("cancel keeps tariff", pg.get_by_role("row",name="Home bill").count()==1)
    # 8 persistence across reload
    pg.reload(); pg.wait_for_selector("text=Add a tariff",timeout=30000); pg.wait_for_timeout(1000)
    step("tariff persists after reload", pg.get_by_role("row",name="Home bill").count()==1)
    # the duplicate-name step deliberately makes the server answer 409, which Chromium logs as a console error
    unexpected=[e for e in errs if "409" not in e]
    step("no unexpected console errors (the deliberate 409 is excluded)", len(unexpected)==0, "; ".join(unexpected[:3]))
    b.close()
json.dump(R,open("/home/claude/pro/logs/verify_tariff.json","w"),indent=1)
print(sum(v["ok"] for v in R.values()),"/",len(R))
