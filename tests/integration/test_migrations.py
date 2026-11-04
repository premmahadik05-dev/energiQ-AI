"""The Alembic migration must build exactly the schema the ORM models describe, and be reversible."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from conftest import make_settings
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from backend.app.db import Base
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def _cfg(url: str, monkeypatch) -> Config:
    monkeypatch.setenv("ENERGIQ_DATABASE_URL", url)
    return Config(str(ROOT / "backend" / "alembic.ini"))


def test_upgrade_matches_models_and_downgrade_is_clean(tmp_path, monkeypatch):
    db_file = tmp_path / "mig.db"
    url = f"sqlite:///{db_file.as_posix()}"
    cfg = _cfg(url, monkeypatch)
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    tables = set(inspect(eng).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"models and migration disagree: {diff}"
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
    eng.dispose()


def test_prod_app_boots_on_migrated_database_and_serves_requests(tmp_path, monkeypatch):
    db_file = tmp_path / "prod.db"
    url = f"sqlite:///{db_file.as_posix()}"
    command.upgrade(_cfg(url, monkeypatch), "head")
    s = make_settings(tmp_path, env="prod", database_url=url, secret_key="p" * 48, cors_origins=["https://app.example.org"],
                      admin_email="", admin_password="")
    with TestClient(create_app(s), base_url="https://testserver") as c:  # prod refuses to create tables itself
        r = c.post("/api/v1/auth/register", json={"email": "p@example.com", "password": "Correct-Horse-9"})
        assert r.status_code == 201
        assert c.get("/health/ready").json()["database"] == "up"
        assert "strict-transport-security" in c.get("/health/live").headers
        assert c.get("/docs").status_code == 404  # interactive docs are disabled in production
    con = sqlite3.connect(db_file)
    assert con.execute("select count(*) from users").fetchone()[0] == 1
    con.close()


def test_migration_on_postgresql(monkeypatch):
    """Runs only when ENERGIQ_TEST_DATABASE_URL points at PostgreSQL; otherwise it is skipped (not passed)."""
    import pytest
    from conftest import PG_URL, reset_database

    if not PG_URL.startswith("postgresql"):
        pytest.skip("ENERGIQ_TEST_DATABASE_URL is not a PostgreSQL URL")
    reset_database(PG_URL)
    cfg = _cfg(PG_URL, monkeypatch)
    command.upgrade(cfg, "head")
    eng = create_engine(PG_URL)
    assert set(inspect(eng).get_table_names()) - {"alembic_version"} == set(Base.metadata.tables)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"models and PostgreSQL migration disagree: {diff}"
    command.downgrade(cfg, "base")
    assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
    eng.dispose()
