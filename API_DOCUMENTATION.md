# EnergiQ AI: API documentation

The backend is a FastAPI application. This guide explains how to call it and what the society endpoints return. Two generated files complete it and cannot drift from the code, because `scripts/make_api_reference.py` rebuilds them from the real routes:

* [`docs/api/API_REFERENCE.md`](docs/api/API_REFERENCE.md): every operation (76), its access rule, success status and handler.
* [`docs/api/openapi.json`](docs/api/openapi.json): the machine-readable OpenAPI 3.1 schema (69 paths, 74 operations under `/api/v1`).

When the app runs in the `dev` environment (what `RUN_PROJECT.bat` uses) an interactive page lists and tries every endpoint: **http://127.0.0.1:8000/docs**. In `prod` the interactive page and the schema are switched off.

## 1. Basics

| | |
|---|---|
| Base URL | `http://127.0.0.1:8000/api/v1` (the launcher may choose the next free port; it prints the address) |
| Format | JSON in and out, except uploads (multipart) and downloads (CSV, PDF) |
| Timestamps | Local, **timezone-less** text such as `2017-12-31 23:00:00`: the local clock time of the community (`timezone` field of a society) exactly as published in the source data, which has no daylight-saving gap or repeat. The app does not shift timestamps. |
| Units | Power in **kW**, energy in **kWh**, area in m², money in the currency of the tariff |
| Errors | `{"detail": ...}`. `401` not signed in, `403` wrong role, `404` unknown id, `409` conflict (for example a duplicate tariff name), `410` models not installed, `413`/`422` invalid input, `429` rate limit (with `Retry-After`) |
| Missing data | Never invented. A missing hour is `null`; summary figures say how many hours they cover |
| Long work | Upload, import and training return `202` and a job; poll `GET /jobs/{id}` until `status` is `succeeded` or `failed` |

### Sign in

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<your password>"}'
# {"access_token":"eyJ...","token_type":"bearer","expires_in":3600,"user":{"id":1,"email":"...","role":"admin",...}}
```

PowerShell:

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" -Body '{"email":"admin@example.com","password":"<your password>"}'
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/societies -Headers $h
```

Send `Authorization: Bearer <token>` on every other call. Tokens last one hour. The launcher's password for your copy is in `.energiq-run/admin_login.txt`.

### Roles

| Role | Can do |
|---|---|
| `viewer` | read everything the app shows |
| `analyst` | everything a viewer can, plus acknowledge alerts, create reports, create and delete own tariffs. New accounts from `POST /auth/register` are analysts. |
| `admin` | everything, plus import, upload, train and delete societies, manage users, read the audit log and the admin-only meter details |

The "Access" column of [`API_REFERENCE.md`](docs/api/API_REFERENCE.md) shows the rule of each route, read from the code.

Protections that are always on: passwords stored with Argon2, short-lived signed tokens, per-IP rate limits on sign-in and registration, an audit log of sign-ins (successful and failed), registrations, imports, uploads, training, deletions, tariff changes and role changes, uploads limited in size, strict input validation (wrong types and out-of-range numbers return `422`), and building names shown as pseudonymous codes (`FOX-B04`) to everyone except admins.

## 2. Society endpoints

`{id}` is the society id from `GET /societies`.

| Method and path | Parameters | Returns |
|---|---|---|
| `GET /societies` | | The communities, with size, period, `has_model`, `forecast_ready` |
| `GET /societies/compare` | | One row per community: energy per m², load factor, peak per m², saved 24 h accuracy as a share of average demand, plus notes on how to compare |
| `GET /societies/{id}` | | One community with its data card |
| `GET /societies/{id}/overview` | | Latest demand, 24 h / 7 d / 30 d energy, forecast headline, cost under the chosen tariff, open alerts |
| `GET /societies/{id}/consumption` | `resolution` = `hourly`, `daily` (default), `weekly`, `monthly`; `start`, `end` | Energy, average and peak demand per period, with the number of valid hours |
| `GET /societies/{id}/forecast` | `origin` (default: last hour of data), `horizons` (comma list), `tariff_id` | Forecast points with an 80 % range, the model used per horizon, and its saved accuracy |
| `GET /societies/{id}/backtest` | `horizon` 1 to 168 (default 24), `start`, `end`, `limit` ≤ 6000 | Held-out predictions next to what happened and the baseline |
| `GET /societies/{id}/models` | | The evaluation: cross-validation, test results per model and horizon, the model selected, the paired bootstrap |
| `GET /societies/{id}/error-analysis` | `horizon` 1 to 168 (default 24) | Bias, error percentiles, error by hour of day, error histogram, interval coverage |
| `GET /societies/{id}/explain/global` | | Mean absolute SHAP value per input and per input group |
| `POST /societies/{id}/explain/local` | body `{horizon, origin?}` | SHAP contributions that add up to the forecast for one origin |
| `GET /societies/{id}/buildings` | `start`, `end` | Buildings: energy, share, energy per m², peak |
| `GET /societies/{id}/buildings/{bid}/consumption` | `resolution`, `start`, `end` | One building |
| `GET /societies/{id}/buildings-monthly` | | Monthly energy per building |
| `GET /societies/{id}/facilities` | | Lifts, pumps, street lighting and clubhouse when they are metered; otherwise a clear "not metered" answer |
| `GET /societies/{id}/peaks` | `start`, `end` | Top hours, daily peaks, load-duration curve, demand distribution, peak-forecast evaluation |
| `POST /societies/{id}/cost` | body `{tariff_id, start?, end?}` | Energy cost with a monthly breakdown (a demo tariff is the default and is labelled) |
| `GET /societies/{id}/anomalies` | `scope`, `severity`, `min_severity` 1 to 3, `building_id`, `acknowledged`, `start`, `end`, `sort` = `time` or `severity`, `limit` ≤ 500, `offset` | Alert events with their explanation, and a summary |
| `PATCH /societies/{id}/anomalies/{eid}` | body `{acknowledged}` | Acknowledge or reopen (analyst, admin) |
| `POST /societies/{id}/recommendations` | body `{tariff_id}` | Recommendations, each with the evidence it is based on |
| `GET /societies/{id}/reports`, `POST /societies/{id}/reports` | body `{kind, format, start?, end?, resolution?, horizon?, tariff_id?}` | List reports; create `monthly` (PDF) or `consumption`, `forecast`, `anomalies`, `cost`, `buildings` (CSV) |
| `GET /societies/{id}/reports/{rid}/download` | | The file |
| `DELETE /societies/{id}` | | Delete a community and its data (admin) |

### Tariffs

| Method and path | Notes |
|---|---|
| `GET /tariffs` | The built-in `DEMO tariff` (not a real utility price, marked `is_demo`) and the tariffs you saved |
| `POST /tariffs` | body below; `201`. A second tariff with the same name for the same owner returns `409`. |
| `DELETE /tariffs/{id}` | Only the owner may delete. The built-in demo tariff is not stored, so it cannot be deleted. |

```json
{ "name": "Home bill",
  "currency": "INR",
  "weekday_rates": [7.5, 7.5, "... 24 numbers, one per hour of the day, per kWh"],
  "weekend_rates": [7.5, 7.5, "... 24 numbers"],
  "daily_fixed_charge": 12 }
```

Rules: `name` 1 to 80 characters, `currency` 1 to 8 characters, exactly 24 + 24 rates, each between 0 and 1,000,000, fixed charge 0 to 1,000,000. Violations return `422` with the field names, which the app shows next to the fields.

### Administration and system

| Method and path | Purpose |
|---|---|
| `POST /admin/societies/import-bundled` | Import the bundled communities that are not in the database yet (job, admin) |
| `POST /admin/societies/upload` | Upload a wide CSV of real meter readings (timestamp column plus one column per meter) and an optional meter mapping; processed as a job (admin) |
| `POST /admin/societies/{id}/train` | Evaluate and deploy forecasting models for a stored society (job, admin) |
| `GET /admin/users`, `PATCH /admin/users/{id}` | List users; change role or active state (admin; you cannot demote or deactivate your own account) |
| `GET /admin/audit`, `GET /admin/system` | Audit log and system counts (admin) |
| `GET /jobs`, `GET /jobs/{id}` | Background jobs and their progress |
| `GET /notifications`, `POST /notifications/read-all`, `POST /notifications/{id}/read` | Messages about finished jobs |
| `GET /health/live`, `GET /health/ready` | Liveness and readiness (public) |
| `GET /metrics` | Prometheus text metrics when enabled |

### Single-meter (household) endpoints

`/datasets`, `/forecasts`, `/models`, `/anomalies`, `/explain`, `/optimize` and `/benchmark` belong to the first stage of the project (one household meter, the UCI data). They remain available and tested, but the web interface no longer has pages for them. See [`docs/09_backend_and_api.md`](docs/09_backend_and_api.md) and the reference table.

## 3. Examples (real responses, shortened)

**Communities**

```
GET /societies
[{"id":1,"key":"bull","name":"BDG2 site Bull residential community","timezone":"US/Central",
  "start":"2016-01-01 00:00:00","end":"2017-12-31 23:00:00","hours":17544,"valid_hours":16862,
  "buildings":16,"floor_area_sqm":171886.1,"has_model":true,"forecast_ready":true,
  "source_name":"Building Data Genome Project 2 (BDG2)", ...}, ...]
```

**Forecast** (Fox, next hours after the last data hour; `family` says which model produced each point)

```
GET /societies/3/forecast?horizons=1,2,24
{"origin":"2017-12-31 23:00:00","origin_value_missing":false,
 "points":[{"horizon":1,"ts":"2018-01-01 00:00:00","kw":1077.99,"lower_kw":1042.12,"upper_kw":1117.48,"family":"random_forest","actual_kw":null},
           {"horizon":2,"ts":"2018-01-01 01:00:00","kw":1077.53,"lower_kw":1034.70,"upper_kw":1122.74,"family":"random_forest","actual_kw":null}, ...],
 "trained_through":"2017-12-31 23:00:00","model_id":"society_fox_2017123123",
 "accuracy":{"24":{"model":"random_forest","mae_kw":38.47,"rmse_kw":64.82,"mape_pct":2.74,"r2":0.93,"baseline":"naive","baseline_mae_kw":48.51}, ...},
 "note":"Each point is a direct forecast from the origin hour using data up to the origin only. Ranges are empirical 80% bands from out-of-fold residuals."}
```

`lower_kw` and `upper_kw` are an empirical 80 % range from out-of-fold residuals. On the held-out test period the Fox 24 h range covered 85.9 % of actual values (`error-analysis`), so it is an estimate of the range, not a guarantee. An `origin` earlier than the end of the data gives a retrospective forecast that uses only data up to that hour, and `actual_kw` then holds what really happened. An origin outside the data range returns `422 {"detail":"origin is outside the data range"}`.

**Error analysis**

```
GET /societies/3/error-analysis?horizon=24
{"horizon":24,"model":"random_forest","baseline":"naive","test_period":["2017-07-01 00:00:00","2017-12-31 23:00:00"],
 "hours":4356,"bias_kw":4.05,"mae_kw":38.47,"rmse_kw":64.82,"baseline_mae_kw":48.51,
 "abs_error_percentiles_kw":{"p50":24.39,"p90":85.95,"p95":117.93,"p99":241.85},"interval_coverage_pct":85.88,
 "by_hour":[{"hour":0,"n":181,"mae_kw":39.36,"bias_kw":1.40,"baseline_mae_kw":45.47}, ...],
 "histogram":[{"from_kw":-242.0,"to_kw":-221.83,"hours":9}, ...]}
```

**A rejected request** (empty tariff name)

```
POST /tariffs   {"name":"","currency":"INR","hourly_rates":[1,1,...]}
422 {"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character", ...},
               {"type":"missing","loc":["body","weekday_rates"],"msg":"Field required", ...}, ...]}
```

**Not signed in / unknown id**

```
GET /societies                 -> 401 {"detail":"Not authenticated"}
GET /societies/9999/overview   -> 404 {"detail":"Society not found"}
```

## 4. What the numbers mean (read before quoting them)

* The bundled communities are real hourly meter data of residential-labelled university buildings from the public BDG2 research data set (2016 to 2017). They are **not** a registered housing society. Forecasts for `2018-01-01` onward are genuine forecasts beyond the end of the data; there is no 2018 measurement to compare them with.
* Accuracy figures come from a held-out test period (`2017-07-01` to `2017-12-31`) scored once. The model at each horizon is chosen by cross-validated error on earlier data, **baselines included**. For some communities and horizons the best choice is a simple baseline (for example Eagle and Rat at 24 h), and the API says so (`best_overall_is_baseline`).
* `mae_improvement_vs_best_baseline_pct` compares the best *learned* model with the best *baseline* on the test period. It is not necessarily the improvement of the deployed model.
* The default tariff is a placeholder (`is_demo: true`) and its cost is an estimate, not a bill.

## 5. How this documentation is kept honest

* The route table and the OpenAPI file are generated: `python scripts/make_api_reference.py`.
* `tests/integration/test_api_*.py` call every society endpoint with real data, including the error cases above; `tests/integration/test_security.py` checks the access rule of every route against the table. The latest run is recorded in [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md).
