# 09. Backend design and API

Code: `backend/app/`. Full endpoint list with access rules: `docs/api/API_REFERENCE.md` (generated from the running application by
`scripts/make_api_reference.py`); schema: `docs/api/openapi.json`. Diagrams: `docs/diagrams/`.

## 1. Layers

| Layer | Files | Responsibility |
|---|---|---|
| Entry point | `main.py` | `create_app(settings)` factory: CORS, request-id / security-header / metrics middleware, routers, health and `/metrics`, start-up job recovery, optional administrator seeding |
| HTTP API | `api/auth, datasets, ml, anomalies, optimize, reports, admin` | Validation, authorisation, ownership checks, status codes. No ML code. |
| Services | `services/core.py, data.py, ml.py` | Audit trail, notifications, job runner and metrics (`core`); upload streaming, ingestion into the database, series loading (`data`); training, forecasting, explanation, anomaly job, monitoring (`ml`) |
| ML engine | `ml_engine/` (no web dependencies) | Ingestion/quality, features, models, evaluation, anomaly detection, SHAP, tariff and recommendations |
| Persistence | `models.py, db.py, migrations/` | SQLAlchemy 2 models; SQLite (WAL, foreign keys on) for development and tests, PostgreSQL 16 in production; Alembic migration `0001` |
| Security | `security.py, config.py` | Password hashing, JWT, rate limiter, roles, settings and production safety checks |

Settings come from environment variables with prefix `ENERGIQ_` (or `.env`); a production start-up refuses the built-in development secret, secrets shorter than 32 characters and wildcard CORS.

## 2. Data model (`docs/diagrams/er_diagram.png`)

Twelve tables, generated into the diagram from the ORM so it cannot drift: `users`, `datasets`, `readings`, `jobs`, `model_versions`, `forecasts`, `anomaly_runs`, `anomalies`, `tariffs`, `recommendation_snapshots`, `notifications`, `audit_events`. Every user-owned row carries `owner_id`; foreign keys cascade on delete from dataset to its readings, models, forecasts and anomalies. The Alembic migration is checked against the models by a test (`test_migrations.py`), on SQLite and, where available, PostgreSQL.

## 3. Background jobs

Upload processing, training and anomaly detection can take seconds to minutes, so each is a **job**: the request returns `202` with a job id, a worker thread runs it, and its state (`queued → running → succeeded | failed`, progress 0–1, message, result, error) lives in the `jobs` table. Properties worth knowing:

* Job rows survive a restart; on start-up any job left `queued` or `running` by a previous process is marked `failed: Interrupted by a server restart` (it can never finish).
* Only expected user-facing errors (bad data, missing file) reach the job's `error` field; unexpected exceptions are logged with a stack trace and shown to the user as "Internal error; see server logs" (tested).
* A second train/anomaly job for the same dataset is refused with 409 while one is running.
* The pool lives inside the API process. Therefore **run exactly one API process per deployment** (see `docs/13_limitations.md`).

## 4. Upload pipeline

`POST /api/v1/datasets` (multipart): extension whitelist (`.csv .txt .tsv`) → streamed to a uuid-named temporary file with a size cap (default 50 MB in code, 200 MB in the compose file) so the client's file name never touches the file system → NUL-byte/binary rejection → declared unit (`kW, W, MW, kWh, Wh, MWh`) and time-zone convention (`logger_clock, utc, local_with_dst`) validated → job. Parsing is tolerant of delimiter and encoding but strict about meaning: unparseable timestamps, non-numeric values and wrong headers are rejected with explanations, and the quality report shows completeness, duplicates, gaps and flat runs. Energy units are converted to power only when the sampling interval is known; the report states the assumption.

## 5. Forecast and explanation endpoints

* `POST /datasets/{id}/append` (file only; the column mapping stored with the dataset is reused) adds newer readings. Hours present in the new file with a value **replace** the stored value; hours that are absent from the new file, or present but blank, **keep the stored reading** (an earlier version erased stored readings wherever the new file had a gap; this was found while writing documentation and is covered by a regression test, `test_append_replaces_overlapping_values_but_never_erases_readings_with_gaps`, which fails on the old code). A model trained before an append stays active until the user retrains.
* `POST /datasets/{id}/train` works in two stages. (1) **Evaluation:** for h = 1, 6 and 24 an XGBoost model is fitted only on rows whose target lies before a chronological hold-out (the last 20 % of the dataset's timeline) and scored once on that block against the baselines; per-horizon residual quantiles and a SHAP summary are stored. (2) **Deployment:** the 24 models of the bundle (h = 1…24) are **refitted on all the data**, so the model used for forecasting has also seen the hold-out period. The reported hold-out metrics therefore describe the protocol, not the exact deployed models. The application uses one fixed, untuned XGBoost configuration (`n_estimators=300, max_depth=4, learning_rate=0.05`, the first entry of the benchmark's grid) so that training takes seconds to minutes on a laptop; it is not the per-horizon configuration chosen by cross-validation in the research benchmark. The model is optionally activated.
* `POST /forecasts` builds features from the data at the origin (default: last timestamp) and returns 24 points with an 80 % range. A regression test changes the data after the origin and checks the forecast is unchanged.
* `POST /explain/local` returns exact TreeSHAP contributions; `GET /explain/global` returns the stored benchmark SHAP summary; `GET /benchmark` and `/benchmark/figures/{group}/{name}` serve the stored benchmark results and a whitelist of figure files (path traversal is tested).

## 6. Observability endpoints

`/health/live` (process up), `/health/ready` (database reachable, otherwise 503), `/metrics` (Prometheus text format: request counts and latency histograms per route template and status, job counts by status), `/api/v1/admin/system` (admin only) and `/api/v1/models/{id}/monitoring` (drift and realised error, `docs/14_mlops_monitoring.md`). Every response carries an `X-Request-ID`.
