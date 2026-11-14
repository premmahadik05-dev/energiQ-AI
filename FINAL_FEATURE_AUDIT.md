# Final feature audit

What every feature of EnergiQ AI does today, whether it works, and the evidence. The commands, results and what could *not* be tested are in [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md); what was wrong and was repaired is in [`BUGS_FIXED.md`](BUGS_FIXED.md).

**How to read the status column**

| Status | Meaning |
|---|---|
| **PASS** | Used in a real browser (Chromium) against the real server and real data, or called over HTTP, and the result was checked. |
| **PASS, fixed** | Was wrong in the baseline (the delivered project before this upgrade); repaired and re-checked. |
| **PASS, new** | Added by this upgrade, then checked. |
| **BY DESIGN** | Deliberately absent or limited; the application says so where a user would look for it. |
| **NOT TESTED** | Could not be run in the available environment. |

Nothing was marked PASS from reading code. "Evidence" names the log or test that shows it; `V` means `docs/final_verification/` (logs in `V/logs`, the scripts that drove the browser in `V/tools`, raw audit results in `V/audit_json`).

## 1. Method

1. **Inventory** (`V/tools/inventory.py`, `V/audit_json/inventory.json`): every page was opened at 1440 px and its headings, buttons, links and form fields were listed; the API operations were listed from the running application (76 in `docs/api/API_REFERENCE.md`; the list of 74 taken before the new routes is `V/audit_json/backend_routes_baseline.txt`).
2. **Probe every control** (`audit_a.py`, `audit_b.py`, `audit_c.py`): a script clicked controls, filled forms, uploaded a file, trained a model, deleted a society, downloaded every report type and checked what came back. This was run on the **baseline** first, so the list of problems is from the delivered project, not from the improved one.
3. **Classify each failed probe.** A failed probe is either an application bug or a bad probe. Both kinds happened; each is named in §8 so that nothing is hidden and nothing is counted as a fix that was not one.
4. **Fix, then re-run with a corrected probe** (`verify_*.py`), and add automated tests so the fix stays.
5. **Crawl and accessibility scan** of all routes at three screen widths after the last code change.
6. **Re-compute the numbers.** All reported accuracy figures, the live forecasts, the alert counts and the raw-data checks were recomputed independently (§6).

## 2. Summary

| Area | Features checked | Result |
|---|---|---|
| Sign-in, registration, roles, sign-out | 9 flows | all PASS (one fixed) |
| Society pages (overview, compare, consumption, forecasting, buildings, facilities, cost and peaks, alerts, recommendations, reports, data sources) | 11 pages | all PASS (4 fixed, 3 new capabilities) |
| System pages (notifications, jobs, society admin, admin, 404) | 5 pages | all PASS |
| Society upload, processing, training, delete | 1 complete flow | PASS (one display choice, see §8) |
| Backend, database, authorisation | 76 operations | PASS (293 automated tests, 2 databases) |
| ML engine and the numbers shown | 7 communities x 5 horizons | PASS; one wording defect fixed |
| Launcher and start scripts | 5 scripts | logic PASS; **`.bat` files NOT TESTED on Windows** |

## 3. Pages and controls

### 3.1 Sign-in, registration, access control

| Feature | Status | Evidence |
|---|---|---|
| Sign-in with e-mail and password; wrong password shows "Invalid e-mail or password" | PASS | audit B3b; `auth.test.tsx` |
| Field validation before sending (empty e-mail, empty password) | PASS | audit B3c; `pages.test.tsx` |
| The old server error disappears when the fields are edited | PASS, fixed | BUGS_FIXED A4; `auth.test.tsx` |
| Registration: rules shown, mismatch and weak password refused, valid account signs in | PASS | audit B3d, B3e; `pages.test.tsx` |
| "Remember my e-mail" stores only the address, never the token; unticking forgets it | PASS | `pages.test.tsx` |
| "Forgot password?" | BY DESIGN | Opens a note saying this version has no password reset by e-mail and whom to ask. It does not pretend to send anything. |
| Visiting a page while signed out goes to sign-in and returns to that page after sign-in | PASS | `V/logs/verify_routing.log` (11 of 11) |
| Back, forward, reload keep session and page; unknown URL shows an in-app 404; sign-out closes protected pages | PASS | same log |
| Roles: an analyst cannot open the Admin or Society admin pages and does not see their menu items; viewers are read-only | PASS | audit B3f, B3g, B3h; `tests/integration/test_security.py` (role matrix derived from the route table) |
| Page title follows the page ("Cost and peaks · EnergiQ AI") | PASS, fixed | BUGS_FIXED C3; crawl shows 16 distinct titles |

### 3.2 Society pages

All pages share a **society selector** in the page header. Selection persists across pages and reload (audit F01, PASS).

| Page | What it offers | Status | Evidence |
|---|---|---|---|
| **Society overview** | Last 7 days of measured demand and the next 24 hours of forecast with its 80 % range; chart/table toggle and zoom; latest demand, 24 h / 7 d / 30 d energy; predicted energy and peak; estimated cost with a tariff selector; alerts needing attention; whole-period facts; data and model cards. A note says the data are historical research data, not a live feed. | PASS | audit F01 to F03; crawl; `society.test.tsx`; `verify_ml_live.log` for the forecast |
| **Compare communities** | Seven communities side by side: energy per m², load factor, peak per m², 24 h forecast error as a share of average demand, and an all-figures table; the selected community is highlighted. | PASS, new | `verify_new_rr7.log` (7 table rows, error KPI shown); `newfeatures.test.tsx`; `tests/integration/test_api_society.py` |
| **Consumption** | Resolution (hourly, daily, weekly, monthly), metric (energy, average and peak power) and range (90 days, year, all) each send a different request; table view; zoom. | PASS | `verify_functional.log` F04 (6 calls, 6 distinct) and F04b (717 rows) |
| **Forecasting** | Horizon buttons (1, 6, 12, 24 h and 7 days) change the evaluation; actual vs predicted on data the model never saw; error analysis (average bias, mean absolute error against the baseline, median and 95th-percentile error, share of hours inside the 80 % band, histogram of errors, error by hour of day, the largest errors); model comparison with the selected model, cross-validation error and the bootstrap interval; "Forecast from a chosen hour" (default origin = the last data hour; a past origin is sent to the API and its forecast is shown next to what happened; an origin outside the data range shows "Choose a time between ..." and sends nothing); SHAP "what drives the forecast" with a local explanation of the latest forecast. | PASS; comparison note fixed; error analysis new | `verify_functional.log` F05b to F05d; audit F05a, F05e; `verify_model_choice.log`; `verify_ml_live.log` |
| **Buildings** | Metric selector, comparison chart, all-buildings table, building selector with daily-energy chart, a note about the building with an unusual ratio to the median. | PASS | audit F06; crawl (3 charts, 1 table) |
| **Common facilities** | Lifts, water pumps, street lighting, clubhouse: charted **only when the data contain a separate meter**. The bundled communities have none, so the page says so instead of drawing empty charts. | PASS (BY DESIGN for bundled data) | crawl; audit C6: for an uploaded society with a mapped lift meter the page charts it |
| **Cost and peaks** | Tab *Cost*: estimate for 30 days, 90 days, year or all data, daily and monthly charts with a table view, tariff selector, a yellow banner that this is an estimate and not a bill. Tab *Peak demand*: daily-peak forecast evaluation, load-duration curve, distribution of demand. | PASS, fixed and new | BUGS_FIXED A1 and F; `verify_tariff_rr7.log`; `newfeatures.test.tsx` |
| **Tariff manager** (on Cost and peaks) | Add a tariff from your own bill: flat or peak/off-peak, in any of the offered currencies, with a fixed daily charge and a live rate preview; list, use, delete. Rules enforced by the server and shown beside the field: negative or non-numeric rate refused; duplicate name answers 409; an equal start and end time is refused; the demo tariff cannot be deleted; deleting the tariff in use falls back to the demo tariff; tariffs survive a reload. | PASS, new | `verify_tariff_rr7.log` (13 of 13); `lib/tariff.test.ts`; API tests |
| **Alerts** | Severity, scope and status filters change the match count (42, 169, 2,200 and 0 in the probe); pagination (1 to 15 of 42, then 16 to 30); acknowledging an alert persists after reload and lowers the open count (2,369 to 2,368); clicking an event time opens a detail card with an explanation and a Close button. The page says these are candidate events from an unsupervised detector and that there are no fault labels. | PASS | audit F08b, F08c; `verify_functional.log` F08a, F08d, F08e |
| **Recommendations** | Evidence-based items generated from the society's own data (for example a building that uses 6.2 times the median energy per area), each listing the evidence it used. A cost figure appears only as a stated what-if scenario; no saving is promised. | PASS | crawl; inventory; `society.test.tsx` |
| **Reports** | Six report types (monthly PDF, consumption, forecast results, alerts, cost estimate, building comparison). Each can be created and appears in the list; every listed report downloads and is valid (PDF header and end marker, or CSV with the expected columns); the list persists after reload; an empty list shows one placeholder row. | PASS, fixed | `verify_functional.log` B1, B2 (12 of 12 downloads); audit B1, B1b; BUGS_FIXED C2 (hidden header) |
| **Data sources** | The data card: source, licence, period, number of buildings, the preprocessing rules applied to every meter, and what the rules removed. | PASS | crawl; `society.test.tsx` |

### 3.3 System pages

| Page | What it offers | Status | Evidence |
|---|---|---|---|
| **Notifications** | List, show all or unread, mark all as read; messages appear when a background job finishes. | PASS | audit F10; `pages.test.tsx` |
| **Jobs** | Background jobs with kind, status, progress, created and finished times and the result or error. | PASS | audit B5 (the import job shows "succeeded") |
| **Society admin** (admin only) | Import bundled communities (a job); upload a meter file with an optional facility mapping; train a model for an uploaded society; delete a society, with a confirmation that names what is removed and a Cancel that keeps it. | PASS | audit C1 to C9; end-to-end test in `tests/e2e` |
| **Admin** (admin only) | Users (roles can be changed, your own account is protected), Audit log (filter by action), System (record counts, health). | PASS | audit B4, B4b |
| **Top bar** | Society name and the data period; background-jobs link, notifications bell, account menu with sign-out; on phones a navigation button. | PASS | audit F14; crawl at 390 px |
| **Not found** | In-app 404 with a link back; the window title says "Page not found". | PASS | `verify_routing.log` |

### 3.4 Charts

Every chart has a title, axis titles with units, a legend where there is more than one series, hover values, and a table view where the data are a series over time. Empty and error states are shown as messages in place of an empty frame. The only charts present are ones the data support: no solar, renewable or carbon chart exists because there are no such data.

| Check | Result |
|---|---|
| 48 visits (16 routes x 3 screen widths): console errors, page errors, HTTP errors >= 400, horizontal overflow, broken images | 0, 0, 0, 0, 0 (`V/logs/crawl_final.log`, `V/audit_json/crawl_final.json`) |
| Charts drawn (per page) | overview 1, consumption 1, forecasting 6, compare 4, buildings 3, cost and peaks 2, alerts 1 |
| axe-core accessibility scan (WCAG 2.0/2.1 A and AA rules plus best-practice rules), 15 signed-in routes at desktop and phone width plus the sign-in page at desktop width (31 scans) | **0 violations** (`V/logs/a11y_scan.log`) |

## 4. Backend, API and database

| Feature | Status | Evidence |
|---|---|---|
| 76 API operations (69 paths), JWT authentication, roles viewer / analyst / admin | PASS | [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md); `tests/integration` (86 tests); `test_security.py` refuses every route without a token except health and sign-in/registration |
| Every route's role is derived from the route table in the test, so a new route cannot silently skip the role matrix | PASS | `test_security.py` |
| Background jobs return 202 and a job id; progress and result at `/jobs/{id}` | PASS | integration tests; the import and train jobs in the audit |
| Rate limits on login, registration and uploads; a forged `X-Forwarded-For` does not evade them | PASS | `test_security.py` |
| Audit log of sign-ins, failures and administrative actions | PASS | audit B4 |
| Database: SQLite by default, PostgreSQL 16 for production; Alembic migration equals the ORM schema, upgrade and downgrade | PASS | full suite on both: [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md) §2 |
| Backup and restore round trip (`pg_dump` on PostgreSQL) | PASS | `test_backup_restore.py` ran on PostgreSQL 16.15 |
| Security headers, CORS, mass assignment, SQL-injection strings stored as data, report HTML escaping, IDOR returns 404 | PASS | `test_security.py` |
| Production mode refuses the public development signing key | PASS | `test_security.py`; launcher tests |

## 5. Data pipeline

| Feature | Status | Evidence |
|---|---|---|
| Four layers never mixed: raw readings, cleaned readings, aggregated community demand, ML predictions | PASS | `docs/society/03_preprocessing_and_aggregation.md` |
| Cleaned and aggregated data of all seven communities follow from the raw BDG2 files by the documented rules | PASS | **103 of 103** checks in the verifier's full mode, official files supplied and SHA-256 checked (`V/logs/verify_raw_download.log`); 31 verification tests pass with the raw files present (`pytest_raw_verification.log`) |
| A community's hour is missing unless every meter in it is valid; nothing is filled in | PASS | the same checks |
| CSV upload: a malformed file is refused with a readable reason; a good file is processed in a job and the society appears; building names become codes by design (§8) | PASS | audit C1, C2 |

## 6. ML engine and the numbers shown

| Check | Result | Evidence |
|---|---|---|
| All 714 reported MAE, RMSE and R² values (7 communities, 5 horizons, every model) recomputed from the saved predictions | PASS, largest relative difference 6.3e-07 | `V/logs/verify_ml_live.log` |
| The API's evaluation of each community equals the stored `evaluation.json` (24 h best model and its test MAE) | PASS, 7 of 7 | same |
| Live 24 h forecast from the deployed model: finite, non-negative, hourly, lower <= forecast <= upper | PASS, **7 of 7** (was 2 of 7 at baseline) | same; BUGS_FIXED A3 |
| Anomaly events through the API equal the model-generated file | PASS, 7 of 7 (for example Fox 2,369) | same |
| A forecast origin before the data start and a back-test horizon of 0 are refused with 422 and a message | PASS | same |
| The selected model is chosen by cross-validation on earlier data; the test period is scored once and never used to choose | PASS | `docs/society/04_models_and_evaluation.md`; `evaluation.json` fields |
| The note under the model table states the truth in all three cases (learned model better; baseline selected; learned model selected but worse on the test period) | PASS, fixed | `verify_model_choice.log` (Fox, Eagle, Peacock); BUGS_FIXED A2 |
| Evaluation and prediction files are unchanged by installing the extra deployment bundles | PASS | SHA-256 before and after in `scripts/society_deploy_bundles.py`; `V/audit_json/deploy_bundles.log` |

**What the numbers mean.** The 24-hour forecast error (mean absolute error as a share of average demand) is lowest for Fox and highest for Rat; for Eagle and Rat the deployed 24 h model is the naive baseline because cross-validation did not favour any learned model. That is a result, not a defect, and the page says so. XGBoost results depend on the library version; the pinned versions are in `requirements.txt`.

## 7. Launcher and start scripts

| Item | Status | Evidence |
|---|---|---|
| `run_energiq.py`: checks Python and Node, creates `.venv`, installs only when the package lists changed (fingerprint), prepares the database, starts backend and web app on free ports, waits until both really answer (backend health with database up; web page; health through the web app's proxy), prints the address and sign-in, one instance at a time, `--stop`, `--status`, `--doctor`, `launcher.log` | PASS on Linux | 49 unit tests; clean-extract run of the delivery ZIP (`docs/final_verification/clean_extract/`) |
| Per-installation random admin password and signing key; no shared default; password never written to `launcher.log` | PASS | `tests/unit/test_launcher.py` |
| Stop: marks the record, asks the window to exit cleanly, force-stops only what verifiably still answers as EnergiQ | PASS on Linux | `tests/unit/test_launcher.py`; clean-extract run |
| Windows branches (`tasklist`, `taskkill`, `.venv\Scripts`, Smart App Control note) | logic PASS with the system calls replaced by test doubles | `tests/unit/test_launcher.py` |
| `RUN_PROJECT.bat`, `STOP_PROJECT.bat`, `CHECK_ENVIRONMENT.bat` | **NOT TESTED on Windows** | Reason: no Windows computer or emulator in the test environment. Instead: 54 tests check the files (CRLF, ASCII only, labels, no `( )` blocks, no elevation or destructive command) and follow their control flow in a simulator under simulated computers (no Python, unsupported Python, ZIP not extracted, unusable folder, launcher failing or cancelled). This cannot show how `cmd.exe` parses an odd line. `.github/workflows/windows-launcher.yml` is a ready-made real Windows test, never run. [`START_HERE.md`](START_HERE.md) says this and gives the manual commands. |
| Node.js 26 (what you have) | **NOT TESTED** | The launcher accepts 20.19 or newer; the project was run on Node 22. |

## 8. Things that looked wrong, and what they were

| Observation | Verdict |
|---|---|
| Probes F04, F05b, F05d, F08a, F08d failed on the baseline | **Bad probe, not application bugs.** F04: the metric buttons are not offered at hourly resolution (the page is right to hide them); F05b: the forecast for the default origin was already on the page and cached; F05d: the message is inline text, not an `alert` element; F08a: the word "Buildings" is also a menu item; F08d: the detail is a card, not a dialog. Corrected probes pass (`verify_functional.log`, 11 of 11). |
| Probe C7: the Buildings page of an uploaded society does not list "Block A to D" | **By design.** Uploaded societies show pseudonymous codes (`QA-TEST-SOCIETY-SYNT-B01`); names and cleaning counts are admin-only. |
| One report download timed out (20 s) in the second audit pass | Not reproduced: the same download passed in the first and third audit passes and in the final run (12 of 12). The cause was not established, so this is recorded as an unexplained, single occurrence on a busy test machine, not as fixed. |
| Large alert counts (2,369 for Fox) | Candidate events from an unsupervised detector over two years of hourly data. There are no fault labels, so the alert count is not an accuracy figure and the page says so. |
| 165 `net::ERR_ABORTED` entries in the crawl | Browser-cancelled requests when navigating away from a page that was still loading. No HTTP error status occurred. |

## 9. Not present, on purpose

* **The single-meter household pages** (sample data set, model training) were removed from the interface before this upgrade. Their API routes, ML library and tests remain.
* **Live meter feed.** The communities are historical records (2016 to 2017). The overview says "not a live feed".
* **Real tariffs.** No real utility price exists in the project. The built-in tariff is labelled DEMO; users enter their own.
* **Images.** The interface draws no photographs or stock pictures. Charts, tables and icons carry the content; decoration would not inform an energy decision and would add files that need a licence.
* **No saving, accuracy or cost figure is invented.** Cost is the measured energy times the tariff you choose; recommendations state evidence, not a promised saving.

## 10. Not tested

* Windows: the `.bat` files, the Windows branches of the launcher on a real system, SmartScreen and Smart App Control behaviour.
* Node 26, macOS.
* Docker: images were not built and no container was run (no Docker daemon in the test environment).
* AWS templates (lint only), GitHub Actions (never run).
* Load and stress behaviour. The 80 % forecast band was checked for ordering (lower <= forecast <= upper); the share of test hours inside it is computed by the evaluation and shown on the Forecasting page, but it was not re-measured separately in this upgrade.
* The accuracy of the data themselves: BDG2 is accepted as published; the verification shows the stored numbers follow from the files, not that the files are error-free.
