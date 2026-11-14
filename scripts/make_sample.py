"""Create the small bundled sample dataset (calendar year 2009, hourly kW) from the UCI file.

The sample is a subset of the UCI "Individual household electric power consumption" data
(Hebrail & Berard, 2006; CC BY 4.0, DOI 10.24432/C58K54), aggregated to hourly mean
Global_active_power with the same 45-valid-minutes rule used everywhere else. Missing hours are blank.

    python scripts/make_sample.py --input data/raw/uci_household_power/household_power_consumption.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/sample/uci_hourly_2009_sample.csv"))
    args = ap.parse_args()
    s = ingest_csv(args.input, UCI_CONFIG).hourly["value_kw"].loc["2009-01-01":"2009-12-31 23:00"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out = s.rename("power_kw").round(4).rename_axis("timestamp")
    out.to_csv(args.out, date_format="%Y-%m-%d %H:%M:%S")
    print(f"wrote {args.out}: {len(out)} hours, {int(out.notna().sum())} valid")


if __name__ == "__main__":
    main()
