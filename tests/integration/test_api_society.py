"""Society-level API on REAL data: the processed Fox community (BDG2) and its trained, deployed models.

Expected values are recomputed from the processed CSV files and the saved evaluation files, independently of the API
code. The tests need `data/society/processed/fox` and `artifacts/society/fox` (shipped with the project; rebuild with
scripts/society_prepare.py and scripts/society_train.py --deploy).
"""
from __future__ import annotations

import io
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from itest_support import REPO, login, make_settings, signup

from backend.app.main import create_app
from backend.app.services.society_import import import_processed
from ml_engine.society.serving import forecast_from_bundle

API = "/api/v1"
PROCESSED = REPO / "data" / "society" / "processed"
ARTIFACTS = REPO / "artifacts" / "society"

pytestmark = pytest.mark.skipif(not (PROCESSED / "fox" / "society_hourly.csv.gz").is_file() or not (ARTIFACTS / "fox" / "bundle.json").is_file(),
                                reason="processed Fox data / trained bundle not present; run scripts/society_prepare.py and scripts/society_train.py --deploy")


def _settings(tmp):
    return make_settings(tmp, society_dir=ARTIFACTS, society_data_dir=PROCESSED)


@pytest.fixture(scope="module")
def raw():
    d = pd.read_csv(PROCESSED / "fox" / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    m = pd.read_csv(PROCESSED / "fox" / "meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    ev = json.loads((ARTIFACTS / "fox" / "evaluation.json").read_text())
    return {"soc": d["society_kwh"], "meters": m, "ev": ev}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("society")
    st = _settings(tmp)
    app = create_app(st)
    with TestClient(app) as c:
        with app.state.db.session() as s:
            import_processed(s, "fox", st.society_data_dir, st.society_dir, log_fn=lambda *a: None)
        admin = login(c, "admin@example.com", "AdminPass-12345")
        analyst = signup(c, "analyst@example.com")
        viewer_h = signup(c, "viewer@example.com")
        users = c.get(f"{API}/admin/users", headers=admin).json()
        vid = next(u["id"] for u in users if u["email"] == "viewer@example.com")
        assert c.patch(f"{API}/admin/users/{vid}", headers=admin, json={"role": "viewer"}).status_code == 200
        sid = c.get(f"{API}/societies", headers=analyst).json()[0]["id"]
        yield {"c": c, "admin": admin, "analyst": analyst, "viewer": viewer_h, "sid": sid, "app": app, "tmp": tmp, "settings": st}


def get(env, path, who="analyst", **params):
    return env["c"].get(f"{API}/societies/{env['sid']}{path}", headers=env[who], params=params)


# ----------------------------------------------------------------------------- auth and privacy
def test_endpoints_require_login(env):
    assert env["c"].get(f"{API}/societies").status_code == 401
    assert env["c"].get(f"{API}/societies/{env['sid']}/overview").status_code == 401


def test_list_and_detail_describe_the_real_source(env):
    lst = env["c"].get(f"{API}/societies", headers=env["analyst"]).json()
    assert [s["key"] for s in lst] == ["fox"]
    s = lst[0]
    assert s["buildings"] == 11 and s["has_model"] and s["forecast_ready"]
    assert s["hours"] == 17544 and s["valid_hours"] == 17486
    assert "CC BY-SA 4.0" in s["license"]
    d = get(env, "").json()
    assert d["source_url"].startswith("https://github.com/buds-lab/")
    assert "representative community" in d["description"]  # honest framing: not a registered housing society


def test_data_card_cleaning_totals_equal_the_sum_of_the_per_building_counts(env):
    rep = json.loads((PROCESSED / "fox" / "cleaning_report.json").read_text())
    per = rep["cleaning_counts_per_building"].values()
    card = get(env, "").json()["data_card"]
    t = card["cleaning_totals"]
    for key in ("readings", "missing_in_source", "negative", "zero_long_runs", "zero_short", "stuck_sensor", "spike", "valid_out"):
        assert t[key] == sum(v[key] for v in per), key
    assert t["valid_out"] + t["missing_in_source"] + t["negative"] + t["zero_long_runs"] + t["zero_short"] + t["stuck_sensor"] + t["spike"] == t["readings"]
    assert card["excluded_count"] == rep["buildings_excluded"]
    assert "cleaning_counts_per_building" not in card  # per-meter detail is admin-only


def test_admin_meter_list_links_each_building_meter_to_its_building(env):
    meters = get(env, "/meters", who="admin").json()
    ids = {b["code"]: b["id"] for b in get(env, "/buildings", who="admin").json()["buildings"]}
    assert len(meters) == 11 and all(m["kind"] == "building" for m in meters)
    assert all(m["building_id"] == ids[m["code"]] for m in meters)
    assert get(env, "/meters", who="analyst").status_code == 403


def test_dataset_identifiers_are_admin_only(env):
    admin_b = get(env, "/buildings", who="admin").json()["buildings"]
    user_b = get(env, "/buildings", who="analyst").json()["buildings"]
    assert all(b["source_id"] for b in admin_b)
    assert all("source_id" not in b for b in user_b)
    assert {b["code"] for b in user_b} == {f"FOX-B{i:02d}" for i in range(1, 12)}
    assert "excluded_meters" in get(env, "", who="admin").json()["data_card"]
    assert "excluded_meters" not in get(env, "").json()["data_card"]
    assert "Fox_lodging" not in get(env, "").text and "Fox_lodging" not in get(env, "/buildings").text


def test_admin_only_actions_are_forbidden_to_others(env):
    c, sid = env["c"], env["sid"]
    for who in ("analyst", "viewer"):
        h = env[who]
        assert c.delete(f"{API}/societies/{sid}", headers=h).status_code == 403
        assert c.post(f"{API}/admin/societies/import-bundled", headers=h).status_code == 403
        assert c.post(f"{API}/admin/societies/{sid}/train", headers=h).status_code == 403
        assert c.post(f"{API}/admin/societies/upload", headers=h, data={"name": "Some society"}, files={"file": ("a.csv", b"x", "text/csv")}).status_code == 403
        assert c.get(f"{API}/societies/{sid}/meters", headers=h).status_code == 403
        assert c.patch(f"{API}/societies/{sid}/buildings/1", headers=h, json={"is_active": False}).status_code == 403


# ----------------------------------------------------------------------------- consumption
def test_overview_matches_the_raw_data(env, raw):
    o = get(env, "/overview").json()
    s = raw["soc"].dropna()
    assert o["latest"]["demand_kw"] == pytest.approx(s.iloc[-1]) and o["as_of"].startswith("2017-12-31 23")
    assert o["totals"]["energy_kwh"] == pytest.approx(s.sum(), rel=1e-9)
    assert o["totals"]["peak_kw"] == pytest.approx(s.max()) and o["totals"]["peak_ts"].startswith("2016-09-11 21")
    last24 = raw["soc"].loc["2017-12-31 00:00":"2017-12-31 23:00"]
    assert o["windows"]["last_24h"]["energy_kwh"] == pytest.approx(last24.sum(), rel=1e-9)
    assert o["totals"]["load_factor"] == pytest.approx(s.mean() / s.max())
    assert o["forecast"]["peak_kw"] > 0 and len(o["forecast"]["peak_range_kw"]) == 2
    assert o["cost_last_24h"]["is_demo_tariff"] is True and o["tariff"]["is_demo"] is True
    assert "not a live feed" in o["as_of_note"]


def test_daily_and_monthly_energy_equal_sums_of_the_hourly_data(env, raw):
    pts = get(env, "/consumption", resolution="daily", start="2017-03-01", end="2017-03-31T23:00:00").json()["points"]
    assert len(pts) == 31
    for p in pts[:5]:
        day = raw["soc"].loc[p["ts"][:10]]
        assert p["energy_kwh"] == pytest.approx(day.sum(), abs=0.01) and p["peak_kw"] == pytest.approx(day.max(), abs=0.01)
        assert p["avg_kw"] == pytest.approx(day.mean(), abs=0.01)
    months = get(env, "/consumption", resolution="monthly").json()["points"]
    assert len(months) == 24
    jan = months[0]
    assert jan["valid_hours"] == int(raw["soc"].loc["2016-01"].notna().sum()) and jan["complete"] is False  # a few missing hours are flagged, not filled
    assert jan["energy_kwh"] == pytest.approx(raw["soc"].loc["2016-01"].sum(), abs=0.1)


def test_hourly_requests_are_capped_and_ranges_validated(env):
    assert get(env, "/consumption", resolution="hourly", start="2016-01-01", end="2017-12-31").status_code == 422
    ok = get(env, "/consumption", resolution="hourly", start="2017-06-01", end="2017-06-03T23:00:00").json()["points"]
    assert len(ok) == 72
    assert get(env, "/consumption", start="2017-06-03", end="2017-06-01").status_code == 422
    assert get(env, "/consumption", resolution="yearly").status_code == 422
    z = get(env, "/consumption", resolution="daily", start="2017-06-01T00:00:00Z", end="2017-06-02T00:00:00+05:30")  # offsets are accepted, not a server error
    assert z.status_code == 200


def test_hourly_buildings_sum_to_the_society_total_where_all_are_valid(env, raw):
    c = env["c"]
    blds = get(env, "/buildings").json()["buildings"]
    day = ("2017-05-10", "2017-05-10T23:00:00")
    mats = []
    for b in blds:
        r = c.get(f"{API}/societies/{env['sid']}/buildings/{b['id']}/consumption", headers=env["analyst"], params={"resolution": "hourly", "start": day[0], "end": day[1]})
        mats.append(pd.Series({p["ts"]: p["energy_kwh"] for p in r.json()["points"]}))
    total = pd.concat(mats, axis=1).sum(axis=1, min_count=11)
    api_total = pd.Series({p["ts"]: p["energy_kwh"] for p in get(env, "/consumption", resolution="hourly", start=day[0], end=day[1]).json()["points"]})
    assert len(total) == 24
    assert np.allclose(total.to_numpy(), api_total.reindex(total.index).to_numpy(), atol=0.02)


def test_building_comparison_matches_the_raw_meters(env, raw):
    r = get(env, "/buildings", start="2017-01-01", end="2017-06-30T23:00:00").json()
    seg = raw["meters"].loc["2017-01-01":"2017-06-30 23:00"]
    for b in r["buildings"]:
        assert b["energy_kwh"] == pytest.approx(seg[b["code"]].sum(), rel=1e-6)
        assert b["peak_kw"] == pytest.approx(seg[b["code"]].max(), abs=0.01)
    assert sum(b["share_pct"] for b in r["buildings"]) == pytest.approx(100.0, abs=0.01)
    m = get(env, "/buildings-monthly").json()
    assert len(m["months"]) == 24 and len(m["buildings"]) == 11
    b1 = next(b for b in m["buildings"] if b["code"] == "FOX-B01")
    assert b1["energy_kwh"][5] == pytest.approx(raw["meters"]["FOX-B01"].loc["2016-06"].sum(), abs=0.2)
    assert get(env, "/buildings/999999/consumption").status_code == 404


def test_facilities_are_reported_as_not_measured(env):
    f = get(env, "/facilities").json()
    assert f["available"] is False
    assert {c["category"] for c in f["categories"]} == {"lift", "pump", "streetlight", "clubhouse"}
    assert all(c["measured"] is False and c["status"] == "not measured in this dataset" and c["meters"] == [] for c in f["categories"])
    assert "not metered separately" in f["message"]


def test_admin_can_deactivate_a_building_and_meters_list_is_admin_only(env):
    c, sid = env["c"], env["sid"]
    ms = get(env, "/meters", who="admin").json()
    assert len(ms) == 11 and all(m["kind"] == "building" and m["unit"] == "kWh" and m["interval_minutes"] == 60 for m in ms)
    b = get(env, "/buildings").json()["buildings"][0]
    r = c.patch(f"{API}/societies/{sid}/buildings/{b['id']}", headers=env["admin"], json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert len(get(env, "/buildings").json()["buildings"]) == 10
    assert c.patch(f"{API}/societies/{sid}/buildings/{b['id']}", headers=env["admin"], json={"is_active": True}).json()["is_active"] is True
    assert len(get(env, "/buildings").json()["buildings"]) == 11
    assert c.patch(f"{API}/societies/{sid}/buildings/999999", headers=env["admin"], json={"is_active": True}).status_code == 404


def test_peak_analysis(env, raw):
    p = get(env, "/peaks").json()
    assert len(p["profile"]) == 24
    ev = p["forecast_evaluation"]
    assert ev["days"] > 100 and ev["horizon_h"] == 24 and ev["model"]["peak_mae_kw"] > 0
    saved = json.loads((ARTIFACTS / "fox" / "peak_evaluation.json").read_text())
    assert ev["model"]["peak_mae_kw"] == pytest.approx(saved["model"]["peak_mae_kw"])
    prof = raw["soc"].groupby(raw["soc"].index.hour).mean()
    assert p["profile"][19]["mean_kw"] == pytest.approx(prof[19], rel=1e-6)


def test_peak_evaluation_names_the_scored_methods(env, raw):
    """Older saved files lost the names; the API reads them from the 24 h cross-validation result they were computed for."""
    ev = get(env, "/peaks").json()["forecast_evaluation"]
    h24 = raw["ev"]["horizons"]["24"]
    assert ev["model_name"] == h24["best_overall_by_cv"]
    assert ev["baseline_name"] == h24["best_baseline_by_cv"]
    assert isinstance(ev["model"], dict) and isinstance(ev["baseline"], dict)


# ----------------------------------------------------------------------------- models and forecasts
def test_models_endpoint_reports_the_saved_evaluation(env, raw):
    m = get(env, "/models").json()
    assert m["model"]["protocol"]["test_period"] == ["2017-07-01 00:00:00", "2017-12-31 23:00:00"]
    assert set(m["horizons"]) == {"1", "6", "12", "24", "168"}
    for h, r in m["horizons"].items():
        assert r["test"][r["best_overall_by_cv"]]["mae"] == raw["ev"]["horizons"][h]["test"][r["best_overall_by_cv"]]["mae"]
    assert m["deployed"]["24"]["family"] in {"linear", "random_forest", "xgboost", "xgboost_weather", "baseline"}
    assert "nearest evaluated" in m["note"]


def test_live_forecast_uses_the_deployed_models_and_has_ordered_ranges(env, raw):
    f = get(env, "/forecast").json()
    assert f["origin"].startswith("2017-12-31 23") and len(f["points"]) == 24
    assert [p["horizon"] for p in f["points"]] == list(range(1, 25))
    for p in f["points"]:
        assert p["lower_kw"] <= p["kw"] <= p["upper_kw"] and p["actual_kw"] is None  # the future is not in the data
    direct = forecast_from_bundle(ARTIFACTS / "fox", raw["soc"].rename("demand_kw"),
                                  pd.read_csv(PROCESSED / "fox" / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")[["airTemperature", "dewTemperature", "windSpeed"]],
                                  pd.Timestamp("2017-12-31 23:00"), [1, 24])
    got = {p["horizon"]: p["kw"] for p in f["points"]}
    assert got[1] == pytest.approx(direct["points"][0]["kw"]) and got[24] == pytest.approx(direct["points"][1]["kw"])
    assert f["summary"]["next_24h_energy_kwh"] == pytest.approx(sum(p["kw"] for p in f["points"]))
    assert f["summary"]["peak_kw"] == pytest.approx(max(p["kw"] for p in f["points"]))
    assert f["accuracy"]["24"]["mae_kw"] == pytest.approx(raw["ev"]["horizons"]["24"]["test"][f["accuracy"]["24"]["model"]]["mae"])


def test_forecast_from_an_earlier_origin_uses_only_data_up_to_that_origin(env, raw):
    origin = pd.Timestamp("2017-10-12 08:00")
    f = get(env, "/forecast", origin=str(origin), horizons="1,6,24").json()
    cut = raw["soc"].loc[:origin].rename("demand_kw")  # a series that ends at the origin: nothing after it can leak in
    wx = pd.read_csv(PROCESSED / "fox" / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")[["airTemperature", "dewTemperature", "windSpeed"]].loc[:origin]
    direct = forecast_from_bundle(ARTIFACTS / "fox", cut, wx, origin, [1, 6, 24])
    assert [p["kw"] for p in f["points"]] == pytest.approx([p["kw"] for p in direct["points"]])
    for p in f["points"]:  # the realised value is shown next to the forecast when the data contain it
        assert p["actual_kw"] == pytest.approx(raw["soc"].loc[p["ts"]])


def test_forecast_input_validation(env):
    assert get(env, "/forecast", horizons="0,5").status_code == 422
    assert get(env, "/forecast", horizons="abc").status_code == 422
    assert get(env, "/forecast", horizons="200").status_code == 422
    assert get(env, "/forecast", horizons="50").status_code == 422  # only 1-24 h and 168 h are deployed
    assert get(env, "/forecast", origin="2030-01-01").status_code == 422


def test_backtest_returns_real_out_of_sample_results_whose_metrics_can_be_recomputed(env, raw):
    r = get(env, "/backtest", horizon=24, limit=6000).json()
    pts = pd.DataFrame(r["points"]).dropna(subset=["actual_kw"])
    assert pts["ts"].min() >= "2017-07-01" and len(pts) == r["metrics"]["n"]  # the held-out test period only
    mae = float((pts["predicted_kw"] - pts["actual_kw"]).abs().mean())
    assert mae == pytest.approx(r["metrics"]["mae"], rel=1e-3)
    base_mae = float((pts["baseline_kw"] - pts["actual_kw"]).abs().mean())
    assert base_mae == pytest.approx(r["baseline_metrics"]["mae"], rel=1e-3)
    assert (pd.to_datetime(pts["ts"]) - pd.to_datetime(pts["origin"])).eq(pd.Timedelta(hours=24)).all()
    actual = raw["soc"].reindex(pd.to_datetime(pts["ts"]))
    assert np.allclose(actual.to_numpy(), pts["actual_kw"].to_numpy(), atol=0.01)  # actuals are the stored measurements
    cov = float(((pts["actual_kw"] >= pts["lower_kw"]) & (pts["actual_kw"] <= pts["upper_kw"])).mean() * 100)
    assert cov == pytest.approx(r["metrics"]["band_80_coverage_pct"], abs=0.5)
    assert get(env, "/backtest", horizon=24, start="2017-09-01", end="2017-09-07T23:00:00").json()["points"][0]["ts"].startswith("2017-09-01")
    assert get(env, "/backtest", horizon=5).status_code == 404  # horizon 5 h was not evaluated separately


def test_global_and_local_explanations_are_consistent_with_the_forecast(env):
    g = get(env, "/explain/global").json()
    top = g["horizons"]["24"]["top_features"]
    assert top[0]["mean_abs_shap_kw"] >= top[-1]["mean_abs_shap_kw"] > 0 and abs(sum(g["horizons"]["24"]["group_share_pct"].values()) - 100) < 0.5
    fc = get(env, "/forecast", horizons="24").json()["points"][0]["kw"]
    loc = env["c"].post(f"{API}/societies/{env['sid']}/explain/local", headers=env["analyst"], json={"horizon": 24}).json()
    assert loc["prediction_kw"] == pytest.approx(fc)
    assert loc["base_value_kw"] + sum(d["contribution_kw"] for d in loc["drivers"]) == pytest.approx(loc["prediction_kw"], rel=0.05)  # drivers shown are the largest; the rest is small
    assert env["c"].post(f"{API}/societies/{env['sid']}/explain/local", headers=env["analyst"], json={"horizon": 500}).status_code == 422


# ----------------------------------------------------------------------------- anomalies
def test_anomaly_alerts_filter_acknowledge_and_explain(env):
    allr = get(env, "/anomalies", limit=500).json()
    assert allr["total"] > 0 and allr["summary"]["total"] == allr["summary"]["open"]
    mh = get(env, "/anomalies", min_severity=2, limit=500).json()
    assert 0 < mh["total"] < allr["total"] and all(e["severity_level"] >= 2 for e in mh["events"])
    soc_events = get(env, "/anomalies", scope="society", severity="high", limit=500).json()["events"]
    assert soc_events and all(e["scope"] == "society" and e["building"] is None for e in soc_events)
    assert all("kW" in e["explanation"] and e["start_ts"] <= e["peak_ts"] <= e["end_ts"] for e in soc_events)
    assert any(e["top_contributors"] for e in soc_events)  # a society alert says which buildings drove it
    b_events = get(env, "/anomalies", scope="building", min_severity=3, limit=50).json()["events"]
    assert b_events and all(e["building"].startswith("FOX-B") for e in b_events)
    ordered = get(env, "/anomalies", sort="severity", limit=20).json()["events"]
    assert [e["severity_level"] for e in ordered] == sorted([e["severity_level"] for e in ordered], reverse=True)
    window = get(env, "/anomalies", start="2017-08-01", end="2017-08-31T23:00:00", limit=500).json()["events"]
    assert window and all(e["end_ts"] >= "2017-08-01" and e["start_ts"] <= "2017-08-31 23:59" for e in window)
    assert "no ground-truth" in allr["note"]
    page2 = get(env, "/anomalies", limit=5, offset=5).json()["events"]
    assert page2 and page2[0]["id"] != get(env, "/anomalies", limit=5).json()["events"][0]["id"]

    eid = soc_events[0]["id"]
    c, sid = env["c"], env["sid"]
    assert c.patch(f"{API}/societies/{sid}/anomalies/{eid}", headers=env["viewer"], json={"acknowledged": True}).status_code == 403
    r = c.patch(f"{API}/societies/{sid}/anomalies/{eid}", headers=env["analyst"], json={"acknowledged": True})
    assert r.status_code == 200 and r.json()["acknowledged"] is True
    acked = get(env, "/anomalies", acknowledged="true", limit=500).json()
    assert [e["id"] for e in acked["events"]] == [eid] and acked["summary"]["open"] == allr["summary"]["open"] - 1
    assert c.patch(f"{API}/societies/{sid}/anomalies/{eid}", headers=env["analyst"], json={"acknowledged": False}).json()["acknowledged"] is False
    assert c.patch(f"{API}/societies/{sid}/anomalies/99999999", headers=env["analyst"], json={"acknowledged": True}).status_code == 404
    assert get(env, "/anomalies", severity="critical").status_code == 422


# ----------------------------------------------------------------------------- cost and recommendations
def test_cost_uses_the_chosen_tariff_and_is_labelled_an_estimate(env, raw):
    c, sid = env["c"], env["sid"]
    t = c.post(f"{API}/tariffs", headers=env["analyst"], json={"name": "Flat 0.20", "currency": "INR", "weekday_rates": [0.2] * 24, "weekend_rates": [0.2] * 24, "daily_fixed_charge": 10})
    assert t.status_code == 201
    r = c.post(f"{API}/societies/{sid}/cost", headers=env["analyst"], json={"tariff_id": t.json()["id"], "start": "2017-03-01", "end": "2017-03-31T23:00:00"}).json()
    seg = raw["soc"].loc["2017-03-01":"2017-03-31 23:00"]
    assert r["total"]["energy_kwh"] == pytest.approx(seg.sum(), abs=0.1)
    assert r["total"]["energy_cost"] == pytest.approx(0.2 * seg.sum(), rel=1e-6)  # flat rate: cost is exactly rate x kWh
    assert r["total"]["currency"] == "INR" and r["total"]["is_demo_tariff"] is False
    assert r["total"]["fixed_cost"] == pytest.approx(10 * 31)
    demo = c.post(f"{API}/societies/{sid}/cost", headers=env["analyst"], json={"start": "2017-03-01", "end": "2017-03-31T23:00:00"}).json()
    assert demo["total"]["is_demo_tariff"] is True
    assert c.post(f"{API}/societies/{sid}/cost", headers=env["viewer"], json={"tariff_id": t.json()["id"]}).status_code == 404  # tariffs are private to their owner
    assert c.post(f"{API}/societies/{sid}/cost", headers=env["analyst"], json={"tariff_id": "bogus"}).status_code == 422


def test_recommendations_are_evidence_based_and_caveated(env):
    r = env["c"].post(f"{API}/societies/{env['sid']}/recommendations", headers=env["analyst"], json={}).json()
    recs = r["recommendations"]
    assert recs
    for x in recs:
        assert x["evidence"] and x["caveats"] and x["explanation"]
        if x["scenario"]:
            # a saving appears only as a scenario with a stated assumption, and a caveat says it is not a measured or forecast saving
            assert x["scenario"]["assumption"] and any("saving" in cv and "not" in cv for cv in x["caveats"])
    assert any("DEMO tariff" in " ".join(x["caveats"]) for x in recs)


# ----------------------------------------------------------------------------- reports
def test_reports_are_created_downloaded_and_contain_the_real_numbers(env, raw):
    c, sid = env["c"], env["sid"]
    base = f"{API}/societies/{sid}/reports"
    pdf = c.post(base, headers=env["analyst"], json={"kind": "monthly", "format": "pdf", "start": "2017-11-01", "end": "2017-11-30T23:00:00"})
    assert pdf.status_code == 201, pdf.text
    body = c.get(f"{base}/{pdf.json()['id']}/download", headers=env["analyst"])
    assert body.status_code == 200 and body.content.startswith(b"%PDF-") and body.headers["content-type"] == "application/pdf"
    assert "attachment" in body.headers["content-disposition"]

    r = c.post(base, headers=env["analyst"], json={"kind": "consumption", "format": "csv", "resolution": "daily", "start": "2017-03-01", "end": "2017-03-10T23:00:00"})
    csv = pd.read_csv(io.BytesIO(c.get(f"{base}/{r.json()['id']}/download", headers=env["analyst"]).content))
    assert len(csv) == 10 and csv.iloc[0, 1] == pytest.approx(raw["soc"].loc["2017-03-01"].sum(), abs=0.01)

    f = c.post(base, headers=env["analyst"], json={"kind": "forecast", "format": "csv", "horizon": 24, "start": "2017-07-01", "end": "2017-07-03T23:00:00"})
    fc = pd.read_csv(io.BytesIO(c.get(f"{base}/{f.json()['id']}/download", headers=env["analyst"]).content))
    assert len(fc) == 72 and {"predicted_kw", "actual_kw"} <= set(fc.columns)
    for kind in ("anomalies", "cost", "buildings"):
        k = c.post(base, headers=env["analyst"], json={"kind": kind, "format": "csv"})
        assert k.status_code == 201 and k.json()["size_bytes"] > 100
    assert len(c.get(base, headers=env["viewer"]).json()) >= 6  # everyone signed in can list and download

    assert c.post(base, headers=env["viewer"], json={"kind": "cost", "format": "csv"}).status_code == 403
    assert c.post(base, headers=env["analyst"], json={"kind": "monthly", "format": "csv"}).status_code == 422
    assert c.post(base, headers=env["analyst"], json={"kind": "cost", "format": "pdf"}).status_code == 422
    assert c.post(base, headers=env["analyst"], json={"kind": "forecast", "format": "csv", "horizon": 24, "start": "2016-02-01", "end": "2016-02-03"}).status_code == 422  # no held-out forecasts before the test period
    assert c.post(base, headers=env["analyst"], json={"kind": "consumption", "format": "csv", "resolution": "hourly"}).status_code == 422
    assert c.get(f"{base}/99999/download", headers=env["analyst"]).status_code == 404


def test_default_monthly_report_covers_the_last_calendar_month(env):
    r = env["c"].post(f"{API}/societies/{env['sid']}/reports", headers=env["analyst"], json={"kind": "monthly", "format": "pdf"}).json()
    assert r["period_start"] == "2017-12-01 00:00:00" and r["period_end"] == "2017-12-31 23:00:00"


def test_peak_analysis_load_duration_and_distribution_match_the_raw_data(env, raw):
    soc = env["c"].get(f"{API}/societies/{env['sid']}", headers=env["analyst"]).json()
    p = get(env, "/peaks", start=soc["start"], end=soc["end"]).json()
    v = raw["soc"].dropna()
    ld = p["load_duration"]
    assert len(ld) == 101 and ld[0]["percent_of_time"] == 0 and ld[-1]["percent_of_time"] == 100
    assert ld[0]["kw"] == pytest.approx(v.max()) and ld[-1]["kw"] == pytest.approx(v.min())  # exceeded 0 % of the time = the peak; 100 % of the time = the minimum
    assert ld[50]["kw"] == pytest.approx(v.median(), rel=1e-6)
    assert all(a["kw"] >= b["kw"] for a, b in zip(ld, ld[1:]))  # a load-duration curve never rises
    dist = p["distribution"]
    assert sum(b["hours"] for b in dist) == len(v)  # every valid hour is in exactly one band
    assert dist[0]["from_kw"] == pytest.approx(v.min()) and dist[-1]["to_kw"] == pytest.approx(v.max())


def test_error_analysis_is_recomputed_from_the_held_out_forecasts(env, raw):
    e = get(env, "/error-analysis", horizon=24).json()
    bt = get(env, "/backtest", horizon=24, limit=6000).json()
    pts = pd.DataFrame(bt["points"]).dropna(subset=["actual_kw"])
    err = pts["predicted_kw"] - pts["actual_kw"]
    assert e["hours"] == len(pts) == bt["metrics"]["n"]
    assert e["mae_kw"] == pytest.approx(err.abs().mean(), rel=1e-9) and e["bias_kw"] == pytest.approx(err.mean(), rel=1e-9)
    assert e["rmse_kw"] == pytest.approx(float(np.sqrt((err ** 2).mean())), rel=1e-9)
    assert e["mae_kw"] == pytest.approx(bt["metrics"]["mae"], rel=1e-3)  # the same number the Forecasting page shows from the saved evaluation
    hours = pd.to_datetime(pts["ts"]).dt.hour
    for row in e["by_hour"]:
        sel = hours == row["hour"]
        assert row["n"] == int(sel.sum()) and row["mae_kw"] == pytest.approx(err[sel].abs().mean(), rel=1e-9)
    assert sum(b["hours"] for b in e["histogram"]) == e["hours"]  # tails are folded into the outer bars, nothing is dropped
    assert e["abs_error_percentiles_kw"]["p50"] == pytest.approx(err.abs().median())
    assert e["worst"][0]["error_kw"] == pytest.approx(err.loc[err.abs().idxmax()])
    assert 0 <= e["interval_coverage_pct"] <= 100 and e["horizon"] == 24
    assert get(env, "/error-analysis", horizon=5).status_code == 404  # 5 h was not evaluated separately
    assert env["c"].get(f"{API}/societies/{env['sid']}/error-analysis").status_code == 401


def test_community_comparison_matches_the_raw_data_and_the_saved_evaluation(env, raw):
    r = env["c"].get(f"{API}/societies/compare", headers=env["analyst"])
    assert r.status_code == 200
    rows = r.json()["communities"]
    assert len(rows) == 1 and rows[0]["key"] == "fox"  # the fixture imports only Fox
    row, v = rows[0], raw["soc"].dropna()
    assert row["avg_kw"] == pytest.approx(v.mean()) and row["peak_kw"] == pytest.approx(v.max()) and row["energy_kwh"] == pytest.approx(v.sum())
    assert row["load_factor"] == pytest.approx(v.mean() / v.max())
    assert row["kwh_per_sqm_year"] == pytest.approx(v.mean() * 8766 / row["floor_area_sqm"])
    ev24 = raw["ev"]["horizons"]["24"]
    best = ev24["best_overall_by_cv"]
    assert row["accuracy_24h"]["mae_kw"] == pytest.approx(ev24["test"][best]["mae"]) and row["accuracy_24h"]["model"] == best
    assert row["accuracy_24h"]["mae_pct_of_average"] == pytest.approx(100 * ev24["test"][best]["mae"] / v.mean())
    assert "source_id" not in json.dumps(r.json())  # dataset identifiers stay admin-only
    assert env["c"].get(f"{API}/societies/compare").status_code == 401
    assert env["c"].get(f"{API}/societies/{env['sid']}", headers=env["analyst"]).status_code == 200  # "compare" is not captured by the {society_id} route


# Tests that use the module-wide `env` come before the import and upload tests below: those build their own apps with make_settings(),
# which on a shared PostgreSQL database (ENERGIQ_TEST_DATABASE_URL) drops the schema and so removes the data `env` imported.

# ----------------------------------------------------------------------------- import and upload (separate apps)
def test_admin_can_import_every_bundled_society_as_a_job(tmp_path):
    index = json.loads((PROCESSED / "societies.json").read_text())["societies"]
    st = _settings(tmp_path)
    with TestClient(create_app(st)) as c:
        admin = login(c, "admin@example.com", "AdminPass-12345")
        r = c.post(f"{API}/admin/societies/import-bundled", headers=admin)
        assert r.status_code == 202
        job = c.get(f"{API}/jobs/{r.json()['id']}", headers=admin).json()
        assert job["status"] == "succeeded", job
        assert sorted(job["result"]["imported"]) == sorted(e["key"] for e in index)
        keys = [s["key"] for s in c.get(f"{API}/societies", headers=admin).json()]
        assert sorted(keys) == sorted(e["key"] for e in index)
        again = c.post(f"{API}/admin/societies/import-bundled", headers=admin)
        assert c.get(f"{API}/jobs/{again.json()['id']}", headers=admin).json()["result"]["imported"] == []  # nothing is duplicated
        sid = next(s["id"] for s in c.get(f"{API}/societies", headers=admin).json() if s["key"] == "robin")
        assert c.post(f"{API}/societies/{sid}/reports", headers=admin, json={"kind": "buildings", "format": "csv"}).status_code == 201
        assert c.delete(f"{API}/societies/{sid}", headers=admin).status_code == 204
        assert c.get(f"{API}/societies/{sid}", headers=admin).status_code == 404
        from sqlalchemy import func, select

        from backend.app.models import AnomalyEvent, Building, ConsumptionRecord, Meter, SocietyHourly, SocietyReport
        with c.app.state.db.session() as s:
            assert s.scalar(select(func.count(Building.id)).where(Building.society_id == sid)) == 0
            assert s.scalar(select(func.count(SocietyHourly.ts)).where(SocietyHourly.society_id == sid)) == 0
            assert s.scalar(select(func.count(AnomalyEvent.id)).where(AnomalyEvent.society_id == sid)) == 0
            assert s.scalar(select(func.count(Meter.id)).where(Meter.society_id == sid)) == 0
            assert s.scalar(select(func.count(SocietyReport.id)).where(SocietyReport.society_id == sid)) == 0  # stored reports go too
            assert s.scalar(select(func.count()).select_from(ConsumptionRecord).join(Meter, Meter.id == ConsumptionRecord.meter_id).where(Meter.society_id == sid)) == 0


def _upload_files(raw, n_meters=8, days=200):
    """A real slice of Fox meter data written as the wide CSV format an administrator would upload."""
    m = raw["meters"].iloc[: 24 * days, :n_meters].copy()
    m.columns = [f"M{i + 1}" for i in range(m.shape[1])]
    m.index.name = "timestamp"
    return m.reset_index().to_csv(index=False).encode(), m


def test_admin_uploads_real_meter_data_and_it_behaves_like_any_society(tmp_path, raw):
    st = make_settings(tmp_path)  # empty temporary society folders: an upload must never write into the shipped artifacts
    data, meters = _upload_files(raw)
    mapping = b"meter_id,building,kind,facility_category,floor_area_sqm\nM8,Pump house,facility,pump,\nM1,Block 1,building,,1500\n"
    with TestClient(create_app(st)) as c:
        admin = login(c, "admin@example.com", "AdminPass-12345")
        form = {"name": "Green Park Residency", "unit": "kwh", "description": "Test upload"}
        r = c.post(f"{API}/admin/societies/upload", headers=admin, data=form, files={"file": ("meters.csv", data, "text/csv"), "mapping": ("map.csv", mapping, "text/csv")})
        assert r.status_code == 202, r.text
        job = c.get(f"{API}/jobs/{r.json()['id']}", headers=admin).json()
        assert job["status"] == "succeeded", job
        res = job["result"]
        assert res["buildings"] == 7 and res["facility_meters"] == 1 and res["hours"] == 24 * 200
        sid = res["society_id"]
        s = c.get(f"{API}/societies/{sid}", headers=admin).json()
        assert s["key"] == "green-park-residency" and s["source_name"] == "Administrator upload" and s["has_model"] is False
        fac = c.get(f"{API}/societies/{sid}/facilities", headers=admin, params={"resolution": "daily"}).json()
        assert fac["available"] is True
        pump = next(x for x in fac["categories"] if x["category"] == "pump")
        assert pump["measured"] is True and len(pump["series"]) == 200
        assert next(x for x in fac["categories"] if x["category"] == "lift")["measured"] is False  # unmeasured categories stay unavailable
        total = c.get(f"{API}/societies/{sid}/consumption", headers=admin, params={"resolution": "daily"}).json()["points"]
        both = meters.dropna()
        day0 = both.loc["2016-01-01"]
        if len(day0) == 24:  # hours where every kept meter is valid in the source slice
            assert total[0]["energy_kwh"] == pytest.approx(day0.sum().sum(), abs=0.1)
        assert c.get(f"{API}/societies/{sid}/overview", headers=admin).json()["forecast"] is None  # no model yet: nothing is invented
        assert c.get(f"{API}/societies/{sid}/forecast", headers=admin).status_code == 409
        assert c.post(f"{API}/admin/societies/{sid}/train", headers=admin).status_code == 422  # 200 days is too little to evaluate
        # same name again gets its own key; nothing is overwritten
        r2 = c.post(f"{API}/admin/societies/upload", headers=admin, data=form, files={"file": ("meters.csv", data, "text/csv")})
        assert c.get(f"{API}/jobs/{r2.json()['id']}", headers=admin).json()["result"]["key"] == "green-park-residency-2"


def test_bad_uploads_are_rejected_with_clear_messages(tmp_path, raw):
    st = make_settings(tmp_path)
    data, _ = _upload_files(raw, days=30)
    with TestClient(create_app(st)) as c:
        admin = login(c, "admin@example.com", "AdminPass-12345")
        url = f"{API}/admin/societies/upload"
        form = {"name": "Bad upload"}
        assert c.post(url, headers=admin, data=form, files={"file": ("x.xlsx", data, "text/csv")}).status_code == 415
        assert c.post(url, headers=admin, data=form, files={"file": ("x.csv", b"\x00\x01\x02" * 100, "text/csv")}).status_code == 415
        assert c.post(url, headers=admin, data=form, files={"file": ("x.csv", b"", "text/csv")}).status_code == 422
        r = c.post(url, headers=admin, data=form, files={"file": ("x.csv", b"timestamp,A\n2024-01-01 00:00,1\n", "text/csv")})
        assert r.status_code == 422 and "24 rows" in r.json()["detail"]
        r = c.post(url, headers=admin, data=form, files={"file": ("x.csv", data, "text/csv"), "mapping": ("m.csv", b"meter_id,kind\nNOPE,building\n", "text/csv")})
        assert r.status_code == 422 and "not columns" in r.json()["detail"]
        r = c.post(url, headers=admin, data={"name": "Bad upload", "unit": "mwh"}, files={"file": ("x.csv", data, "text/csv")})
        assert r.status_code == 422
        zeros = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=24 * 30, freq="h").strftime("%Y-%m-%d %H:%M"), "A": 0.0, "B": 0.0})
        r = c.post(url, headers=admin, data=form, files={"file": ("x.csv", zeros.to_csv(index=False).encode(), "text/csv")})
        job = c.get(f"{API}/jobs/{r.json()['id']}", headers=admin).json()  # cleaning runs in the job: all-zero meters are not data
        assert job["status"] == "failed" and "validity rule" in job["error"]
        assert c.get(f"{API}/societies", headers=admin).json() == []  # nothing was stored by any of the failures
