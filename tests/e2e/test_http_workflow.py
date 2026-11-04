"""The whole product workflow over real HTTP against a real server process (no TestClient, no mocks)."""
from __future__ import annotations

import math
import time

import httpx

PASSWORD = "Correct-Horse-42"


def wait_job(c: httpx.Client, headers: dict, job_id: int, timeout: float = 240) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_full_workflow_over_http(server):
    with httpx.Client(base_url=server["base"], timeout=120) as c:
        assert c.get("/health/live").json() == {"status": "ok"}
        # --- account
        assert c.post("/api/v1/auth/register", json={"email": "e2e@example.com", "password": PASSWORD, "full_name": "E2E"}).status_code == 201
        token = c.post("/api/v1/auth/login", json={"email": "e2e@example.com", "password": PASSWORD}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert c.get("/api/v1/auth/me", headers=h).json()["role"] == "analyst"
        # --- data
        r = c.post("/api/v1/datasets/sample", headers=h)
        assert r.status_code == 202
        did = r.json()["dataset"]["id"]
        assert wait_job(c, h, r.json()["job"]["id"])["status"] == "succeeded"
        ds = c.get(f"/api/v1/datasets/{did}", headers=h).json()
        assert ds["status"] == "ready" and ds["hours"] == 8760 and 0 < ds["valid_hours"] <= ds["hours"]
        rd = c.get(f"/api/v1/datasets/{did}/readings", headers=h).json()
        assert rd, "readings must be returned"
        # --- train (real XGBoost, real parameters)
        r = c.post(f"/api/v1/datasets/{did}/train", headers=h, json={"activate": True})
        assert r.status_code == 202
        job = wait_job(c, h, r.json()["id"])
        assert job["status"] == "succeeded", job
        mae = job["result"]["holdout_mae_kw"]
        assert set(mae) == {"1", "6", "24"} and all(math.isfinite(v) and 0 < v < 3 for v in mae.values())
        models = c.get("/api/v1/models", headers=h, params={"dataset_id": did}).json()
        assert len(models) == 1 and models[0]["is_active"] is True
        mid = models[0]["id"]
        # --- forecast: 24 ordered points with a range that contains the point value for most hours
        fc = c.post("/api/v1/forecasts", headers=h, json={"dataset_id": did})
        assert fc.status_code == 201
        pts = fc.json()["points"]
        assert [p["horizon"] for p in pts] == list(range(1, 25))
        assert all(p["lower_kw"] <= p["upper_kw"] and p["kw"] >= 0 for p in pts)
        assert sum(p["lower_kw"] <= p["kw"] <= p["upper_kw"] for p in pts) >= 20
        csv = c.get(f"/api/v1/forecasts/{fc.json()['id']}/export.csv", headers=h)
        assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("origin,target_time,horizon_h,forecast_kw")
        assert len(csv.text.strip().splitlines()) == 25
        # --- explanation: additivity is exact (base + contributions == prediction)
        ex = c.post("/api/v1/explain/local", headers=h, json={"model_id": mid, "horizon": 6})
        assert ex.status_code == 200
        e = ex.json()
        assert e["additivity_error_kw"] < 1e-4, "SHAP contributions must add up to the model output"
        assert abs(e["base_value_kw"] + sum(e["grouped_kw"].values()) - e["prediction_kw"]) < 1e-4
        assert e["drivers"] and e["narrative"]
        # --- anomalies
        r = c.post(f"/api/v1/datasets/{did}/anomalies/run", headers=h, json={"sensitivity": "medium"})
        assert wait_job(c, h, r.json()["id"])["status"] == "succeeded"
        an = c.get("/api/v1/anomalies", headers=h, params={"dataset_id": did}).json()
        items = an["items"] if isinstance(an, dict) else an
        assert items and all({"start_ts", "severity", "explanation"} <= set(a) for a in items)
        # --- optimisation
        cost = c.post("/api/v1/optimize/cost", headers=h, json={"dataset_id": did, "tariff_id": "demo"}).json()
        assert cost["total"]["is_demo_tariff"] is True and cost["total"]["energy_kwh"] > 0
        rec = c.post("/api/v1/optimize/recommendations", headers=h, json={"dataset_id": did, "tariff_id": "demo"}).json()
        assert all(r_["priority"] in ("high", "medium", "low") for r_ in rec["recommendations"])
        sch = c.post("/api/v1/optimize/schedule", headers=h, json={"dataset_id": did, "tariff_id": "demo", "duration_h": 3, "power_kw": 2.0}).json()
        assert sch["saving_vs_first_hour"] >= 0 and sch["is_demo_tariff"] is True
        # --- monitoring, report, metrics
        mon = c.get(f"/api/v1/models/{mid}/monitoring", headers=h).json()
        assert "drift" in mon and "realized_performance" in mon
        rep = c.get(f"/api/v1/datasets/{did}/report", headers=h)
        assert rep.status_code == 200 and "DEMO tariff" in rep.text
        metrics = c.get("/metrics").text
        assert 'energiq_http_requests_total{method="POST",route="/api/v1/forecasts",status="201"}' in metrics
        # --- deletion cleans up
        assert c.delete(f"/api/v1/datasets/{did}", headers=h).status_code == 204
        assert c.get(f"/api/v1/datasets/{did}", headers=h).status_code == 404
        assert c.get(f"/api/v1/models/{mid}", headers=h).status_code == 404


def test_unauthenticated_and_foreign_access_over_http(server):
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        assert c.get("/api/v1/datasets").status_code == 401
        t1 = c.post("/api/v1/auth/register", json={"email": "own1@example.com", "password": PASSWORD}).status_code
        assert t1 == 201
        h1 = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"email": "own1@example.com", "password": PASSWORD}).json()["access_token"]}
        c.post("/api/v1/auth/register", json={"email": "own2@example.com", "password": PASSWORD})
        h2 = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"email": "own2@example.com", "password": PASSWORD}).json()["access_token"]}
        did = c.post("/api/v1/datasets/sample", headers=h1).json()["dataset"]["id"]
        wait_job(c, h1, c.get("/api/v1/jobs", headers=h1).json()[0]["id"])
        assert c.get(f"/api/v1/datasets/{did}", headers=h2).status_code == 404
        assert c.delete(f"/api/v1/datasets/{did}", headers=h2).status_code == 404
        assert c.get(f"/api/v1/datasets/{did}", headers=h1).status_code == 200
