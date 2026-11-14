# Residential society electricity forecasting and smart energy management

This is the society-level part of EnergiQ AI: it forecasts the **total electricity demand of a residential community
(several buildings summed per hour)**, flags unusual demand, estimates cost under a configurable tariff, gives
evidence-based recommendations and produces reports. The original single-meter (household) web pages were removed from the interface in a
later change; their API routes, ML library and research benchmark remain in the repository.

## What the data are, in one paragraph

No open dataset of a registered Indian (or any) housing society with separate lift, pump, street-light and clubhouse meters
was available. The society data are therefore a **research-based representative community**: for each of seven sites of the
public *Building Data Genome Project 2* (BDG2), the real hourly electricity meters of the buildings whose recorded primary use
is *Lodging/residential* (this label **includes student residence halls**: 56 of the 73 buildings are labelled `Dormitory`; hotels excluded) are cleaned and **summed per hour**. Community
consumption is exactly the sum of its meters at every hour. Every reading is a real measurement; the grouping into
a "society" is this project's construction, and the application says so on every page. The data are **not** data of family flats and **not** data of a registered housing society. Nothing is simulated, filled or invented.
An administrator can also upload the meter file of a real society (hourly or sub-hourly CSV), which goes through the same
cleaning, evaluation and model-training steps.

## Documents

| File | Content |
|---|---|
| [01_architecture.md](01_architecture.md) | Components, data flow, module map, how a request and a training job travel |
| [02_data_sources.md](02_data_sources.md) | Data card: dataset, URL, publisher, licence, download date, meters, period, units, missing values |
| [03_preprocessing_and_aggregation.md](03_preprocessing_and_aggregation.md) | Cleaning rules, the aggregation method, the processed-data layout |
| [04_models_and_evaluation.md](04_models_and_evaluation.md) | Models, features, splits, selection, metrics, bands, explainability, anomalies, cost and recommendations |
| [RESULTS.md](RESULTS.md) | **Generated** result tables for all seven communities (from the saved evaluation files) |
| [05_api_and_database.md](05_api_and_database.md) | Endpoint groups, roles, privacy, jobs; links to the generated API reference and schema |
| [SCHEMA.md](SCHEMA.md) | **Generated** society database tables |
| [06_admin_and_upload_guide.md](06_admin_and_upload_guide.md) | Importing, uploading a society's meter CSV, mapping facilities, training |
| [07_testing_and_verification.md](07_testing_and_verification.md) | What was run, what passed, what was not tested |
| [08_limitations_and_future_work.md](08_limitations_and_future_work.md) | What not to over-trust; what to do next |
| [10_raw_data_verification.md](10_raw_data_verification.md) | **Independent verification from the raw BDG2 files**: method, the four data layers, SHA-256 checks, exclusion criteria and rejected sites, spike and stuck-sensor rules, raw-versus-application comparison, tests, limits, how to run |
| [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) | **Generated** result of that verification (127 of 127 checks), with [verification_report.json](verification_report.json) and the recorded [test run](verification_test_run.txt) |
| [09_viva_notes.md](09_viva_notes.md) | Likely examiner questions with straight answers |

## Run it

```bash
# backend (Python 3.11); the database schema is created on first start (SQLite by default, PostgreSQL via ENERGIQ_DATABASE_URL)
pip install -r requirements.txt
ENERGIQ_ENV=dev uvicorn backend.app.main:create_app --factory --reload --port 8000
# frontend (Node 22)
cd frontend && npm ci && npm run dev        # http://localhost:5173
```

Sign in as an administrator (seeded from `ENERGIQ_ADMIN_EMAIL` and `ENERGIQ_ADMIN_PASSWORD`), open **Society admin** and press **Import bundled communities**. The seven communities (processed
data, evaluation results, explanations, anomaly events; deployed forecasting models of all seven communities) are imported from the repository.
Regenerate any part with the scripts listed in [06_admin_and_upload_guide.md](06_admin_and_upload_guide.md).
