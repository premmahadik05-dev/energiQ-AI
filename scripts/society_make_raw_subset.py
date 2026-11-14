"""Extract the small raw-data subset that lets the raw-data verification run without the 194 MB BDG2 download.

    python scripts/society_make_raw_subset.py            # reads data/society/raw/bdg2, writes data/society/raw_subset/

What it keeps, unchanged:
  * metadata.csv  - the complete official BDG2 metadata file, byte for byte (its SHA-256 equals the official one);
  * electricity_residential_meters.csv.gz - the official electricity.csv restricted to the COLUMNS of every building whose
    primary space use is 'Lodging/residential' (hotels included, buildings without a meter absent). Every row (all 17,544 hours)
    and every value is copied as the same text the official file has; nothing is rounded, filled or cleaned.
What it leaves out: all non-residential meters and the weather file.

The manifest (subset_manifest.json) records the SHA-256 of the full official files it was taken from, the list of columns and the SHA-256 of the
uncompressed subset CSV, so scripts/verify_society_raw_data.py can detect any later change. `verify_society_raw_data.py --raw <full> --check-subset`
re-compares the subset with the full official file value by value.

This script uses only the standard library plus pandas. It does not import any application code.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_USE = "Lodging/residential"  # the BDG2 metadata label; this label includes student residence halls (see docs/society/10_raw_data_verification.md)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data/society/raw/bdg2", help="folder with the full official BDG2 files")
    ap.add_argument("--out", type=Path, default=ROOT / "data/society/raw_subset")
    a = ap.parse_args()

    prov_path = a.raw / "provenance.json"
    if not prov_path.is_file():
        sys.exit(f"{prov_path} not found. Download the raw data first (python scripts/verify_society_raw_data.py --download).")
    prov = json.loads(prov_path.read_text())
    for rel, meta in prov["files"].items():
        got = sha256_file(a.raw / rel)
        if got != meta["sha256"]:
            sys.exit(f"SHA-256 mismatch for {rel}: expected {meta['sha256']}, found {got}. Refusing to build a subset from a changed file.")
    print("full raw files match the recorded SHA-256")

    md = pd.read_csv(a.raw / "data/metadata/metadata.csv")
    ids = sorted(md.loc[md["primaryspaceusage"] == PRIMARY_USE, "building_id"])
    # read as TEXT so that every value is written back exactly as published
    head = pd.read_csv(a.raw / "data/meters/raw/electricity.csv", nrows=0)
    cols = [c for c in ids if c in head.columns]
    sub = pd.read_csv(a.raw / "data/meters/raw/electricity.csv", usecols=["timestamp", *cols], dtype=str, keep_default_na=False)
    sub = sub[["timestamp", *cols]]

    a.out.mkdir(parents=True, exist_ok=True)
    csv_bytes = sub.to_csv(index=False, lineterminator="\n").encode("utf-8")
    with gzip.GzipFile(a.out / "electricity_residential_meters.csv.gz", "wb", mtime=0) as f:
        f.write(csv_bytes)
    shutil.copyfile(a.raw / "data/metadata/metadata.csv", a.out / "metadata.csv")

    manifest = {
        "purpose": "Raw readings of every 'Lodging/residential' building of BDG2, extracted unchanged for the independent verification.",
        "source": prov["source"],
        "license_note": "Creative Commons Attribution-ShareAlike 4.0; attribution and licence text are in data/society/raw_subset/LICENSE and docs/society/02_data_sources.md",
        "downloaded_at": prov["downloaded_at"],
        "taken_from": {rel: {"url": meta["url"], "sha256": meta["sha256"], "bytes": meta["bytes"]} for rel, meta in prov["files"].items() if rel.startswith("data/")},
        "selection": f"primaryspaceusage == '{PRIMARY_USE}' (hotels included; buildings with no electricity column are absent)",
        "rows": int(len(sub)),
        "columns": cols,
        "buildings_labelled_residential_in_metadata": len(ids),
        "buildings_with_an_electricity_meter": len(cols),
        "files": {
            "metadata.csv": {"sha256": sha256_file(a.out / "metadata.csv"), "note": "identical to the official file"},
            "electricity_residential_meters.csv.gz": {"sha256_of_uncompressed_csv": hashlib.sha256(csv_bytes).hexdigest(), "bytes_uncompressed": len(csv_bytes)},
        },
    }
    (a.out / "subset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lic = a.raw / "LICENSE"
    if lic.is_file():
        shutil.copyfile(lic, a.out / "LICENSE")
    print(f"wrote {a.out}: {len(cols)} meters of {len(ids)} residential-labelled buildings, {len(sub):,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
