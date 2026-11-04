# EnergiQ AI frontend

Single-page web app for the EnergiQ AI backend (energy forecasting, anomaly detection, optimisation).
React 18 + TypeScript (strict) + Vite + Tailwind + Recharts + React Router. Every number, label, series and
table row shown comes from the API; nothing is hard-coded demo data.

## Run it

Requires Node 20.19 or newer (developed and tested on Node 22) and the backend on `http://127.0.0.1:8000`.

```bash
cd frontend
npm ci            # installs exactly what package-lock.json pins
npm run dev       # http://localhost:5173, /api and /health are proxied to the backend
```

| Script | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with the API proxy |
| `npm run build` | `tsc -b` (strict type check, must be clean) then `vite build` into `dist/` |
| `npm run preview` | serves `dist/` on `http://localhost:4173` with the same proxy |
| `npm run lint` | ESLint (flat config, typescript-eslint, react-hooks) |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm test` | Vitest + Testing Library (jsdom), single run |
| `npm run test:watch` / `npm run test:coverage` | watch mode / v8 coverage |

All scripts are plain npm scripts (no shell syntax), so they run the same on Windows, macOS and Linux.

Backend for local work (from the repository root, see the root README for the full setup):

```bash
ENERGIQ_ENV=dev python -m uvicorn backend.app.main:create_app --factory --port 8000
```

New accounts get the `analyst` role. To get an admin account set `ENERGIQ_ADMIN_EMAIL` and
`ENERGIQ_ADMIN_PASSWORD` for the backend; the admin page is only reachable with that role.

## Environment variables

All optional, read at build/start time (see `.env.example`; copy to `.env.local` to override).

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE` | empty (same origin) | Base URL of the API, e.g. `https://api.example.org`. Leave empty when a proxy (Vite in dev, nginx in production) serves `/api` and `/health` on the same origin. If you set an absolute URL the backend must allow the origin in `ENERGIQ_CORS_ORIGINS`. |
| `VITE_MAX_UPLOAD_MB` | `50` | Client-side pre-check for uploads only. The server limit (`ENERGIQ_MAX_UPLOAD_MB`) stays authoritative. |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the Vite dev and preview servers forward `/api` and `/health`. |

## What is in the app

| Route | Page |
| --- | --- |
| `/login`, `/register` | Sign in / create account. Client checks mirror the backend rules (e-mail shape, password 10-128 characters with letters and digits, common passwords, at least 5 distinct characters). |
| `/` | Dashboard: active dataset selector, KPI tiles (quality score, valid hours, active model hold-out MAE vs best baseline, open anomalies, latest forecast peak), history + latest forecast chart, unread notifications, running jobs. |
| `/datasets`, `/datasets/:id` | Upload (drag and drop or picker, client pre-check), load the bundled sample, list; detail with the quality report and warnings verbatim, profile charts, readings explorer (range, drag/keyboard zoom, gaps stay gaps), append, delete with confirmation, authenticated HTML report download. |
| `/forecast` | Create a forecast (model version, optional origin for back-tests), chart with the interval band, table view, saved forecasts, authenticated CSV export, hold-out accuracy note. |
| `/models`, `/models/:modelId` | Versions, train (background job with progress), activate, delete, per-horizon hold-out table vs best baseline with the improvement, drift and realised-error monitoring with PSI/KS explained. |
| `/anomalies` | Run detection with a sensitivity, severity summary, filtered/sorted event table (severity, status, date range), acknowledge/unacknowledge, timeline with markers, "not confirmed faults" note. |
| `/explain` | Global feature-group shares per horizon, top individual features, local explanation (baseline to forecast, by group, plus the largest single drivers). |
| `/optimize` | Tariffs (the built-in one is marked DEMO), create a tariff (24 weekday + 24 weekend rates), cost analysis with monthly chart, recommendations with evidence and estimate-labelled scenarios, cheapest-window scheduler. |
| `/benchmark` | The stored offline benchmark: method/horizon tables, bootstrap differences, protocol, anomaly benchmark, feature importance, and the figures (authenticated PNG blobs, alt text and a caption naming the hold-out period). Numbers are shown as the server stored them, never recomputed. |
| `/admin` | Admin only: users (role, deactivate; you cannot change your own role), audit log with action filter, system statistics. |
| `/notifications`, `/jobs` | Notification list (mark read / all read), recent background jobs. |
| `*` | Not-found page. A render error shows the error boundary instead of a blank screen. |

The app shell has a sidebar (drawer on phones), the active dataset selector, a running-jobs indicator, the notification
bell with a dropdown, a manual light/dark toggle (on top of `prefers-color-scheme`) and the user menu.

## Structure

```
src/
  api/        client.ts (fetch wrapper, errors, blobs), endpoints.ts (one typed function per route),
              polling.ts (job polling with back-off), types.ts (response shapes)
  auth/       tokenStore.ts, AuthContext.tsx, guards.tsx (RequireAuth, PublicOnly, RequireRole, WriteOnly)
  state/      ToastContext, JobsContext (tracks and polls background jobs), DatasetContext (active dataset)
  hooks/      useApi (keyed fetch with cancellation), useJob, useBlobUrl, useTheme
  components/ ui/ (forms, table, modal, tabs, feedback), charts/ (ChartFrame, TimeSeriesChart, CategoryCharts, ForecastChart)
  lib/        formatting, naive-timestamp helpers, axis scale, validation, evidence labels, storage
  layout/     AppShell, Topbar
  pages/      one file per route, each lazy loaded
  test/       setup.ts, harness.tsx (fetch mock + app renderer), fixtures/ (captured API responses)
```

Every page is its own chunk and Recharts sits in its own vendor chunk (`vendor-recharts`, about 113 kB gzipped),
which only loads with the first page that draws a chart.

## Decisions worth knowing

### Authentication and storage

* The bearer token is kept in memory and in `sessionStorage` (`energiq.token`) so a reload of the same tab keeps the
  session. It is **not** in `localStorage`, never in a URL, and is cleared on logout and on any 401 from an
  authenticated request (the user then lands on the sign-in page with a "session ended" notice). An ESLint rule bans
  the bare `localStorage` global so it cannot slip in.
* `sessionStorage` also holds the active dataset id. `localStorage` holds only the theme choice. All storage access is
  wrapped in try/catch; the app renders correctly with storage blocked.
* Roles: `admin` and `analyst` may change data, `viewer` is read-only. Write buttons are hidden for viewers
  (`WriteOnly`) and `/admin` shows "Access denied" for non-admins, but this is convenience only: the backend stays
  the authority and its 403 is shown if it ever disagrees.
* Authenticated downloads (forecast CSV, dataset HTML report) and the benchmark figure PNGs are fetched with the
  `Authorization` header as blobs, then saved or shown through an object URL that is revoked afterwards. A plain
  `<a href>` or `<img src>` could not carry the header.
* No `dangerouslySetInnerHTML` anywhere (lint-enforced); API text is rendered through React's escaping. Notification
  links are only followed when they are app-internal paths.

### Background jobs

Upload, sample load, append, training and anomaly detection answer `202` with a job. `JobsContext` polls
`GET /jobs/{id}` about once a second, backing off to 5 s while nothing changes (and resetting when progress moves),
stops on a terminal status, and then refreshes the affected data. Polling is cancelled on unmount. A job that
resumes after a page reload is picked up from `GET /jobs`. `429` responses show the server text plus the
`Retry-After` seconds ("Too many requests, slow down. Try again in 295 s.").

### Honesty rules the UI follows

* Dataset warnings, the "DEMO tariff" labelling, anomaly notes and the model hold-out period are shown verbatim from
  the API. Anomalies are called unlabelled statistical findings ("not confirmed faults") and no accuracy figure is
  ever shown for them. Scenario savings are labelled "estimate".
* Accuracy is always described as measured on a hold-out period at selected horizons; the benchmark figure captions
  name the benchmark's hold-out period, except the anomaly figures which are whole-series unsupervised runs.
* When the monitoring response says no data arrived since training, the drift card says that the "recent" window is
  the end of the training data itself.
* Timestamps from the API are naive wall-clock strings. They are displayed as given and mapped to "milliseconds as if
  UTC" only for chart arithmetic, so the browser time zone or DST can never shift a value.
* Chart axis ranges are computed from the data that is drawn (`lib/scale.ts`) rather than Recharts' automatic domain,
  which mis-sized the axis in one live case (a short anomaly window drew a 0 to 0.4 axis for data up to 4 kW).

### Charts and accessibility

One value axis per chart, fixed categorical colour order, 2 px lines, a legend whenever there are two or more series,
anomalies as distinct marker shapes (spike, drop, flat run, pattern) plus a severity colour plus a table, the forecast
band as a light area. Every chart sits in a `ChartFrame` with a text summary for assistive technology and a
Chart/Table switch showing the same numbers. Forms use labelled inputs, focus rings are visible, the layout works down
to a 390 px phone width without horizontal page scroll, and colour is never the only encoding.

## Tests

`npm test` runs 122 tests (Vitest, Testing Library, jsdom):

* API client: Authorization header, no token on login, 401 handling, 429 + Retry-After, validation error parsing,
  non-JSON error bodies, network failure, blob downloads.
* Job polling: terminal states, back-off and reset, abort, transient errors, `useJob` with fake timers and unmount.
* Auth: token only in `sessionStorage`, cleared on logout and 401, route guards, viewer cannot see write buttons,
  non-admin cannot reach `/admin`, sign-in returns to the originally requested page (never an off-site path).
* Form validation, formatting, naive timestamps, axis scale, series helpers.
* Page renders with a mocked `fetch` that answers with response bodies **captured from the running backend**
  (`src/test/fixtures/`, described in `fixtures/index.ts`): login errors, dashboard KPIs and empty/error states,
  datasets, anomalies, models, forecast CSV export, optimisation DEMO labelling, benchmark figures, admin,
  notifications, not-found, theme and storage decisions, markup in API text staying inert.

There are no markup snapshot tests. The only edit to the captured fixtures is that the JWT in `login*.json` was
replaced by a placeholder. Role variants (`viewer`) reuse the captured user with the `role` field changed.

## Known limitations

* `npm audit --omit=dev --audit-level=high` passes (no high or critical findings). It still lists two **moderate**
  advisories against react-router 6.x (open redirect via a backslash in `<Link>`/`useNavigate`, and an SSR hydration
  issue). The npm fix is a jump to react-router 7, so it is left for a deliberate upgrade. The SSR one does not apply
  to a client-only app; for the redirect, the only redirect target built from untrusted input (the post-login return
  path) and API-supplied notification links go through `safeInternalLink`, which refuses off-site and backslash paths.
* Recharts 2.15 is pinned (npm lists the 2.x line as deprecated). It is stable and fully typed; a move to 3.x is a
  separate piece of work.
* The date-range filter on the anomaly table is applied in the browser: the API has no range filter and returns at
  most 500 events per request (the page says so when the list is truncated).
* PSI/KS thresholds in the monitoring explanation are copied from the backend's documented cut-offs; the API does not
  send them.
* jsdom has no layout, so chart geometry is verified in a real browser (Playwright against the live backend), not in
  the unit tests; the tests check the table alternative that every chart has.
* Dates are shown as `YYYY-MM-DD HH:mm` in the dataset's own clock; there is no locale or time zone switch.
* The login endpoint is limited by the backend to 5 attempts per e-mail per 5 minutes and 10 per minute per IP,
  counting successful sign-ins too; repeated automated sign-ins during testing will hit `429`.
