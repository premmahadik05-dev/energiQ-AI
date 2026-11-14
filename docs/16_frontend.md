# 16. Web frontend

> **Updated by the final upgrade** (details: [`UI_UX_IMPROVEMENTS.md`](../UI_UX_IMPROVEMENTS.md), [`FINAL_TEST_REPORT.md`](../FINAL_TEST_REPORT.md)). React Router is now **7.18.5** and Vitest **5.1.0**; there are **12** society pages (new: *Compare communities*) and **151** frontend tests; tariffs are created on the *Cost and peaks* page (tariff manager), not only through the API; production dependencies have **0** advisories. Sections below that still describe the earlier state (118 tests, router 6.30, tariff through the API only, two moderate advisories) are kept as the record of that state and are corrected here, in this note.

Code: `frontend/` (about 7,800 lines of TypeScript/TSX in 76 files, tests included). Run instructions: `frontend/README.md` and
`docs/manuals/installation.md`. Usage: `docs/manuals/user_guide.md`. Screenshots: `docs/screenshots/` (taken from the real
application against a real backend, Chromium only).

## 1. Stack and structure

React 18.3, TypeScript (strict), Vite 6, Tailwind 3, Recharts 2.15, React Router 7.18 (6.30 before the final upgrade). Dependencies are pinned exactly in
`package.json` and locked in `package-lock.json`; `npm ci` reproduces the install.

| Folder | Content |
|---|---|
| `src/api` | One typed client for the API (`client.ts`; endpoint groups in `endpoints.ts`; response types in `types.ts`), job polling (`polling.ts`). Errors carry the server's message; HTTP 429 shows how long to wait (`Retry-After`). |
| `src/auth` | Auth context, route guards (sign-in required; admin page only for admins), `WriteOnly` (hides write actions from viewers). |
| `src/hooks` | `useApi` (loading/error/data with abort), `useJob` (poll a background job). |
| `src/pages` | Sign-in and registration; the twelve society pages in `pages/society` (overview, compare communities, consumption, forecasting, buildings, common facilities, cost and peaks, alerts, recommendations, reports, data sources, society admin); Jobs, Notifications, Administration (users, audit, system), 404. |
| `src/components` | Charts (line/band/markers and bars, each with a table alternative), form fields, tables, notices, error boundary, the sign-in/registration layout. |
| `src/lib` | Formatting, validation (same password rule as the server), safe internal links, storage wrapper, time handling. |

Society imports, uploads and training are **background jobs**: the page shows a progress bar and updates when the
job finishes, so the browser never waits on one long request.

## 2. Design decisions that matter

* **Real data only.** Every number, series and table row comes from an API response; there is no demo data in the
  interface. The one exception is the built-in DEMO tariff, which the *server* provides and which is labelled "not a real
  utility price" wherever it is shown (requirement NFR-09).
* **Honest wording** is part of the interface, not an afterthought: anomalies are "unusual hours, not confirmed
  faults" and no accuracy is shown for them; savings are labelled scenario estimates with their assumption; the hold-out
  period and the baseline comparison sit next to every accuracy figure; forecast bands are called a rough range;
  warnings and caveats sent by the API are displayed verbatim.
* **Token handling.** The access token lives in memory and `sessionStorage` (cleared on sign-out and on any 401). The only
  thing kept in `localStorage` is the e-mail address, and only while "Remember my e-mail" is ticked on the sign-in page; lint rules forbid direct
  `localStorage` use, so everything goes through `lib/storage.ts`. There is no
  `dangerouslySetInnerHTML` (also lint-banned), so server text is always escaped by React.
* **Authenticated downloads.** The PDF and CSV reports are fetched with the bearer token as
  blobs (an `<img src>` cannot send a header), and the object URLs are revoked afterwards. Tokens are never put in URLs
  (the backend rejects that, see `docs/10_security.md`).
* **Open-redirect protection.** The post-login return path and links inside notifications pass through
  `safeInternalLink`, which refuses `//host`, backslash and off-site targets.
* **Roles.** Viewers see no write buttons and non-admins cannot open `/admin` or `/society-admin`. This is convenience only; the server
  enforces roles on every request (role-matrix test in `tests/integration/test_security.py`).
* **Accessibility.** Semantic landmarks and headings, labelled inputs, visible focus, a skip link, a **Chart/Table
  toggle on every chart**, status never conveyed by colour alone, one light theme with text and chart colours that pass the WCAG 2 AA contrast rules,
  responsive down to phone width. Checked by keyboard, by automated tests and, for the society pages, by an axe-core audit (`scripts/ui_audit.py`); **not** checked with a screen reader.
* **Charts** follow one rule set: one y-axis per chart, thin lines, a legend whenever there are two or more series, a
  light forecast band, event markers with a table of the same events.

## 3. Verification (what was run, with results)

Commands run in `frontend/` on Linux with Node 22 (re-run independently by the project lead after the frontend was
written, from a clean `npm ci`):

| Check | Result |
|---|---|
| `npm run lint` | exit 0, no errors or warnings |
| `npm run typecheck` (`tsc -b --noEmit`, strict) | exit 0 |
| `npm test` (Vitest + Testing Library, jsdom) | **118 tests in 9 files, all passed** at that time; **151 tests in 12 files** after the final upgrade |
| `npm run build` | exit 0; largest chunk `vendor-recharts` 417 kB (113 kB gzip), `vendor-react` 167 kB (54 kB gzip) |
| `npm audit --omit=dev --audit-level=high` (production dependencies) | exit 0: **0 high/critical**, 2 moderate (react-router 6.x, see §4) at that time; **0 vulnerabilities** after the upgrade to react-router 7.18.5 |

The 118 tests are split as pages 21 (sign-in, registration, notifications, administration, removed addresses), society 26, auth 18, library 14,
API client 16, validation 4, components 8, job polling 5 and polling helper 6. They run against **40 JSON fixtures captured from the running
backend** (17 from the sign-in, jobs, tariff, notification and administration endpoints and 23 from the society endpoints; only the JWT in the
login fixtures was replaced by a placeholder), so the interface is tested against the real response shapes rather than shapes invented by the
test author. They cover rendering from API data, client-side validation that sends nothing when invalid, error and 429 handling, the real
route-guard flow, role gating, escaping, and storage decisions.

**Live checks (first stage, before the single-meter pages were removed).** The frontend author drove a production build in real Chromium (Playwright) against a real backend:
registration and sign-in, sample load, upload, append and delete of a throwaway dataset, training with progress,
forecast and look-back forecast, anomaly detection with acknowledge/unacknowledge, explainability, tariff create/delete,
all 11 benchmark figures, jobs and notifications, administration (role change, audit filter, system stats), viewer
read-only behaviour, authenticated downloads, the real 401 and 429 paths, and the dashboard figures; a
final script passed 9 of 9 checks with an empty browser console. 33 page/theme/viewport combinations showed no
horizontal overflow. The screenshots in `docs/screenshots/` come from these runs.

*Later changes.* (1) The interface now has a single light theme. The dark theme and its toggle were removed, together with their screenshots, and the
society screens were redesigned (`docs/society/01_architecture.md`, section Interface design). (2) **The single-meter (household) pages were removed from the interface**:
Dashboard, Datasets, Forecast, Models, Anomalies, Explainability, Optimisation and Benchmark, with the "Single-meter tools" navigation group, the dataset picker, the dataset state and the code only they used. Their old
addresses now show the not-found page. The backend routes (`/api/v1/datasets`, `/models`, `/forecasts`, `/anomalies`, `/explain`, `/tariffs`, `/optimize`, `/benchmark`), the ML library and the research benchmark were **not** changed and are still tested
through the API (`tests/e2e/test_http_workflow.py`); they simply have no web page any more. Jobs and Administration stay, now under a "System" group. The one thing that
used to be done on a removed page and is still needed is creating a tariff: it was done through the API only at that time; the final upgrade added a tariff manager to the *Cost and peaks* page (add, use and delete a tariff from your own bill; see `UI_UX_IMPROVEMENTS.md`). The screenshots of the removed pages were deleted;
`society_01_` to `society_12_`, `auth_01_` to `auth_08_` and `system_01_` to `system_07_` show the current interface.

**Browser end-to-end test in the repository** (`tests/e2e/test_ui_workflow.py`): a real Chromium drives the built app
against a real uvicorn server through registration (including the weak-password and mismatched-confirmation refusals), the Fox society overview, an alert
acknowledgement and the creation and download of a monthly PDF report, and asserts that the numbers on screen (7-day energy, predicted peak) equal what the
API returned, that the single-meter links are gone and their old address shows the not-found page, that no request failed with a 5xx status and that the console stayed free of errors.
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
* Frontend line/branch coverage was not measured in the final pass (`npm run test:coverage` exists).
* Models trained before the forecast-band sign fix (`residual_band`, found while writing the documentation) keep their
  stored quantiles, so their band is mirrored; **retrain** such models. No deployment of this project predates the fix.
* The notification bell and page remain, but only the removed household jobs created notifications; the society jobs leave none, so the list is normally empty.
