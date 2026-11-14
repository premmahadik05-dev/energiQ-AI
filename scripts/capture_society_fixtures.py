"""Capture REAL society API responses (Fox community, BDG2 data, trained models) as frontend test fixtures.

Runs the real FastAPI app on a throw-away database, imports the processed Fox community and records the response
bodies the dashboard pages consume. Nothing is written by hand and nothing is trimmed: short date ranges are
requested instead so the files stay small.

    python scripts/capture_society_fixtures.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from fastapi.testclient import TestClient  # noqa: E402
from itest_support import login, make_settings, signup  # noqa: E402

from backend.app.main import create_app  # noqa: E402
from backend.app.services.society_import import import_processed  # noqa: E402

API = "/api/v1"
OUT = REPO / "frontend" / "src" / "test" / "fixtures" / "society"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="soc_fx_"))
    st = make_settings(tmp, society_dir=REPO / "artifacts" / "society", society_data_dir=REPO / "data" / "society" / "processed")
    app = create_app(st)
    with TestClient(app) as c:
        with app.state.db.session() as s:
            import_processed(s, "fox", st.society_data_dir, st.society_dir, log_fn=lambda *a: None)
        admin = login(c, "admin@example.com", "AdminPass-12345")
        user = signup(c, "analyst@example.com")
        sid = c.get(f"{API}/societies", headers=user).json()[0]["id"]
        base = f"{API}/societies/{sid}"

        def save(name: str, resp, headers_note: str = "") -> object:
            assert resp.status_code in (200, 201, 202), (name, resp.status_code, resp.text[:300])
            body = resp.json()
            (OUT / f"{name}.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
            return body

        lst = save("societies", c.get(f"{API}/societies", headers=user))
        detail_user = save("detail_user", c.get(base, headers=user))
        save("detail_admin", c.get(base, headers=admin))
        save("overview", c.get(f"{base}/overview", headers=user))
        end = detail_user["end"]
        # a short window keeps the files small while staying real data
        save("consumption_daily", c.get(f"{base}/consumption", headers=user, params={"resolution": "daily", "start": "2017-11-01T00:00:00", "end": end}))
        save("consumption_hourly", c.get(f"{base}/consumption", headers=user, params={"resolution": "hourly", "start": "2017-12-25T00:00:00", "end": end}))
        b = save("buildings", c.get(f"{base}/buildings", headers=user, params={"start": "2017-10-01T00:00:00", "end": end}))
        save("buildings_monthly", c.get(f"{base}/buildings-monthly", headers=user))
        bid = b["buildings"][0]["id"]
        save("building_consumption", c.get(f"{base}/buildings/{bid}/consumption", headers=user, params={"resolution": "daily", "start": "2017-12-01T00:00:00", "end": end}))
        save("facilities", c.get(f"{base}/facilities", headers=user, params={"start": "2017-10-01T00:00:00", "end": end}))
        save("peaks", c.get(f"{base}/peaks", headers=user, params={"start": "2017-10-01T00:00:00", "end": end}))
        save("models", c.get(f"{base}/models", headers=user))
        save("forecast", c.get(f"{base}/forecast", headers=user))
        save("backtest", c.get(f"{base}/backtest", headers=user, params={"horizon": 24, "start": "2017-12-20T00:00:00", "end": end}))
        save("explain_global", c.get(f"{base}/explain/global", headers=user))
        save("explain_local", c.post(f"{base}/explain/local", headers=user, json={"horizon": 24}))
        save("anomalies", c.get(f"{base}/anomalies", headers=user, params={"min_severity": 2, "limit": 15}))
        save("cost", c.post(f"{base}/cost", headers=user, json={"tariff_id": "demo", "start": "2017-12-01T00:00:00", "end": end}))
        save("recommendations", c.post(f"{base}/recommendations", headers=user, json={"tariff_id": "demo"}))
        rep = save("report_created", c.post(f"{base}/reports", headers=user, json={"kind": "consumption", "format": "csv", "resolution": "daily", "start": "2017-12-01T00:00:00", "end": end}))
        save("reports", c.get(f"{base}/reports", headers=user))
        save("meters", c.get(f"{base}/meters", headers=admin))
        save("tariffs", c.get(f"{API}/tariffs", headers=user))
        save("error_analysis", c.get(f"{base}/error-analysis", headers=user, params={"horizon": 24}))
        # the comparison needs more than one community: add Rat only now, so every fixture above stays a Fox-only capture
        with app.state.db.session() as s:
            import_processed(s, "rat", st.society_data_dir, st.society_dir, log_fn=lambda *a: None)
        save("compare", c.get(f"{API}/societies/compare", headers=user))
        print(f"{len(lst)} society, report {rep['id']}; wrote {len(list(OUT.glob('*.json')))} fixtures to {OUT}")


if __name__ == "__main__":
    main()
