# 16. Web frontend

Code: `frontend/` (about 6,700 lines of TypeScript/TSX in 58 source files). Run instructions: `frontend/README.md` and
`docs/manuals/installation.md`. Usage: `docs/manuals/user_guide.md`. Screenshots: `docs/screenshots/` (taken from the real
application against a real backend, Chromium only).

## 1. Stack and structure

React 18.3, TypeScript (strict), Vite 6, Tailwind 3, Recharts 2.15, React Router 6.30. Dependencies are pinned exactly in
`package.json` and locked in `package-lock.json`; `npm ci` reproduces the install.

| Folder | Content |
|---|---|
| `src/api` | One typed client for the API (`client.ts`; endpoint groups in `endpoints.ts`; response types in `types.ts`), job polling (`polling.ts`). Errors carry the server's message; HTTP 429 shows how long to wait (`Retry-After`). |
| `src/auth` | Auth context, route guards (sign-in required; admin page only for admins), `WriteOnly` (hides write actions from viewers). |
| `src/hooks` | `useApi` (loading/error/data with abort), `useJob` (poll a background job), `useBlobUrl` (authenticated image download), `useTheme`. |
| `src/pages` | Login/Register, Dashboard, Datasets and dataset detail, Forecast, Models, Anomalies, Explainability, Optimisation (tariffs, cost, recommendations, scheduler), Benchmark, Jobs, Notifications, Admin (users, audit, system), 404. |
| `src/components` | Charts (line/band/markers/waterfall with a table alternative for each), form fields, tables, notices, error boundary. |
| `src/lib` | Formatting, validation (same password rule as the server), safe internal links, storage wrapper, time handling. |

Uploads, training, forecasting and detection are **background jobs**: the page shows a progress bar and updates when the
job finishes, so the browser never waits on one long request.

## 2. Design decisions that matter

* **Real data only.** Every number, series and table row comes from an API response; there is no demo data in the
  interface. The one exception is the built-in DEMO tariff, which the *server* provides and which is labelled "not a real
  utility price" wherever it is shown (requirement NFR-09).
* **Honest wording** is part of the interface, not an afterthought: anomalies are "unusual hours, not confirmed
  faults" and no accuracy is shown for them; savings are labelled scenario estimates with their assumption; the hold-out
  period and the baseline comparison sit next to every accuracy figure; forecast bands are called a rough range;
  warnings and caveats sent by the API are displayed verbatim.
* **Token handling.** The access token lives in memory and `sessionStorage` (cleared on sign-out and on any 401). Only the
  theme preference uses `localStorage`; lint rules forbid direct `localStorage` use elsewhere. There is no
  `dangerouslySetInnerHTML` (also lint-banned), so server text is always escaped by React.
* **Authenticated downloads.** CSV exports, the HTML report and the benchmark PNGs are fetched with the bearer token as
  blobs (an `<img src>` cannot send a header), and the object URLs are revoked afterwards. Tokens are never put in URLs
  (the backend rejects that, see `docs/10_security.md`).
* **Open-redirect protection.** The post-login return path and links inside notifications pass through
  `safeInternalLink`, which refuses `//host`, backslash and off-site targets.
* **Roles.** Viewers see no write buttons and non-admins cannot open `/admin`. This is convenience only; the server
  enforces roles on every request (role-matrix test in `tests/integration/test_security.py`).
* **Accessibility.** Semantic landmarks and headings, labelled inputs, visible focus, a skip link, a **Chart/Table
  toggle on every chart**, status never conveyed by colour alone, light/dark themes (system setting plus manual toggle),
  responsive down to phone width. Checked by keyboard and automated tests; **not** checked with a screen reader.
* **Charts** follow one rule set: one y-axis per chart, thin lines, a legend whenever there are two or more series, a
  light forecast band, event markers with a table of the same events.

## 3. Verification (what was run, with results)

Commands run in `frontend/` on Linux with Node 22 (re-run independently by the project lead after the frontend was
written, from a clean `npm ci`):

| Check | Result |
|---|---|
| `npm run lint` | exit 0, no errors or warnings |
| `npm run typecheck` (`tsc -b --noEmit`, strict) | exit 0 |
| `npm test` (Vitest + Testing Library, jsdom) | **122 tests in 8 files, all passed** |
| `npm run build` | exit 0; largest chunk `vendor-recharts` 417 kB (113 kB gzip), `vendor-react` 167 kB (54 kB gzip) |
| `npm audit --omit=dev --audit-level=high` (production dependencies) | exit 0: **0 high/critical**, 2 moderate (react-router 6.x, see §4) |

The 122 tests are split as pages 39, auth 18, library 19, API client 16, validation 11, components 8, job polling 5 and
polling helper 6. They run against **45 JSON fixtures captured from the running backend** (only the JWT in the login
fixtures was replaced by a placeholder), so the interface is tested against the real response shapes rather than shapes
invented by the test author. They cover rendering from API data, client-side validation that sends nothing when invalid,
error and 429 handling, the real route-guard flow, role gating, escaping, and storage decisions.

**Live checks.** The frontend author drove a production build in real Chromium (Playwright) against a real backend:
registration and sign-in, sample load, upload, append and delete of a throwaway dataset, training with progress,
forecast and look-back forecast, anomaly detection with acknowledge/unacknowledge, explainability, tariff create/delete,
all 11 benchmark figures, jobs and notifications, administration (role change, audit filter, system stats), viewer
read-only behaviour, authenticated downloads, theme toggle, the real 401 and 429 paths, and the dashboard figures; a
final script passed 9 of 9 checks with an empty browser console. 33 page/theme/viewport combinations showed no
horizontal overflow. The screenshots in `docs/screenshots/` come from these runs.

**Browser end-to-end test in the repository** (`tests/e2e/test_ui_workflow.py`): a real Chromium drives the built app
against a real uvicorn server through registration (including the weak-password refusal), sample load, model training,
forecast and anomaly detection, and asserts that the numbers on screen (dataset hours, 1-hour hold-out MAE, forecast
peak) equal what the API returned, that no request failed with a 5xx status and that the console stayed free of errors.
It skips with a stated reason when Node, the built bundle or Chromium is missing.

## 4. Known gaps and risks

* **Dependency advisories.** The production dependencies carry two *moderate* advisories in react-router 6.x (fixed only in
  7.18 and later): an open redirect through a backslash in `<Link>`/`useNavigate`, and a constructor-injection issue in
  server-side-rendering hydration. The second does not apply to a client-only application. For the first, the
  application only navigates to targets it builds itself or that pass through `safeInternalLink` (which rejects `//`,
  backslash and off-site paths, covered by tests); the upgrade to react-router 7 was deferred as a deliberate change. The full `npm audit` (including
  development tools that never ship in the bundle) still lists **2 critical** advisories in `vitest`/`tinypool`; the fix is
  a breaking major upgrade of the test runner, and the issues concern the test runner's own mock/worker options, not the
  application. One high advisory in `postcss` (build-time) was removed by updating to 8.5.32 during final verification.
  Recharts 2.x is flagged as deprecated by npm; it was kept for stability.
* Rendering was checked in **Chromium only**; other browsers, slow networks and screen readers were not tested.
* Chart geometry is verified only in a real browser; jsdom tests check data and table alternatives, not pixels.
* The anomaly list is limited to 500 events per request by the API and has no server-side date filter, so the date
  filter works on the loaded events only.
* Drift thresholds quoted in the monitoring text (PSI/KS) are copied from the backend documentation, not read from an
  endpoint; if the backend changes them the text goes stale.
* Frontend line/branch coverage was not measured in the final pass (`npm run test:coverage` exists).
* Models trained before the forecast-band sign fix (`residual_band`, found while writing the documentation) keep their
  stored quantiles, so their band is mirrored; **retrain** such models. No deployment of this project predates the fix.
