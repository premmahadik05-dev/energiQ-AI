# 11. Testing and verification

Everything below was run for real in the build workspace (Linux, 2 CPU cores, 7 GB RAM, Python 3.11.15 with the
pinned `requirements.txt`, Node 22.23, PostgreSQL 16). Numbers are copied from the command output; nothing here is
estimated. What was **not** tested is listed in §7 and in `docs/15_verification_matrix.md`.

## 1. Test suites

| Suite | Where | Tests | What it covers |
|---|---|---|---|
| Unit | `tests/unit` | 84 | CSV loading and ingestion (units, time conventions, bad files), quality report, feature building and leakage canaries, chronological splits, forecasting models and registry, LSTM, anomaly detector, TreeSHAP additivity, tariff cost, recommendations and scheduler, forecast residual band, secret scanner |
| Integration and security | `tests/integration` | 46 | The real FastAPI app over HTTP (TestClient) with a real database: auth, ownership (IDOR), uploads, jobs, train → forecast → explain → anomalies → optimise → monitoring, migrations (Alembic ↔ models), backup/restore, and 16 dedicated security tests (see §3) |
| End to end | `tests/e2e` | 3 | A real uvicorn process driven over real HTTP (2 tests) and a real Chromium driving the built React app against it (1 test) |
| Front end | `frontend/src/**/*.test.*` | 122 | Vitest + Testing Library against 45 fixtures captured from the running backend: pages, auth and guards, API client, polling, validation, components |
| **Total** | | **255** | |

### Results of the final runs

| Command | Result |
|---|---|
| `pytest` (all of the above Python suites, SQLite) | **131 passed, 2 skipped** in 154 s (the 2 skips need PostgreSQL) |
| `pytest tests/integration` with `ENERGIQ_TEST_DATABASE_URL` = PostgreSQL 16 | **46 passed, 0 skipped** in 55 s (includes the PostgreSQL migration and `pg_dump`/restore tests) |
| `npm test` in `frontend/` | **122 passed** (8 files) |
| Line coverage, `pytest --cov=backend --cov=ml_engine` | **95 %** (2,971 statements, 147 missed); the e2e server runs in a subprocess and is not counted; `ml_engine/evaluation/style.py` (plot styling used by the research scripts) has 0 % |

Frontend coverage was not measured. The Python suites also passed on Python 3.13 earlier in the project (126 passed, 2
skipped at that time, before the browser and reproducibility tests were added); the final run above is Python 3.11 only.

## 2. Properties the tests pin down (not just "it runs")

* **No leakage.** Features use only data at or before the forecast origin; training never sees rows after the cut-off;
  rewriting every reading after an origin does not move the forecast (service-level and API-level canaries);
  splits are chronological.
* **Reproducibility (NFR-04).** Training the same dataset twice gives identical hold-out metrics, residual quantiles and
  forecasts, and the same data hash (`test_retraining_on_identical_data_reproduces_metrics_and_forecasts`). On a larger
  scale the whole research benchmark was re-run from the raw file: baselines, Random Forest and all three LSTM seeds
  reproduced exactly; XGBoost depends on the library version (`docs/06_model_evaluation.md` §8).
* **Explanation correctness.** TreeSHAP contributions plus the base value equal the model output to at most 3.8 × 10⁻⁶ kW
  on 7,233 test rows (asserted in unit tests and measured in `shap_global.json`).
* **Forecast band.** The 10th/90th percentile band is built from `actual − predicted` residuals; four tests cover the
  sign convention (see bug 1 in §6).
* **Data integrity.** Append mode replaces an hour only when the new file has a value for it
  (`test_append_replaces_overlapping_values_but_never_erases_readings_with_gaps`; the test fails on the previous code).
* **Schema.** The Alembic migration reproduces exactly the schema of the ORM models, upgrades and downgrades on SQLite
  and PostgreSQL, and the production-mode app boots on a migrated database.
* **Backup and restore.** A dump/restore round trip returns identical data on SQLite and PostgreSQL; corrupted
  archives and path-traversal entries are refused.

## 3. Security tests (`tests/integration/test_security.py`, 16 tests)

Every route except health and the auth endpoints refuses an unauthenticated call; the role matrix (viewer / analyst /
admin) is derived from the route table itself so a new route cannot silently skip it; security headers and CORS
behaviour; mass assignment (clients cannot set `role`, `owner_id`, …); SQL-injection strings stored and returned as data;
HTML report escapes user text (stored-XSS canary) under a restrictive CSP; one user cannot read, change or delete
another's datasets, models, forecasts, jobs, anomalies or tariffs (IDOR) and gets 404 rather than 403; upload size,
extension and content checks; login, registration and upload rate limits; a forged `X-Forwarded-For` does not evade
rate limiting; error responses and job errors do not leak internals; tokens in the query string are rejected.

Static and dependency checks:

| Tool | Result |
|---|---|
| `ruff check .` | clean |
| `bandit -r backend ml_engine -ll` (medium and high severity) | no findings; one low-severity note (B105) on the development-only placeholder secret, which production mode refuses |
| `pip-audit -r requirements.txt` | no known vulnerabilities (at the time of the run) |
| `npm audit --omit=dev --audit-level=high` | exit 0; 0 high/critical; 2 moderate (react-router 6.x, see `docs/16_frontend.md` §4) |
| `npm audit` (including development tools) | 2 critical in `vitest`/`tinypool` (test runner only, never shipped; fix is a breaking major upgrade) |
| `cfn-lint infrastructure/aws/*.yaml` | clean |
| `scripts/check_secrets.py` | 0 findings |
| `docker compose config -q` | valid |

## 4. Measured performance and resources

Single user on `localhost`, one uvicorn process, production mode, PostgreSQL 16, 100 requests per endpoint. This is a
functional measurement, **not a load test**; it supports no capacity claim.

| Item | Measured |
|---|---|
| `/health/live` | p50 1.6 ms, p95 2.0 ms |
| `GET /datasets` | p50 5.2 ms, p95 6.3 ms |
| `GET /datasets/{id}/readings` | p50 8.7 ms, p95 11.4 ms |
| Bundled sample ingestion (8,760 hours) | 0.5 s |
| Training the 24-model bundle on the sample | 12.4 s to 25 s (varies with machine load) |
| 24-hour forecast / anomaly run on the sample | 0.6 s / 0.5 s |
| Peak memory of the API process over the whole workflow | 294 MB |
| Research benchmark, tree models (full 34,151 valid hours) | peak 600 MB, 743 s |
| Research benchmark, one LSTM seed | peak 1.1 GB, 145 s (3 seeds: 667 s) |
| Dataset profiling of the raw file (2,075,259 one-minute rows, 127 MB) | peak 508 MB |

All of these are below the 8 GB budget (NFR-01). Peak memory of the Docker images was not measured (they were not run).

## 5. Browser end-to-end test

`tests/e2e/test_ui_workflow.py` registers a new user in Chromium (first with a weak password, which the form must refuse
before sending anything), loads the sample, trains a model with production parameters, creates a forecast and runs
anomaly detection. It asserts that the dataset hours, the 1-hour hold-out MAE and the forecast peak shown on screen equal
the values the API returned, that every expected API call happened with the expected status, and that there were no 5xx
responses or console errors. Screenshots go to `docs/screenshots/e2e/` (git-ignored; uploaded as CI artefacts).

**A test-quality lesson.** The first version of this test passed on its first run but was **vacuous**: it waited for "a
table" and matched the empty *Saved forecasts* table, so it passed before any forecast existed. This was only noticed
by looking at the screenshot it had saved. The test now waits for the forecast card itself and compares numbers with the
API. Screenshots are therefore part of the review of any UI test.

## 6. Defects found during verification

1. **Forecast band sign.** The 10th/90th percentile band had been built from `predicted − actual`, which mirrored it (the
   wider side was below the forecast; measured coverage on a skewed synthetic case was 70.5 % against a nominal 80 %).
   Found while writing the documentation; fixed (`residual_band`) with four tests. Models trained before the fix keep
   their stored quantiles and should be retrained.
2. **Rate-limit evasion.** The client address was taken from the left-most `X-Forwarded-For` entry, which a client can forge.
   Fixed to count trusted hops from the right (`ENERGIQ_TRUSTED_PROXY_HOPS`), with tests.
3. **Unclosed file handles** in the CSV reader (ResourceWarning). Fixed.
4. **Append data loss.** Appending a file with gaps erased stored readings in the overlap. Fixed with a regression test
   that fails on the old code.
5. **Benchmark not reproducible across XGBoost builds.** Found by re-running the chain; results regenerated under the
   pinned environment and library versions are now recorded in every result file (`docs/06_model_evaluation.md` §8).
6. **Post-sign-in redirect** (frontend): opening a protected page while signed out landed on `/` after sign-in instead of
   the requested page. Found in live testing by the frontend author; fixed with two tests.
7. **Vacuous browser test** (§5).

## 7. Not tested

* **Docker images were never built or run** (the workspace cannot pull base images); `docker compose config` and the
  entrypoint script (with a stub for Alembic) were checked, nothing more. The CI job that builds them has not run.
* **No GitHub Actions run**: the repository was not pushed, so every CI job is unexecuted as a pipeline (each step was run
  locally instead, as listed above).
* **No AWS deployment**; the CloudFormation templates only passed `cfn-lint`.
* **Windows** was not used; **browsers other than Chromium**, screen readers, slow networks and phones (beyond emulated
  viewport sizes) were not tested.
* **No load or soak testing**; no multi-process deployment testing (the rate limiter and job runner are single-process).
* **Anomaly accuracy on real faults** cannot be tested: the dataset has no labels (synthetic injection only).
* **Frontend coverage** was not measured.
