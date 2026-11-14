# 10. Independent verification of the society data from the raw BDG2 files

This document explains how the society data are checked, from the raw Building Data Genome Project 2 (BDG2) files to the numbers the application shows, by a separate program that
shares no code with the application. The latest result is in the generated [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) (machine-readable: [verification_report.json](verification_report.json)).
The numbers in the tables below are copied from that report; nothing here is estimated.

## Result of the committed run

**127 of 127 checks passed, none failed.** Run on 2026-11-08 12:14:54 UTC with the full official files (`full` mode), the shipped raw subset compared with the full file value by value, and the
running API compared with the independent computation (overview totals, all 24 calendar months and every building of all 7 communities). The verifier script had SHA-256 `cad71f70088a2f3392d5d87a52bc119b8447dab58f8764951e0e4fd9f3aa4df8`; Python 3.11.15, pandas 3.1.0, numpy 2.4.6.

What this proves: the numbers the application stores and serves follow, by the documented rules, from the raw files. What it does not prove is listed in [Limits of this verification](#limits-of-this-verification).

## What the data are, and what they are not

* BDG2 buildings whose metadata primary use is `Lodging/residential` **include student residence halls**. Of the 73 buildings used in the seven communities, **56 carry the BDG2 sub-use label `Dormitory`**,
  8 carry `Housing` (all of Eagle) and 9 carry `Other - Lodging/Residential` (all of Rat). BDG2 does not describe the last two labels further, so nothing here claims that they are family flats either.
* The seven communities are therefore **research-based representative communities**: groups of real whole-building electricity meters of residential-use buildings, summed per hour. They are **not** data of family flats,
  **not** data of individual homes and **not** data of a registered housing society, and no result from them says anything about those. Lifts, water pumps, street lighting and a clubhouse are not metered in this data.
* The community is this project's construction. Every reading underneath it is a real BDG2 measurement.

| Community | BDG2 site | Buildings | Sub-use labels in the BDG2 metadata |
|---|---|---:|---|
| bull | Bull | 16 | Dormitory (16) |
| eagle | Eagle | 8 | Housing (8) |
| fox | Fox | 11 | Dormitory (11) |
| hog | Hog | 10 | Dormitory (10) |
| peacock | Peacock | 11 | Dormitory (11) |
| rat | Rat | 9 | Other - Lodging/Residential (9) |
| robin | Robin | 8 | Dormitory (8) |

## The four data layers

The verification, the application and the documents keep these apart. They are four different things and are never mixed in one number.

| Layer | What it is | Where it lives | Verified by this process? |
|---|---|---|---|
| 1. **Raw readings** | BDG2 `electricity.csv` exactly as published: kWh per meter and hour (numerically the average kW of that hour), with gaps, zeros and sensor faults left in | `data/society/raw/bdg2/` (full, not shipped in the ZIP) and `data/society/raw_subset/` (shipped) | **Yes**, by SHA-256 and by reading it |
| 2. **Cleaned readings** | The raw readings with invalid ones set to *missing*. A reading is never changed, filled in or interpolated; stored with 3 decimals | `data/society/processed/<key>/meters_hourly_kwh.csv.gz` | **Yes**, re-done independently and compared value by value |
| 3. **Aggregated community demand** | The sum of the cleaned readings of the kept buildings in each hour; **missing** in every hour where any kept building is missing (no partial sums) | `data/society/processed/<key>/society_hourly.csv.gz`, the database, the API overview, consumption and buildings pages | **Yes**, re-done independently and compared hour by hour, and against the running API |
| 4. **ML predictions** | Forecasts, prediction bands, backtests and SHAP values of trained models for layer 3; anomaly alerts and costs derived from layers 3 and 4 | `artifacts/society/`, the forecast, backtest, alerts and cost pages | **No.** They are estimates, not measurements; their accuracy is reported in [RESULTS.md](RESULTS.md) |

Cleaning removes readings, so layer 2 has fewer values than layer 1, and layer 3 has fewer hours than a plain sum of layer 1. The report shows both side by side. Example, Bull: a plain sum of the raw
meters peaks at 13,791 kW, the cleaned community demand at 4,842 kW.

| Community | Hours with a plain raw sum | Hours with a community value | Hours only in the plain sum | Plain-sum peak (kW) | Community peak (kW) |
|---|---:|---:|---:|---:|---:|
| bull | 17,490 | 16,862 | 628 | 13,791 | 4,842 |
| eagle | 17,544 | 16,704 | 840 | 908 | 908 |
| fox | 17,528 | 17,486 | 42 | 2,283 | 2,283 |
| hog | 17,246 | 17,051 | 195 | 2,917 | 2,917 |
| peacock | 17,425 | 17,393 | 32 | 1,339 | 1,339 |
| rat | 17,085 | 16,620 | 465 | 938 | 938 |
| robin | 17,544 | 17,334 | 210 | 1,165 | 1,165 |

## What the verifier does

`scripts/verify_society_raw_data.py` is a second implementation of the pipeline, written from the rules in this document. It imports only the Python standard library, numpy and pandas; it does not import `ml_engine`, `backend` or any other
part of this repository (a test enforces this), and it hard-codes the thresholds as `SPEC` instead of reading them from the application. Its run-length and quantile code is its own.

1. Hash the input files (SHA-256) and compare with the recorded values.
2. Check that the raw readings sit on one complete hourly grid.
3. Apply the selection rules to the BDG2 metadata and screen every site that has a residential-labelled building.
4. Clean every candidate meter with the cleaning rules, keep the meters that pass the 95 % rule, and aggregate each qualifying site.
5. Compare with the application: the processed files (selection, grid, every meter, invalid readings left, community sum) and, optionally, the running API (overview totals, every calendar month, every building).
6. Write the report and exit with 0 (all passed), 1 (a check failed) or 2 (inputs missing).

### SHA-256 file integrity

| File (official BDG2 repository) | Bytes | SHA-256 |
|---|---:|---|
| `data/metadata/metadata.csv` | 272,024 | `992d0b29f24f96ad4332bc4dbb534b7bdd7dd2689aad093f94e93068ecddca02` |
| `data/weather/weather.csv` | 19,457,782 | `a8189f1c6acdf3b9933a9e6354b8e7c1278cd56a7075929623a17565d44f04bd` |
| `data/meters/raw/electricity.csv` | 174,239,039 | `039d909d8981e2d69eaeb366144e6ab7e84fa5e7e216aee42bddd95384a66418` |
| `LICENSE` | 21,227 | `1df42bd84afc40e676a0cbf3d34e30e5151e3f0d995a68b406178dad3b0e23dc` |
| `README.md` | 6,359 | `7f2a1539a17c3183fbfe69b06deea1d976ec9a4c92d34c4ad8d23e5b24fe8ca3` |

* **Full mode** (`data/society/raw/bdg2`, 174 MB for the electricity file): all five files are hashed and compared with `provenance.json`.
* **Subset mode** (`data/society/raw_subset`, shipped, 6.4 MB): `metadata.csv` is hashed and must equal the official metadata hash above; the extracted electricity subset (the columns of every `Lodging/residential` building, all 17,544 rows, every value copied as the
  same text the official file has) is hashed and must equal the value in `subset_manifest.json`. `--check-subset` additionally compares the subset with the full file value by value.
* `--download` fetches the official files from the URLs in the manifest and keeps a file only if its SHA-256 matches (the download path is covered by a test with a local file; it was not run against GitHub in the delivery workspace).

## Selection and exclusion criteria

A building enters a community only if all of these hold (the verifier applies them in this order):

1. its BDG2 metadata `primaryspaceusage` is `Lodging/residential` (this label includes student residence halls);
2. its `sub_primaryspaceusage` is not `Hotel` (whitespace stripped; a blank label is allowed);
3. it has a column in the electricity file;
4. after cleaning, at least 95% of its 17,544 hours are valid;
5. its site keeps at least 8 such buildings; and
6. in at least 94% of the site's hours every kept building is valid.

Of 168 buildings labelled `Lodging/residential`, 3 are hotels (excluded by rule 2), 19 have no electricity meter (rule 3) and 146 are candidates. Thirteen of the 19 BDG2 sites have at least one such building.

## Rejected sites

Six of the thirteen sites with a residential-labelled building do not form a community. `Candidate valid share` is the share of valid hours after cleaning of the site's candidate meters (smallest, median, largest). `Removed` counts, over all candidate
meters of the site, the readings taken out by rule: negative / zero / stuck / spike.

| Site | Labelled | Hotels | No meter | Candidates | Candidate valid share (min / median / max) | Removed (negative / zero / stuck / spike) | Meters at least 95 % valid | Reason |
|---|---:|---:|---:|---:|---|---|---:|---|
| Bear | 4 | 0 | 0 | 4 | 68.6% / 99.8% / 99.8% | 0 / 0 / 0 / 0 | 3 | only 3 meters pass the validity rule (need 8) |
| Bobcat | 3 | 0 | 0 | 3 | 94.0% / 94.0% / 94.1% | 0 / 0 / 0 / 0 | 0 | only 0 meters pass the validity rule (need 8) |
| Cockatoo | 29 | 1 | 1 | 27 | 81.7% / 91.9% / 91.9% | 0 / 638 / 0 / 0 | 0 | only 0 meters pass the validity rule (need 8) |
| Lamb | 2 | 1 | 0 | 1 | 60.9% / 60.9% / 60.9% | 0 / 47 / 6,805 / 0 | 0 | only 0 meters pass the validity rule (need 8) |
| Mouse | 1 | 1 | 0 | 0 | - | - | - | no residential meters |
| Panther | 44 | 0 | 17 | 27 | 80.7% / 80.7% / 82.4% | 0 / 90,711 / 0 / 1 | 0 | only 0 meters pass the validity rule (need 8) |

* **Bear, Bobcat, Lamb and Mouse** fail rule 5 even before data quality is considered: they have 4, 3, 1 and 0 candidate buildings, and a community needs 8.
* **Cockatoo and Panther** have 27 candidate meters each, but none reaches 95 % valid hours after cleaning (best meter: 91.9% and 82.4%). In Panther the readings that fail are almost all zeros (90,711 zero readings removed, 87,847 of them in runs of 24 h or longer).
* The three Bobcat meters sit at 94.0% to 94.1% valid, just under the 95 % line, and the rules removed none of their readings (the missing hours are missing in the raw file). They would not suffice anyway: 3 meters, 8 needed.

## Accepted sites

| Site | Labelled | Candidates | Meters kept | Meters rejected by rule 4 | Hours with every kept meter valid |
|---|---:|---:|---:|---:|---:|
| Bull | 19 | 19 | 16 | 3 | 96.1% |
| Eagle | 10 | 10 | 8 | 2 | 95.2% |
| Fox | 12 | 12 | 11 | 1 | 99.7% |
| Hog | 11 | 11 | 10 | 1 | 97.2% |
| Peacock | 12 | 11 | 11 | 0 | 99.1% |
| Rat | 11 | 11 | 9 | 2 | 94.7% |
| Robin | 10 | 10 | 8 | 2 | 98.8% |

## Meters rejected inside accepted sites

Rule 4 removes a meter, not the site. These 11 candidate meters fall below 95 % valid hours after cleaning and are listed, with their BDG2 identifiers, in each community's `excluded_meters.csv` (the application shows these identifiers to administrators only).

| Community | Meter | Valid share after cleaning | Missing in raw | Zero | Stuck | Spike |
|---|---|---:|---:|---:|---:|---:|
| bull | `Bull_lodging_Anibal` | 89.1% | 55 | 1,858 | 0 | 0 |
| bull | `Bull_lodging_Danielle` | 90.6% | 34 | 1,579 | 0 | 28 |
| bull | `Bull_lodging_Terence` | 91.4% | 46 | 1,448 | 0 | 16 |
| eagle | `Eagle_lodging_Blake` | 68.9% | 0 | 5,406 | 57 | 0 |
| eagle | `Eagle_lodging_Garland` | 0.0% | 17,544 | 0 | 0 | 0 |
| fox | `Fox_lodging_Warren` | 83.2% | 2 | 8 | 2,936 | 0 |
| hog | `Hog_lodging_Edgar` | 73.3% | 0 | 2,484 | 2,204 | 0 |
| rat | `Rat_lodging_Lakisha` | 64.0% | 100 | 4,022 | 2,194 | 0 |
| rat | `Rat_lodging_Lucille` | 59.5% | 70 | 7,028 | 0 | 0 |
| robin | `Robin_lodging_Armand` | 90.6% | 0 | 0 | 1,642 | 0 |
| robin | `Robin_lodging_Donna` | 88.7% | 0 | 0 | 1,985 | 0 |

## Spike and stuck-sensor filtering: rules and thresholds

The rules are applied to each meter separately, on its full 17,544-hour series. They only **remove** readings (set them to missing); no value is changed, filled or interpolated.

| Rule | Definition | Threshold |
|---|---|---|
| Missing | no value in the raw file | stays missing |
| Negative | reading below 0 | removed |
| Zero | reading of exactly 0 kWh in an hour; counted as a *long* zero run when it lasts at least 24 consecutive hours, otherwise *short*; both are removed | `zero_is_invalid = True`, long run at 24 h |
| **Stuck sensor** | a run of **identical positive readings**; a missing, zero or negative reading ends the run (so 24 identical readings, a gap, then 24 more are not stuck) | at least **48 consecutive hours** |
| **Spike** | a reading above 4 times the 99.5% quantile (linear interpolation) of that meter's positive readings | **4 x p99.5**; applies only to meters with at least 100 positive readings |

A reading hit by several rules is counted once, in the order negative, stuck sensor, spike; zero readings are counted separately. A meter is kept when at least 95% of its hours remain valid. The per-meter spike limits are in
section 5 of the report. What the rules removed from the 73 kept meters (their raw readings: 1,280,712 meter-hours):

| Community | Meters | Missing in raw | Negative | Zero | Stuck | Spike | Valid after cleaning |
|---|---:|---:|---:|---:|---:|---:|---|
| bull | 16 | 433 | 0 | 4,999 | 0 | 29 | 275,243 of 280,704 |
| eagle | 8 | 0 | 0 | 1,978 | 496 | 0 | 137,878 of 140,352 |
| fox | 11 | 37 | 0 | 62 | 0 | 0 | 192,885 of 192,984 |
| hog | 10 | 298 | 0 | 11 | 186 | 0 | 174,945 of 175,440 |
| peacock | 11 | 259 | 0 | 34 | 0 | 0 | 192,691 of 192,984 |
| rat | 9 | 780 | 0 | 471 | 0 | 0 | 156,645 of 157,896 |
| robin | 8 | 0 | 0 | 68 | 862 | 0 | 139,422 of 140,352 |

The thresholds are choices made for this project (they are not part of BDG2). They are written once more as data so that a test can compare them with the verifier and with the application's defaults:

```json spec
{
  "selection": {
    "primary_use": "Lodging/residential",
    "exclude_sub_uses": [
      "Hotel"
    ],
    "min_meter_valid_share": 0.95,
    "min_buildings": 8,
    "min_society_valid_share": 0.94
  },
  "cleaning": {
    "zero_is_invalid": true,
    "long_zero_hours": 24,
    "stuck_min_hours": 48,
    "spike_factor": 4.0,
    "spike_quantile": 0.995,
    "spike_min_positive_readings": 100,
    "negative_is_invalid": true
  },
  "storage_decimals": 3
}
```

## Meter-level and building-level verification

For every kept building (a "building" is one meter, as BDG2 has one whole-building electricity meter per building) the checks are, per community:

| Check id | What it requires |
|---|---|
| `selection.kept_buildings`, `selection.excluded_meters`, `selection.building_codes` | the buildings kept and the meters rejected equal the application's `buildings.csv` and `excluded_meters.csv`; codes follow the rule (`FOX-B01` ... in sorted source order) |
| `buildings.metadata` | each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata |
| `grid.complete` | the processed hourly grid equals the raw grid: unique, regular one-hour steps, no missing timestamp |
| `meters.unaltered` | no stored value differs from the raw reading of the same hour by more than the 3-decimal rounding |
| `meters.cleaned_equals_independent` | the application's cleaned meters equal the independently cleaned meters (same valid hours, same values) |
| `meters.removal_counts` | the per-rule counts (missing, negative, zero, stuck, spike, valid) of every meter equal the application's cleaning report |
| `invalid.none_left` | the processed meters contain no negative, zero, stuck or spike reading |
| `spec.rules_match` | the thresholds recorded by the application equal the verifier's `SPEC` |

## Community aggregation, missing hours and invalid readings

| Check id | What it requires |
|---|---|
| `aggregate.total_equals_independent` | the stored community demand equals the independent sum of the cleaned meters, hour by hour (allowed difference 0.0005 x (meters + 1) kWh from 3-decimal storage), with the same pattern of missing hours |
| `aggregate.no_partial_sums` | the community value is missing in exactly the hours where any kept meter is missing |
| `aggregate.n_valid_meters` | the stored count of valid meters equals the number of non-missing meters in each hour |
| `aggregate.valid_hours` | the number of hours with a community value equals the application's cleaning report and is at least 94 % |

Missing hours per community (an hour is missing when at least one kept meter has no valid reading; they are never filled):

| Community | Hours with a value | Missing hours | Missing | Gaps | Longest gap |
|---|---:|---:|---:|---:|---|
| bull | 16,862 | 682 | 3.89 % | 40 | 115 h from 2016-05-26 15:00:00 |
| eagle | 16,704 | 840 | 4.79 % | 56 | 533 h from 2016-09-28 08:00:00 |
| fox | 17,486 | 58 | 0.33 % | 17 | 13 h from 2017-11-07 14:00:00 |
| hog | 17,051 | 493 | 2.81 % | 11 | 196 h from 2016-06-12 07:00:00 |
| peacock | 17,393 | 151 | 0.86 % | 26 | 58 h from 2016-08-02 15:00:00 |
| rat | 16,620 | 924 | 5.27 % | 443 | 96 h from 2017-08-28 00:00:00 |
| robin | 17,334 | 210 | 1.20 % | 6 | 94 h from 2017-05-03 02:00:00 |

## Raw against application

**Processed files.** Section 8 of the report: all processed-file checks passed for the seven communities. **Running API**: the verifier logs in as an administrator, reads `/overview`, `/consumption?resolution=monthly` and `/buildings`
and compares them with its own numbers. The independent figure is computed from the raw readings; the API figure from the stored 3-decimal values.

| Community | API energy (kWh) | Independent energy (kWh) | Difference | Valid hours (API / independent) | Peak kW (API / independent) | Months / buildings compared |
|---|---:|---:|---:|---|---|---|
| bull | 32,549,761.910 | 32,549,761.910 | +0.000 | 16,862 / 16,862 | 4,841.960 / 4,841.960 | 24 / 16 |
| eagle | 9,289,115.977 | 9,289,115.984 | -0.007 | 16,704 / 16,704 | 907.685 / 907.685 | 24 / 8 |
| fox | 26,464,352.430 | 26,464,352.430 | +0.000 | 17,486 / 17,486 | 2,283.160 / 2,283.160 | 24 / 11 |
| hog | 29,804,910.654 | 29,804,910.649 | +0.005 | 17,051 / 17,051 | 2,917.163 / 2,917.163 | 24 / 10 |
| peacock | 15,596,896.757 | 15,596,896.740 | +0.017 | 17,393 / 17,393 | 1,338.578 / 1,338.578 | 24 / 11 |
| rat | 8,328,445.710 | 8,328,445.710 | +0.000 | 16,620 / 16,620 | 938.380 / 938.380 | 24 / 9 |
| robin | 9,440,079.218 | 9,440,078.881 | +0.337 | 17,334 / 17,334 | 1,165.238 / 1,165.238 | 24 / 8 |

The energy differences are rounding, not error. The processed files hold three decimals, so each stored value is within 0.0005 of its raw reading (this is a check, `meters.unaltered`), and the stored hourly community totals are rounded again. The largest difference is Robin,
+0.337 kWh on 9,440,079 kWh; Robin's raw file contains readings with more than three decimals. The allowed tolerance of the check is far larger
(0.0005 x (meters + 1) kWh per hour, summed over the valid hours). The valid-hour counts and peak hours are identical.

## Automated tests of the data-integrity checks

| File | What it checks |
|---|---|
| `tests/unit/test_society_raw_verification.py` | the cleaning rules on small known series (negative, short and long zeros, stuck at 48 vs 47 hours, a gap ending a run, spike at 4 x p99.5, fewer than 100 readings, overlap counting); site selection (hotel with whitespace, no meter, 8-meter and 94 % rules); no partial sums; SHA-256 mismatch and download refusal; **tamper tests** (a changed meter value, an uncleaned negative, a partial community sum, a changed total, a missing building, a forgotten excluded meter, a changed count, a changed threshold, a changed raw file, a changed metadata file must each make the right check fail); the independent pipeline on the shipped raw subset against all seven processed communities; the full official files when present; the committed report belongs to the shipped script and passed; the thresholds in this document equal the verifier's; every rejected site is documented; the disclosures are present in README, this document and the report |
| `tests/integration/test_society_raw_vs_api.py` | all seven communities imported into a temporary database and compared with the independent computation through the real API (totals, 24 months, every building); a wrong energy total, a missing month, a wrong building figure, a non-admin account and a society that is not imported must each be reported |

The recorded run of these tests is in [verification_test_run.txt](verification_test_run.txt).

## Limits of this verification

* It does not show that the BDG2 files are free of errors; they are hashed and used as published. A pattern the rules do not catch (for example a slowly drifting meter) stays in the data.
* It does not make the communities representative of family flats or of any registered housing society. They are groups of whole-building meters, mostly student residence halls.
* It does not check layer 4: the forecasting models, their accuracy, the anomaly events, the tariff costs or the recommendations.
* The thresholds are rules chosen for this project; the verifier checks that they were applied as written, not that they are the best possible rules. Because the verifier is a second implementation by the same author, it can catch a coding slip but not a misunderstanding shared by both.
* In `subset` mode the SHA-256 of the 174 MB electricity file is not re-checked (only the hash of the extracted subset and of the official metadata file). Use the full files, or `--check-subset`, for that.
* `--download` was not run over the network in the delivery workspace. The data of a society uploaded by an administrator is not covered (no raw BDG2 source exists for it).

## How to run

```bash
# 1. no download needed: uses the shipped data/society/raw_subset, checks the processed files
python scripts/verify_society_raw_data.py --use-subset

# 2. with the full official files (174 MB electricity file; SHA-256 of all five files is checked)
python scripts/verify_society_raw_data.py --download            # once; fetches and verifies
python scripts/verify_society_raw_data.py --check-subset        # also compares the shipped subset with the full file

# 3. everything, including a live API: starts a throw-away API with an empty temporary database, imports the bundled societies,
#    verifies against it, stops it, and rewrites docs/society/VERIFICATION_REPORT.md and verification_report.json (about 1 minute)
python scripts/verify_society_end_to_end.py --check-subset

# against your own running API (an administrator account is needed because BDG2 identifiers are admin-only)
ENERGIQ_VERIFY_EMAIL=... ENERGIQ_VERIFY_PASSWORD=... python scripts/verify_society_raw_data.py --api-url http://127.0.0.1:8000

# rebuild the shipped subset from the full files
python scripts/society_make_raw_subset.py

# the tests
python -m pytest tests/unit/test_society_raw_verification.py tests/integration/test_society_raw_vs_api.py
```

Add `--no-report` to print the summary without writing the report files. Exit code 0: every check passed; 1: a check failed; 2: inputs missing.
