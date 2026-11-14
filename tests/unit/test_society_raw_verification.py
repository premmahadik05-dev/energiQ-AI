"""Tests of the independent raw-data verification (scripts/verify_society_raw_data.py).

Four groups:
  1. the checker's own logic, on tiny hand-made series (these are test inputs for the checker, not data of the project);
  2. the checker must CATCH tampering: a processed file or a raw file is altered and the right check has to fail;
  3. the real data: the independent pipeline, run on the shipped raw subset (and on the full official files when present), has to reproduce
     the application's processed files, and the committed report has to belong to this script and to have passed;
  4. the documentation: thresholds, rejected sites and the dataset disclosures are written down and agree with the script and the report.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify_society_raw_data.py"
SUBSET = REPO / "data" / "society" / "raw_subset"
FULL = REPO / "data" / "society" / "raw" / "bdg2"
PROCESSED = REPO / "data" / "society" / "processed"
DOC = REPO / "docs" / "society" / "10_raw_data_verification.md"
REPORT_MD = REPO / "docs" / "society" / "VERIFICATION_REPORT.md"
REPORT_JSON = REPO / "docs" / "society" / "verification_report.json"

_spec = importlib.util.spec_from_file_location("verify_society_raw_data", SCRIPT)
V = importlib.util.module_from_spec(_spec)
sys.modules["verify_society_raw_data"] = V
_spec.loader.exec_module(V)

have_subset = (SUBSET / "subset_manifest.json").is_file() and (PROCESSED / "societies.json").is_file()
needs_subset = pytest.mark.skipif(not have_subset, reason="raw subset or processed society data not present")


# ======================================================================================================================================================
# 1. the checker's logic
# ======================================================================================================================================================
def _noisy(n=500, seed=1, base=100.0):
    """A plausible-looking positive series with no repeated values, so that no rule fires by accident."""
    return base + np.random.default_rng(seed).uniform(0, 20, n)


def test_negative_and_zero_readings_are_removed_and_zero_runs_are_labelled():
    x = _noisy()
    x[10], x[20:23], x[100:130] = -5.0, 0.0, 0.0           # one negative, a short zero run (3 h), a long zero run (30 h)
    cleaned, c = V.clean_meter(x)
    assert np.isnan(cleaned[10]) and np.isnan(cleaned[20:23]).all() and np.isnan(cleaned[100:130]).all()
    assert (c["negative"], c["zero_short"], c["zero_long_runs"]) == (1, 3, 30)
    assert c["valid_out"] == 500 - 1 - 3 - 30


def test_stuck_rule_needs_48_identical_positive_readings_and_a_gap_ends_the_run():
    x = _noisy()
    x[0:48] = 77.0                                           # exactly 48 identical: stuck
    x[100:147] = 55.0                                        # 47 identical: not stuck
    x[200:224] = 33.0
    x[224] = np.nan                                          # a missing hour ends the run ...
    x[225:249] = 33.0                                        # ... so 24 + 24 identical readings are not stuck
    cleaned, c = V.clean_meter(x)
    assert np.isnan(cleaned[0:48]).all() and c["stuck_sensor"] == 48
    assert np.isfinite(cleaned[100:147]).all() and np.isfinite(cleaned[200:224]).all() and np.isfinite(cleaned[225:249]).all()
    assert V.stuck_mask(np.array([5.0] * 48), 48).all() and not V.stuck_mask(np.array([5.0] * 47), 48).any()
    assert not V.stuck_mask(np.zeros(100), 48).any(), "a run of zeros is a zero run, not a stuck sensor"


def test_spike_rule_is_four_times_the_995_quantile_of_positive_readings():
    x = _noisy(1000)                                         # values between 100 and 120, so the limit is about 480
    x[500], x[600] = 5000.0, 400.0                           # one clear spike, one large but legitimate reading below the limit
    cleaned, c = V.clean_meter(x)
    assert c["spike_limit"] == pytest.approx(4.0 * np.quantile(x[x > 0], 0.995))
    assert 380 < c["spike_limit"] < 520 and np.isnan(cleaned[500]) and cleaned[600] == 400.0 and c["spike"] == 1
    few = _noisy(99)
    few[5] = 1e6
    assert V.spike_limit(few, V.SPEC["cleaning"]) is None and np.isfinite(V.clean_meter(few)[0][5]), "fewer than 100 positive readings: the spike rule does not apply"
    assert V.spike_limit(_noisy(100), V.SPEC["cleaning"]) is not None


def test_cleaning_only_removes_and_never_changes_a_reading():
    rng = np.random.default_rng(7)
    x = rng.uniform(1, 200, 3000)
    x[rng.integers(0, 3000, 40)] = 0.0
    x[rng.integers(0, 3000, 10)] = np.nan
    x[rng.integers(0, 3000, 5)] = -1.0
    x[1000:1060] = 42.5
    x[2000] = 1e5
    cleaned, c = V.clean_meter(x)
    keep = np.isfinite(cleaned)
    assert np.array_equal(cleaned[keep], x[keep]), "every kept reading must equal the raw reading"
    assert c["valid_out"] == int(keep.sum()) and c["valid_out"] < 3000


def test_a_reading_hit_by_several_rules_is_counted_once_as_stuck_then_spike():
    x = _noisy(20000)                                        # long enough that 60 readings are well under 0.5 % of the series
    x[10:70] = 1e4                                           # 60 identical readings that are ALSO far above the spike limit
    cleaned, c = V.clean_meter(x)
    assert np.isnan(cleaned[10:70]).all()
    assert (c["stuck_sensor"], c["spike"], c["negative"]) == (60, 0, 0), "counted once, as stuck"
    y = _noisy(20000)
    y[500] = 1e4                                             # a lone spike is a spike
    assert V.clean_meter(y)[1]["spike"] == 1


def _toy_world(n_good=9, low_quality=0, hotel=False, no_meter=False, bad_share=False, hours=800):
    """A made-up site 'Toy' for the selection tests: metadata plus an electricity table."""
    idx = pd.date_range("2016-01-01", periods=hours, freq="h")
    rng = np.random.default_rng(3)
    rows, cols = [], {}
    total = n_good + low_quality
    for i in range(total):
        bid = f"Toy_lodging_{i:02d}"
        rows.append({"building_id": bid, "site_id": "Toy", "primaryspaceusage": "Lodging/residential", "sub_primaryspaceusage": "Dormitory" if i % 2 else None})
        v = 50 + rng.uniform(0, 10, hours)
        if i >= n_good:
            v[: int(hours * 0.2)] = np.nan                 # a meter with only 80 % valid hours
        if bad_share and i < 3:
            v[(i * 100): (i * 100 + 36)] = np.nan          # three meters at 95.5 % valid (kept), each missing different hours -> community valid share about 86 %
        cols[bid] = v
    if hotel:
        rows.append({"building_id": "Toy_hotel", "site_id": "Toy", "primaryspaceusage": "Lodging/residential", "sub_primaryspaceusage": " Hotel\t"})
        cols["Toy_hotel"] = 50 + rng.uniform(0, 10, hours)
    if no_meter:
        rows.append({"building_id": "Toy_nometer", "site_id": "Toy", "primaryspaceusage": "Lodging/residential", "sub_primaryspaceusage": None})
    rows.append({"building_id": "Toy_office", "site_id": "Toy", "primaryspaceusage": "Office", "sub_primaryspaceusage": None})
    cols["Toy_office"] = 50 + rng.uniform(0, 10, hours)
    return pd.DataFrame(rows), pd.DataFrame(cols, index=idx)


def test_selection_ignores_other_uses_hotels_and_buildings_without_a_meter():
    md, elec = _toy_world(hotel=True, no_meter=True)
    f = V.selection_funnel(md, elec.columns)
    assert len(f) == 9 + 2                                   # nine dormitories, the hotel and the building without a meter; the office is not residential
    assert int(f["is_excluded_sub_use"].sum()) == 1, "' Hotel\\t' must be recognised after stripping whitespace"
    assert int((~f["is_excluded_sub_use"] & ~f["has_meter"]).sum()) == 1
    assert int(f["candidate"].sum()) == 9 and "Toy_office" not in set(f["building_id"])


def test_site_qualifies_only_with_eight_good_meters_and_94_percent_community_hours():
    md, elec = _toy_world(n_good=9, low_quality=2)
    res = V.build_site("Toy", V.selection_funnel(md, elec.columns), elec)
    assert res["qualifies"] and len(res["kept"]) == 9 and len(res["excluded"]) == 2, "meters below 95 % valid hours are dropped, not the whole site"
    md, elec = _toy_world(n_good=7)
    res = V.build_site("Toy", V.selection_funnel(md, elec.columns), elec)
    assert not res["qualifies"] and "only 7 meters" in res["reason"]
    md, elec = _toy_world(n_good=9, bad_share=True)
    res = V.build_site("Toy", V.selection_funnel(md, elec.columns), elec)
    assert not res["qualifies"] and "society total valid in only" in res["reason"], res["reason"]


def test_community_total_is_the_sum_of_cleaned_meters_and_missing_when_any_meter_is_missing():
    md, elec = _toy_world(n_good=9)
    elec.iloc[5, 0] = np.nan                                 # one meter has no reading in hour 5
    res = V.build_site("Toy", V.selection_funnel(md, elec.columns), elec)
    total = res["total"].to_numpy()
    assert np.isnan(total[5]), "no partial sum"
    ok = np.isfinite(total)
    assert np.allclose(total[ok], res["matrix"][ok].sum(axis=1)) and ok.sum() == len(total) - 1
    summ = V.missing_hours_summary(res["total"], res["matrix"], res["kept"])
    assert summ["missing_hours"] == 1 and summ["gaps"] == 1 and summ["longest_gap_hours"] == 1
    assert summ["hours_blocked_only_by_meter"][res["kept"][0]] == 1


def _serve(directory):
    """A real HTTP server on localhost serving `directory`, so that the download is tested over HTTP and not through a file: URL."""
    import functools
    import http.server
    import threading

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_sha256_and_download_refuse_a_file_that_does_not_match(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    src = served / "source.csv"
    src.write_bytes(b"timestamp,a\n2016-01-01 00:00:00,1.5\n")
    good = hashlib.sha256(src.read_bytes()).hexdigest()
    assert V.sha256_file(src) == good
    server = _serve(served)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/source.csv"
        dest = tmp_path / "out" / "copy.csv"
        V.download_file(url, dest, good)
        assert dest.read_bytes() == src.read_bytes()
        bad_dest = tmp_path / "out" / "bad.csv"
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            V.download_file(url, bad_dest, "0" * 64)
        assert not bad_dest.exists() and not bad_dest.with_suffix(".csv.part").exists(), "a file that fails the hash must not be left behind"
    finally:
        server.shutdown()
        server.server_close()


def test_the_verifier_only_opens_http_and_https_urls(tmp_path):
    """urlopen would also read local files (file:) and custom schemes; a recorded URL must never be able to make the verifier do that (bandit B310)."""
    src = tmp_path / "source.csv"
    src.write_bytes(b"x")
    for url in (src.as_uri(), "ftp://example.org/x.csv", "gopher://example.org/x"):
        with pytest.raises(ValueError, match="only http and https"):
            V.download_file(url, tmp_path / "out" / "x.csv", "0" * 64)
    with pytest.raises(ValueError, match="only http and https"):
        V.http_getter(src.as_uri(), "a@b.c", "pw")


def test_the_verifier_imports_nothing_from_the_application():
    """The independence requirement: only the standard library, numpy and pandas."""
    tree = ast.parse(SCRIPT.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    allowed = set(sys.stdlib_module_names) | {"numpy", "pandas"}
    assert mods <= allowed, f"unexpected imports: {sorted(mods - allowed)}"
    assert not ({"ml_engine", "backend", "scripts"} & mods)
    sub_tree = ast.parse((REPO / "scripts" / "society_make_raw_subset.py").read_text())
    sub_mods = {a.name.split(".")[0] for n in ast.walk(sub_tree) if isinstance(n, ast.Import) for a in n.names} | {n.module.split(".")[0] for n in ast.walk(sub_tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert sub_mods <= allowed, f"the subset extractor imports {sorted(sub_mods - allowed)}"


def test_spec_equals_the_defaults_of_the_application():
    """Drift guard. The verifier hard-codes its rules; if the application's defaults change, this fails until both and the documentation agree."""
    from ml_engine.society.aggregate import SocietyRule
    from ml_engine.society.cleaning import CleaningConfig

    rule, cfg = SocietyRule().to_dict(), CleaningConfig().to_dict()
    for k in V.PROCESSED_RULE_KEYS:
        assert rule[k] == V.SPEC["selection"][k], k
    for k in V.PROCESSED_CLEANING_KEYS:
        assert cfg[k] == V.SPEC["cleaning"][k], k
    assert V.SPEC["storage_decimals"] == 3


# ======================================================================================================================================================
# 2. the checker must catch tampering
# ======================================================================================================================================================
@pytest.fixture(scope="module")
def baseline():
    if not have_subset:
        pytest.skip("raw subset not present")
    rep = V.run_verification(FULL, SUBSET, PROCESSED, only=["fox"], force_subset=True)
    assert rep["summary"]["failed"] == 0, rep["summary"]["failed_ids"]
    return rep


@pytest.fixture
def fox_copy(tmp_path, baseline):
    """A scratch copy of the processed data (catalogue + Fox) that a test may damage."""
    dst = tmp_path / "processed"
    shutil.copytree(PROCESSED / "fox", dst / "fox")
    shutil.copyfile(PROCESSED / "societies.json", dst / "societies.json")
    return dst


def _failed(processed, only=("fox",), subset=SUBSET):
    rep = V.run_verification(FULL, subset, processed, only=list(only), force_subset=True)
    return {c["id"] for c in rep["checks"] if not c["passed"]}


def _first_valid(series: pd.Series, start: int) -> int:
    """Index of the first non-missing value at or after `start` (an edit of a missing value would change nothing)."""
    return int(series.index[(series.index >= start) & series.notna()][0])


def _edit_csv(path, fn):
    df = pd.read_csv(path)
    out = fn(df)                                             # `fn` either changes `df` in place or returns a new frame
    (df if out is None else out).to_csv(path, index=False)


@needs_subset
def test_a_changed_meter_value_is_detected(fox_copy):
    p = fox_copy / "fox" / "meters_hourly_kwh.csv.gz"
    def change(d):
        i = _first_valid(d["FOX-B01"], 3000)
        d.loc[i, "FOX-B01"] += 1.0
    _edit_csv(p, change)
    bad = _failed(fox_copy)
    assert {"fox.meters.unaltered", "fox.meters.cleaned_equals_independent"} <= bad


@needs_subset
def test_a_reading_that_should_have_been_removed_is_detected(fox_copy):
    p = fox_copy / "fox" / "meters_hourly_kwh.csv.gz"
    _edit_csv(p, lambda d: d.__setitem__("FOX-B02", d["FOX-B02"].where(d.index != 100, -4.0)))   # a negative reading in hour 100
    assert "fox.invalid.none_left" in _failed(fox_copy)


@needs_subset
def test_a_partial_community_sum_is_detected(fox_copy):
    s = pd.read_csv(fox_copy / "fox" / "society_hourly.csv.gz")
    miss = s.index[s["society_kwh"].isna()][0]
    s.loc[miss, "society_kwh"] = 500.0                       # a value in an hour where a meter has no reading
    s.to_csv(fox_copy / "fox" / "society_hourly.csv.gz", index=False)
    bad = _failed(fox_copy)
    assert {"fox.aggregate.no_partial_sums", "fox.aggregate.total_equals_independent"} <= bad


@needs_subset
def test_a_changed_community_total_is_detected(fox_copy):
    s = pd.read_csv(fox_copy / "fox" / "society_hourly.csv.gz")
    s.loc[_first_valid(s["society_kwh"], 1234), "society_kwh"] += 0.5
    s.to_csv(fox_copy / "fox" / "society_hourly.csv.gz", index=False)
    assert "fox.aggregate.total_equals_independent" in _failed(fox_copy)


@needs_subset
def test_a_missing_building_is_detected(fox_copy):
    _edit_csv(fox_copy / "fox" / "buildings.csv", lambda d: d.iloc[:-1])
    assert {"fox.selection.kept_buildings", "fox.selection.building_codes"} <= _failed(fox_copy)


@needs_subset
def test_a_meter_that_the_application_forgot_to_exclude_is_detected(fox_copy):
    p = fox_copy / "fox" / "excluded_meters.csv"
    assert "Fox_lodging_Warren" in p.read_text()             # the meter that falls below the 95 % rule in the real data
    p.write_text(",".join(p.read_text().splitlines()[0].split(",")) + "\n")   # header only: the application reports no excluded meter
    assert "fox.selection.excluded_meters" in _failed(fox_copy)


@needs_subset
def test_a_wrong_cleaning_count_in_the_application_report_is_detected(fox_copy):
    p = fox_copy / "fox" / "cleaning_report.json"
    rep = json.loads(p.read_text())
    rep["cleaning_counts_per_building"]["FOX-B01"]["spike"] += 1
    p.write_text(json.dumps(rep))
    assert "fox.meters.removal_counts" in _failed(fox_copy)


@needs_subset
def test_a_changed_threshold_in_the_application_report_is_detected(fox_copy):
    p = fox_copy / "fox" / "cleaning_report.json"
    rep = json.loads(p.read_text())
    rep["cleaning"]["stuck_min_hours"] = 24
    p.write_text(json.dumps(rep))
    assert "fox.spec.rules_match" in _failed(fox_copy)


@needs_subset
def test_a_changed_raw_file_is_detected_by_its_hash(tmp_path, baseline):
    sub = tmp_path / "subset"
    shutil.copytree(SUBSET, sub)
    raw = pd.read_csv(sub / "electricity_residential_meters.csv.gz", dtype=str, keep_default_na=False)
    raw.iloc[100, 5] = "999.9"
    raw.to_csv(sub / "electricity_residential_meters.csv.gz", index=False)
    rep = V.run_verification(FULL, sub, PROCESSED, only=["fox"], force_subset=True)
    failed = {c["id"] for c in rep["checks"] if not c["passed"]}
    assert "integrity.sha256.subset_csv" in failed
    metadata_only = tmp_path / "subset2"
    shutil.copytree(SUBSET, metadata_only)
    (metadata_only / "metadata.csv").write_text((SUBSET / "metadata.csv").read_text().replace("Lodging/residential", "Office", 1))
    assert "integrity.sha256.metadata.csv" in {c["id"] for c in V.run_verification(FULL, metadata_only, PROCESSED, only=["fox"], force_subset=True)["checks"] if not c["passed"]}


# ======================================================================================================================================================
# 3. the real data
# ======================================================================================================================================================
@pytest.fixture(scope="module")
def real():
    if not have_subset:
        pytest.skip("raw subset not present")
    return V.run_verification(FULL, SUBSET, PROCESSED, force_subset=True)


@needs_subset
def test_independent_pipeline_reproduces_every_processed_community(real):
    failed = [c["id"] for c in real["checks"] if not c["passed"]]
    assert not failed, failed
    assert real["meta"]["mode"] == "subset" and real["summary"]["checks"] >= 100
    catalogue = json.loads((PROCESSED / "societies.json").read_text())["societies"]
    assert sorted(real["societies"]) == sorted(s["key"] for s in catalogue)
    for s in catalogue:
        mine = real["societies"][s["key"]]
        assert mine["buildings"] == s["buildings"], s["key"]
        assert mine["layers"]["community_valid_hours"] == s["valid_hours"], s["key"]


@needs_subset
def test_sites_that_were_left_out_are_left_out_for_the_documented_reasons(real):
    by = {x["site"]: x for x in real["sites"]}
    assert {k for k, x in by.items() if x["qualifies"]} == {"Bull", "Eagle", "Fox", "Hog", "Peacock", "Rat", "Robin"}
    for site in ("Bear", "Bobcat", "Cockatoo", "Lamb", "Panther"):
        assert not by[site]["qualifies"] and "meters pass the validity rule" in by[site]["reason"], site
    assert by["Bear"]["meters_valid"] == 3 and by["Panther"]["meters_valid"] == 0 and by["Cockatoo"]["meters_valid"] == 0
    assert by["Mouse"]["reason"] == "no residential meters" and by["Mouse"]["hotels_excluded"] == 1
    assert real["funnel"]["labelled_residential"] == 168 and real["funnel"]["hotels_excluded"] == 3 and real["funnel"]["no_meter"] == 19


@needs_subset
def test_the_four_layers_are_consistent_with_each_other(real):
    for key, v in real["societies"].items():
        ly = v["layers"]
        removed = sum(ly["removed_by_rule"].values())
        assert ly["raw_readings_present"] + ly["raw_readings_missing"] == ly["meter_hours"], key
        assert ly["cleaned_readings_valid"] == ly["raw_readings_present"] - removed, f"{key}: every raw reading is either kept or removed by exactly one rule"
        assert ly["community_valid_hours"] + ly["hours_in_naive_not_in_community"] == ly["raw_naive_sum_hours"], f"{key}: cleaning can only take hours away"
        assert v["missing"]["valid_hours"] + v["missing"]["missing_hours"] == v["missing"]["hours"] == 17544, key
        assert ly["community_peak_kw"] <= ly["raw_naive_peak_kw"] + 1e-6, "cleaning can only lower the peak"
    # the case where cleaning matters: Bull's plain sum of raw meters peaks above 13,000 kW, its cleaned community demand below 5,000 kW
    bull = real["societies"]["bull"]["layers"]
    assert bull["raw_naive_peak_kw"] > 2 * bull["community_peak_kw"] and bull["raw_naive_peak_kw"] > 13000 > 5000 > bull["community_peak_kw"]


@pytest.mark.skipif(not (FULL / "data/meters/raw/electricity.csv").is_file() or not have_subset, reason="the full official BDG2 files are not present (about 194 MB; python scripts/verify_society_raw_data.py --download)")
def test_full_official_files_pass_all_checks_and_contain_the_subset():
    rep = V.run_verification(FULL, SUBSET, PROCESSED, check_subset=True)
    assert rep["meta"]["mode"] == "full" and rep["meta"]["raw_meters_in_file"] == 1578
    assert [c for c in rep["checks"] if not c["passed"]] == []
    assert any(c["id"] == "integrity.subset_equals_full" and c["passed"] for c in rep["checks"])


@needs_subset
def test_subset_manifest_is_complete_and_unchanged():
    man = json.loads((SUBSET / "subset_manifest.json").read_text())
    assert man["buildings_labelled_residential_in_metadata"] == 168 and man["buildings_with_an_electricity_meter"] == 149 == len(man["columns"])
    assert man["rows"] == 17544 and "ShareAlike" in man["license_note"]
    assert (SUBSET / "LICENSE").is_file()
    for rel, meta in man["taken_from"].items():
        assert len(meta["sha256"]) == 64 and meta["url"].startswith("https://"), rel


@needs_subset
def test_committed_report_belongs_to_this_script_and_passed():
    """The report in the repository must come from the script as it is shipped, from a run in which nothing failed."""
    rep = json.loads(REPORT_JSON.read_text())
    assert rep["summary"]["failed"] == 0 and rep["summary"]["passed"] == rep["summary"]["checks"] > 100
    assert rep["meta"]["script_sha256"] == V.sha256_file(SCRIPT), "scripts/verify_society_raw_data.py changed after the report was generated: re-run scripts/verify_society_end_to_end.py"
    assert rep["spec"] == json.loads(json.dumps(V.SPEC))
    assert rep["meta"]["mode"] in ("full", "subset") and rep["meta"]["raw_hours"] == 17544
    md = REPORT_MD.read_text()
    assert f"{rep['summary']['passed']} of {rep['summary']['checks']} checks passed" in md and "generated; it is not edited by hand" in md
    assert V.render_markdown(rep) == md, "the Markdown report must be exactly what the script renders from the JSON report"


# ======================================================================================================================================================
# 4. documentation and disclosures
# ======================================================================================================================================================
def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, f"section '{heading}' not found"
    return m.group(1)


def test_documented_thresholds_equal_the_scripts_spec():
    doc = DOC.read_text()
    block = re.search(r"```json spec\n(.*?)\n```", doc, re.S)
    assert block, "the documentation must contain the machine-readable ```json spec block"
    assert json.loads(block.group(1)) == json.loads(json.dumps(V.SPEC))


@needs_subset
def test_documentation_lists_every_rejected_site_and_no_accepted_one():
    rep = json.loads(REPORT_JSON.read_text())
    rejected = {x["site"] for x in rep["sites"] if not x["qualifies"]}
    accepted = {x["site"] for x in rep["sites"] if x["qualifies"]}
    sec = _section(DOC.read_text(), "Rejected sites")
    for site in rejected:
        assert re.search(rf"\|\s*{site}\s*\|", sec), f"rejected site {site} missing from the documentation"
    for site in accepted:
        assert not re.search(rf"\|\s*{site}\s*\|", sec), f"accepted site {site} listed as rejected"


def test_dataset_disclosures_are_in_the_readme_the_method_document_and_the_report():
    needles = [("student residence halls", True), ("family flats", True), ("registered housing society", True)]
    for path in (REPO / "README.md", DOC, REPORT_MD, REPO / "docs" / "society" / "02_data_sources.md"):
        text = re.sub(r"\s+", " ", path.read_text()).lower()
        for needle, _ in needles:
            assert needle in text, f"{path.relative_to(REPO)} does not mention '{needle}'"
        assert re.search(r"not[^.|]{0,80}(family flats|registered housing society)", text), f"{path.relative_to(REPO)} does not say the data are NOT family-flat or registered-society data"


def test_no_document_describes_the_data_as_family_flats_or_a_real_housing_society():
    """Guard against over-claiming: any sentence that uses these phrases has to negate them."""
    bad = []
    for path in [REPO / "README.md", DOC, REPORT_MD, *sorted((REPO / "docs" / "society").glob("*.md"))]:
        for sent in re.split(r"(?<=[.!?])\s+|\n", path.read_text()):
            s = sent.lower()
            if re.search(r"(family flats?|registered housing society|real housing society|individual homes)", s) and not re.search(r"\b(not|no|nor|neither|without|never|cannot|n't)\b", s):
                bad.append(f"{path.relative_to(REPO)}: {sent.strip()[:140]}")
    assert not bad, "\n".join(bad)
