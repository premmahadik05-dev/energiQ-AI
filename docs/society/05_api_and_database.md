# 5. API and database

The complete, generated operation list (method, path, required role, status, handler) is
[`docs/api/API_REFERENCE.md`](../api/API_REFERENCE.md) and the OpenAPI schema is [`docs/api/openapi.json`](../api/openapi.json). Both are
produced from the running application's routes. The society tables are in [`SCHEMA.md`](SCHEMA.md) (generated from the models) and in the ER diagram
[`docs/diagrams/er_diagram.png`](../diagrams/er_diagram.png).

## Society endpoints (all under `/api/v1`, bearer JWT)

| Group | Operations | Notes |
|---|---|---|
| Societies | `GET /societies`, `GET /societies/{id}` (data card), `DELETE` (admin) | List carries `has_model` and `forecast_ready` |
| Aggregation and analytics | `/overview`, `/consumption`, `/buildings`, `/buildings/{bid}/consumption`, `/buildings-monthly`, `/facilities`, `/peaks` | `consumption` takes `resolution` = hourly, daily, weekly, monthly and an optional `start`/`end`. Every period carries `valid_hours`, `expected_hours` and `complete` |
| Forecasting | `/models`, `/forecast`, `/backtest`, `/explain/global`, `POST /explain/local` | `/forecast` returns points for hours 1–24 (or the `horizons` asked for, up to 168), each with an 80 % range, plus a summary (energy next 24 h, peak, time of peak, cost). `410` when the deployed models are not installed; `409` when no model was trained; `422` for an origin after the data end |
| Anomalies | `GET /anomalies` (filters: scope, severity, min_severity, building_id, acknowledged, start, end, sort, limit, offset), `PATCH /anomalies/{id}` | Acknowledging needs analyst or admin |
| Cost and advice | `POST /cost`, `POST /recommendations` | Tariff = `"demo"`, or the id of a tariff saved through `POST /api/v1/tariffs` (analyst or admin; the web application has no form for it) |
| Reports | `GET /reports`, `POST /reports` (analyst, admin), `GET /reports/{id}/download` | `kind` = monthly (PDF), consumption, forecast, anomalies, cost, buildings (CSV); stored on disk and in `society_reports` |
| Administration | `POST /admin/societies/import-bundled`, `POST /admin/societies/upload` (multipart), `POST /admin/societies/{id}/train`, `GET /societies/{id}/meters`, `PATCH /societies/{id}/buildings/{bid}` | All admin-only. Import, upload and train return `202` with a job, polled through `/jobs/{id}` like every other job |

Example:

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"..."}' | jq -r .access_token)
curl -s -H "authorization: Bearer $TOKEN" 'localhost:8000/api/v1/societies/1/forecast?horizons=1,6,12,24' | jq '.summary'
curl -s -H "authorization: Bearer $TOKEN" 'localhost:8000/api/v1/societies/1/consumption?resolution=daily&start=2017-12-01&end=2017-12-31' | jq '.points[0]'
```

## Privacy

* Buildings have pseudonymous codes (`FOX-B04`). The original dataset identifier (`source_id`), the list of rejected meters and the per-meter cleaning counts appear only in admin responses (the key is omitted for other roles, and a test asserts the dataset's own name never appears in a non-admin response).
* Uploaded societies keep the admin's meter names in `source_id` and `label` (admin-only); other users see `KEY-B01`, `KEY-F01` codes.
* No household identity exists in the data. All authentication events and administrative actions are written to the audit log.

## Validation, errors and security

* Pydantic models validate every body; query parameters are range-checked (`horizon` 1–168, `limit` ≤ 500). Upload format, size (meter file up to 40 MB, mapping file up to 2 MB), interval, column counts and timestamps are validated *before* a job starts (`415`, `413`, `422`).
* Unknown or foreign resources are `404`, wrong role `403`, missing or invalid token `401`; a test calls every route unauthenticated and requires `401` (the society routes included).
* Passwords use Argon2; JWT with expiry; rate limiting, security headers and a strict CORS list are inherited from the platform (`docs/10_security.md`). Errors do not expose stack traces.
* Logging: structured request log with request ids; jobs record progress and failure messages.

## Database

SQLite for development and tests, PostgreSQL 16 for deployment (Alembic migrations; `0002` adds the society tables). Society tables:
`societies`, `buildings`, `meters`, `consumption_records` (hourly kWh per meter), `society_hourly` (hourly society total, valid-meter count, weather),
`society_models` (the evaluation and deployment record per society), `forecast_results` (stored evaluation predictions used by backtests),
`anomaly_events` (whole-society and per-building events with severity, explanation and acknowledgement) and `society_reports`.
Deleting a society removes its rows from all of them, including the stored report files (kept in `society_reports.content`).
