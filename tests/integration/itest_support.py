"""Helpers shared by the API integration tests (settings, sign-up and login, synthetic CSV, upload).

They live in this uniquely named module instead of conftest.py: several folders have a conftest.py, pytest registers all of
them under the same module name "conftest", and ``from conftest import ...`` therefore picked a different folder's file
depending on the order in which pytest collected the tests.

By default every test gets its own SQLite file. Set ENERGIQ_TEST_DATABASE_URL (for example
postgresql+psycopg://user:pw@127.0.0.1:5433/energiq_test) to run the same tests against that database instead;
the schema is dropped and recreated before each test, so use a throw-away database.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.config import Settings

REPO = Path(__file__).resolve().parents[2]
PASSWORD = "Correct-Horse-42"
PG_URL = os.environ.get("ENERGIQ_TEST_DATABASE_URL", "")


def reset_database(url: str) -> None:
    """Drop every table (including Alembic's bookkeeping) so each test starts from an empty schema."""
    from sqlalchemy import create_engine, text

    from backend.app import models  # noqa: F401
    from backend.app.db import Base

    eng = create_engine(url)
    Base.metadata.drop_all(eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    eng.dispose()


def make_settings(tmp: Path, **over) -> Settings:
    base = dict(env="test", database_url=f"sqlite:///{tmp / 'test.db'}", jobs_sync=True, upload_dir=tmp / "uploads",
                models_dir=tmp / "models", reports_dir=REPO / "artifacts" / "reports", secret_key="test-secret-" + "x" * 40,
                sample_dataset=REPO / "data" / "sample" / "uci_hourly_2009_sample.csv", admin_email="admin@example.com",
                admin_password="AdminPass-12345", max_upload_mb=5,
                # Society training and import write into these folders. They default to EMPTY temporary folders so that no test can
                # ever overwrite the shipped trained bundles in artifacts/society (tests that need the real data pass them explicitly).
                society_dir=tmp / "society_artifacts", society_data_dir=tmp / "society_data")
    base.update(over)
    if PG_URL and "database_url" not in over:
        base["database_url"] = PG_URL
        reset_database(PG_URL)
    return Settings(**base)


def signup(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test"})
    assert r.status_code == 201, r.text
    return login(client, email, password)


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def synthetic_csv(days: int = 60, start: str = "2022-01-03", seed: int = 0, nan_frac: float = 0.01,
                  value_name: str = "kw", ts_name: str = "time") -> str:
    idx = pd.date_range(start, periods=24 * days, freq="h")
    rng = np.random.default_rng(seed)
    h = idx.hour.to_numpy()
    v = 0.4 + 1.1 * np.exp(-((h - 19) ** 2) / 8) + 0.25 * (idx.day_of_week.to_numpy() >= 5) + rng.normal(0, 0.06, len(idx))
    s = pd.Series(np.clip(v, 0.05, None), index=idx)
    s[rng.random(len(s)) < nan_frac] = np.nan
    return pd.DataFrame({ts_name: idx.strftime("%Y-%m-%d %H:%M:%S"), value_name: s.round(4).to_numpy()}).to_csv(index=False)


def upload(client: TestClient, headers: dict, text: str, name: str = "My meter", filename: str = "meter.csv", **form):
    data = {"name": name, "value_column": "kw", "timestamp_column": "time", "unit": "kW", **form}
    return client.post("/api/v1/datasets", headers=headers, data=data, files={"file": (filename, text.encode(), "text/csv")})
