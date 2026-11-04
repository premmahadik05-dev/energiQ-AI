"""Train -> forecast -> explain -> anomalies -> optimisation -> monitoring, through the HTTP API on the bundled UCI sample."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_settings, signup
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services import ml as ml_svc

API = "/api/v1"
FAST_XGB = {"n_estimators": 40, "max_depth": 3, "learning_rate": 0.15, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ml")
    original = ml_svc.XGB_PARAMS
    ml_svc.XGB_PARAMS = FAST_XGB  # wiring test: small trees keep the suite fast; accuracy is covered by the benchmark
    app = create_app(make_settings(tmp))
    with TestClient(app) as c:
        h = signup(c, "ml-user@example.com")
        r = c.post(f"{API}/datasets/sample", headers=h)
        assert r.status_code == 202, r.text
        did = r.json()["dataset"]["id"]
        assert c.get(f"{API}/jobs/{r.json()['job']['id']}", headers=h).json()["status"] == "succeeded"
        t = c.post(f"{API}/datasets/{did}/train", headers=h)
        assert t.status_code == 202, t.text
        job = c.get(f"{API}/jobs/{t.json()['id']}", headers=h).json()
        assert job["status"] == "succeeded", job
        yield {"c": c, "h": h, "did": did, "mid": job["result"]["model_id"], "app": app, "tmp": tmp}
    ml_svc.XGB_PARAMS = original


def test_sample_dataset_matches_known_values(env):
    ds = env["c"].get(f"{API}/datasets/{env['did']}", headers=env["h"]).json()
    assert ds["hours"] == 8760 and ds["valid_hours"] == 8687  # from scripts/make_sample.py
    assert ds["start_ts"].startswith("2009-01-01") and ds["end_ts"].startswith("2009-12-31T23")


def test_trained_model_metadata_and_artifacts(env):
    c, h = env["c"], env["h"]
    models = c.get(f"{API}/models?dataset_id={env['did']}", headers=h).json()
    assert len(models) == 1 and models[0]["is_active"] and models[0]["id"] == env["mid"]
    m = models[0]
    ev = m["evaluation"]
    assert set(ev["horizons"]) == {"1", "6", "24"} and ev["caveat"] is None
    for hz in ev["horizons"].values():
        assert hz["rows_scored"] > 24 and hz["residual_q10_kw"] < hz["residual_q90_kw"]
        assert {"xgboost", "naive", "seasonal_naive_24", "seasonal_naive_168"} <= set(hz["metrics"])
    assert ev["horizons"]["1"]["metrics"]["xgboost"]["mae"] < ev["horizons"]["1"]["metrics"]["naive"]["mae"]
    assert "chronological" in ev["protocol"].lower() and ev["holdout_start"] > "2009-08"
    root = env["tmp"] / "models"
    dirs = list(root.glob("user_*/xgboost_h*"))
    assert len(dirs) == 24 and all((d / "metadata.json").is_file() for d in dirs)


def test_forecast_curve(env):
    c, h = env["c"], env["h"]
    r = c.post(f"{API}/forecasts", headers=h, json={"dataset_id": env["did"]})
    assert r.status_code == 201, r.text
    fc = r.json()
    pts = fc["points"]
    assert len(pts) == 24 and [p["horizon"] for p in pts] == list(range(1, 25))
    ts = pd.to_datetime([p["ts"] for p in pts])
    assert ts[0] == pd.Timestamp(fc["origin"]) + pd.Timedelta(hours=1) and (np.diff(ts) == pd.Timedelta(hours=1)).all()
    assert all(0 <= p["lower_kw"] <= p["kw"] + 1e-9 or p["lower_kw"] == 0 for p in pts) and all(p["upper_kw"] >= p["kw"] - 1e-9 for p in pts)
    assert fc["origin"].startswith("2009-12-31T23")
    csv = c.get(f"{API}/forecasts/{fc['id']}/export.csv", headers=h)
    assert csv.status_code == 200 and csv.text.splitlines()[0] == "origin,target_time,horizon_h,forecast_kw,lower_kw,upper_kw" and len(csv.text.splitlines()) == 25
    assert c.get(f"{API}/forecasts", headers=h).json()[0]["id"] == fc["id"]
    assert c.post(f"{API}/forecasts", headers=h, json={"dataset_id": env["did"], "origin": "2031-01-01T00:00:00"}).status_code == 422
    assert c.post(f"{API}/forecasts", headers=h, json={"dataset_id": env["did"], "model_id": "nope"}).status_code == 404


def test_forecast_uses_only_data_up_to_the_origin(env):
    """Leakage canary at the service level: rewriting every reading after the origin must not move the forecast."""
    from backend.app.models import ModelVersion
    from backend.app.services.data import load_series

    origin = pd.Timestamp("2009-11-15 12:00")
    with env["app"].state.db.session() as s:
        mv = s.get(ModelVersion, env["mid"])
        series = load_series(s, env["did"])
    tampered = series.copy()
    tampered[tampered.index > origin] = 99.0
    a = ml_svc.forecast_curve(env["app"].state.settings, mv, series, origin)
    b = ml_svc.forecast_curve(env["app"].state.settings, mv, tampered, origin)
    assert [p["kw"] for p in a["points"]] == [p["kw"] for p in b["points"]]
    again = env["c"].post(f"{API}/forecasts", headers=env["h"], json={"dataset_id": env["did"], "origin": str(origin)}).json()
    assert [p["kw"] for p in again["points"]] == [p["kw"] for p in a["points"]]  # and the API path is deterministic


def test_explanations(env):
    c, h = env["c"], env["h"]
    r = c.post(f"{API}/explain/local", headers=h, json={"model_id": env["mid"], "horizon": 6, "origin": "2009-11-15T12:00:00"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert abs(e["base_value_kw"] + sum(e["grouped_kw"].values()) - e["prediction_kw"]) < 2e-3
    assert e["target_time"].startswith("2009-11-15 18") and len(e["drivers"]) == 6 and "kW" in e["narrative"]
    assert c.post(f"{API}/explain/local", headers=h, json={"model_id": env["mid"], "horizon": 30}).status_code == 422
    g = c.get(f"{API}/explain/global?model_id={env['mid']}", headers=h).json()
    assert set(g["horizons"]) == {"1", "6", "24"} and g["horizons"]["1"]["top_features"][0]["feature"]


def test_monitoring_with_realised_errors(env):
    c, h = env["c"], env["h"]
    c.post(f"{API}/forecasts", headers=h, json={"dataset_id": env["did"], "origin": "2009-12-01T00:00:00"})
    m = c.get(f"{API}/models/{env['mid']}/monitoring", headers=h).json()
    assert m["drift"]["status"] in ("stable", "moderate shift", "significant shift") and m["drift"]["new_data_since_training"] is False
    rp = m["realized_performance"]
    assert rp["points_scored"] > 0 and rp["realized_mae_kw"] > 0 and rp["ratio_realized_to_holdout"] > 0
    assert "retrain_recommended" in m


def test_anomaly_detection_flow(env):
    c, h = env["c"], env["h"]
    r = c.post(f"{API}/datasets/{env['did']}/anomalies/run", headers=h, json={"sensitivity": "medium"})
    assert r.status_code == 202, r.text
    job = c.get(f"{API}/jobs/{r.json()['id']}", headers=h).json()
    assert job["status"] == "succeeded" and job["result"]["events"] > 0
    out = c.get(f"{API}/anomalies?dataset_id={env['did']}&limit=10", headers=h).json()
    assert out["total"] >= len(out["items"]) > 0
    levels = [a["severity_level"] for a in out["items"]]
    assert levels == sorted(levels, reverse=True)
    first = out["items"][0]
    assert first["explanation"] and first["acknowledged"] is False
    ack = c.patch(f"{API}/anomalies/{first['id']}", headers=h, json={"acknowledged": True}).json()
    assert ack["acknowledged"] and ack["acknowledged_at"]
    open_only = c.get(f"{API}/anomalies?dataset_id={env['did']}&acknowledged=false&limit=500", headers=h).json()
    assert first["id"] not in [a["id"] for a in open_only["items"]]
    s = c.get(f"{API}/anomalies/summary?dataset_id={env['did']}", headers=h).json()
    assert s["summary"]["events"] == out["total"] and "no ground-truth" in s["note"].lower()
    # a new run replaces the old one; high sensitivity flags at least as many events as low
    lo = c.post(f"{API}/datasets/{env['did']}/anomalies/run", headers=h, json={"sensitivity": "low"}).json()
    n_low = c.get(f"{API}/jobs/{lo['id']}", headers=h).json()["result"]["events"]
    hi = c.post(f"{API}/datasets/{env['did']}/anomalies/run", headers=h, json={"sensitivity": "high"}).json()
    n_high = c.get(f"{API}/jobs/{hi['id']}", headers=h).json()["result"]["events"]
    assert n_high >= n_low
    assert c.get(f"{API}/anomalies?dataset_id={env['did']}&limit=500", headers=h).json()["total"] == n_high
    assert c.post(f"{API}/datasets/{env['did']}/anomalies/run", headers=h, json={"sensitivity": "extreme"}).status_code == 422


def test_tariffs_cost_recommendations_schedule(env):
    c, h, did = env["c"], env["h"], env["did"]
    tariffs = c.get(f"{API}/tariffs", headers=h).json()
    assert tariffs[0]["id"] == "demo" and tariffs[0]["is_demo"] is True
    flat = {"name": "Flat 0.25", "currency": "EUR", "weekday_rates": [0.25] * 24, "weekend_rates": [0.25] * 24, "daily_fixed_charge": 0.1}
    created = c.post(f"{API}/tariffs", headers=h, json=flat)
    assert created.status_code == 201 and c.post(f"{API}/tariffs", headers=h, json=flat).status_code == 409
    for bad in ({**flat, "name": "b1", "weekday_rates": [0.2] * 23}, {**flat, "name": "b2", "weekend_rates": [-1] + [0.2] * 23},
                {**flat, "name": "b3", "currency": ""}):
        assert c.post(f"{API}/tariffs", headers=h, json=bad).status_code == 422
    cost = c.post(f"{API}/optimize/cost", headers=h, json={"dataset_id": did, "tariff_id": created.json()["id"]}).json()
    assert len(cost["monthly"]) == 12 and cost["total"]["energy_kwh"] > 1000
    assert cost["total"]["energy_cost"] == pytest.approx(cost["total"]["energy_kwh"] * 0.25, rel=1e-6)
    assert cost["total"]["total_cost"] == pytest.approx(cost["total"]["energy_cost"] + 0.1 * cost["total"]["valid_hours"] / 24, rel=1e-6)
    demo_cost = c.post(f"{API}/optimize/cost", headers=h, json={"dataset_id": did}).json()
    assert demo_cost["total"]["is_demo_tariff"] is True
    rec = c.post(f"{API}/optimize/recommendations", headers=h, json={"dataset_id": did, "tariff_id": "demo"}).json()
    ids = {r["id"] for r in rec["recommendations"]}
    assert ids and ids <= {"shift_peak_load", "reduce_baseload", "forecast_peak", "review_anomalies", "data_gaps"}
    assert all(any("scenario" in cv.lower() or "model forecast" in cv.lower() or "anomaly" in cv.lower() or "baseload" in cv.lower() or "flexible" in cv.lower()
                   for cv in r["caveats"]) or r["id"] == "data_gaps" for r in rec["recommendations"])
    flat_rec = c.post(f"{API}/optimize/recommendations", headers=h, json={"dataset_id": did, "tariff_id": created.json()["id"]}).json()
    assert "shift_peak_load" not in {r["id"] for r in flat_rec["recommendations"]}
    sch = c.post(f"{API}/optimize/schedule", headers=h, json={"dataset_id": did, "duration_h": 2, "power_kw": 1.5}).json()
    assert sch["saving_vs_first_hour"] >= 0 and sch["energy_kwh"] == 3.0 and sch["is_demo_tariff"]
    assert c.post(f"{API}/optimize/schedule", headers=h, json={"duration_h": 2, "power_kw": 0}).status_code == 422
    assert c.delete(f"{API}/tariffs/{created.json()['id']}", headers=h).status_code == 204
    assert c.post(f"{API}/optimize/cost", headers=h, json={"dataset_id": did, "tariff_id": created.json()["id"]}).status_code == 404


def test_append_extends_dataset_and_retrain_switches_active_model(env):
    c, h, did = env["c"], env["h"], env["did"]
    idx = pd.date_range("2010-01-01", periods=72, freq="h")
    csv = pd.DataFrame({"timestamp": idx.strftime("%Y-%m-%d %H:%M:%S"), "power_kw": np.linspace(0.5, 2.0, 72)}).to_csv(index=False)
    before = c.get(f"{API}/datasets/{did}", headers=h).json()
    r = c.post(f"{API}/datasets/{did}/append", headers=h, files={"file": ("new.csv", csv.encode(), "text/csv")})
    assert r.status_code == 202, r.text
    assert c.get(f"{API}/jobs/{r.json()['job']['id']}", headers=h).json()["status"] == "succeeded"
    after = c.get(f"{API}/datasets/{did}", headers=h).json()
    assert after["hours"] == before["hours"] + 72 and after["end_ts"].startswith("2010-01-03T23")
    assert len(after["report"]["appends"]) == 1
    m = c.get(f"{API}/models/{env['mid']}/monitoring", headers=h).json()
    assert m["drift"]["new_data_since_training"] is True
    t = c.post(f"{API}/datasets/{did}/train", headers=h).json()
    new_id = c.get(f"{API}/jobs/{t['id']}", headers=h).json()["result"]["model_id"]
    active = [x["id"] for x in c.get(f"{API}/models?dataset_id={did}", headers=h).json() if x["is_active"]]
    assert active == [new_id] != [env["mid"]]
    assert c.post(f"{API}/models/{env['mid']}/activate", headers=h).json()["is_active"] is True
    active = [x["id"] for x in c.get(f"{API}/models?dataset_id={did}", headers=h).json() if x["is_active"]]
    assert active == [env["mid"]]


def test_benchmark_reports_and_figure_whitelist(env):
    c, h = env["c"], env["h"]
    b = c.get(f"{API}/benchmark", headers=h).json()
    assert b["evaluation"]["horizons"]["1"]["metrics"]["xgboost"]["mae"] > 0
    assert "evaluation" in b["figures"] and "fig_mae_by_horizon.png" in b["figures"]["evaluation"]
    ok = c.get(f"{API}/benchmark/figures/evaluation/fig_mae_by_horizon.png", headers=h)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png" and ok.content[:4] == b"\x89PNG"
    for bad in ("evaluation/..%2F..%2Fdataset_profile.json", "evaluation/evaluation.json", "secrets/fig_x.png", "evaluation/fig_..png"):
        assert c.get(f"{API}/benchmark/figures/{bad}", headers=h).status_code == 404


def test_delete_dataset_removes_everything(env):
    c, h, did = env["c"], env["h"], env["did"]
    assert c.delete(f"{API}/datasets/{did}", headers=h).status_code == 204
    assert c.get(f"{API}/datasets/{did}", headers=h).status_code == 404
    assert c.get(f"{API}/models", headers=h).json() == [] and c.get(f"{API}/forecasts", headers=h).json() == []
    assert list((env["tmp"] / "models").glob("user_*/xgboost_h*")) == []
    assert list((env["tmp"] / "uploads").rglob("dataset_*.csv")) == []


def test_append_replaces_overlapping_values_but_never_erases_readings_with_gaps(tmp_path):
    """Regression: the appended file is expanded to a regular grid; its gaps must not overwrite stored valid readings."""
    from conftest import upload

    from backend.app.services.data import load_series

    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        h = signup(c, "append@example.com")
        idx = pd.date_range("2022-01-03", periods=240, freq="h")                    # stored: hours 0..239, all 1.0
        base = pd.DataFrame({"time": idx.strftime("%Y-%m-%d %H:%M:%S"), "kw": 1.0})
        did = upload(c, h, base.to_csv(index=False)).json()["dataset"]["id"]
        # appended file covers hours 200..259 with value 5.0, except: hours 210-219 are absent rows, hours 220-224 are blank
        part = pd.DataFrame({"time": pd.date_range(idx[200], periods=60, freq="h").strftime("%Y-%m-%d %H:%M:%S"), "kw": 5.0})
        part = part.drop(index=range(10, 20)).reset_index(drop=True)                 # rows 0-9 -> hours 200-209, rows 10.. -> hours 220..259
        part.loc[(part.index >= 10) & (part.index < 15), "kw"] = np.nan              # hours 220-224 blank
        r = c.post(f"{API}/datasets/{did}/append", headers=h, files={"file": ("n.csv", part.to_csv(index=False).encode(), "text/csv")})
        assert r.status_code == 202 and c.get(f"{API}/jobs/{r.json()['job']['id']}", headers=h).json()["status"] == "succeeded"
        with app.state.db.session() as s:
            series = load_series(s, did)
        at = lambda i: series.loc[idx[0] + pd.Timedelta(hours=i)]  # noqa: E731
        assert at(199) == 1.0                                                          # before the overlap: untouched
        assert all(at(i) == 5.0 for i in range(200, 210))                              # overlap with a new value: replaced
        assert all(at(i) == 1.0 for i in range(210, 220)), "hours absent from the new file must keep their old reading"
        assert all(at(i) == 1.0 for i in range(220, 225)), "blank values in the new file must not erase old readings"
        assert all(at(i) == 5.0 for i in range(225, 260))                              # overlap tail + extension beyond the old end
        assert series.index.is_unique and series.notna().sum() == 260


def test_retraining_on_identical_data_reproduces_metrics_and_forecasts(tmp_path, monkeypatch):
    """NFR-04: fixed seeds + stored data hash. Training twice on the same series gives the same hold-out metrics and forecasts."""
    from backend.app.models import ModelVersion

    monkeypatch.setattr(ml_svc, "XGB_PARAMS", FAST_XGB)
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        h = signup(c, "repro@example.com")
        did = c.post(f"{API}/datasets/sample", headers=h).json()["dataset"]["id"]
        ids = []
        for _ in range(2):
            job = c.get(f"{API}/jobs/{c.post(f'{API}/datasets/{did}/train', headers=h).json()['id']}", headers=h).json()
            assert job["status"] == "succeeded", job
            ids.append(job["result"]["model_id"])
        assert ids[0] != ids[1]
        by_id = {m["id"]: m for m in c.get(f"{API}/models?dataset_id={did}", headers=h).json()}
        a_m, b_m = by_id[ids[0]], by_id[ids[1]]
        with app.state.db.session() as s:
            h1, h2 = (s.get(ModelVersion, i).data_hash for i in ids)
        assert h1 and h1 == h2                                  # same series -> same fingerprint
        for hz in ("1", "6", "24"):
            a, b = a_m["evaluation"]["horizons"][hz], b_m["evaluation"]["horizons"][hz]
            assert a["metrics"] == b["metrics"] and a["residual_q10_kw"] == b["residual_q10_kw"] and a["residual_q90_kw"] == b["residual_q90_kw"]
        origin = "2009-11-15T12:00:00"
        f1, f2 = (c.post(f"{API}/forecasts", headers=h, json={"dataset_id": did, "model_id": m, "origin": origin}).json() for m in ids)
        assert [p["kw"] for p in f1["points"]] == [p["kw"] for p in f2["points"]]
