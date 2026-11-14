# Final test report

Date of the runs: 9 November 2026. Every result below was copied from a log file kept in [`docs/final_verification/logs/`](docs/final_verification/logs/) (`L/` below); the browser scripts are in [`docs/final_verification/tools/`](docs/final_verification/tools/) (`T/`). Nothing is estimated and nothing is recalled from memory. Where something could not be run, it is listed as **BLOCKED** or **NOT TESTED** in §8, with the reason.

Status words: **PASS** (ran, as expected), **FAIL** (ran, not as expected; what was done about it is stated), **BLOCKED** (the environment cannot run it), **NOT TESTED** (not run).

## 1. Where this was run

| | |
|---|---|
| Machine | Linux sandbox (x86-64, 2 CPU cores). **Not Windows, not the user's computer.** |
| Python | 3.11.15, packages as pinned in `requirements.txt` / `requirements-dev.txt` |
| Node.js | 22.23.4 (the project's frontend lock file; the machine the user has runs Node 26, see §8) |
| Databases | SQLite (default) and PostgreSQL 16.15 (local server) |
| Browser | Chromium through Playwright (the version installed in the sandbox) |
| Baseline | the delivered project before this upgrade: git commit `58cf2ae`, ZIP SHA-256 `cfc3887b41df12d874510f97c4f196ecb59c4fbff3cc07636951dd116e09a012` |
| Final | git branch `professional-upgrade` (the upgrade starts at commit `980cb18`; `git log` lists them all) |

## 2. Automated tests: backend and ML (pytest)

| # | What | Exact command | Result | Log |
|---|---|---|---|---|
| 2.1 | **Baseline**, before any change | `python -m pytest -q -rs` | **PASS** 256 passed, 3 skipped, 217 s | `L/baseline/pytest.log` |
| 2.2 | **Final**, SQLite, the folders in the order unit, integration, e2e (re-run after the one-click launcher work; run from the project folder with `--basetemp` outside it) | `python -m pytest tests/unit tests/integration tests/e2e -q -rs -p no:cacheprovider --basetemp=/tmp/pt` | **PASS** 368 passed, 3 skipped, 227 s | `L/pytest_full_final_unit_first.log` |
| 2.3 | SQLite, default order (e2e, integration, unit). **Run on the commit before the one-click launcher work**; since then only `run_energiq.py`, its two test files, the `.bat`/`.sh` files and documents changed, no application code (`git diff 7f08f8f --stat -- backend ml_engine frontend scripts` is empty) | `python -m pytest -q -rs -p no:cacheprovider` | **PASS** 293 passed, 3 skipped, 243 s | `L/pytest_full_final_default_order.log` |
| 2.4 | PostgreSQL 16.15, unit and integration (**same note as 2.3**: run before the launcher work, which does not touch the database code) | `ENERGIQ_TEST_DATABASE_URL=postgresql+psycopg://energiq@127.0.0.1:55432/energiq_test python -m pytest tests/unit tests/integration -q -p no:cacheprovider -rs` | **PASS** 291 passed, 1 skipped, 0 failed, 225 s | `L/pytest_postgres.log` |
| 2.5 | The first PostgreSQL run | same command | **FAIL**: 3 failed, 288 passed, 1 skipped. Cause: three tests *I added* ran after tests that rebuild the database schema, which on PostgreSQL drops it. Fixed by moving them earlier in the file with a comment; re-run is 2.4. | `L/pytest_postgres_FIRST_RUN_3_failures.log` |
| 2.6 | Raw-data verification tests with the 194 MB official BDG2 files present | `python -m pytest tests/unit/test_society_raw_verification.py -q` | **PASS** 31 passed, 17 s | `L/pytest_raw_verification.log` |
| 2.7 | Launcher unit tests: readiness checks, database step, stop ownership and graceful stop, logging without the password, notes about the computer, port choice, one instance, keys | part of 2.2; `python -m pytest tests/unit/test_launcher.py` | **PASS** 49 tests | `L/pytest_full_final_unit_first.log` |
| 2.8 | Windows launcher file checks and simulator (new): CRLF, ASCII, labels, no `( )` blocks, no elevation or destructive command, and the control flow of each `.bat` under simulated computers | part of 2.2; `python -m pytest tests/unit/test_windows_launchers.py` | **PASS** 54 tests. **This is not a run on Windows** (§8) | `L/pytest_full_final_unit_first.log` |

**Reading the numbers.** The final suite collects 371 tests (281 unit, 86 integration and 4 end-to-end; parametrised cases make the count larger than the number of test functions). 368 passed and 3 skipped on SQLite; the 3 skips are the two tests that need PostgreSQL (restore with `pg_dump`; PostgreSQL migration check) and the raw-data test that needs the 194 MB files, which the ZIP leaves out. On PostgreSQL the first two run and pass; only the raw-data test is skipped (the files were not present in that run; it passed in 2.6 with the files present). **The 4 end-to-end tests (real server plus real Chromium) were run on SQLite only**, not on PostgreSQL. Baseline to final: 256 to 368 passed (+112: the 49 launcher tests, the 54 Windows-launcher file tests and tests for the new society features).

**Two defects in the test suite itself were found and fixed** (BUGS_FIXED D1): pytest registers every `conftest.py` under the same module name, so `from conftest import ...` picked a different folder's file depending on collection order. The failing run is kept as `L/pytest_full_BEFORE_conftest_fix.log`. After the fix, the suite passes with the folders in either order (2.2 and 2.3), and the PostgreSQL ordering problem above was found by actually running on PostgreSQL, which is why that run was repeated.

## 3. Automated tests: frontend

| # | What | Exact command (in `frontend/`) | Result | Log |
|---|---|---|---|---|
| 3.1 | **Baseline** unit tests | `npm test` | **PASS** 118 passed, 9 files | `L/baseline/vitest.log` |
| 3.2 | **Final** unit tests, Vitest 5.1.0 | `npm test` | **PASS** 151 passed, 12 files | `L/vitest5.log` |
| 3.3 | Type check | `npm run typecheck` (`tsc -b --noEmit`) | **PASS** exit 0 | `L/tsc_final.log` |
| 3.4 | Lint | `npm run lint` (`eslint .`) | **PASS** exit 0 | `L/eslint_final.log` |
| 3.5 | Production build | `npm run build` | **PASS** built in 4.0 s; the largest chunk, Recharts, is 417 kB (113 kB gzipped) | `L/build_final.log` |

Between 3.1 and 3.2 the router was upgraded (6.30.6 to 7.18.5) and the test tool was upgraded (Vitest 3.2.7 to 5.1.0); both were run after the change (`L/vitest_rr7.log`, `L/vitest5.log`).

## 4. Static analysis and dependency scans

| # | What | Exact command | Result | Log |
|---|---|---|---|---|
| 4.1 | Lint, baseline | `ruff check backend ml_engine scripts tests run_energiq.py` | **FAIL** 1 error (UP031 in `run_energiq.py`), removed by the launcher rewrite | `L/baseline/ruff.log` |
| 4.2 | Lint, final | same | **PASS** "All checks passed" | `L/ruff_all.log` |
| 4.3 | Security lint, application code | `bandit -r backend ml_engine run_energiq.py` | **PASS** 0 high, 0 medium; 13 low (8 x B603, 3 x B607, 1 x B404 in the launcher, which starts the two servers on purpose with fixed argument lists and no shell; 1 x B105, the public development placeholder key that production mode refuses) | `L/bandit.log`, `L/bandit.json` |
| 4.4 | Security lint, including `scripts/` | `bandit -r backend ml_engine scripts run_energiq.py` | 0 high, 0 medium; 37 low, all in the same categories (developer tools starting subprocesses; two `assert`s) | `L/bandit_with_scripts.log` |
| 4.5 | Secret scan | `python scripts/check_secrets.py` | **PASS** 0 findings (run again after the evidence files were added) | `L/secrets_scan.log` |
| 4.6 | Python dependency advisories | `pip-audit -r requirements.txt` | **PASS** "No known vulnerabilities found" | `L/pip_audit.log` |
| 4.7 | Web packages that ship to the user | `npm audit --omit=dev` | **PASS** 0 vulnerabilities (baseline: 2 moderate in `react-router-dom`) | `L/npm_audit_prod.log` |
| 4.8 | Web packages including development tools | `npm audit` | 7 moderate (baseline: 2 critical and more). All 7 are in `typescript-eslint` / `minimatch` (the code linter). The only offered fix downgrades `typescript-eslint`. **Accepted**: the packages are not in the browser bundle or the server. | `L/npm_audit_all.log` |

## 5. Browser tests (real Chromium, real server, real data)

All use the running application (backend on port 8000, web app on 5173) with the seven bundled communities loaded. They sign in through the real form or with a real token, click real controls and read what the page shows.

| # | What | Script and log | Result |
|---|---|---|---|
| 5.1 | Crawl: 16 routes x 3 screen widths (1440, 820, 390 px) = 48 visits; console errors, uncaught errors, HTTP status >= 400, horizontal overflow, broken images | `T/crawl_final.py`, `L/crawl_final.log` | **PASS** 0, 0, 0, 0, 0. (165 browser-cancelled requests `ERR_ABORTED` when leaving a page that was still loading; no error status.) |
| 5.2 | Accessibility: axe-core, WCAG 2.0/2.1 A and AA plus best-practice rules; 15 signed-in routes at desktop and phone width and the sign-in page at desktop width | `T/a11y_scan.py`, `L/a11y_scan.log`, `L/a11y.json` | **PASS** 0 violations in 31 scans |
| 5.3 | Routing and session: guard redirect, return to the original page after sign-in, title follows the route, back, forward, reload keeps session, 404 inside the app, sign-out | `T/verify_routing.py`, `L/verify_routing.log` | **PASS** 11 of 11 |
| 5.4 | Functional probes: Consumption controls each send a different request; table view; forecast from the default and from a chosen origin; an origin outside the data range is refused on the page and sends nothing; Alerts filters, detail card and Close; every report type created and every download valid | `T/verify_functional.py`, `L/verify_functional.log` | **PASS** 11 of 11 |
| 5.5 | Tariff manager: empty submit, negative rate, live preview, save and use, rupee display, duplicate name (409), equal start and end time, peak tariff, delete, fallback to demo, cancel, persistence after reload | `T/verify_tariff.py`, `L/verify_tariff_rr7.log` | **PASS** 13 of 13 |
| 5.6 | New pages after the router upgrade: Compare communities (7 rows) and the error-analysis tiles | `T/verify_new.py`, `L/verify_new_rr7.log` | **PASS** |
| 5.7 | Live ML in the browser's API: 7 communities x (stored evaluation equals the API; live 24 h forecast finite, non-negative, hourly, lower <= point <= upper; alert events equal the model's file), refused inputs, and every reported MAE/RMSE/R² recomputed | `T/verify_ml_live.py`, `L/verify_ml_live.log` | **PASS** 24 of 24 checks; **714** metric values recomputed from the saved predictions, largest relative difference 6.3e-07 |
| 5.8 | The model-comparison note for the three situations (Fox: learned model better; Eagle: baseline selected; Peacock: learned model selected but worse than the baseline on the test period) | `T/verify_model_choice.py`, `L/verify_model_choice.log` | **PASS** 3 of 3, no console message |
| 5.9 | Every chart: a title, tick labels, at least one axis title, and a hover tooltip with value and unit | `T/hover_check.py`, `L/hover_check.log` | **PASS** 18 of 18 charts, no console message |
| 5.10 | **Baseline audit** (before any change): 66 recorded probes (16 + 39 + 11) of every page, form, upload, training job, report download, role guard and admin tab | `T/audit_a.py`, `audit_b.py`, `audit_c.py`; raw results in `docs/final_verification/audit_json/` | Mixed on purpose; every FAIL was classified as an application bug or a bad probe in [`FINAL_FEATURE_AUDIT.md`](FINAL_FEATURE_AUDIT.md) §8 |

## 6. Data and model verification (not browser)

| # | What | Command | Result | Log |
|---|---|---|---|---|
| 6.1 | Independent re-computation of the cleaned and aggregated data of all seven communities from the official BDG2 files (SHA-256 checked), the verifier importing nothing from the application | `python scripts/verify_society_raw_data.py --download` (full mode) | **PASS** 103 of 103 (run without an API: the log says `api=not run`; the earlier delivery recorded 127 of 127 in a run that included the comparison with a running API) | `L/verify_raw_download.log` |
| 6.2 | Installing the extra deployment bundles must not change any evaluation or prediction file | `python scripts/society_deploy_bundles.py` (it hashes `evaluation.json` and every `predictions_h*.csv.gz` before and after and stops on a difference; every community printed "evaluation files unchanged") | **PASS** no hash changed | `docs/final_verification/audit_json/deploy_bundles.log`, `artifacts_before.sha256` |

## 7. Launcher and start scripts

| # | What | Result | Evidence |
|---|---|---|---|
| 7.1 | Launcher logic, 49 unit tests with the system calls replaced by test doubles: port choice, one instance, stale state, password and signing-key creation (the password never reaches `launcher.log`), installation fingerprint, **strict readiness** (a different program answering on the port is not accepted; a server that died is reported), the **database step** (created, and plain-language failures), **stop ownership** (a recorded process number that no longer answers as EnergiQ is left alone; a clean shutdown is requested before anything is force-stopped), log rotation, notes (long path, cloud-sync folder, Smart App Control), Windows process check with `tasklist`/`taskkill` | **PASS** 49 tests | 2.7 |
| 7.2 | `run_energiq.py --doctor`, `--status`, `--stop` and `bash check_environment.sh` on Linux, before any install | **PASS** (doctor: all OK or NOTE; status: not running, exit 1; stop: nothing to stop, exit 0) | `L/launcher_live_linux.log` |
| 7.3 | The launcher from the extracted delivery ZIP on Linux, in a folder whose name contains spaces and brackets: first start (creates `.venv`, installs, prepares the database, starts both servers, waits for real readiness, imports the communities), a second start refused, status, stop, start again | see §9 | `CE/` |
| 7.4 | The three `.bat` files: static rules and control flow in a simulator, 54 tests. Static: CRLF line endings, ASCII only, `@echo off`, `setlocal ... DisableDelayedExpansion`, `cd /d "%~dp0"`, every `goto` has exactly one label, no `( )` blocks (a folder named `Programs (x86)` cannot break them), no `rem` line with `<>\|&`, no elevation, no destructive, network or registry command, a `pause` before every exit, every file they name exists. Flow, under simulated computers: Python 3.11 / 3.12 / 3.13 through `py`, plain `python`, an unsupported or missing Python, a ZIP that was not extracted, a folder `cmd` cannot use (network), the launcher succeeding, failing (exit 1) or cancelled (130); the options reach the launcher; STOP and CHECK likewise; the final pause can be skipped only with `ENERGIQ_NO_PAUSE`. The tests were checked by deliberately breaking a copy of `RUN_PROJECT.bat` (typo in a label, `( )` block, missing pause, options not forwarded, wrong message, LF endings, non-ASCII character, unset exit code, elevation): each break made tests fail | **PASS** 54 tests | 2.8; the break experiment is described here and was not saved as a log |
| 7.5 | `RUN_PROJECT.bat`, `STOP_PROJECT.bat`, `CHECK_ENVIRONMENT.bat` **run on Windows** | **NOT TESTED** | §8 |

## 8. BLOCKED and NOT TESTED

| What | Why | Consequence for you |
|---|---|---|
| **`RUN_PROJECT.bat`, `STOP_PROJECT.bat`, `CHECK_ENVIRONMENT.bat` and the launcher's Windows-only paths, run on a real Windows computer** | **NOT TESTED.** The test environment is Linux; there is no Windows computer, virtual machine or emulator (no `cmd.exe`, no Wine) in it. | The launcher they start was run for real on Linux (§9) and its Windows branches are unit-tested with test doubles; the `.bat` files were checked for structure and their control flow was simulated (7.4). That cannot show how `cmd.exe` parses an unusual line, how the console behaves when closed or interrupted, or what SmartScreen does. A mistake of that kind would only show on Windows. **`.github/workflows/windows-launcher.yml` runs exactly the Windows test** (CHECK, first start with a real install, readiness through the proxy, second start refused, no password in the logs, STOP ends the window cleanly) on a GitHub Windows computer; it is started by hand from the Actions tab and **has never been run**. [`START_HERE.md`](START_HERE.md) also gives the same steps by hand (`py -3.11 run_energiq.py`). |
| **Windows Smart App Control / SmartScreen** | Windows-only. | The Unblock-the-ZIP step and the `py -3.11 run_energiq.py` route in `START_HERE.md` are the documented workarounds; they were not exercised. |
| **Node.js 26** | The sandbox has Node 22. The launcher accepts Node 20.19 or newer; the lock file was installed with Node 22. | Very likely fine, not proven. If `npm ci` complains, install Node 22 LTS. |
| **Docker images and `docker compose up`** | No Docker daemon in the test environment. | The Dockerfiles and compose file are written and statically checked only. Not needed to run the project. |
| **AWS CloudFormation, GitHub Actions** | Not deployed; the workflow has never run. | Not needed to run the project. |
| **macOS, Firefox, Safari, real phones** | Not available. | Browser tests are Chromium only; phone and tablet widths are emulated. |
| **Load, stress and long-running behaviour** | Not part of this upgrade. | |
| **The 4 end-to-end tests on PostgreSQL** | The PostgreSQL run covered `tests/unit` and `tests/integration`. | The end-to-end tests ran on SQLite. |
| **A human screen-reader session** | Not available. | Only the automated axe scan. |
| **The accuracy of the source data** | BDG2 is taken as published. | Test 6.1 shows the stored numbers follow from the files, not that the files are error-free. |

## 9. The delivery ZIP itself

The delivered ZIP was extracted into a new, empty folder whose name contains spaces and brackets (`Energiq Test (x86)/EnergiQ-AI`, the kind of name that breaks careless scripts) and used as a new user would, **on the Linux sandbox** (Python 3.11, Node 22) with `bash run_project.sh`, which starts the same launcher (`run_energiq.py`) that `RUN_PROJECT.bat` starts. Logs and scripts: `docs/final_verification/clean_extract/` (`CE/`). The generated administrator password is redacted in the logs, and step 9.4 checks that no log contains it. **None of this was run on Windows.**

| # | Step | Result | Log |
|---|---|---|---|
| 9.1 | `bash check_environment.sh` before anything is installed | **PASS** exit 0: Python, Node.js, npm, project files, writable folder, free disk space, ports 8000 and 5173 free; the environment, database and packages reported as "will be created" | `CE/doctor_before_install.log` |
| 9.2 | `bash run_project.sh --no-browser`, first start: creates `.venv`, installs the Python and the web packages, **prepares the database** ("created, 21 tables, 0 user accounts"), starts the backend and waits until it reports `ok` with the database up, starts the web app and waits until it serves the EnergiQ page **and** passes the health check through its proxy, imports the 7 bundled communities, prints the address and a generated password | **PASS** 51 s from start to "running" (this machine already had pip and npm caches; an earlier run of the same procedure took 121 s and the previous report's cold run 163 s) | `CE/first_start.log`, `CE/timings.txt` |
| 9.3 | `check_running.py`: health through the web app's proxy; sign-in; the 7 communities; a live 24 h forecast for each (lower <= forecast <= upper checked); the old shared password `EnergiQ-Local-2026` refused; sign-in through the real form in Chromium and 13 pages opened (heading, window title, no console message, no HTTP error >= 400) | **PASS** 7 of 7 forecasts, HTTP 401 for the old password, 13 of 13 pages, 0 problems | `CE/check_running.log` |
| 9.4 | No log file under `.energiq-run` contains the generated password | **PASS** none | `CE/check_running.log` |
| 9.5 | `--status`, then a **second start** while the first is running | **PASS** "already running" with the address, exit 0, one backend process before and after | `CE/second_start_refused.log` |
| 9.6 | **Stop**: `bash stop_project.sh` asks the running window to shut down | **PASS** the first window printed "stopped with STOP_PROJECT.bat" and **ended with exit code 0** (not an error code); no server process left | `CE/stop_and_ownership.log`, `CE/first_start.log` |
| 9.7 | **Stop safety**: a record whose backend number belongs to an unrelated program (`sleep`) while nothing answers as EnergiQ; then stop with nothing recorded; then `--status` | **PASS** the unrelated process was left alone and still running; the stale record was removed; nothing recorded: "Nothing to stop", exit 0; status: not running, exit 1 | `CE/stop_and_ownership.log` |
| 9.8 | Start again (warm) | **PASS** 4 s; "packages already installed"; "Database: ready (1 user account)"; "7 societies are already loaded"; the same password as before | `CE/warm_start.log` |
| 9.9 | **A database that cannot be prepared** (`data/energiq.db` replaced by a folder) | **PASS** the start stops with "The database could not be prepared", a one-line reason (`unable to open database file`), the common causes and the log to read; exit 1; no server started; no record left. With the database restored the next start works | `CE/database_failure.log`, `CE/recovery_after_failure.log` |
| 9.10 | The complete Python suite run from the extracted folder | **PASS** 367 passed, 4 skipped, 0 failed, 220 s. Three skips are the usual ones (§2). The 4th is the browser end-to-end test, which skips itself because `frontend/dist` is not in the ZIP (it is built from the source) | `CE/pytest_full_from_extract.log` |
| 9.11 | After `npm run build` in the extract: the 4 end-to-end tests (real server and real Chromium) | **PASS** 4 passed, 47 s | `CE/build_in_extract.log`, `CE/pytest_e2e_from_extract.log` |

The ZIP that these steps were run on has SHA-256 `60f8335643f9bf6a9f7066f4c7626409206f1c5beb8cea203884e1cab8f8e826`. The delivered ZIP was rebuilt afterwards to add this section and the logs above; it differs from the verified one **only in documents** (`FINAL_TEST_REPORT.md` and the files under `docs/final_verification/`), which was checked by comparing the SHA-256 of every file in the two ZIPs. Its own checksum is in `SHA256SUMS.txt`, delivered next to it.

What this still does not show: that it runs on **Windows** (the `.bat` files, `cmd.exe`, SmartScreen, a real console being closed or interrupted), on Node 26, or on a computer with a different network, antivirus or folder-sync setup. The Windows-specific launcher code is covered by unit tests with test doubles only.

## 10. Reproduce

To run the Windows test that could not be run here: push the project to GitHub, open the **Actions** tab, choose **windows-launcher**, click **Run workflow**. It executes `CHECK_ENVIRONMENT.bat`, `RUN_PROJECT.bat` (a real first start) and `STOP_PROJECT.bat` on a GitHub Windows computer and checks readiness, the refused second start, the password-free log and the clean stop. It has never been run; its first run is the first test of the `.bat` files on Windows. Or simply double-click `RUN_PROJECT.bat` on your computer and compare with [`START_HERE.md`](START_HERE.md).


```bash
# backend and ML
python -m pytest -q -rs
# PostgreSQL (needs a server and a database the user can write to)
ENERGIQ_TEST_DATABASE_URL=postgresql+psycopg://USER@HOST:PORT/DB python -m pytest tests/unit tests/integration -q -rs
# frontend
cd frontend && npm ci && npm test && npm run typecheck && npm run lint && npm run build
# scans
ruff check backend ml_engine scripts tests run_energiq.py
bandit -r backend ml_engine run_energiq.py
python scripts/check_secrets.py
pip-audit -r requirements.txt
cd frontend && npm audit --omit=dev
# browser scripts (start the application first: python run_energiq.py; edit the base URL and the test administrator in tools/common.py)
python docs/final_verification/tools/verify_routing.py   # and the other scripts in that folder
```

The browser scripts were written for the test sandbox: `common.py` holds its URLs, a throw-away administrator account and a token cache path. They are kept as evidence of what was run and can be adapted, not as a portable test suite. The portable suites are the pytest and Vitest tests.
