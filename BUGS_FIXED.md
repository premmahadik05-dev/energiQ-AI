# Bugs fixed and problems closed

Every entry says what was wrong, why, what was changed, and how it is checked now. Baseline means the delivered project before this upgrade (git commit `58cf2ae`, ZIP SHA-256 `cfc3887b...`); the upgrade is the git history after it. Entries are ordered by how much they could mislead or harm a user.

Items found by this upgrade's own checks are marked **found by audit**. Nothing here was invented to pad the list: where an earlier check failed because the *test probe* was wrong and the application was right, that is said in [`FINAL_FEATURE_AUDIT.md`](FINAL_FEATURE_AUDIT.md), not counted as a bug.

## A. Wrong or misleading output

### A1. "[object Object]" in the peak-forecast evaluation
* **Symptom.** On *Cost and peaks*, Peaks tab, the daily-peak evaluation showed `[object Object]` where the model and baseline names belong.
* **Cause.** The saved `peak_evaluation.json` used the keys `model` and `baseline` for the *metrics* of each method, while the page used the same keys as *names*. The page printed an object as text.
* **Fix.** The runner now writes the names under `model_name` and `baseline_name` (`ml_engine/society/runner.py`). Results that were already saved are served with the names filled in from the saved evaluation (`backend/app/api/societies.py`), so no re-training was needed and no number changed. The frontend types and labels use the new keys.
* **Checked by.** `tests/unit/test_society_ingest_runner.py` (names), `tests/integration/test_api_society.py::test_peak_evaluation_names...`, `frontend/src/pages/newfeatures.test.tsx`, and a browser run of the Peaks tab.

### A2. The model-comparison note could say something false
* **Symptom.** Under *Forecasting, Model comparison*, the note below the table was wrong for 8 of the 35 community-and-horizon combinations. In 6 of them (Eagle 24 h and 7 d, Fox 7 d, Hog 7 d, Rat 12 h and 24 h) it said "the selected model's test MAE is X % lower than the best simple baseline" although the selected model **was** the baseline. In 2 (Peacock 12 h and 24 h) it said "a simple baseline (Random forest) is the selected model" although a learned model had been selected and then did worse than the baseline on the test period. The *Selected (lowest CV error)* row also showed no cross-validation error for baselines.
* **Cause.** `mae_improvement_vs_best_baseline_pct` and `learned_beats_best_baseline` compare the best **learned** model with the best **baseline**, not the deployed model; the text treated them as the deployed model's result. **found by audit** (the ML verification, which recomputed every reported figure and then read the deployed model per horizon).
* **Fix.** `frontend/src/lib/modelChoice.ts` states which model is deployed and how the best learned model did, in three cases (learned model better; baseline selected; learned model selected but worse on the test period). The table now shows the cross-validation error of baselines too, so the selection can be seen to follow the lowest value.
* **Checked by.** `frontend/src/lib/modelChoice.test.ts` (the three cases with real numbers) and `tools/verify_model_choice.py` (Fox, Eagle and Peacock in the real UI, no console errors).

### A3. The live forecast worked for only 2 of the 7 communities
* **Symptom.** For Bull, Eagle, Hog, Peacock and Robin the *Forecasting* page and the overview forecast said "models not installed" (API `410`).
* **Cause.** The delivery shipped deployment bundles (the models refit on all data) only for Fox and Rat, to save space.
* **Fix.** `scripts/society_deploy_bundles.py` fits the configuration that cross-validation chose at each horizon, from the already saved `evaluation.json`, for the other five. It never re-runs the evaluation, and it hashes `evaluation.json` and every `predictions_h*.csv.gz` before and after and stops if one changed. All seven communities now answer the live forecast. Cost: about 150 MB more in the ZIP (about 200 MB of models in all).
* **Checked by.** `tools/verify_ml_live.py` (7 of 7 live forecasts finite, non-negative, hourly, lower ≤ forecast ≤ upper), the import job in `tests/e2e`, and the unchanged SHA-256 of the evaluation files.

### A4. Stale server error on the sign-in form
* **Symptom.** After a wrong password, fixing the e-mail or password (or leaving a field empty) left the old "Invalid e-mail or password" next to the new validation message.
* **Fix.** The server error is cleared when either field is edited and when client-side validation fails (`frontend/src/pages/AuthPages.tsx`).
* **Checked by.** `frontend/src/auth/auth.test.tsx` and `newfeatures.test.tsx` (sign-in case); browser flow B3 in the audit log.

## B. Security of the way the project is started

### B1. One shared admin password for every copy of the project
* **Symptom.** The old launcher printed the same fixed administrator password (`EnergiQ-Local-2026`) for everyone, and it was written in the ZIP's instructions.
* **Fix.** Each installation makes its own random password on the first start, prints it, and keeps it in `.energiq-run/admin_login.txt` (mode 600 where the system supports it). `ENERGIQ_ADMIN_PASSWORD` overrides it. A database created by the old launcher keeps its old password so it still opens. Nothing secret ships in the ZIP; the secret scan reports 0 findings.
* **Checked by.** `tests/unit/test_launcher.py` (generated password policy, reuse on the second start, environment override, legacy database, file mode).

### B2. Sign-in tokens were signed with the public development key
* **Symptom.** The old launcher started the backend in development mode without setting a signing key, so tokens were signed with the built-in development secret. That secret is visible in the source, so anyone who knew it could forge a token for a copy that was reachable on a network (the launcher listens on `127.0.0.1` only, which limits the exposure, but the key should still be private).
* **Fix.** The launcher creates a random per-installation signing key (`.energiq-run/secret_key.txt`) and passes it to the backend; `ENERGIQ_SECRET_KEY` overrides it. Production mode still refuses the development key.
* **Checked by.** `test_signing_key_is_random_persistent_and_never_the_public_dev_key` and three related tests.

### B3. Launcher could start two copies, and had no stop, status or check command
* **Fix.** One instance at a time (an atomic state file, with stale records from crashes cleaned up), `--stop`, `--status`, `--doctor`, ports chosen safely, and the Windows process check uses `tasklist`/`taskkill` (calling `os.kill(pid, 0)` on Windows would **terminate** the process it was meant to check). `RUN_PROJECT.bat`, `STOP_PROJECT.bat`, `CHECK_ENVIRONMENT.bat` and the shell equivalents wrap it and never close silently.
* **Checked by.** Unit tests including the Windows branches with mocked `tasklist`/`taskkill`, and live runs of `--doctor`, `--status` and `--stop` on Linux. **The `.bat` files themselves have not been run on Windows** (see the test report).

### B3b. One-click launcher: things that would have misreported or misbehaved (found while preparing `RUN_PROJECT.bat`)
| Problem | Fix |
|---|---|
| "Ready" meant only that *something* answered on the port. Another program on port 8000 or 5173 could be taken for EnergiQ and the address printed as working. | Readiness is the real answer: the backend must report `status ok` and `database up` on `/health/ready`, the web app must serve the EnergiQ page, and the same health answer must come back **through the web app's proxy** (the path the browser uses). A server that has died is reported even if something else answers on its port. |
| The database was created implicitly by the backend; a read-only or locked folder showed up as a stack trace later. | An explicit step ("Preparing the database") creates `data/energiq.db` and its tables, reports how many tables and accounts exist, and explains a failure in plain words (read-only folder, OneDrive or antivirus lock). Existing data is kept. |
| STOP could end an unrelated program if a recorded process number had been reused after a crash. | A recorded server is stopped only if something verifiably EnergiQ still answers on its recorded port; the launcher only if it is alive and one of its servers answers or it is still within its start-up time. Otherwise the process is left alone and the message says why. |
| STOP force-killed the launcher, so the launcher window ended with an error code and a "crashed" message. | STOP marks the record as stopping and asks the running window to shut down by itself; that window ends with exit code 0 and says it was stopped with STOP_PROJECT.bat. Force-kill is the fallback after 20 s, and during first-time setup. |
| The batch file said "EnergiQ AI has stopped" even when it had only found a copy already running, and used `( )` blocks that a folder such as `Programs (x86)` breaks. | Neutral end message; no `( )` blocks; a clear message for a folder on a network share, a ZIP that was not extracted, a missing or unsupported Python (including the Microsoft Store stub). |
| No record of what the launcher did. | `.energiq-run/launcher.log` (rotated) holds every step; the generated password goes to the window only, never to the log. `backend.log`, `frontend.log`, `pip-install.log`, `npm-install.log`, `database.log` as before. |
| Silent traps on Windows: very long paths, cloud-sync folders, Smart App Control. | The launcher prints a note when it sees one of them. |
* **Checked by.** `tests/unit/test_launcher.py` (49 tests: readiness predicates, a different program answering on the port, a server that dies, the database step, stop ownership, graceful stop, log content, notes) and `tests/unit/test_windows_launchers.py` (54 tests: static rules and a simulator, described in the test report). Not run on Windows.

### B3c. The launcher's secrets folder could have been committed to GitHub (found while preparing the master package)
| Problem | Fix |
|---|---|
| On its first start the launcher writes `.energiq-run/admin_login.txt` (the generated administrator password) and `.energiq-run/secret_key.txt` (the key that signs sign-in tokens). `.gitignore` did not list `.energiq-run/`, so after one start a plain `git add .` would have put both into the repository. Docker builds were not affected: the Dockerfiles copy named folders only. | `.energiq-run/` is now in `.gitignore` (`git check-ignore` confirms `admin_login.txt`, `secret_key.txt` and the logs are ignored). If you already committed one of these files, treat the password and key as leaked: delete the folder, start the project again to generate new ones, and remove the files from the repository history. |

### B4. Dependency advisories
* `react-router-dom` 6.30.6 carried 2 moderate advisories in the **production** bundle. Upgraded to 7.18.5; its two future flags are now the defaults and were removed. `npm audit --omit=dev` reports **0 vulnerabilities**. Checked by typecheck, lint, 151 unit tests, the production build, a 48-visit browser crawl and 11 routing flows (guard redirect, return to the original page after sign-in, back and forward, deep link, 404, sign-out).
* `vitest` 3.2.7 carried 2 critical advisories (`vitest` and `tinypool`) in the **test tooling**. Upgraded to 5.1.0; all 151 tests pass. 7 moderate advisories remain in `typescript-eslint`/`minimatch` (lint tooling, no fix available that does not downgrade); they are not part of the application or its bundle. Accepted and recorded.

## C. Accessibility and usability **found by audit**

| # | Problem | Fix |
|---|---|---|
| C1 | A table wider than the screen scrolls sideways but could not be reached by keyboard and had no name for a screen reader | The scroll region is a focusable, named region with a visible focus ring (`components/ui/Table.tsx`) |
| C2 | The Reports table had a column with an empty header (the download button column) | A visually hidden "Download" header |
| C3 | The browser tab said just "EnergiQ AI" on every page inside the app (only the sign-in and register pages set their own title) | `lib/pageTitle.ts`: "Cost and peaks · EnergiQ AI" and so on, including the not-found page |
| C4 | Rupee amounts were grouped the international way | Indian grouping (12,34,567) for INR (`lib/format.ts`) |

Result: axe-core (WCAG 2.0/2.1 A and AA plus best-practice rules) reports **0 violations** on the 15 signed-in routes at desktop (1440 px) and phone (390 px) width and on the sign-in page at desktop width: 31 scans.

## D. Test suite

### D1. Order-dependent tests
* **Symptom.** Several folders have a `conftest.py`; pytest registers all of them under the module name `conftest`, so `from conftest import ADMIN` picked a different folder's file depending on collection order. After new tests were added, two end-to-end tests failed in a full run and a collection error appeared when the folders ran in the opposite order. The log of the failing run is kept as `pytest_full_BEFORE_conftest_fix.log`.
* **Fix.** Shared helpers moved to the uniquely named `tests/integration/itest_support.py`; end-to-end tests take the administrator from a fixture.
* **Checked by.** The full suite (293 passed) and the folders in both orders.

### D2. Baseline lint failure
`ruff` reported one error in `run_energiq.py` (UP031) at baseline. Gone with the launcher rewrite; `ruff check backend ml_engine scripts tests run_energiq.py` is clean.

## E. Documentation that was out of date

* `docs/api/openapi.json` lacked `/societies/compare` and `/societies/{id}/error-analysis` and could drift because only the table was generated. `scripts/make_api_reference.py` now writes both files together.
* README, installation guide, demo script and society documents said only Fox and Rat have forecasting models (see A3). Corrected; the dated PostgreSQL and clean-unzip records keep their original wording with a note, because they describe what was true when they were recorded.
* Old `START_ENERGIQ.bat`, `HOW_TO_RUN.txt` and `start_energiq.sh` replaced by the new scripts and `START_HERE.md`.

## F. Defects in the new features, found while verifying them

These never reached a user; they are listed because they show what the checks catch.

* The tariff preview chart auto-zoomed to 7.4 to 8.6 and exaggerated a flat tariff: the chart now starts at zero (`zero` option); the unit label was clipped and was shortened to `INR/kWh`.
* The community comparison table wrapped "Period" over four lines; headers were shortened, cells set not to wrap, and horizontal bar charts gained axis titles.
* The load-duration curve had irregular x ticks; ticks are now every 10 %.
* A duplicate tariff name must answer `409` and a negative or non-numeric rate must be refused with the field named: both are enforced by the server and shown beside the field (13 of 13 browser checks).

## G. Not bugs, but looked like it

* Uploaded societies show building codes (`FOX-B04`) instead of the names in the file. This is a documented privacy decision: names, identifiers and cleaning counts are admin-only.
* Alert counts are large (for example 2,369 for Fox). They are candidate events from an unsupervised detector, there are no fault labels, and the page says so.
* Several communities are best forecast by a simple baseline at some horizons. That is the honest outcome of the protocol and is now stated plainly (A2).

## H. Known and not fixed

See "Limitations and not tested" in [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md) and [`FINAL_FEATURE_AUDIT.md`](FINAL_FEATURE_AUDIT.md): Docker was not run, the `.bat` files were not run on Windows, 7 moderate lint-tooling advisories remain, and the data are university buildings, not a housing society.
