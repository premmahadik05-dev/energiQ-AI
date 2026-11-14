"""Backup and restore of the EnergiQ database and file store.

  python scripts/backup.py backup  --out backups/            # uses ENERGIQ_DATABASE_URL, ENERGIQ_UPLOAD_DIR, ENERGIQ_MODELS_DIR
  python scripts/backup.py restore --archive backups/energiq-20261103T101500Z.tar.gz [--yes]

SQLite  : consistent online copy through SQLite's backup API (safe while the API is running).
Postgres: `pg_dump --format=custom` (needs the PostgreSQL client tools on PATH); restore uses `pg_restore --clean --if-exists`.
The archive also contains the upload and model directories and a manifest with SHA-256 checksums that `restore` verifies.
The database password is passed to PostgreSQL tools through PGPASSWORD, never on the command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import Settings  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _pg_env(url) -> dict[str, str]:
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def _pg_args(url) -> list[str]:
    return ["-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "postgres"]


def backup(settings: Settings, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    url = make_url(settings.database_url)
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        manifest: dict = {"created_utc": stamp, "database_backend": url.get_backend_name(), "files": {}}
        if url.get_backend_name() == "sqlite":
            src = sqlite3.connect(f"file:{url.database}?mode=ro", uri=True)
            dst = sqlite3.connect(tmp / "database.sqlite")
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            db_file = tmp / "database.sqlite"
        elif url.get_backend_name() == "postgresql":
            if shutil.which("pg_dump") is None:
                raise SystemExit("pg_dump not found; install the PostgreSQL client tools")
            db_file = tmp / "database.dump"
            subprocess.run(["pg_dump", "--format=custom", "--no-owner", "-f", str(db_file), *_pg_args(url), url.database],
                           check=True, env=_pg_env(url))
        else:
            raise SystemExit(f"Unsupported database backend {url.get_backend_name()}")
        manifest["files"][db_file.name] = sha256(db_file)
        for label, directory in (("uploads", settings.upload_dir), ("models", settings.models_dir)):
            manifest[f"{label}_dir_present"] = Path(directory).is_dir()
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))
        archive = out_dir / f"energiq-{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(tmp / "manifest.json", arcname="manifest.json")
            tar.add(db_file, arcname=db_file.name)
            for label, directory in (("uploads", settings.upload_dir), ("models", settings.models_dir)):
                if Path(directory).is_dir():
                    tar.add(directory, arcname=label)
    print(f"backup written: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    return archive


def _safe_members(tar: tarfile.TarFile):
    for m in tar.getmembers():
        p = Path(m.name)
        if p.is_absolute() or ".." in p.parts or m.issym() or m.islnk():
            raise SystemExit(f"refusing to extract unsafe archive member: {m.name}")
        yield m


def restore(settings: Settings, archive: Path, assume_yes: bool) -> None:
    url = make_url(settings.database_url)
    if not assume_yes:
        answer = input(f"This OVERWRITES the database {url.render_as_string(hide_password=True)} and the file stores. Type 'yes': ")
        if answer.strip().lower() != "yes":
            raise SystemExit("aborted")
    with tempfile.TemporaryDirectory() as tmp_s, tarfile.open(archive) as tar:
        tmp = Path(tmp_s)
        tar.extractall(tmp, members=list(_safe_members(tar)), filter="data")
        manifest = json.loads((tmp / "manifest.json").read_text())
        for name, digest in manifest["files"].items():
            if sha256(tmp / name) != digest:
                raise SystemExit(f"checksum mismatch for {name}; the archive is corrupt")
        if manifest["database_backend"] != url.get_backend_name():
            raise SystemExit("archive and target use different database backends")
        if url.get_backend_name() == "sqlite":
            target = Path(url.database)
            target.parent.mkdir(parents=True, exist_ok=True)
            for suffix in ("", "-wal", "-shm"):
                Path(f"{target}{suffix}").unlink(missing_ok=True)
            shutil.copy2(tmp / "database.sqlite", target)
        else:
            subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "-d", url.database, *_pg_args(url), str(tmp / "database.dump")],
                           check=True, env=_pg_env(url))
        for label, directory in (("uploads", settings.upload_dir), ("models", settings.models_dir)):
            if (tmp / label).is_dir():
                shutil.rmtree(directory, ignore_errors=True)
                shutil.copytree(tmp / label, directory)
    print("restore complete; restart the API")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--out", type=Path, default=Path("backups"))
    r = sub.add_parser("restore")
    r.add_argument("--archive", type=Path, required=True)
    r.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    settings = Settings()
    backup(settings, args.out) if args.cmd == "backup" else restore(settings, args.archive, args.yes)


if __name__ == "__main__":
    main()
