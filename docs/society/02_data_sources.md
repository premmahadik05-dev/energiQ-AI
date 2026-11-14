# 2. Data sources (data card)

| Item | Value |
|---|---|
| Dataset name | **Building Data Genome Project 2 (BDG2)** |
| Official URL | https://github.com/buds-lab/building-data-genome-project-2 |
| Files used | `data/meters/raw/electricity.csv` (174,239,039 bytes), `data/metadata/metadata.csv`, `data/weather/weather.csv`, `LICENSE`, `README.md` (URLs, sizes and SHA-256 in `data/society/processed/societies.json`) |
| Publisher | Building and Urban Data Science (BUDS) Lab, National University of Singapore, with the organisers of the ASHRAE Great Energy Predictor III competition |
| Paper | Miller, C., Kathirgamanathan, A., Picchetti, B. et al. *The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition.* Scientific Data 7, 368 (2020). doi:10.1038/s41597-020-00712-x |
| Licence | Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0), as stated in the repository's `LICENSE` file. Derived data in this project (`data/society/processed`) must be shared under the same licence with attribution. |
| Download date | 2026-11-08 |
| Frequency and period | Hourly, 2016-01-01 00:00 to 2017-12-31 23:00 (17,544 rows per meter) |
| Units | Whole-building electricity, **kWh per hour** per meter. The numeric value equals the average demand in **kW** over that hour; the application keeps the two labels separate (energy is summed, demand is averaged, peak demand is the highest hourly mean). |
| Timestamps | Local clock time of the site as published, with no daylight-saving gap or repeat (exactly 17,544 hourly rows). The site time zone comes from the metadata and is shown in the application. |
| Meters | The full BDG2 electricity file has 1,578 meter columns (one per building) over 19 sites. **This project keeps only buildings whose metadata primary use is `Lodging/residential`** (hotels excluded), in sites where at least 8 such meters are clean: **73 buildings in 7 communities**. |
| Raw data in this repository | `data/society/raw_subset/`: the official metadata file (byte-identical) and the electricity readings of every `Lodging/residential` building, extracted unchanged (6.4 MB); `subset_manifest.json` records the SHA-256 of the full official files. The full 174 MB file is downloaded on request (`python scripts/verify_society_raw_data.py --download`). |
| Weather | Hourly site weather from the same dataset (air temperature, dew temperature, wind speed), used only by the "XGBoost + observed weather" family. |

## Student residence halls, not family flats

BDG2 buildings whose metadata primary use is `Lodging/residential` **include student residence halls**. Of the 73 buildings used (sub-use labels in the BDG2 metadata): **56 `Dormitory`**, 8 `Housing` (all of Eagle) and 9 `Other - Lodging/Residential` (all of Rat).
BDG2 does not describe the last two labels further, so this project does not claim that they are family flats either. The data are **not** data of family flats, **not** data of individual homes and **not** data of a registered housing society.
Per community: [10_raw_data_verification.md](10_raw_data_verification.md), "What the data are, and what they are not".

## Four layers that are kept apart

1. **Raw readings**: BDG2 `electricity.csv` as published (hashed; `data/society/raw_subset/` and, when downloaded, `data/society/raw/bdg2/`).
2. **Cleaned readings**: the raw readings with invalid ones set to missing (`data/society/processed/<key>/meters_hourly_kwh.csv.gz`). Nothing is changed or filled.
3. **Aggregated community demand**: the hourly sum of the cleaned readings of the kept buildings, missing where any is missing (`society_hourly.csv.gz`; what the overview, consumption and building pages show).
4. **ML predictions**: forecasts, bands, backtests and SHAP values of trained models for layer 3 (`artifacts/society/`). Estimates, not measurements.

Layers 1 to 3 are verified independently of the application ([10_raw_data_verification.md](10_raw_data_verification.md), [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)); layer 4 is evaluated in [RESULTS.md](RESULTS.md).

## Why a "representative community" and not a housing society

The task needs hourly electricity of a *residential society with several buildings and common facilities*. No open dataset of
that kind was found that also gives a per-meter series whose sum is the community total. BDG2 is the closest genuine public
multi-consumer set: it contains student residence halls, i.e. real residential buildings whose meters are measured on the same
clock, so a community total can be defined as an exact sum. Its authors describe BDG2 as non-residential data in general, and
residence halls are not family housing. The communities are called **research-based representative communities** in the
application, in the database `description` and here.

What is **not** in the data: lifts, water pumps, street lighting and clubhouse meters (the Facilities page says "not measured
in this dataset"), apartment- or household-level meters inside the buildings, tariffs, occupancy, and any fault labels. The
administrator can upload a real society that has such meters (see `06_admin_and_upload_guide.md`).

## The seven communities

Generated table (buildings, floor area, valid hours, mean demand, test period): [`RESULTS.md`](RESULTS.md) §1.
Sites that did not pass the rule (Bear, Bobcat, Cockatoo, Lamb, Mouse, Panther) and the reason for each are listed in [10_raw_data_verification.md](10_raw_data_verification.md), "Rejected sites".

## Missing values

Per community, the share of hours with no valid society total is in RESULTS §1 (for Fox, 58 of 17,544 hours; for Rat, 924). They are
**not filled**: a missing hour stays missing, is excluded from any metric or sum that needs it, and is reported with the count of valid hours.
The cleaning counts per community are in `data/society/processed/<key>/cleaning_report.json` and in the Data sources page.
Buildings are shown under pseudonymous codes (`FOX-B01`, ...); the BDG2 identifiers (`source_id`) and the per-meter cleaning counts are visible to administrators only.

## Citation

Please cite Miller et al. (2020) whenever results derived from these data are shown.
