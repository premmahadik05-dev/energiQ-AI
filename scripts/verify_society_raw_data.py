#!/usr/bin/env python
"""Independent verification of the society data, starting from the raw BDG2 files.

    python scripts/verify_society_raw_data.py                       # checks, writes docs/society/VERIFICATION_REPORT.md and .json
    python scripts/verify_society_raw_data.py --download            # first fetch the official raw files (174 MB) and check their SHA-256
    python scripts/verify_society_raw_data.py --check-subset        # also compare data/society/raw_subset with the full official file
    ENERGIQ_VERIFY_PASSWORD=... python scripts/verify_society_raw_data.py --api-url http://127.0.0.1:8000 --email admin@example.com

WHAT THIS IS. A second, separate implementation of the society data pipeline, written from the rules in docs/society/10_raw_data_verification.md.
It reads the RAW BDG2 files, applies the documented selection and cleaning rules with its own code, aggregates, and then compares the result with what the
application holds: the processed files in data/society/processed and (optionally) a running API.

WHY IT IS INDEPENDENT. It imports nothing from `ml_engine`, `backend` or any other part of this repository: only the standard library, numpy and pandas
(a test, tests/unit/test_society_raw_verification.py, enforces this). Its thresholds are written down below as SPEC, not read from the application.

FOUR LAYERS, KEPT APART. (1) raw readings: BDG2 electricity.csv exactly as published. (2) cleaned readings: the raw readings with invalid ones set to
missing; no reading is ever changed or filled in. (3) aggregated community demand: the sum of the cleaned readings of the kept buildings, missing in any hour
where one of them is missing. (4) ML predictions: forecasts of layer 3 made by trained models; this script does not touch them.

HONEST SCOPE. BDG2 buildings labelled 'Lodging/residential' include student residence halls. This is not data of family flats or of a registered housing
society, and nothing here changes that. Passing these checks shows that the application's numbers follow from the raw files by the documented rules.
It does not show that the raw files are free of errors, or that the communities are representative of any real housing society.

Exit code: 0 all checks passed, 1 at least one check failed, 2 inputs missing.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import platform
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# ----------------------------------------------------------------------------------------------------------------------------------------------------
# SPEC: the rules this script verifies. Written out here on purpose; docs/society/10_raw_data_verification.md describes the same numbers.
# ----------------------------------------------------------------------------------------------------------------------------------------------------
SPEC = {
    "selection": {
        "primary_use": "Lodging/residential",      # BDG2 metadata column `primaryspaceusage`; includes student residence halls
        "exclude_sub_uses": ["Hotel"],              # `sub_primaryspaceusage` (whitespace stripped, missing treated as empty)
        "min_meter_valid_share": 0.95,              # a meter is kept when at least 95 % of its 17,544 hours are valid after cleaning
        "min_buildings": 8,                         # a site needs at least 8 kept meters to form a community
        "min_society_valid_share": 0.94,            # and at least 94 % of hours in which ALL kept meters are valid
    },
    "cleaning": {
        "zero_is_invalid": True,                    # a reading of exactly 0 kWh is treated as a sensor/outage artefact
        "long_zero_hours": 24,                      # (only used to label zero readings as 'long run' or 'short'; both are removed)
        "stuck_min_hours": 48,                      # >= 48 consecutive identical positive readings are a stuck sensor
        "spike_factor": 4.0,                        # a reading above 4 x the meter's 99.5th percentile of positive readings is a spike
        "spike_quantile": 0.995,
        "spike_min_positive_readings": 100,         # the spike rule applies only to meters with at least 100 positive readings
        "negative_is_invalid": True,
    },
    "storage_decimals": 3,                          # processed files hold 3 decimals, so stored values may differ from raw by at most 0.0005
}
ROUND_TOL = 0.5 * 10 ** (-SPEC["storage_decimals"]) + 1e-9
PROCESSED_RULE_KEYS = ("primary_use", "exclude_sub_uses", "min_meter_valid_share", "min_buildings", "min_society_valid_share")
PROCESSED_CLEANING_KEYS = ("zero_is_invalid", "long_zero_hours", "stuck_min_hours", "spike_factor", "spike_quantile")
RULE_COLUMNS = ("negative", "zero_long_runs", "zero_short", "stuck_sensor", "spike")


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# hashing and download
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _http_only(url: str) -> str:
    """urlopen also opens file: and custom schemes; the verifier only ever needs http(s), so anything else is refused."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"only http and https URLs are accepted, got {url!r}")
    return url


def download_file(url: str, dest: Path, expected_sha256: str, timeout: int = 120) -> None:
    """Download `url` to `dest` and keep it only if its SHA-256 equals `expected_sha256`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    with urllib.request.urlopen(_http_only(url), timeout=timeout) as r, open(tmp, "wb") as f:  # noqa: S310 - scheme checked above; the URL comes from the recorded provenance  # nosec B310
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {h.hexdigest()}")
    tmp.replace(dest)


def download_raw(raw_dir: Path, subset_dir: Path) -> None:
    """Fetch the official metadata and electricity files named in the subset manifest and verify them."""
    man = json.loads((subset_dir / "subset_manifest.json").read_text())
    files = {}
    for rel, meta in man["taken_from"].items():
        print(f"downloading {rel} ({meta['bytes']:,} bytes) ...", flush=True)
        download_file(meta["url"], raw_dir / rel, meta["sha256"])
        files[rel] = {"url": meta["url"], "bytes": meta["bytes"], "sha256": meta["sha256"]}
    (raw_dir / "provenance.json").write_text(json.dumps({"source": man["source"], "downloaded_at": datetime.now(UTC).strftime("%Y-%m-%d"), "files": files}, indent=2) + "\n")


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# the independent cleaning rules
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def run_bounds(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start index and length of every run of equal consecutive values in a 1-D array without NaN."""
    n = len(a)
    if n == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    change = np.flatnonzero(a[1:] != a[:-1]) + 1
    starts = np.concatenate(([0], change))
    return starts, np.diff(np.concatenate((starts, [n])))


def stuck_mask(x: np.ndarray, min_hours: int) -> np.ndarray:
    """True where a reading belongs to a run of at least `min_hours` identical POSITIVE readings. A missing, zero or negative reading ends a run."""
    x = np.asarray(x, dtype=float)
    out = np.zeros(len(x), dtype=bool)
    if min_hours <= 1:
        return out
    p = np.where(x > 0, x, -1.0)
    for s, ln in zip(*run_bounds(p), strict=True):
        if p[s] != -1.0 and ln >= min_hours:
            out[s:s + ln] = True
    return out


def spike_limit(x: np.ndarray, cfg: dict) -> float | None:
    pos = np.asarray(x, dtype=float)
    pos = pos[pos > 0]
    if pos.size < cfg["spike_min_positive_readings"]:
        return None
    return float(cfg["spike_factor"] * np.quantile(pos, cfg["spike_quantile"]))


def clean_meter(raw: np.ndarray, cfg: dict | None = None) -> tuple[np.ndarray, dict]:
    """Layer 1 -> layer 2. Returns the cleaned array (invalid readings -> NaN, nothing else changed) and what each rule removed.

    A reading removed by several rules is counted once, in the order: negative, stuck sensor, spike. Zero readings are counted on their own."""
    cfg = cfg or SPEC["cleaning"]
    x = np.asarray(raw, dtype=float)
    missing = np.isnan(x)
    neg = x < 0
    zero = x == 0
    zero_len = np.zeros(len(x), dtype=int)
    for s, ln in zip(*run_bounds(zero), strict=True):
        if zero[s]:
            zero_len[s:s + ln] = ln
    long_zero = zero & (zero_len >= cfg["long_zero_hours"])
    short_zero = zero & ~long_zero
    stuck = stuck_mask(x, cfg["stuck_min_hours"])
    lim = spike_limit(x, cfg)
    spike = (x > lim) if lim is not None else np.zeros(len(x), dtype=bool)
    invalid = neg | stuck | spike | (zero if cfg["zero_is_invalid"] else False)
    cleaned = np.where(invalid, np.nan, x)
    counts = {
        "readings": int(len(x)), "missing_in_source": int(missing.sum()), "negative": int(neg.sum()),
        "zero_long_runs": int(long_zero.sum()), "zero_short": int(short_zero.sum()),
        "stuck_sensor": int((stuck & ~neg).sum()), "spike": int((spike & ~neg & ~stuck).sum()),
        "valid_out": int(np.isfinite(cleaned).sum()), "valid_share": float(np.isfinite(cleaned).mean()) if len(x) else 0.0,
        "spike_limit": lim,
    }
    return cleaned, counts


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# loading the raw data
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def load_raw(raw_dir: Path, subset_dir: Path, force_subset: bool = False) -> dict:
    """Return {'mode', 'metadata', 'elec', 'integrity': [checks], 'inputs': {...}}. Prefers the full official files, falls back to the subset."""
    full_elec = raw_dir / "data/meters/raw/electricity.csv"
    integrity: list[dict] = []
    inputs: dict[str, dict] = {}
    if full_elec.is_file() and not force_subset:
        prov = json.loads((raw_dir / "provenance.json").read_text())
        for rel, meta in prov["files"].items():
            got = sha256_file(raw_dir / rel)
            inputs[rel] = {"sha256": got, "bytes": (raw_dir / rel).stat().st_size, "url": meta.get("url")}
            integrity.append(_check("raw", f"integrity.sha256.{rel}", f"SHA-256 of {rel} equals the recorded value", got == meta["sha256"], f"expected {meta['sha256'][:16]}..., found {got[:16]}..."))
        md = pd.read_csv(raw_dir / "data/metadata/metadata.csv")
        elec = pd.read_csv(full_elec, parse_dates=["timestamp"], index_col="timestamp")
        return {"mode": "full", "metadata": md, "elec": elec, "integrity": integrity, "inputs": inputs, "source": prov["source"]}
    man_path = subset_dir / "subset_manifest.json"
    if not man_path.is_file():
        raise FileNotFoundError(f"neither {full_elec} nor {man_path} exists")
    man = json.loads(man_path.read_text())
    md_sha = sha256_file(subset_dir / "metadata.csv")
    official_md = man["taken_from"]["data/metadata/metadata.csv"]["sha256"]
    inputs["metadata.csv"] = {"sha256": md_sha, "bytes": (subset_dir / "metadata.csv").stat().st_size}
    integrity.append(_check("raw", "integrity.sha256.metadata.csv", "SHA-256 of metadata.csv equals the OFFICIAL BDG2 metadata hash", md_sha == official_md, f"expected {official_md[:16]}..., found {md_sha[:16]}..."))
    csv_bytes = gzip.open(subset_dir / "electricity_residential_meters.csv.gz").read()
    got = hashlib.sha256(csv_bytes).hexdigest()
    want = man["files"]["electricity_residential_meters.csv.gz"]["sha256_of_uncompressed_csv"]
    inputs["electricity_residential_meters.csv.gz"] = {"sha256_of_uncompressed_csv": got, "bytes": (subset_dir / "electricity_residential_meters.csv.gz").stat().st_size}
    integrity.append(_check("raw", "integrity.sha256.subset_csv", "SHA-256 of the extracted electricity subset equals the manifest value", got == want, f"expected {want[:16]}..., found {got[:16]}..."))
    elec = pd.read_csv(io.BytesIO(csv_bytes), parse_dates=["timestamp"], index_col="timestamp")
    return {"mode": "subset", "metadata": pd.read_csv(subset_dir / "metadata.csv"), "elec": elec, "integrity": integrity, "inputs": inputs, "source": man["source"],
            "manifest": man}


def _check(society: str, cid: str, desc: str, passed: bool, detail: str = "") -> dict:
    return {"society": society, "id": cid, "description": desc, "passed": bool(passed), "detail": detail}


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# selection and the independent society pipeline
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def selection_funnel(md: pd.DataFrame, columns, sel: dict | None = None) -> pd.DataFrame:
    """One row per building labelled with the primary use, with the reason it falls out (if it does) before cleaning."""
    sel = sel or SPEC["selection"]
    d = md[md["primaryspaceusage"] == sel["primary_use"]].copy()
    d["sub_use"] = d["sub_primaryspaceusage"].fillna("").str.strip()
    d["is_excluded_sub_use"] = d["sub_use"].isin(sel["exclude_sub_uses"])
    d["has_meter"] = d["building_id"].isin(set(columns))
    d["candidate"] = ~d["is_excluded_sub_use"] & d["has_meter"]
    return d.reset_index(drop=True)


def build_site(site: str, funnel: pd.DataFrame, elec: pd.DataFrame, sel: dict | None = None, cfg: dict | None = None) -> dict:
    """The whole pipeline for one BDG2 site, from raw readings to community demand."""
    sel, cfg = sel or SPEC["selection"], cfg or SPEC["cleaning"]
    cand = funnel[(funnel["site_id"] == site) & funnel["candidate"]]
    res: dict = {"site": site, "labelled": int((funnel["site_id"] == site).sum()),
                 "hotels_excluded": int(((funnel["site_id"] == site) & funnel["is_excluded_sub_use"]).sum()),
                 "no_meter": int(((funnel["site_id"] == site) & ~funnel["is_excluded_sub_use"] & ~funnel["has_meter"]).sum()),
                 "candidates": int(len(cand)), "qualifies": False, "reason": "no residential meters"}
    if cand.empty:
        return res
    ids = sorted(cand["building_id"])
    grid = elec.index
    raw = {b: elec[b].to_numpy(dtype=float) for b in ids}
    cleaned, counts = {}, {}
    for b in ids:
        cleaned[b], counts[b] = clean_meter(raw[b], cfg)
    kept = [b for b in ids if counts[b]["valid_share"] >= sel["min_meter_valid_share"]]
    res.update({"raw": raw, "cleaned_all": cleaned, "counts": counts, "kept": kept, "excluded": [b for b in ids if b not in kept], "grid": grid})
    res["meters_valid"] = len(kept)
    shares = [counts[b]["valid_share"] for b in ids]
    res["candidate_valid_share"] = {"min": float(min(shares)), "median": float(np.median(shares)), "max": float(max(shares))}
    res["candidate_removed"] = {k: int(sum(counts[b][k] for b in ids)) for k in RULE_COLUMNS}      # what the rules took out of ALL candidate meters of the site
    if len(kept) < sel["min_buildings"]:
        res["reason"] = f"only {len(kept)} meters pass the validity rule (need {sel['min_buildings']})"
        return res
    mat = np.column_stack([cleaned[b] for b in kept])
    total = mat.sum(axis=1)                      # NaN wherever any kept meter is NaN: no partial sums
    share = float(np.isfinite(total).mean())
    res.update({"matrix": mat, "total": pd.Series(total, index=grid, name="society_kwh"), "society_valid_share": share})
    if share < sel["min_society_valid_share"]:
        res["reason"] = f"society total valid in only {share:.1%} of hours"
        return res
    res.update({"qualifies": True, "reason": "accepted"})
    return res


def _maxdiff(a: np.ndarray, b: np.ndarray) -> tuple[float, bool]:
    """(largest absolute difference where both exist, whether the missing-value pattern is identical)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    same_pattern = bool(np.array_equal(np.isnan(a), np.isnan(b)))
    both = ~np.isnan(a) & ~np.isnan(b)
    return (float(np.abs(a[both] - b[both]).max()) if both.any() else 0.0), same_pattern


def missing_hours_summary(total: pd.Series, matrix: np.ndarray, kept: list[str]) -> dict:
    miss = ~np.isfinite(total.to_numpy())
    bounds = run_bounds(miss.astype(int))
    gaps = [(int(s), int(ln)) for s, ln in zip(*bounds, strict=True) if miss[s]]
    longest = max(gaps, key=lambda g: g[1]) if gaps else None
    nm = np.isnan(matrix)
    sole = {b: int((miss & (nm.sum(axis=1) == 1) & nm[:, i]).sum()) for i, b in enumerate(kept)}
    return {"hours": int(len(total)), "missing_hours": int(miss.sum()), "valid_hours": int((~miss).sum()), "gaps": len(gaps),
            "longest_gap_hours": longest[1] if longest else 0, "longest_gap_start": str(total.index[longest[0]]) if longest else None,
            "missing_per_meter": {b: int(nm[:, i].sum()) for i, b in enumerate(kept)}, "hours_blocked_only_by_meter": sole}


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# comparison with the application's processed files
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def load_processed(processed_dir: Path, key: str) -> dict:
    d = processed_dir / key
    ex_path = d / "excluded_meters.csv"
    excluded = pd.read_csv(ex_path) if ex_path.is_file() and ex_path.read_text().strip() else pd.DataFrame({"source_id": []})   # an empty file means no meter was excluded
    return {"buildings": pd.read_csv(d / "buildings.csv"), "excluded": excluded,
            "meters": pd.read_csv(d / "meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp"),
            "society": pd.read_csv(d / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp"),
            "report": json.loads((d / "cleaning_report.json").read_text())}


def verify_against_processed(key: str, res: dict, proc: dict, md: pd.DataFrame) -> tuple[list[dict], dict]:
    """All checks of independent pipeline `res` against the application's processed files `proc`. Returns (checks, details)."""
    chk: list[dict] = []
    add = lambda cid, desc, ok, detail="": chk.append(_check(key, f"{key}.{cid}", desc, ok, detail))  # noqa: E731
    b = proc["buildings"]
    src_of = dict(zip(b["code"], b["source_id"], strict=True))
    code_of = {v: k for k, v in src_of.items()}
    kept = res["kept"]
    details: dict = {}

    # --- selection (building level)
    add("selection.kept_buildings", "Buildings kept by the independent selection equal the application's buildings.csv", set(kept) == set(b["source_id"]),
        f"independent {len(kept)}, application {len(b)}; only independent: {sorted(set(kept) - set(b['source_id']))}; only application: {sorted(set(b['source_id']) - set(kept))}")
    ex_app = set(proc["excluded"]["source_id"])
    add("selection.excluded_meters", "Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv", set(res["excluded"]) == ex_app,
        f"independent {sorted(res['excluded'])}, application {sorted(ex_app)}")
    prefix = res["site"][:3].upper()
    expect_codes = [f"{prefix}-B{i + 1:02d}" for i in range(len(kept))]
    add("selection.building_codes", "Building codes follow the documented rule (site prefix, source ids sorted)", list(b["code"]) == expect_codes and list(b["source_id"]) == sorted(kept), "")
    mdi = md.set_index("building_id").loc[list(b["source_id"])]
    meta_ok = (np.allclose(b["floor_area_sqm"].to_numpy(float), mdi["sqm"].to_numpy(float), equal_nan=True, atol=0.06)
               and (b["sub_use"].fillna("").to_numpy() == mdi["sub_primaryspaceusage"].fillna("").str.strip().to_numpy()).all()
               and (mdi["primaryspaceusage"] == SPEC["selection"]["primary_use"]).all() and (mdi["site_id"] == res["site"]).all())
    add("buildings.metadata", "Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata", bool(meta_ok), "")
    sub_mix = b["sub_use"].fillna("").replace("", "(blank)").value_counts().to_dict()
    details["sub_use_mix"] = {str(k): int(v) for k, v in sub_mix.items()}

    # --- time grid
    pm, ps = proc["meters"], proc["society"]
    grid_ok = pm.index.equals(res["grid"]) and ps.index.equals(res["grid"]) and (np.diff(res["grid"].values) == np.timedelta64(1, "h")).all() and res["grid"].is_unique
    add("grid.complete", "Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp", bool(grid_ok), f"{len(res['grid']):,} hours, {res['grid'][0]} to {res['grid'][-1]}")

    # --- meter level
    per_meter, altered_total, mismatch_total, pattern_bad = [], 0, 0, []
    for src in kept:
        code = code_of.get(src)
        if code is None or code not in pm.columns:
            pattern_bad.append(src)
            continue
        p, r, c = pm[code].to_numpy(dtype=float), res["raw"][src], res["cleaned_all"][src]
        both = ~np.isnan(p)
        altered = int((np.abs(p[both] - r[both]) > ROUND_TOL).sum())
        diff, same = _maxdiff(p, c)
        if not same or diff > ROUND_TOL:
            pattern_bad.append(src)
        rep = proc["report"]["cleaning_counts_per_building"].get(code, {})
        mism = {k: (int(rep.get(k, -1)), int(res["counts"][src][k])) for k in ("missing_in_source", *RULE_COLUMNS, "valid_out") if int(rep.get(k, -1)) != int(res["counts"][src][k])}
        altered_total += altered
        mismatch_total += len(mism)
        per_meter.append({"code": code, "source_id": src, "sub_use": str(mdi.loc[src, "sub_primaryspaceusage"]) if src in mdi.index else "", **{k: res["counts"][src][k] for k in ("readings", "missing_in_source", *RULE_COLUMNS, "valid_out", "valid_share", "spike_limit")},
                          "stored_values_altered": altered, "max_abs_diff_vs_independent": diff, "count_mismatches_vs_application_report": mism})
    details["meters"] = per_meter
    add("meters.unaltered", "No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding", altered_total == 0,
        f"{altered_total} of {sum(m['valid_out'] for m in per_meter):,} stored meter values differ")
    add("meters.cleaned_equals_independent", "Application's cleaned meters equal the independently cleaned meters (same valid hours, same values)", not pattern_bad,
        f"meters that differ: {pattern_bad}" if pattern_bad else f"{len(per_meter)} meters identical in missing pattern and values")
    add("meters.removal_counts", "Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report", mismatch_total == 0,
        "no difference" if mismatch_total == 0 else "; ".join(f"{m['code']}: {m['count_mismatches_vs_application_report']}" for m in per_meter if m["count_mismatches_vs_application_report"]))

    # --- invalid readings left in the processed data
    neg = int((pm.to_numpy(float) < 0).sum())
    zero = int((pm.to_numpy(float) == 0).sum())
    stuck_left = sum(int(stuck_mask(pm[c].to_numpy(float), SPEC["cleaning"]["stuck_min_hours"]).sum()) for c in pm.columns)
    over = 0
    for src in kept:
        lim = res["counts"][src]["spike_limit"]
        if lim is not None and src in code_of and code_of[src] in pm.columns:
            over += int((pm[code_of[src]].to_numpy(float) > lim).sum())
    add("invalid.none_left", "The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading", neg == zero == stuck_left == over == 0,
        f"negative {neg}, zero {zero}, stuck {stuck_left}, spike {over}")

    # --- aggregation (community level)
    n = len(kept)
    tot_diff, tot_pattern = _maxdiff(ps["society_kwh"].to_numpy(float), res["total"].to_numpy(float))
    tol = ROUND_TOL * (n + 1)
    add("aggregate.total_equals_independent", "Application's community demand equals the independent sum of the cleaned meters, hour by hour", tot_pattern and tot_diff <= tol,
        f"largest hourly difference {tot_diff:.5f} kWh (allowed {tol:.4f} from 3-decimal storage); missing-hour pattern identical: {tot_pattern}")
    all_valid = ~np.isnan(pm.to_numpy(float)).any(axis=1)
    add("aggregate.no_partial_sums", "The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum)",
        bool(np.array_equal(~np.isnan(ps["society_kwh"].to_numpy(float)), all_valid)), f"{int(all_valid.sum()):,} hours with every meter valid")
    nv = ps["n_valid_meters"].to_numpy() if "n_valid_meters" in ps.columns else None
    add("aggregate.n_valid_meters", "n_valid_meters equals the number of non-missing meters in each hour", nv is not None and bool(np.array_equal(nv, (~np.isnan(pm.to_numpy(float))).sum(axis=1))), "")
    rep = proc["report"]
    add("aggregate.valid_hours", "Valid community hours and the 94 % rule agree with the application's cleaning report",
        int(np.isfinite(res["total"]).sum()) == int(rep["society_valid_hours"]) and res["society_valid_share"] >= SPEC["selection"]["min_society_valid_share"],
        f"independent {int(np.isfinite(res['total']).sum()):,} h ({res['society_valid_share']:.4f}), application {rep['society_valid_hours']:,} h")

    # --- recorded rules equal the SPEC
    rule_ok = all(rep["rule"][k] == SPEC["selection"][k] for k in PROCESSED_RULE_KEYS) and all(rep["cleaning"][k] == SPEC["cleaning"][k] for k in PROCESSED_CLEANING_KEYS)
    add("spec.rules_match", "Thresholds recorded in the application's cleaning report equal this script's SPEC", bool(rule_ok), "")

    # --- layers (informational numbers, not pass/fail)
    raw_mat = np.column_stack([res["raw"][s] for s in kept])
    naive = raw_mat.sum(axis=1)                                      # no cleaning at all; NaN if any raw reading is missing
    naive_ok, agg_ok = np.isfinite(naive), np.isfinite(res["total"].to_numpy())
    removed = {k: int(sum(res["counts"][s][k] for s in kept)) for k in ("missing_in_source", *RULE_COLUMNS)}
    layers = {
        "meters": n, "meter_hours": int(raw_mat.size),
        "raw_readings_present": int(np.isfinite(raw_mat).sum()), "raw_readings_missing": removed["missing_in_source"],
        "removed_by_rule": {k: removed[k] for k in RULE_COLUMNS},
        "cleaned_readings_valid": int(np.isfinite(res["matrix"]).sum()),
        "raw_naive_sum_hours": int(naive_ok.sum()), "community_valid_hours": int(agg_ok.sum()),
        "raw_naive_sum_kwh": float(naive[naive_ok].sum()), "community_demand_kwh": float(res["total"].sum()),
        "hours_in_naive_not_in_community": int((naive_ok & ~agg_ok).sum()),
        "kwh_in_those_hours": float(naive[naive_ok & ~agg_ok].sum()),
        "raw_naive_peak_kw": float(np.nanmax(naive)) if naive_ok.any() else None, "community_peak_kw": float(res["total"].max()),
    }
    details["layers"] = layers
    details["excluded_meters"] = [{"source_id": s, **{k: res["counts"][s][k] for k in ("valid_share", "missing_in_source", *RULE_COLUMNS, "valid_out")}} for s in res["excluded"]]
    details["missing"] = missing_hours_summary(res["total"], res["matrix"], kept)
    details["cleaning_thresholds_by_meter"] = {m["source_id"]: m["spike_limit"] for m in per_meter}
    return chk, details


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# comparison with the running application (API)
# ----------------------------------------------------------------------------------------------------------------------------------------------------
GetJson = Callable[[str, dict | None], dict | list]


def http_getter(base_url: str, email: str, password: str, timeout: int = 180) -> GetJson:
    """A `get_json(path, params)` that logs in over real HTTP (standard library only) and sends the bearer token."""
    base = base_url.rstrip("/")
    req = urllib.request.Request(_http_only(f"{base}/api/v1/auth/login"), data=json.dumps({"email": email, "password": password}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - the request URL was checked by _http_only  # nosec B310
        token = json.loads(r.read())["access_token"]

    def get(path: str, params: dict | None = None):
        url = f"{base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        with urllib.request.urlopen(urllib.request.Request(_http_only(url), headers={"Authorization": f"Bearer {token}"}), timeout=timeout) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read())
    return get


def compare_with_api(get: GetJson, results: dict[str, dict]) -> tuple[list[dict], dict]:
    """Community totals, valid hours, peak, every calendar month and every building: API against the independent pipeline (admin account needed for source ids)."""
    chk: list[dict] = []
    details: dict = {}
    listing = {s["key"]: s for s in get("/api/v1/societies", None)}
    for key, res in results.items():
        add = lambda cid, desc, ok, detail="", k=key: chk.append(_check(k, f"{k}.api.{cid}", desc, ok, detail))  # noqa: E731
        if key not in listing:
            add("present", "The society is loaded in the application", False, "not imported; import the bundled societies first")
            continue
        sid, n = listing[key]["id"], len(res["kept"])
        total = res["total"]
        valid = total.dropna()
        ov = get(f"/api/v1/societies/{sid}/overview", {"tariff_id": "demo"})["totals"]
        tol_hour = ROUND_TOL * (n + 1)
        tol_energy = tol_hour * len(valid)
        add("totals", "API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand",
            ov["hours"] == len(total) and ov["valid_hours"] == len(valid) and abs(ov["energy_kwh"] - valid.sum()) <= tol_energy and abs(ov["avg_kw"] - valid.mean()) <= tol_hour
            and abs(ov["peak_kw"] - valid.max()) <= tol_hour and ov["peak_ts"] == str(valid.idxmax()),
            f"energy API {ov['energy_kwh']:,.3f} vs independent {valid.sum():,.3f} kWh (diff {ov['energy_kwh'] - valid.sum():+.4f}, allowed {tol_energy:.2f}); valid hours {ov['valid_hours']:,} vs {len(valid):,}; "
            f"peak {ov['peak_kw']:,.3f} vs {valid.max():,.3f} kW at {ov['peak_ts']}")
        # every calendar month
        mon = get(f"/api/v1/societies/{sid}/consumption", {"resolution": "monthly"})["points"]
        m_energy = total.resample("MS").sum(min_count=1)
        m_valid = total.resample("MS").count()
        bad = []
        for p in mon:
            ts = pd.Timestamp(p["ts"])
            e_ref, v_ref = m_energy.get(ts, np.nan), int(m_valid.get(ts, 0))
            e_api = np.nan if p["energy_kwh"] is None else p["energy_kwh"]
            if p["valid_hours"] != v_ref or not (np.isnan(e_ref) and np.isnan(e_api) or abs(e_api - e_ref) <= tol_hour * max(v_ref, 1) + 0.0005):
                bad.append(str(ts.date()))
        add("monthly", "API monthly energy and valid hours equal the independent monthly sums for every calendar month", len(mon) == len(m_energy) and not bad,
            f"{len(mon)} months compared; differing months: {bad if bad else 'none'}")
        # every building
        bl = get(f"/api/v1/societies/{sid}/buildings", None)["buildings"]
        src_ok = all("source_id" in x for x in bl)
        bad_b, max_b = [], 0.0
        if src_ok:
            idx = {s: i for i, s in enumerate(res["kept"])}
            for x in bl:
                col = res["matrix"][:, idx[x["source_id"]]] if x["source_id"] in idx else None
                if col is None:
                    bad_b.append(x["source_id"])
                    continue
                v = col[np.isfinite(col)]
                d = abs((x["energy_kwh"] or 0.0) - float(v.sum()))
                max_b = max(max_b, d)
                if x["valid_hours"] != len(v) or d > ROUND_TOL * len(v) or abs((x["peak_kw"] or 0.0) - float(v.max())) > ROUND_TOL:
                    bad_b.append(x["source_id"])
        add("buildings", "API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view)", src_ok and len(bl) == n and not bad_b,
            f"{len(bl)} buildings compared, largest energy difference {max_b:.4f} kWh; differing: {bad_b if bad_b else 'none'}" if src_ok else "source_id not visible: use an admin account")
        details[key] = {"api_energy_kwh": ov["energy_kwh"], "independent_energy_kwh": float(valid.sum()), "api_valid_hours": ov["valid_hours"], "independent_valid_hours": int(len(valid)),
                        "api_peak_kw": ov["peak_kw"], "independent_peak_kw": float(valid.max()), "months_compared": len(mon), "buildings_compared": len(bl)}
    return chk, details


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# the whole run
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def run_verification(raw_dir: Path, subset_dir: Path, processed_dir: Path, *, api_get: GetJson | None = None, api_url: str | None = None, check_subset: bool = False,
                     only: list[str] | None = None, force_subset: bool = False) -> dict:
    raw = load_raw(raw_dir, subset_dir, force_subset)
    md, elec = raw["metadata"], raw["elec"]
    checks: list[dict] = list(raw["integrity"])
    grid = elec.index
    checks.append(_check("raw", "raw.grid", "Raw readings sit on one complete hourly grid (sorted, unique, 1-hour steps)", bool(grid.is_monotonic_increasing and grid.is_unique and (np.diff(grid.values) == np.timedelta64(1, "h")).all()),
                         f"{len(grid):,} hours, {grid[0]} to {grid[-1]}"))
    if check_subset and raw["mode"] == "full":
        sub = pd.read_csv(subset_dir / "electricity_residential_meters.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
        same = sub.index.equals(elec.index) and all(np.array_equal(sub[c].to_numpy(float), elec[c].to_numpy(float), equal_nan=True) for c in sub.columns)
        checks.append(_check("raw", "integrity.subset_equals_full", "The shipped raw subset equals the full official electricity file, value by value, for every column it contains", bool(same), f"{sub.shape[1]} columns, {len(sub):,} rows"))
    funnel = selection_funnel(md, elec.columns)
    sites = sorted(funnel["site_id"].unique())
    screening, results = [], {}
    for site in sites:
        res = build_site(site, funnel, elec)
        screening.append({k: res.get(k) for k in ("site", "labelled", "hotels_excluded", "no_meter", "candidates", "meters_valid", "society_valid_share", "qualifies", "reason", "candidate_valid_share", "candidate_removed")})
        if res["qualifies"]:
            results[site.lower()] = res
    catalogue = json.loads((processed_dir / "societies.json").read_text())["societies"]
    app_keys = sorted(s["key"] for s in catalogue)
    checks.append(_check("sites", "sites.accepted_match", "Sites accepted by the independent screening equal the communities in the application's catalogue", sorted(results) == app_keys,
                         f"independent {sorted(results)}; application {app_keys}"))
    societies: dict[str, dict] = {}
    for key in sorted(results):
        if only and key not in only:
            continue
        c, d = verify_against_processed(key, results[key], load_processed(processed_dir, key), md)
        checks.extend(c)
        societies[key] = {"site": results[key]["site"], "candidates": results[key]["candidates"], "buildings": len(results[key]["kept"]), **d}
    api_details, api_note = None, "not run (no --api-url given)"
    if api_get is None and api_url:
        api_get = http_getter(api_url, os.environ.get("ENERGIQ_VERIFY_EMAIL", ""), os.environ.get("ENERGIQ_VERIFY_PASSWORD", ""))
    if api_get is not None:
        c, api_details = compare_with_api(api_get, {k: results[k] for k in societies})
        checks.extend(c)
        api_note = f"run against {api_url or 'the supplied client'}"
    passed = sum(c["passed"] for c in checks)
    return {
        "meta": {"generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"), "mode": raw["mode"], "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                 "platform": platform.platform(), "script": "scripts/verify_society_raw_data.py", "script_sha256": sha256_file(Path(__file__)), "inputs": raw["inputs"],
                 "api_comparison": api_note, "subset_cross_check": "run" if (check_subset and raw["mode"] == "full") else "not run",
                 "raw_period": [str(grid[0]), str(grid[-1])], "raw_hours": int(len(grid)), "raw_meters_in_file": int(elec.shape[1]), "source": raw["source"]},
        "spec": SPEC,
        "funnel": {"labelled_residential": int(len(funnel)), "hotels_excluded": int(funnel["is_excluded_sub_use"].sum()), "no_meter": int((~funnel["is_excluded_sub_use"] & ~funnel["has_meter"]).sum()),
                   "candidates": int(funnel["candidate"].sum()), "sub_use_all_labelled": {str(k): int(v) for k, v in funnel["sub_use"].replace("", "(blank)").value_counts().items()}},
        "sites": screening, "societies": societies, "api": api_details, "checks": checks,
        "summary": {"checks": len(checks), "passed": int(passed), "failed": int(len(checks) - passed), "failed_ids": [c["id"] for c in checks if not c["passed"]]},
    }


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------------------------------------------------------------------------------
def _n(x, d=0):
    return "-" if x is None else f"{x:,.{d}f}"


def render_markdown(rep: dict) -> str:
    m, s, sp = rep["meta"], rep["summary"], rep["spec"]
    L: list[str] = []
    w = L.append
    w("# Raw-data verification report\n")
    w(f"Written by `{m['script']}` on {m['generated_at_utc']} UTC. **This file is generated; it is not edited by hand.** Re-create it with "
      "`python scripts/verify_society_end_to_end.py --check-subset` (starts a throw-away API and includes the live-API comparison) or with `python scripts/verify_society_raw_data.py` (files only).\n")
    mix: dict[str, int] = {}
    for v in rep["societies"].values():
        for k_, n_ in v["sub_use_mix"].items():
            mix[k_] = mix.get(k_, 0) + n_
    used = sum(mix.values())
    mix_txt = ", ".join(f"{n_} labelled `{k_}`" for k_, n_ in sorted(mix.items(), key=lambda kv: -kv[1]))
    w(f"> **What the data are.** BDG2 buildings labelled `Lodging/residential` include **student residence halls**. Of the {used} buildings used in the communities below, {mix_txt}. "
      "BDG2 does not describe the `Housing` and `Other - Lodging/Residential` labels further, so nothing here claims that they are family flats either. "
      "Each community is a group of real whole-building electricity meters. It is **not** data of family flats, **not** data of individual homes and **not** data of a registered housing society.\n")
    w("## 1. Verdict and inputs\n")
    verdict = "**all checks passed**" if s["failed"] == 0 else f"**{s['failed']} check(s) FAILED:** {', '.join(s['failed_ids'])}"
    w(f"{s['passed']} of {s['checks']} checks passed: {verdict}.\n")
    w("| Item | Value |\n|---|---|")
    w(f"| Raw input mode | `{m['mode']}` ({'full official files' if m['mode'] == 'full' else 'residential-labelled meters extracted unchanged from the official file (`data/society/raw_subset`)'}) |")
    w(f"| Raw period / hours / meters in the file | {m['raw_period'][0]} to {m['raw_period'][1]} / {m['raw_hours']:,} / {m['raw_meters_in_file']:,} |")
    w(f"| Comparison with the running API | {m['api_comparison']} |")
    w(f"| Subset compared with the full official file | {m['subset_cross_check']} |")
    w(f"| Verifier | `{m['script']}`, SHA-256 `{m['script_sha256'][:16]}...` ; Python {m['python']}, pandas {m['pandas']}, numpy {m['numpy']} |")
    w(f"| Source | {m['source']['name']}, {m['source']['license']} |\n")
    w("SHA-256 of the input files as hashed in this run:\n")
    w("| File | SHA-256 | Check |\n|---|---|---|")
    for c in (x for x in rep["checks"] if x["id"].startswith("integrity.sha256")):
        f = c["id"].replace("integrity.sha256.", "")
        h = m["inputs"].get(f, {})
        w(f"| `{f}` | `{h.get('sha256') or h.get('sha256_of_uncompressed_csv')}` | {'matches' if c['passed'] else 'DIFFERS'} |")
    w("")
    w("## 2. The four data layers\n")
    w("| Layer | What it is | Verified here? |\n|---|---|---|")
    w("| 1. Raw readings | BDG2 `electricity.csv` exactly as published, one value per meter and hour (kWh in that hour = average kW) | hashed (section 1) |")
    w("| 2. Cleaned readings | The raw readings with invalid ones set to missing. A reading is never changed, rounded beyond 3 decimals or filled in | re-done independently, compared value by value |")
    w("| 3. Aggregated community demand | Sum of the cleaned readings of the kept buildings; missing in any hour where one of them is missing | re-done independently, compared hour by hour |")
    w("| 4. ML predictions | Model forecasts of layer 3 | **not** verified here: they are estimates, not measurements (see `docs/society/RESULTS.md`) |\n")
    w("| Community | Meters | Meter-hours | Raw present | Missing in raw | Removed: negative | zero | stuck | spike | Cleaned valid | Hours with a community value | Community energy (kWh) |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k, v in rep["societies"].items():
        ly = v["layers"]
        rr = ly["removed_by_rule"]
        w(f"| {k} | {ly['meters']} | {ly['meter_hours']:,} | {ly['raw_readings_present']:,} | {ly['raw_readings_missing']:,} | {rr['negative']:,} | {rr['zero_long_runs'] + rr['zero_short']:,} | {rr['stuck_sensor']:,} | {rr['spike']:,} | {ly['cleaned_readings_valid']:,} | {ly['community_valid_hours']:,} of {v['missing']['hours']:,} | {ly['community_demand_kwh']:,.0f} |")
    w("\nEffect of cleaning on the community figures, compared with a plain sum of the raw meters with no cleaning at all (`naive`):\n")
    w("| Community | Hours with a naive raw sum | Hours with a community value | Hours only in the naive sum | Energy in those hours (kWh) | Naive peak (kW) | Community peak (kW) |\n|---|---:|---:|---:|---:|---:|---:|")
    for k, v in rep["societies"].items():
        ly = v["layers"]
        w(f"| {k} | {ly['raw_naive_sum_hours']:,} | {ly['community_valid_hours']:,} | {ly['hours_in_naive_not_in_community']:,} | {ly['kwh_in_those_hours']:,.0f} | {ly['raw_naive_peak_kw']:,.0f} | {ly['community_peak_kw']:,.0f} |")
    w("")
    w("## 3. Exclusion criteria and rejected sites\n")
    sel, cl = sp["selection"], sp["cleaning"]
    w("A building enters a community only if all of these hold (checked in this order):\n")
    w(f"1. its BDG2 metadata `primaryspaceusage` is `{sel['primary_use']}` (this label includes student residence halls);")
    w(f"2. its `sub_primaryspaceusage` is not one of {sel['exclude_sub_uses']} (whitespace stripped, blank allowed);")
    w("3. it has a column in the electricity file;")
    w(f"4. after cleaning, at least {sel['min_meter_valid_share']:.0%} of its hours are valid;")
    w(f"5. its site keeps at least {sel['min_buildings']} such buildings; and")
    w(f"6. at least {sel['min_society_valid_share']:.0%} of the site's hours have every kept meter valid.\n")
    f = rep["funnel"]
    w(f"Of {f['labelled_residential']} buildings labelled `{sel['primary_use']}` in the metadata, {f['hotels_excluded']} are hotels (excluded) and {f['no_meter']} have no electricity meter, leaving {f['candidates']} candidates. "
      f"Sub-use labels of all labelled buildings: {', '.join(f'{k} ({v})' for k, v in f['sub_use_all_labelled'].items())}.\n")
    w("| Site | Labelled residential | Hotels | No meter | Candidates | Candidate valid share after cleaning (min / median / max) | Readings removed in the candidates (negative / zero / stuck / spike) | Meters >= 95 % valid | Community valid share | Result |\n|---|---:|---:|---:|---:|---|---|---:|---:|---|")
    for x in rep["sites"]:
        share = "-" if x["society_valid_share"] is None else f"{x['society_valid_share']:.1%}"
        cs, cr = x.get("candidate_valid_share"), x.get("candidate_removed")
        cs_txt = "-" if not cs else f"{cs['min']:.1%} / {cs['median']:.1%} / {cs['max']:.1%}"
        cr_txt = "-" if not cr else f"{cr['negative']:,} / {cr['zero_long_runs'] + cr['zero_short']:,} / {cr['stuck_sensor']:,} / {cr['spike']:,}"
        w(f"| {x['site']} | {x['labelled']} | {x['hotels_excluded']} | {x['no_meter']} | {x['candidates']} | {cs_txt} | {cr_txt} | {x['meters_valid'] if x['meters_valid'] is not None else '-'} | {share} | {'**accepted**' if x['qualifies'] else 'rejected: ' + x['reason']} |")
    w("")
    w("Meters rejected by rule 4 inside accepted sites:\n")
    w("| Community | Meter | Valid share after cleaning | Missing in raw | Negative | Zero | Stuck | Spike | Reason |\n|---|---|---:|---:|---:|---:|---:|---:|---|")
    rows = [(k, e) for k, v in rep["societies"].items() for e in v["excluded_meters"]]
    for k, e in rows:
        w(f"| {k} | {e['source_id']} | {e['valid_share']:.1%} | {e['missing_in_source']:,} | {e['negative']:,} | {e['zero_long_runs'] + e['zero_short']:,} | {e['stuck_sensor']:,} | {e['spike']:,} | below the {sel['min_meter_valid_share']:.0%} rule |")
    if not rows:
        w("| (none) | | | | | | | | |")
    w("")
    w("## 4. Spike and stuck-sensor filtering\n")
    w("Applied to every meter separately, on the full 17,544-hour series, in this way:\n")
    w("| Rule | Definition | Threshold |\n|---|---|---|")
    w("| Missing | no value in the raw file | kept as missing |\n| Negative | reading below 0 | removed |")
    w(f"| Zero | reading exactly 0 kWh; labelled 'long' when the run of zeros lasts at least {cl['long_zero_hours']} h, otherwise 'short'; both are removed | `zero_is_invalid = {cl['zero_is_invalid']}` |")
    w(f"| Stuck sensor | a run of identical POSITIVE readings; a missing, zero or negative reading ends the run | at least {cl['stuck_min_hours']} consecutive hours |")
    w(f"| Spike | reading above {cl['spike_factor']} x the {cl['spike_quantile']:.1%} quantile (linear interpolation) of that meter's positive readings; applies only to meters with at least {cl['spike_min_positive_readings']} positive readings | {cl['spike_factor']} x p{cl['spike_quantile'] * 100:g} |")
    w("\nA reading hit by several rules is counted once, in the order negative, stuck, spike; zero readings are counted separately. Removed readings become missing; no value is replaced or interpolated.\n")
    w("## 5. Meter-level results\n")
    w("`Altered` is the number of stored values that differ from the raw reading of the same hour by more than the 3-decimal rounding (it must be 0). "
      "`Spike limit` is the value above which that meter's readings count as spikes. `Counts` says whether the independent removal counts equal the application's own cleaning report.\n")
    w("| Community | Code | Source id | Sub-use | Missing | Neg. | Zero | Stuck | Spike | Valid | Valid % | Spike limit (kWh/h) | Altered | Counts |\n|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k, v in rep["societies"].items():
        for mt in v["meters"]:
            w(f"| {k} | {mt['code']} | {mt['source_id']} | {mt['sub_use']} | {mt['missing_in_source']} | {mt['negative']} | {mt['zero_long_runs'] + mt['zero_short']} | {mt['stuck_sensor']} | {mt['spike']} | {mt['valid_out']:,} | {mt['valid_share']:.1%} | {_n(mt['spike_limit'], 0)} | {mt['stored_values_altered']} | {'equal' if not mt['count_mismatches_vs_application_report'] else 'DIFFER'} |")
    w("")
    w("## 6. Missing hours\n")
    w("An hour has no community value when at least one kept meter has no valid reading. `Blocked only by` lists the meter that is the single reason for most such hours.\n")
    w("| Community | Hours | With a value | Missing | Missing % | Gaps | Longest gap (h) | Starting | Blocked only by (hours) |\n|---|---:|---:|---:|---:|---:|---:|---|---|")
    for k, v in rep["societies"].items():
        ms = v["missing"]
        top = max(ms["hours_blocked_only_by_meter"].items(), key=lambda kv: kv[1])
        w(f"| {k} | {ms['hours']:,} | {ms['valid_hours']:,} | {ms['missing_hours']:,} | {100 * ms['missing_hours'] / ms['hours']:.2f} % | {ms['gaps']} | {ms['longest_gap_hours']} | {ms['longest_gap_start'] or '-'} | {top[0]} ({top[1]}) |")
    w("")
    w("## 7. Building mix of the accepted communities\n")
    w("| Community | Buildings | Sub-use labels in the BDG2 metadata |\n|---|---:|---|")
    for k, v in rep["societies"].items():
        w(f"| {k} | {v['buildings']} | {', '.join(f'{a} ({b})' for a, b in v['sub_use_mix'].items())} |")
    w("")
    w("## 8. Raw against application\n")
    pf = [c for c in rep["checks"] if c["society"] in rep["societies"] and c["id"].split(".", 1)[1].startswith(("meters.", "invalid.", "aggregate.", "grid.", "selection."))]
    pf_bad = [c["id"] for c in pf if not c["passed"]]
    w(f"**Processed files.** The independent pipeline was compared with the application's processed files on {len(pf)} checks (selection, time grid, every meter, invalid readings, community sum): "
      + ("all passed" if not pf_bad else f"**{len(pf_bad)} FAILED: {', '.join(pf_bad)}**") + ". Details are in section 10.\n")
    if rep["api"]:
        w("**Running API** (overview totals, every calendar month, every building):\n")
        w("| Community | API energy (kWh) | Independent energy (kWh) | Difference | API valid h | Independent valid h | API peak (kW) | Independent peak (kW) | Months | Buildings |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for k, d in rep["api"].items():
            w(f"| {k} | {d['api_energy_kwh']:,.3f} | {d['independent_energy_kwh']:,.3f} | {d['api_energy_kwh'] - d['independent_energy_kwh']:+.4f} | {d['api_valid_hours']:,} | {d['independent_valid_hours']:,} | {d['api_peak_kw']:,.3f} | {d['independent_peak_kw']:,.3f} | {d['months_compared']} | {d['buildings_compared']} |")
        w("")
    else:
        w("**Running API:** not compared in this run.\n")
    w("## 9. What this verification does not show\n")
    for t in ("It does not show that the BDG2 files are free of errors; they are hashed and used as published.",
              "It does not make the communities representative of family flats or of any registered housing society: they are groups of whole-building meters, mostly student residence halls (section 7), and this verification does not change that.",
              "It does not verify the weather columns, the forecasting models, their accuracy, the anomaly events, the tariff costs or the recommendations. Those are layer 4 or derived from layer 3 and are documented in `docs/society/RESULTS.md`.",
              "The cleaning thresholds are rules chosen for this project and documented in `docs/society/10_raw_data_verification.md`; the independent pipeline checks that they were applied as written, not that they are the best possible rules.",
              "In `subset` mode the SHA-256 of the full 174 MB electricity file is not re-checked (only the hash of the extracted subset and of the official metadata file). Run with the full files, or with `--check-subset`, for that."):
        w(f"* {t}")
    w("")
    w("## 10. All checks\n")
    w("| # | Scope | Check | Result | Detail |\n|---:|---|---|---|---|")
    for i, c in enumerate(rep["checks"], 1):
        w(f"| {i} | {c['society']} | `{c['id']}`: {c['description']} | {'PASS' if c['passed'] else '**FAIL**'} | {c['detail'].replace('|', '/')} |")
    w("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data/society/raw/bdg2", help="folder with the full official BDG2 files (default: data/society/raw/bdg2)")
    ap.add_argument("--subset", type=Path, default=ROOT / "data/society/raw_subset", help="folder with the shipped raw subset, used when the full files are absent")
    ap.add_argument("--processed", type=Path, default=ROOT / "data/society/processed")
    ap.add_argument("--download", action="store_true", help="download the official raw files into --raw first (needs internet; checks SHA-256)")
    ap.add_argument("--use-subset", action="store_true", help="use the subset even if the full files exist")
    ap.add_argument("--check-subset", action="store_true", help="also compare the subset with the full official file")
    ap.add_argument("--only", nargs="*", help="verify only these community keys, e.g. fox rat")
    ap.add_argument("--api-url", help="also compare with this running API; set ENERGIQ_VERIFY_EMAIL and ENERGIQ_VERIFY_PASSWORD (an admin account) in the environment")
    ap.add_argument("--email", help="admin e-mail for --api-url (alternative to ENERGIQ_VERIFY_EMAIL)")
    ap.add_argument("--out-md", type=Path, default=ROOT / "docs/society/VERIFICATION_REPORT.md")
    ap.add_argument("--out-json", type=Path, default=ROOT / "docs/society/verification_report.json")
    ap.add_argument("--no-report", action="store_true", help="print the summary only; do not write the report files")
    a = ap.parse_args()
    if a.email:
        os.environ["ENERGIQ_VERIFY_EMAIL"] = a.email
    try:
        if a.download:
            download_raw(a.raw, a.subset)
        rep = run_verification(a.raw, a.subset, a.processed, api_url=a.api_url, check_subset=a.check_subset, only=a.only, force_subset=a.use_subset)
    except FileNotFoundError as exc:
        print(f"inputs missing: {exc}\nUse --download for the official files, or keep data/society/raw_subset.", file=sys.stderr)
        return 2
    for c in rep["checks"]:
        if not c["passed"]:
            print(f"FAIL {c['id']}: {c['description']} | {c['detail']}")
    s = rep["summary"]
    print(f"mode={rep['meta']['mode']}  checks passed {s['passed']}/{s['checks']}  api={rep['meta']['api_comparison']}")
    if not a.no_report:
        a.out_json.write_text(json.dumps(rep, indent=1, default=lambda o: None if isinstance(o, float) and o != o else str(o)) + "\n")
        a.out_md.write_text(render_markdown(rep))
        print(f"wrote {a.out_md} and {a.out_json}")
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
