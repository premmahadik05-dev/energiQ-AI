# 14. MLOps, monitoring and operations

## 1. What is tracked

| Item | Where | Notes |
|---|---|---|
| Model versions | `model_versions` table (+ files under the models directory) | Dataset, horizon-model ids, train end, hash of the training series, hold-out metrics against baselines, residual quantiles, SHAP summary, active flag |
| Reproducibility | `artifacts/reports/benchmark/cv_results.json` | Seed, folds, data hash and run time of the research benchmark |
| Forecasts | `forecasts` table | Every forecast is stored with its origin and model, which enables realised-error tracking |
| Audit trail | `audit_events` | Who did what, from which IP |
| Notifications | `notifications` | Job completions and anomaly runs |

There is no separate experiment-tracking server (MLflow was deliberately left out to keep the stack light for an 8 GB machine); metadata lives in the application database and the JSON reports.

## 2. Model monitoring (`GET /api/v1/models/{id}/monitoring`)

* **Data drift.** Compares the load distribution of the training period with the most recent 28 days using the Population Stability Index (reference-quantile bins) and the two-sample Kolmogorov-Smirnov test. Status: PSI < 0.1 "stable", 0.1–0.25 "moderate shift", ≥ 0.25 "significant shift". These are the customary rules of thumb, not validated cut-offs for this domain. Drift is only reported as meaningful when new data has arrived after training; otherwise the recent window is just the tail of the training data and the response says so.
* **Realised performance.** For the latest 50 stored forecasts, the absolute error against actual readings that have since arrived. The ratio to the mean hold-out MAE (over h = 1, 6, 24) is classified "within expectation" (≤ 1.25) or "degraded – consider retraining". The response notes that the ratio mixes horizons and is a rough alarm.
* **Retrain recommendation.** `retrain_recommended` is true when drift is significant or realised error is degraded. Retraining is manual (the user starts a training job, then activates the new version); old versions are kept until deleted, so rollback is "activate the previous version".

## 3. Service monitoring

* `/health/live` and `/health/ready` for orchestrators; the Docker image and the ALB use `/health/ready`.
* `/metrics` in Prometheus text format: `energiq_http_requests_total{method,route,status}`, `energiq_http_request_duration_seconds` histogram, `energiq_jobs{status}`. Route labels are route *templates* (`/api/v1/datasets/{dataset_id}`), so cardinality stays bounded. Keep the endpoint on the private network.
* `GET /api/v1/admin/system` shows counts, job states and request/latency summary (admin only).
* Logs are plain text on stdout via Python's `logging` and Uvicorn (collected by Docker or CloudWatch); there is no JSON log formatter; each response carries `X-Request-ID` and unhandled errors log that id.
* CloudWatch alarms in the AWS template: API 5xx, no healthy API task, database CPU, database free storage.
* Suggested Prometheus alert rules (not shipped as running configuration): 5xx rate > 1 % for 5 min; p95 latency > 2 s for 10 min; `energiq_jobs{status="failed"}` increasing.

## 4. Backup and restore

`scripts/backup.py` creates one `tar.gz` with the database (SQLite online backup or `pg_dump -Fc`), the uploads and models directories, and a checksum manifest. `restore` verifies the checksums, refuses unsafe archive members and different database backends, and asks for confirmation. Tests cover the SQLite and PostgreSQL round trips, corruption detection and path-traversal refusal. Recommended practice (not automated here): run the backup daily from a scheduler, copy archives off the machine, and rehearse a restore. The AWS template additionally enables 7-day automated RDS backups and EFS backups.

## 5. Release and change process

1. Branch, change, run `ruff check .` and the full test suite locally.
2. CI (`.github/workflows/ci.yml`) repeats lint, unit and integration tests with a coverage report (SQLite, then PostgreSQL), security scans, front-end checks, an end-to-end job (real server plus real Chromium), image builds and a CloudFormation lint. None of these CI jobs has run on GitHub yet because the repository has not been pushed; every check was run locally instead (`docs/11_testing.md`).
3. Database changes go through an Alembic revision, reviewed with the code.
4. Deployment is manual (`deploy-aws.yml`), behind a protected GitHub environment.
