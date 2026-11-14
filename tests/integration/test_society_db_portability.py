"""What the importer writes must be acceptable to PostgreSQL as well as SQLite.

SQLite does not enforce ``VARCHAR(n)`` and stores ``NaN`` in a JSON column as text, so a suite that only runs on SQLite cannot see these
problems. The checks below look at the stored values themselves, so they also fail on SQLite when a value would be rejected by PostgreSQL.
Running the whole suite on PostgreSQL (``ENERGIQ_TEST_DATABASE_URL``, see docs/12_deployment.md) remains the authoritative test.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from itest_support import REPO, make_settings
from sqlalchemy import String, func, select

from backend.app.db import Base
from backend.app.main import create_app
from backend.app.models import Society
from backend.app.services.society_import import import_processed

PROCESSED = REPO / "data" / "society" / "processed"
ARTIFACTS = REPO / "artifacts" / "society"
KEYS = ["bull", "eagle", "fox", "hog", "peacock", "rat", "robin"]

pytestmark = pytest.mark.skipif(not (PROCESSED / "societies.json").is_file(), reason="processed society data not present")


@pytest.fixture(scope="module")
def db_after_import(tmp_path_factory):
    st = make_settings(tmp_path_factory.mktemp("portability"), society_dir=ARTIFACTS, society_data_dir=PROCESSED)
    app = create_app(st)
    with TestClient(app):
        with app.state.db.session() as s:
            for key in KEYS:
                import_processed(s, key, st.society_data_dir, st.society_dir, log_fn=lambda *a: None)
        yield app.state.db


def test_every_bounded_text_column_holds_only_values_that_fit_it(db_after_import):
    checked, too_long = 0, []
    with db_after_import.session() as s:
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                if isinstance(col.type, String) and col.type.length:
                    longest = s.scalar(select(func.max(func.length(col)))) or 0
                    checked += 1
                    if longest > col.type.length:
                        too_long.append(f"{table.name}.{col.name}: {longest} > {col.type.length}")
    assert checked > 30, "the check must actually look at the schema's bounded columns"
    assert not too_long, too_long


def test_json_columns_of_every_society_are_strict_json_and_eagle_has_no_coordinates(db_after_import):
    with db_after_import.session() as s:
        socs = {x.key: x for x in s.scalars(select(Society))}
        assert sorted(socs) == KEYS
        for soc in socs.values():
            json.dumps(soc.meta, allow_nan=False)  # PostgreSQL's json type rejects NaN and Infinity
        eagle = socs["eagle"]
        assert eagle.lat is None and eagle.lng is None, "BDG2 gives no coordinates for Eagle: stored as 'unknown', not as NaN"
        assert eagle.meta["cleaning_report"]["lat"] is None
        assert socs["fox"].lat is not None and socs["fox"].lng is not None
