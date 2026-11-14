"""End-to-end check of the administrator workflow through the real API: upload a society's meter CSV (+ mapping), train it, read the forecast.

The uploaded file is built from REAL BDG2 data: six Peacock residence-hall meters as the buildings, plus a "pump" facility column.
That one column is a copy of a real meter scaled by 0.05; it exists only to exercise the facility-mapping path and is not a measurement.
The script prints what the API returned. It takes about 3 to 6 minutes because the training job runs the full evaluation protocol.

    python scripts/verify_upload_train.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from fastapi.testclient import TestClient  # noqa: E402
from itest_support import login, make_settings  # noqa: E402

from backend.app.main import create_app  # noqa: E402

API = "/api/v1"
MAPPING = "meter_id,building,kind,facility_category,floor_area_sqm\nPUMP_1,Water pump,facility,pump,\n"


def build_upload() -> bytes:
    m = pd.read_csv(REPO / "data/society/processed/peacock/meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    wide = m[list(m.columns[:6])].copy()
    wide["PUMP_1"] = m[m.columns[-1]] * 0.05  # exercises the facility mapping only; not a measurement
    buf = io.StringIO()
    wide.to_csv(buf, index_label="timestamp")
    return buf.getvalue().encode()


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="verify_upload_"))
    settings = make_settings(tmp, society_dir=tmp / "art", society_data_dir=REPO / "data/society/processed")
    t0 = time.time()
    with TestClient(create_app(settings)) as c:
        admin = login(c, "admin@example.com", "AdminPass-12345")
        files = {"file": ("meters.csv", build_upload(), "text/csv"), "mapping": ("map.csv", MAPPING.encode(), "text/csv")}
        r = c.post(f"{API}/admin/societies/upload", headers=admin, data={"name": "Green Park Residency", "unit": "kwh", "description": "check"}, files=files)
        job = c.get(f"{API}/jobs/{r.json()['id']}", headers=admin).json()
        print("upload:", r.status_code, job["status"], job.get("result"))
        soc = c.get(f"{API}/societies", headers=admin).json()
        sid = soc[0]["id"]
        print("society:", [(s["key"], s["buildings"], s["valid_hours"], s["has_model"]) for s in soc])
        cats = c.get(f"{API}/societies/{sid}/facilities", headers=admin).json()["categories"]
        print("facilities measured:", [(x["category"], x["measured"]) for x in cats])
        print("forecast before training (expect 409):", c.get(f"{API}/societies/{sid}/forecast", headers=admin).status_code)
        r = c.post(f"{API}/admin/societies/{sid}/train", headers=admin)
        job = c.get(f"{API}/jobs/{r.json()['id']}", headers=admin).json()
        print("train:", r.status_code, job["status"], job.get("result"), f"{time.time() - t0:.0f}s since start")
        d = c.get(f"{API}/societies/{sid}", headers=admin).json()
        print("has_model:", d["has_model"], "forecast_ready:", d["forecast_ready"], "trained_through:", d["trained_through"])
        f = c.get(f"{API}/societies/{sid}/forecast", headers=admin)
        print("forecast:", f.status_code, f.json().get("summary") if f.status_code == 200 else f.text[:200])
        m = c.get(f"{API}/societies/{sid}/models", headers=admin)
        horizons = m.json().get("horizons") or {}
        print("selected model per horizon:", [(h, v.get("best_overall_by_cv")) for h, v in horizons.items()])
        a = c.get(f"{API}/societies/{sid}/anomalies", headers=admin, params={"limit": 1}).json()
        print("anomaly events stored:", a["summary"]["total"])


if __name__ == "__main__":
    main()
