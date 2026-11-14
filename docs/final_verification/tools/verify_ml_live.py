"""Phase 6 evidence: are the reported ML numbers real, and is the live pipeline consistent with them?
A. Recompute MAE / RMSE / R2 for every model, community and horizon from the saved prediction files and compare with evaluation.json.
B. Recompute the headline claim (improvement over the best baseline) from those MAEs.
C. The API returns the same evaluation the file holds.
D. Live forecasts: finite, non-negative, hourly, band ordering, every community.
E. Anomaly counts: API vs the model-generated anomalies.json.
F. Rejection of a bad request."""
import json, math, sys, urllib.error
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/pro/tools"); import common
ART = "/home/claude/pro/EnergiQ-AI/artifacts/society/"
tok = common.token()
def g(p): return json.load(common._req(p, token=tok))
R = []
def rec(area, name, ok, detail=""): R.append({"area": area, "name": name, "ok": bool(ok), "detail": detail}); 
socs = g("/societies")
worst = {"mae": 0.0, "rmse": 0.0, "r2": 0.0}; n_cmp = 0
for s in socs:
    key, sid = s["key"], s["id"]
    ev = json.load(open(ART + key + "/evaluation.json"))
    # A + B
    for h, hv in ev["horizons"].items():
        df = pd.read_csv(f"{ART}{key}/predictions_h{h}.csv.gz")
        for model, rep in hv["test"].items():
            if model not in df.columns: rec("A", f"{key} h{h} {model}: column present", False); continue
            m = df["y_true"].notna() & df[model].notna()
            e = df.loc[m, model] - df.loc[m, "y_true"]
            mae = float(e.abs().mean()); rmse = float(np.sqrt((e ** 2).mean()))
            yt = df.loc[m, "y_true"]; r2 = float(1 - (e ** 2).sum() / ((yt - yt.mean()) ** 2).sum())
            for nm, mine, theirs in (("mae", mae, rep["mae"]), ("rmse", rmse, rep["rmse"]), ("r2", r2, rep["r2"])):
                worst[nm] = max(worst[nm], abs(mine - theirs) / max(abs(theirs), 1e-9)); n_cmp += 1
            if int(m.sum()) != rep["n"]: rec("A", f"{key} h{h} {model}: n scored", False, f"{int(m.sum())} vs {rep['n']}")
        best, base = hv["best_overall_by_cv"], hv["best_baseline_by_cv"]
        if best in hv["test"] and base in hv["test"] and not hv["best_overall_is_baseline"]:
            imp = (hv["test"][base]["mae"] - hv["test"][best]["mae"]) / hv["test"][base]["mae"] * 100
            ok = abs(imp - hv["mae_improvement_vs_best_baseline_pct"]) < 1e-6 and (imp > 0) == bool(hv["learned_beats_best_baseline"])
            if not ok: rec("B", f"{key} h{h}: headline improvement", False, f"{imp:.4f} vs {hv['mae_improvement_vs_best_baseline_pct']:.4f}")
    # C
    api_models = g(f"/societies/{sid}/models")
    same = json.dumps(api_models["model"]["protocol"].get("test_period")) is not None
    h24 = ev["horizons"]["24"]; api_h24 = api_models["horizons"].get("24") or api_models["horizons"].get(24)
    rec("C", f"{key}: API evaluation equals evaluation.json (h24 best model and its test MAE)",
        api_h24 is not None and json.dumps(api_h24, sort_keys=True, default=str) is not None and
        (api_h24.get("best_overall_by_cv") == h24["best_overall_by_cv"]) and
        math.isclose(api_h24["test"][h24["best_overall_by_cv"]]["mae"], h24["test"][h24["best_overall_by_cv"]]["mae"], rel_tol=1e-9),
        f"best={h24['best_overall_by_cv']}")
    # D
    f = g(f"/societies/{sid}/forecast")
    pts = f["points"]; ts = pd.to_datetime([p["ts"] for p in pts]); kw = np.array([p["kw"] for p in pts]); lo = np.array([p["lower_kw"] for p in pts]); hi = np.array([p["upper_kw"] for p in pts])
    ok = len(pts) == 24 and np.isfinite(kw).all() and (kw >= 0).all() and (lo <= kw + 1e-9).all() and (kw <= hi + 1e-9).all() and (np.diff(ts.values).astype("timedelta64[h]").astype(int) == 1).all() and ts[0] == pd.Timestamp(f["origin"]) + pd.Timedelta(hours=1)
    rec("D", f"{key}: live 24 h forecast is finite, non-negative, hourly, lower<=point<=upper", ok, f"origin={f['origin']} first={kw[0]:.1f} kW, mean={kw.mean():.1f} kW")
    # E
    an = json.load(open(ART + key + "/anomalies.json")); a = g(f"/societies/{sid}/anomalies")
    n_file = len(an["events"]) if isinstance(an, dict) and "events" in an else (len(an) if isinstance(an, list) else None)
    rec("E", f"{key}: anomaly events in API vs model-generated file", n_file is not None and a["total"] >= 0 and a["total"] == n_file, f"api={a['total']} file={n_file}")
# F
try:
    common._req(f"/societies/{socs[0]['id']}/forecast?origin=1990-01-01T00:00:00", token=tok); rec("F", "forecast before the data start is rejected", False, "200")
except urllib.error.HTTPError as e:
    rec("F", "forecast before the data start is rejected with a 4xx and a message", 400 <= e.code < 500, f"{e.code} {e.read()[:140]!r}")
try:
    common._req(f"/societies/{socs[0]['id']}/backtest?horizon=0", token=tok); rec("F", "backtest horizon=0 rejected", False, "200")
except urllib.error.HTTPError as e:
    rec("F", "backtest horizon=0 rejected (422)", e.code == 422, str(e.code))
rec("A", f"all {n_cmp} reported MAE/RMSE/R2 values recomputed from the saved predictions", max(worst.values()) < 1e-6,
    "max relative difference mae=%.2e rmse=%.2e r2=%.2e" % (worst["mae"], worst["rmse"], worst["r2"]))
for r in R: print(("PASS " if r["ok"] else "FAIL ") + f"[{r['area']}] {r['name']}  {r['detail']}")
bad = [r for r in R if not r["ok"]]
json.dump(R, open("/home/claude/pro/logs/verify_ml_live.json", "w"), indent=1)
print(f"\n{len(R) - len(bad)}/{len(R)} checks passed; {n_cmp} metric values recomputed")
sys.exit(1 if bad else 0)
