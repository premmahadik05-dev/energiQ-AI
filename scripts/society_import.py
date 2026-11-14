"""Load the processed real societies (plus trained bundles and anomaly events) into the application database.

    python scripts/society_import.py                      # every society not yet in the database
    python scripts/society_import.py --replace fox        # reload one society
    ENERGIQ_DATABASE_URL=postgresql+psycopg://... python scripts/society_import.py

Run scripts/society_prepare.py, scripts/society_train.py --deploy and scripts/society_anomalies.py first
(the repository already contains their outputs).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.db import Database  # noqa: E402
from backend.app.models import Society  # noqa: E402
from backend.app.services.society_import import import_processed  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("societies", nargs="*", help="keys to import (default: all in societies.json)")
    ap.add_argument("--replace", action="store_true", help="delete and reload societies that already exist")
    a = ap.parse_args()
    st = get_settings()
    db = Database(st.database_url)
    if st.env in {"dev", "test"}:
        db.create_all()
    keys = a.societies or [e["key"] for e in json.loads((st.society_data_dir / "societies.json").read_text())["societies"]]
    with db.session() as s:
        have = set(s.scalars(select(Society.key)))
        for k in keys:
            if k in have and not a.replace:
                print(f"{k}: already present (use --replace to reload)")
                continue
            t0 = time.time()
            out = import_processed(s, k, st.society_data_dir, st.society_dir, replace=a.replace, log_fn=lambda *args: None)
            print(f"{k}: {out} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
