# 6. Administration, upload and reproduction guide

## Importing the bundled communities

Society admin → **Import bundled communities**. The job reads `data/society/processed/<key>` and `artifacts/society/<key>` and
loads whatever is present into the database. A community with an evaluation but no `bundle.json` (deployed models) is
loaded as *Evaluated; models not installed*: the model comparison, backtests, SHAP, peak evaluation and alerts work, the live
forecast does not. The delivered package contains deployed models for **Fox** and **Rat** (the other five would add about 150 MB); regenerate them with

```bash
python scripts/society_train.py --societies bull --deploy      # a few minutes per community on two CPU cores (evaluation alone took 111–161 s each in the delivered runs)
```

## Uploading a real society

Society admin → **Upload a society**.

**Meter readings file (CSV).** First column = timestamp (ISO, e.g. `2024-01-31 14:00`); every other column = one meter. Values are kWh per
interval (choose *Energy*) or average kW (choose *Average power*). Intervals of 1, 5, 10, 15, 30 or 60 minutes are accepted and
aggregated to hourly kWh: kWh values are summed and an hour needs **all** its sub-intervals; kW values are averaged and an hour needs at least 75 %. Up to 200 meters.

```
timestamp,B1,B2,Lift_A,Pump_1,Streetlights
2024-01-01 00:00,41.2,38.0,2.1,0.0,6.0
...
```

**Mapping file (optional CSV)**: `meter_id,building,kind,facility_category,floor_area_sqm`. `kind` is `building` or `facility`; a facility needs
`facility_category` = lift, pump, streetlight, clubhouse or other. Meters not listed are buildings. With facility meters, the
Facilities page shows their consumption over time by category; the society total includes them (common services are part of community demand).

**Rules.** The same cleaning rules as the bundled data apply (negative, stuck for 48 h, spike above 4 × p99.5; exact zeros are invalid for
buildings and valid for facilities). A meter is kept if at least 90 % of its hours are valid; at least 2 meters (one a building) must remain; the society total must be valid in at
least 80 % of hours. Nothing is filled. Rejected meters are listed to the admin with the reason. A file that cannot meet these rules is refused with a message.

**After the upload**: the job stores the readings and runs anomaly detection. Press **Train models** to run the evaluation protocol and deploy
the forecasters (needs about nine months of valid hours; a shorter history is refused with the exact shortage). Progress appears in the Jobs list.

## Reproducing everything from scratch

```bash
pip install -r requirements.txt -r requirements-research.txt
python scripts/society_prepare.py                 # download BDG2 (≈195 MB), record size and SHA-256, clean, aggregate → data/society/processed
python scripts/society_train.py --deploy          # evaluate all seven communities and deploy models (evaluation ≈ 16 min in total on two cores, plus deployment)
python scripts/society_anomalies.py               # anomaly events for all communities
python scripts/society_train.py --peaks-only      # daily-peak evaluation from the saved predictions
python scripts/make_society_docs.py               # RESULTS.md and SCHEMA.md
python scripts/society_import.py                  # (optional) load into the configured database from the command line
python scripts/capture_society_fixtures.py        # regenerate the frontend test fixtures from the real API
python scripts/verify_society_raw_data.py --use-subset   # independent check of the processed data against the raw BDG2 readings (seconds, no download)
python scripts/verify_society_end_to_end.py --check-subset   # the same against the full official files and a throw-away live API; rewrites VERIFICATION_REPORT.md
python scripts/society_make_raw_subset.py          # rebuild data/society/raw_subset from the full official files
```

Seeds are fixed (42). XGBoost results depend on the XGBoost version; the pinned versions are in `requirements.txt`, and every
`evaluation.json` records the library versions that produced it.

## Tariffs

Cost pages use a tariff chosen in the interface. The default is a **demo tariff with placeholder rates**; to use real rates, add a tariff through the API
(`POST /api/v1/tariffs` with `name`, `currency`, 24 `weekday_rates`, 24 `weekend_rates` and `daily_fixed_charge`, as an analyst or admin; see `docs/society/05_api_and_database.md`)
and select it in the *Tariff* box on the society pages. The web application has no tariff form: it was on the Optimisation page, which was removed with the other single-meter pages.
