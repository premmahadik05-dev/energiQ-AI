"""Values that SQLite stores without complaint but PostgreSQL rejects.

Found by running the whole backend suite against PostgreSQL 16 (see docs/12_deployment.md, "Verification status"):

* the BDG2 metadata has no coordinates for the Eagle site, so its cleaning report holds ``NaN``; PostgreSQL's ``json`` type refuses ``NaN``
  and the import of Eagle failed (SQLite stored it as text);
* an uploaded society whose name gives a key of 20 or more characters produced building codes longer than the ``VARCHAR(24)`` column
  (``GREEN-PARK-RESIDENCY-2-B01`` has 26), and a meter column name longer than 120 characters would not fit ``source_id``.

These tests do not need PostgreSQL: they check the values that would be written, so they fail on SQLite too if the bug comes back.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.models import Building, Meter
from backend.app.services.society_import import json_safe
from ml_engine.society.ingest import (
    CODE_MAX_CHARS,
    METER_ID_MAX_CHARS,
    IngestError,
    UploadRule,
    build_uploaded_society,
    read_mapping_csv,
    read_wide_csv,
)


def test_json_safe_replaces_nan_and_infinity_and_the_result_is_strict_json():
    messy = {"lat": float("nan"), "lng": np.float64("nan"), "ok": 1.5, "n": np.int64(3), "arr": [float("inf"), -float("inf"), {"x": np.float32("nan")}], "t": (1, 2), 5: "int key"}
    clean = json_safe(messy)
    assert clean["lat"] is None and clean["lng"] is None and clean["arr"][0] is None and clean["arr"][1] is None and clean["arr"][2]["x"] is None
    assert clean["ok"] == 1.5 and clean["n"] == 3 and isinstance(clean["n"], int) and clean["t"] == [1, 2] and clean["5"] == "int key"
    json.dumps(clean, allow_nan=False)  # raises on NaN/Infinity: this is what PostgreSQL and every strict parser enforce
    with pytest.raises(ValueError):
        json.dumps(messy, allow_nan=False)
    assert math.isnan(messy["lat"]), "the input is not modified"


def test_the_shipped_eagle_report_really_contains_nan_so_the_fix_is_exercised():
    text = (Path(__file__).resolve().parents[2] / "data" / "society" / "processed" / "eagle" / "cleaning_report.json").read_text()
    assert "NaN" in text, "if the data file was regenerated without NaN this test can be dropped, the importer still sanitises"
    with pytest.raises(ValueError):
        json.dumps(json.loads(text), allow_nan=False)
    json.dumps(json_safe(json.loads(text)), allow_nan=False)


def test_column_widths_in_the_models_match_the_limits_the_upload_code_enforces():
    assert Building.code.type.length == CODE_MAX_CHARS and Meter.code.type.length == CODE_MAX_CHARS
    assert Building.source_id.type.length == METER_ID_MAX_CHARS


def _frame(names, n=24 * 10):
    rng = np.random.default_rng(7)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({c: 5 + rng.random(n) for c in names}, index=idx)


@pytest.mark.parametrize("key", ["a", "green-park-residency-2", "g" * 24, "residential-colony-north-2", "x" * 40, "ab-" + "c" * 37])
def test_generated_codes_fit_the_database_column_for_any_key(key):
    df = _frame(["B1", "B2", "P1"])
    mapping = pd.DataFrame({"meter_id": ["B1", "B2", "P1"], "building": ["B1", "B2", "P1"], "kind": ["building", "building", "facility"],
                            "facility_category": ["", "", "pump"], "floor_area_sqm": np.nan})
    codes = list(build_uploaded_society(key, df, mapping, UploadRule())["meters"]["code"])
    assert len(set(codes)) == 3
    assert all(len(c) <= CODE_MAX_CHARS for c in codes), codes
    assert codes[0].endswith("-B01") and codes[1].endswith("-B02") and codes[2].endswith("-F01")
    assert not any(c.startswith("-") or "--" in c for c in codes)


def test_codes_stay_unique_and_in_the_column_when_there_are_more_than_99_meters():
    names = [f"M{i:03d}" for i in range(120)]
    codes = list(build_uploaded_society("green-park-residency-2", _frame(names), read_mapping_csv(None, names), UploadRule())["meters"]["code"])
    assert len(set(codes)) == 120 and all(len(c) <= CODE_MAX_CHARS for c in codes)
    assert codes[0].endswith("-B001") and codes[-1].endswith("-B120"), "three digits once there are more than 99 meters, so the codes still sort"


def test_a_meter_column_name_longer_than_the_database_column_is_rejected_with_a_message():
    idx = pd.date_range("2024-01-01", periods=48, freq="h")
    ok = pd.DataFrame({"timestamp": idx.strftime("%Y-%m-%d %H:%M"), "M" * METER_ID_MAX_CHARS: 1.0, "second": 2.0}).to_csv(index=False).encode()
    read_wide_csv(ok, unit="kwh")  # exactly at the limit is accepted
    bad = pd.DataFrame({"timestamp": idx.strftime("%Y-%m-%d %H:%M"), "M" * (METER_ID_MAX_CHARS + 1): 1.0, "second": 2.0}).to_csv(index=False).encode()
    with pytest.raises(IngestError, match="at most 120 characters"):
        read_wide_csv(bad, unit="kwh")
