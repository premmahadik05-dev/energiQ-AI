"""Ingestion tests: edge cases required by the project specification."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml_engine.data.ingest import UCI_CONFIG, IngestConfig, IngestError, ingest_csv
from ml_engine.data.quality import quality_score

CFG = IngestConfig(value_column="kw", timestamp_column="ts")


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _hourly_csv(path: Path, hours: int = 24 * 40, **mods) -> Path:
    idx = pd.date_range("2022-01-01", periods=hours, freq="h")
    vals = 1.0 + 0.5 * np.sin(np.arange(hours) * 2 * np.pi / 24)
    df = pd.DataFrame({"ts": idx.strftime("%Y-%m-%d %H:%M:%S"), "kw": vals.round(4).astype(str)})
    for fn in mods.values():
        df = fn(df)
    df.to_csv(path, index=False)
    return path


def test_clean_hourly_file(tmp_path):
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv"), CFG)
    r = res.report
    assert r["sampling_interval_seconds"] == 3600
    assert r["valid_hours"] == 24 * 40 and r["suitable_for_forecasting"]
    assert r["quality"]["score"] == pytest.approx(100.0)
    assert res.hourly["value_kw"].notna().all()


def test_fifteen_minute_data_is_averaged_and_watts_converted(tmp_path):
    idx = pd.date_range("2022-01-01", periods=4 * 24 * 40, freq="15min")
    df = pd.DataFrame({"ts": idx, "kw": 2000.0})  # 2000 W
    df.to_csv(tmp_path / "a.csv", index=False)
    res = ingest_csv(tmp_path / "a.csv", IngestConfig(value_column="kw", timestamp_column="ts", unit="W"))
    assert res.hourly["value_kw"].iloc[0] == pytest.approx(2.0)
    assert res.report["sampling_interval_seconds"] == 900


def test_energy_units_become_average_power(tmp_path):
    idx = pd.date_range("2022-01-01", periods=24 * 40, freq="h")
    pd.DataFrame({"ts": idx, "kw": 1.5}).to_csv(tmp_path / "a.csv", index=False)  # 1.5 kWh per hour
    res = ingest_csv(tmp_path / "a.csv", IngestConfig(value_column="kw", timestamp_column="ts", unit="kWh"))
    assert res.hourly["value_kw"].iloc[5] == pytest.approx(1.5)


def test_missing_timestamps_are_counted_and_rows_dropped(tmp_path):
    def blank_ts(df):
        df.loc[[3, 7, 11], "ts"] = ""
        return df
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv", f=blank_ts), CFG)
    assert res.report["unparseable_timestamps"] == 3
    assert res.report["valid_hours"] == 24 * 40 - 3


def test_duplicates_keep_first_and_are_counted(tmp_path):
    def dup(df):
        return pd.concat([df, df.iloc[[5, 6]]], ignore_index=True)
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv", f=dup), CFG)
    assert res.report["duplicate_timestamps"] == 2
    assert res.report["out_of_order_steps"] >= 1  # appended rows were out of order
    assert res.report["valid_hours"] == 24 * 40


def test_non_numeric_and_negative_values_are_invalid_not_silent(tmp_path):
    def bad(df):
        df.loc[10, "kw"] = "abc"
        df.loc[20, "kw"] = "-3.0"
        df.loc[30, "kw"] = "?"
        return df
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv", f=bad), CFG)
    r = res.report
    assert r["non_numeric_values"] == 1 and r["negative_values"] == 1 and r["missing_value_tokens"] == 1
    assert res.hourly["value_kw"].isna().sum() == 3
    assert r["quality"]["score"] < 100


def test_irregular_intervals_detected(tmp_path):
    def drop(df):
        return df.drop(index=[100, 101, 102, 400]).reset_index(drop=True)
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv", f=drop), CFG)
    assert res.report["irregular_steps"] == 2
    assert res.report["gaps_longer_than_1_5_intervals"] == 2
    assert res.report["largest_gap_minutes"] == 240.0
    assert res.hourly["value_kw"].isna().sum() == 4  # absent hours are NaN, never invented


def test_unsorted_file_is_sorted_and_flagged(tmp_path):
    p = _hourly_csv(tmp_path / "a.csv", f=lambda df: df.iloc[::-1].reset_index(drop=True))
    res = ingest_csv(p, CFG)
    assert res.hourly.index.is_monotonic_increasing
    assert res.report["out_of_order_steps"] > 0


def test_empty_header_only_and_missing_column_rejected(tmp_path):
    with pytest.raises(IngestError):
        ingest_csv(_write(tmp_path / "e.csv", ""), CFG)
    with pytest.raises(IngestError, match="no data rows"):
        ingest_csv(_write(tmp_path / "h.csv", "ts,kw\n"), CFG)
    with pytest.raises(IngestError, match="Missing expected column"):
        ingest_csv(_write(tmp_path / "m.csv", "time,power\n2022-01-01,1\n"), CFG)


def test_corrupted_binary_file_rejected(tmp_path):
    p = tmp_path / "bin.csv"
    p.write_bytes(bytes(range(256)) * 50)
    with pytest.raises(IngestError):
        ingest_csv(p, IngestConfig(value_column="kw", timestamp_column="ts", delimiter=","))


def test_mostly_garbage_timestamps_rejected(tmp_path):
    rows = "ts,kw\n" + "\n".join(f"not-a-date,{i}" for i in range(50)) + "\n2022-01-01 00:00:00,1\n"
    with pytest.raises(IngestError, match="timestamps"):
        ingest_csv(_write(tmp_path / "g.csv", rows), CFG)


def test_data_coarser_than_hourly_rejected(tmp_path):
    idx = pd.date_range("2022-01-01", periods=100, freq="D")
    pd.DataFrame({"ts": idx, "kw": 1.0}).to_csv(tmp_path / "d.csv", index=False)
    with pytest.raises(IngestError, match="at most hourly"):
        ingest_csv(tmp_path / "d.csv", CFG)


def test_insufficient_history_is_unsuitable_with_reason(tmp_path):
    res = ingest_csv(_hourly_csv(tmp_path / "a.csv", hours=24 * 10), CFG)
    assert not res.report["suitable_for_forecasting"]
    assert "required" in res.report["unsuitable_reasons"][0]


def test_unsupported_unit_rejected(tmp_path):
    with pytest.raises(IngestError, match="Unsupported unit"):
        ingest_csv(_hourly_csv(tmp_path / "a.csv"), IngestConfig(value_column="kw", timestamp_column="ts", unit="BTU"))


def test_uci_preset_handles_question_marks_and_trailing_empty_field(tmp_path):
    header = "Date;Time;Global_active_power;Global_reactive_power;Voltage;Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3"
    rows = []
    for m in range(120):  # two hours of minutes starting 00:00
        t = pd.Timestamp("2008-03-01") + pd.Timedelta(minutes=m)
        if 70 <= m < 100:  # 30 missing minutes in hour 2 -> only 30 valid (< 45)
            rows.append(f"{t:%d/%m/%Y};{t:%H:%M:%S};?;?;?;?;?;?;")
        else:
            rows.append(f"{t:%d/%m/%Y};{t:%H:%M:%S};1.200;0.1;240.0;5.0;0.0;1.0;18.0")
    res = ingest_csv(_write(tmp_path / "u.txt", "\n".join([header, *rows]) + "\n"), UCI_CONFIG)
    assert res.report["sampling_interval_seconds"] == 60
    assert res.hourly["value_kw"].iloc[0] == pytest.approx(1.2)
    assert np.isnan(res.hourly["value_kw"].iloc[1])  # 30 valid minutes < 45
    assert res.hourly["Sub_metering_3"].iloc[0] == pytest.approx(18.0 * 0.06)  # Wh/min -> kW


def test_quality_score_bounds():
    perfect = quality_score(raw_rows=100, valid_values=100, expected_slots=100, duplicates=0, non_numeric=0,
                            negative=0, unparseable_timestamps=0, irregular_steps=0, steps=99)
    assert perfect["score"] == 100.0 and perfect["grade"] == "excellent"
    worst = quality_score(raw_rows=0, valid_values=0, expected_slots=0, duplicates=0, non_numeric=0,
                          negative=0, unparseable_timestamps=0, irregular_steps=0, steps=0)
    assert worst["score"] == 0.0 and worst["grade"] == "poor"
