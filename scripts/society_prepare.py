"""Build the society datasets from the real BDG2 meters.

    python scripts/society_prepare.py                    # download (if needed), clean, aggregate, write
    python scripts/society_prepare.py --raw /path/to/bdg2 --sites Fox Rat

Outputs (one folder per society under data/society/processed/):
    meters_hourly_kwh.csv.gz   cleaned hourly kWh per building (NaN = invalid or missing, never filled)
    society_hourly.csv.gz      society total kWh, number of valid meters, matched site weather
    buildings.csv              building code, source id, use, floor area, year built, valid share
    excluded_meters.csv        meters dropped by the validity rule, with counts per cleaning rule
    cleaning_report.json       every parameter and every count
and data/society/processed/societies.json (index) plus data/society/DATA_CARD.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_engine.society.aggregate import SocietyRule, build_society, residential_candidates  # noqa: E402
from ml_engine.society.cleaning import CleaningConfig  # noqa: E402
from ml_engine.society.sources import BDG2_CARD, download_bdg2  # noqa: E402

WEATHER_COLUMNS = ["airTemperature", "dewTemperature", "windSpeed", "cloudCoverage", "precipDepth1HR", "seaLvlPressure"]


def society_key(site: str) -> str:
    return site.strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data/society/raw/bdg2")
    ap.add_argument("--out", type=Path, default=ROOT / "data/society/processed")
    ap.add_argument("--sites", nargs="*", help="limit to these BDG2 site names (default: every qualifying site)")
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()

    prov_path = a.raw / "provenance.json"
    if a.no_download:
        if not prov_path.is_file():
            sys.exit(f"--no-download given but {prov_path} is missing")
        prov = json.loads(prov_path.read_text())
    else:
        prov = download_bdg2(a.raw)
    print(f"source files verified (downloaded {prov['downloaded_at']})")

    md = pd.read_csv(a.raw / "data/metadata/metadata.csv")
    meters = pd.read_csv(a.raw / "data/meters/raw/electricity.csv", parse_dates=["timestamp"], index_col="timestamp")
    weather = pd.read_csv(a.raw / "data/weather/weather.csv")
    rule, cleaning = SocietyRule(), CleaningConfig()
    sites = a.sites or sorted(residential_candidates(md, meters, rule)["site_id"].unique())

    index, rejected = [], []
    a.out.mkdir(parents=True, exist_ok=True)
    for site in sites:
        res = build_society(site, md, meters, weather, rule, cleaning)
        if res is None or not res["qualifies"]:
            reason = "no residential meters" if res is None else res["reason"]
            rejected.append({"site": site, "reason": reason})
            print(f"  {site:<9} rejected: {reason}")
            continue
        key = society_key(site)
        folder = a.out / key
        folder.mkdir(parents=True, exist_ok=True)
        b = res["buildings"].sort_values("source_id").reset_index(drop=True)
        b.insert(0, "code", [f"{site[:3].upper()}-B{i + 1:02d}" for i in range(len(b))])
        code_of = dict(zip(b["source_id"], b["code"], strict=True))
        m = res["meters"].rename(columns=code_of)[b["code"].tolist()]
        m.round(3).to_csv(folder / "meters_hourly_kwh.csv.gz", compression="gzip")
        soc = pd.concat([res["society_kwh"].round(3), res["n_valid_meters"], res["weather"][[c for c in WEATHER_COLUMNS if c in res["weather"].columns]]], axis=1)
        soc.to_csv(folder / "society_hourly.csv.gz", compression="gzip")
        b.to_csv(folder / "buildings.csv", index=False)
        pd.DataFrame(res["excluded"]).to_csv(folder / "excluded_meters.csv", index=False)
        total = res["society_kwh"]
        report = {
            "society": key, "bdg2_site": site, "timezone": res["timezone"], "lat": res["lat"], "lng": res["lng"],
            "candidate_residential_buildings": res["candidates"], "buildings_kept": int(len(b)), "buildings_excluded": len(res["excluded"]),
            "timestamps": res["timestamps"], "society_valid_hours": int(total.notna().sum()), "hours": int(len(total)),
            "society_valid_share": round(res["society_valid_share"], 4),
            "society_kwh": {"mean": round(float(total.mean()), 2), "max": round(float(total.max()), 2), "min": round(float(total.min()), 2)},
            "rule": res["rule"], "cleaning": res["cleaning"],
            "cleaning_counts_per_building": {code_of[k]: v for k, v in res["cleaning_counts"].items()},
            "weather_missing_hours": {c: int(res["weather"][c].isna().sum()) for c in WEATHER_COLUMNS if c in res["weather"].columns},
        }
        (folder / "cleaning_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        index.append({"key": key, "bdg2_site": site, "name": f"BDG2 site {site} residential community", "timezone": res["timezone"],
                      "buildings": int(len(b)), "floor_area_sqm": float(b["floor_area_sqm"].sum()),
                      "start": str(total.index[0]), "end": str(total.index[-1]), "hours": int(len(total)),
                      "valid_hours": int(total.notna().sum()), "mean_kw": report["society_kwh"]["mean"]})
        print(f"  {site:<9} ok: {len(b)} buildings, {total.notna().mean():.1%} valid hours, mean {total.mean():.0f} kWh/h")

    (a.out / "societies.json").write_text(json.dumps({"source": BDG2_CARD, "downloaded_at": prov["downloaded_at"],
                                                      "files": prov["files"], "rule": rule.to_dict(), "cleaning": cleaning.to_dict(),
                                                      "societies": index, "rejected_sites": rejected}, indent=2), encoding="utf-8")
    print(f"{len(index)} societies written to {a.out}; {len(rejected)} sites rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
