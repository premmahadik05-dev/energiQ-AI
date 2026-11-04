"""Backup, corruption detection and restore round trip (SQLite always; PostgreSQL when ENERGIQ_TEST_DATABASE_URL is set)."""
from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import tarfile
from pathlib import Path

import pytest
from conftest import PG_URL, make_settings, signup, synthetic_csv, upload
from fastapi.testclient import TestClient

from backend.app.main import create_app

spec = importlib.util.spec_from_file_location("backup_script", Path(__file__).resolve().parents[2] / "scripts" / "backup.py")
backup_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_script)


def _count(settings, table="users") -> int:
    from sqlalchemy import create_engine, text

    eng = create_engine(settings.database_url)
    with eng.connect() as c:
        n = c.execute(text(f"select count(*) from {table}")).scalar()
    eng.dispose()
    return int(n)


def test_sqlite_backup_restore_roundtrip(tmp_path):
    s = make_settings(tmp_path, database_url=f"sqlite:///{(tmp_path / 'live.db').as_posix()}")
    with TestClient(create_app(s)) as c:
        h = signup(c, "bk@example.com")
        assert upload(c, h, synthetic_csv(days=30)).status_code == 202
    users, readings = _count(s), _count(s, "readings")
    assert users == 2 and readings > 0  # the seeded administrator and the new user
    archive = backup_script.backup(s, tmp_path / "out")
    # damage the live state, then restore
    (tmp_path / "live.db").unlink()
    shutil.rmtree(s.upload_dir, ignore_errors=True)
    backup_script.restore(s, archive, assume_yes=True)
    assert _count(s) == users and _count(s, "readings") == readings
    assert any(Path(s.upload_dir).rglob("*.csv")), "uploaded files must come back too"
    assert sqlite3.connect(tmp_path / "live.db").execute("pragma integrity_check").fetchone()[0] == "ok"


def test_restore_refuses_a_corrupted_archive(tmp_path):
    s = make_settings(tmp_path, database_url=f"sqlite:///{(tmp_path / 'live.db').as_posix()}")
    with TestClient(create_app(s)):
        pass
    archive = backup_script.backup(s, tmp_path / "out")
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(archive) as src, tarfile.open(bad, "w:gz") as dst:
        for m in src.getmembers():
            data = src.extractfile(m)
            if m.name == "database.sqlite":
                payload = bytearray(data.read())
                payload[100] ^= 0xFF
                import io

                m.size = len(payload)
                dst.addfile(m, io.BytesIO(bytes(payload)))
            elif data is not None:
                dst.addfile(m, data)
            else:
                dst.addfile(m)
    with pytest.raises(SystemExit, match="checksum mismatch"):
        backup_script.restore(s, bad, assume_yes=True)


def test_restore_refuses_path_traversal_members(tmp_path):
    evil = tmp_path / "evil.tar.gz"
    payload = tmp_path / "x.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w:gz") as t:
        t.add(payload, arcname="../escape.txt")
    s = make_settings(tmp_path, database_url=f"sqlite:///{(tmp_path / 'live.db').as_posix()}")
    with pytest.raises(SystemExit, match="unsafe archive member"):
        backup_script.restore(s, evil, assume_yes=True)
    assert not (tmp_path.parent / "escape.txt").exists()


@pytest.mark.skipif(not PG_URL.startswith("postgresql") or shutil.which("pg_dump") is None, reason="needs PostgreSQL URL and pg_dump")
def test_postgresql_backup_restore_roundtrip(tmp_path):
    s = make_settings(tmp_path)  # resets the PostgreSQL schema
    with TestClient(create_app(s)) as c:
        h = signup(c, "pgbk@example.com")
        assert upload(c, h, synthetic_csv(days=30)).status_code == 202
    users, readings = _count(s), _count(s, "readings")
    archive = backup_script.backup(s, tmp_path / "out")
    from sqlalchemy import create_engine, text

    eng = create_engine(s.database_url)
    with eng.begin() as conn:
        conn.execute(text("delete from users"))  # cascades through datasets and readings
    eng.dispose()
    assert _count(s) == 0
    backup_script.restore(s, archive, assume_yes=True)
    assert _count(s) == users and _count(s, "readings") == readings
