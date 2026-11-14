"""Logic tests for the society upload reader, aggregation rules, split plan and peak evaluation.

The arrays here are tiny hand-built tables used only to check what the code does (units, aggregation, validity
rules, date arithmetic). No model accuracy or data statistics are asserted from them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_engine.society.ingest import IngestError, UploadRule, build_uploaded_society, read_mapping_csv, read_wide_csv, slugify
from ml_engine.society.runner import MIN_VALID_HOURS, NotEnoughData, peak_evaluation, plan_for


def csv_of(index, **cols) -> bytes:
    df = pd.DataFrame({"timestamp": pd.Index(index).strftime("%Y-%m-%d %H:%M"), **cols})
    return df.to_csv(index=False).encode()


# ----------------------------------------------------------------------------- reading
def test_quarter_hour_kwh_is_summed_and_incomplete_hours_are_missing():
    idx = pd.date_range("2024-01-01", periods=24 * 4 * 2, freq="15min")
    v = np.full(len(idx), 0.5)
    df = csv_of(idx, A=v)
    raw = pd.read_csv(pd.io.common.BytesIO(df), dtype=str)
    raw.loc[5, "A"] = ""  # one 15-minute reading lost in hour 1 of day 1
    hourly, rep = read_wide_csv(raw.to_csv(index=False).encode(), unit="kwh")
    assert rep["interval_minutes"] == 15
    assert hourly["A"].iloc[0] == pytest.approx(2.0)  # 4 x 0.5 kWh
    assert np.isnan(hourly["A"].iloc[1])  # energy needs every sub-interval; nothing is scaled up
    assert hourly["A"].iloc[2] == pytest.approx(2.0)
    assert len(hourly) == 48


def test_quarter_hour_kw_is_averaged_with_75_percent_coverage():
    idx = pd.date_range("2024-01-01", periods=24 * 4, freq="15min")
    raw = pd.read_csv(pd.io.common.BytesIO(csv_of(idx, A=np.full(len(idx), 8.0))), dtype=str)
    raw.loc[0:0, "A"] = ""  # 3 of 4 present in hour 0
    raw.loc[4:6, "A"] = ""  # 1 of 4 present in hour 1
    hourly, rep = read_wide_csv(raw.to_csv(index=False).encode(), unit="kw")
    assert hourly["A"].iloc[0] == pytest.approx(8.0)  # mean power over the hour, equal to kWh for that hour
    assert np.isnan(hourly["A"].iloc[1])
    assert "mean of the sub-hourly kW" in rep["aggregation"]


def test_hourly_input_duplicates_gaps_and_text_cells_are_reported_not_filled():
    idx = list(pd.date_range("2024-01-01", periods=48, freq="h"))
    idx = idx[:10] + idx[11:] + [idx[3]]  # one missing hour and one duplicated timestamp
    a = [1.0] * len(idx)
    raw = pd.DataFrame({"timestamp": [t.strftime("%Y-%m-%d %H:%M") for t in idx], "A": a, "B": ["x"] + ["2"] * (len(idx) - 1)})
    hourly, rep = read_wide_csv(raw.to_csv(index=False).encode(), unit="kwh")
    assert rep["duplicate_timestamps"] == 1
    assert rep["timestamps"]["missing_timestamps"] == 1
    assert rep["non_numeric_cells"] == 1
    assert hourly["A"].isna().sum() == 1 and hourly["B"].isna().sum() == 2  # the gap, plus the text cell in B
    assert len(hourly) == 48


def test_unsupported_interval_and_bad_timestamps_are_rejected():
    idx = pd.date_range("2024-01-01", periods=30, freq="2h")
    with pytest.raises(IngestError, match="interval"):
        read_wide_csv(csv_of(idx, A=np.ones(30)))
    raw = pd.DataFrame({"timestamp": ["not a date"] * 40, "A": np.ones(40)})
    with pytest.raises(IngestError, match="timestamps"):
        read_wide_csv(raw.to_csv(index=False).encode())
    with pytest.raises(IngestError, match="unit"):
        read_wide_csv(csv_of(pd.date_range("2024-01-01", periods=30, freq="h"), A=np.ones(30)), unit="mwh")
    with pytest.raises(IngestError, match="24 rows"):
        read_wide_csv(csv_of(pd.date_range("2024-01-01", periods=5, freq="h"), A=np.ones(5)))


def test_mapping_rules():
    ids = ["B1", "B2", "L1"]
    default = read_mapping_csv(None, ids)
    assert list(default["kind"]) == ["building"] * 3
    ok = read_mapping_csv(b"meter_id,building,kind,facility_category,floor_area_sqm\nL1,Lift A,facility,lift,\nB1,Block 1,building,,1200\n", ids)
    assert dict(zip(ok["meter_id"], ok["kind"], strict=True)) == {"B1": "building", "B2": "building", "L1": "facility"}  # unlisted B2 defaults to a building
    assert ok.set_index("meter_id").loc["B1", "floor_area_sqm"] == 1200
    with pytest.raises(IngestError, match="not columns"):
        read_mapping_csv(b"meter_id,kind\nZZ,building\n", ids)
    with pytest.raises(IngestError, match="facility_category"):
        read_mapping_csv(b"meter_id,kind,facility_category\nL1,facility,\n", ids)
    with pytest.raises(IngestError, match="more than once"):
        read_mapping_csv(b"meter_id,kind\nB1,building\nB1,building\n", ids)
    with pytest.raises(IngestError, match="kind"):
        read_mapping_csv(b"meter_id,kind\nB1,house\n", ids)


def test_slugify():
    assert slugify("Green Park – Phase 2!") == "green-park-phase-2"
    assert slugify("???") == "society"


# ----------------------------------------------------------------------------- aggregation rules
def _hourly(n=24 * 30, **cols):
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({k: pd.Series(v, index=idx) if np.ndim(v) else pd.Series(float(v), index=idx) for k, v in cols.items()})


def test_total_exists_only_when_every_retained_meter_is_valid_and_facility_zeros_are_kept():
    rng = np.random.default_rng(1)  # only to vary readings so the stuck-sensor rule does not fire
    n = 24 * 30
    df = _hourly(n, B1=5 + rng.random(n), B2=7 + rng.random(n), P1=np.where(np.arange(n) % 24 < 6, 0.0, 1.0 + rng.random(n)))
    df.iloc[10, 0] = -3.0  # invalid negative reading in B1
    mapping = pd.DataFrame({"meter_id": ["B1", "B2", "P1"], "building": ["B1", "B2", "P1"], "kind": ["building", "building", "facility"],
                            "facility_category": ["", "", "streetlight"], "floor_area_sqm": np.nan})
    built = build_uploaded_society("demo", df, mapping, UploadRule())
    tot = built["society_kwh"]
    assert np.isnan(tot.iloc[10])  # one invalid meter makes the total missing, it is not summed over the others
    assert tot.notna().sum() == n - 1  # the street-light meter's zeros are valid readings
    assert tot.iloc[11] == pytest.approx(df.iloc[11].sum())
    assert list(built["meters"]["code"]) == ["DEMO-B01", "DEMO-B02", "DEMO-F01"]
    assert built["meters"].set_index("code").loc["DEMO-F01", "facility_category"] == "streetlight"
    assert built["n_valid_meters"].iloc[10] == 2 and built["n_valid_meters"].iloc[11] == 3


def test_building_zero_readings_are_invalid_and_poor_meters_are_excluded():
    rng = np.random.default_rng(2)
    n = 24 * 30
    good1, good2 = 5 + rng.random(n), 6 + rng.random(n)
    poor = 4 + rng.random(n)
    poor[: n // 2] = 0.0  # half the history is a dead meter
    df = _hourly(n, G1=good1, G2=good2, P=poor)
    mapping = read_mapping_csv(None, ["G1", "G2", "P"])
    built = build_uploaded_society("demo", df, mapping, UploadRule(min_meter_valid_share=0.9))
    assert [e["source_id"] for e in built["excluded"]] == ["P"]
    assert list(built["meters_df"].columns) == ["DEMO-B01", "DEMO-B02"]
    assert built["society_valid_share"] == pytest.approx(1.0)


def test_too_few_meters_or_low_overlap_is_rejected():
    n = 24 * 30
    rng = np.random.default_rng(3)
    df = _hourly(n, G1=5 + rng.random(n), P=0.0)
    with pytest.raises(IngestError, match="pass the validity rule"):
        build_uploaded_society("demo", df, read_mapping_csv(None, ["G1", "P"]), UploadRule())
    a, b = 5 + rng.random(n), 5 + rng.random(n)
    a[: n // 2] = np.nan
    b[n // 2:] = np.nan
    with pytest.raises(IngestError, match="total is valid in only"):
        build_uploaded_society("demo", _hourly(n, A=a, B=b), read_mapping_csv(None, ["A", "B"]), UploadRule(min_meter_valid_share=0.4))


# ----------------------------------------------------------------------------- split plan
def _series(start: str, hours: int) -> pd.Series:
    idx = pd.date_range(start, periods=hours, freq="h")
    return pd.Series(np.linspace(1, 2, hours), index=idx)


def test_plan_reproduces_the_bdg2_protocol_and_adapts_to_shorter_history():
    p = plan_for(_series("2016-01-01", 17544))
    assert p.test_start == pd.Timestamp("2017-07-01") and p.test_end == pd.Timestamp("2017-12-31 23:00")
    assert [str(f.test_start.date()) for f in p.folds] == ["2016-07-01", "2016-10-01", "2017-01-01", "2017-04-01"]
    assert p.folds[-1].test_end == p.test_start - pd.Timedelta(hours=1)  # CV blocks end exactly where the test block begins
    short = plan_for(_series("2024-01-01", 24 * 420))
    assert short.test_start == pd.Timestamp("2024-12-01") and len(short.folds) == 2
    assert short.folds[0].test_start - pd.Timestamp("2024-01-01") >= pd.Timedelta(days=90)  # >= 90 days of training before the first block


def test_plan_rejects_short_history():
    with pytest.raises(NotEnoughData, match="at least"):
        plan_for(_series("2024-01-01", MIN_VALID_HOURS - 1))
    with pytest.raises(NotEnoughData, match="cross-validation"):
        plan_for(_series("2024-01-01", 24 * 300))


# ----------------------------------------------------------------------------- peak evaluation
def test_peak_evaluation_scores_daily_peak_value_and_hour():
    idx = pd.date_range("2024-02-01", periods=72, freq="h")
    actual = np.ones(72)
    actual[[19, 24 + 20, 48 + 18]] = [10, 12, 9]  # daily peaks at hours 19, 20, 18
    model = actual.copy()
    model[[19, 24 + 20, 24 + 21, 48 + 18]] = [9, 1, 11, 9]  # day1 peak 1 low, day2 peak lands one hour late, day3 exact
    base = np.ones(72) * 2
    base[[5, 24 + 5, 48 + 5]] = 4  # baseline peaks at 05:00 every day
    df = pd.DataFrame({"y_true": actual, "m": model, "b": base}, index=idx)
    r = peak_evaluation(df, "m", "b")
    assert r["days"] == 3
    assert r["model"]["peak_mae_kw"] == pytest.approx((1 + 1 + 0) / 3)
    assert r["model"]["peak_bias_kw"] == pytest.approx(-2 / 3)
    assert r["model"]["peak_hour_exact_pct"] == pytest.approx(200 / 3)
    assert r["model"]["peak_hour_within_1h_pct"] == pytest.approx(100.0)
    assert r["baseline"]["peak_hour_within_2h_pct"] == pytest.approx(0.0)
    assert r["baseline"]["peak_mae_kw"] == pytest.approx(np.mean([6, 8, 5]))
    assert r["mae_improvement_vs_baseline_pct"] > 0


def test_peak_evaluation_keeps_the_method_names_next_to_the_metrics():
    """The names used to be overwritten by the metric dicts, so the saved file could not say which methods were scored."""
    idx = pd.date_range("2024-02-01", periods=48, freq="h")
    df = pd.DataFrame({"y_true": np.arange(48.0), "xgb": np.arange(48.0) + 1, "naive": np.arange(48.0) + 2}, index=idx)
    r = peak_evaluation(df, "xgb", "naive")
    assert r["model_name"] == "xgb" and r["baseline_name"] == "naive"
    assert isinstance(r["model"], dict) and "peak_mae_kw" in r["model"]
    assert isinstance(r["baseline"], dict) and "peak_mae_kw" in r["baseline"]


def test_peak_evaluation_skips_incomplete_days():
    idx = pd.date_range("2024-02-01", periods=10, freq="h")
    df = pd.DataFrame({"y_true": np.arange(10.0), "m": np.arange(10.0), "b": np.arange(10.0)}, index=idx)
    assert peak_evaluation(df, "m", "b")["days"] == 0
