# 7. Testing and verification

Everything below was run for real in the build workspace (Linux, 2 CPU cores, Python 3.11, Node 22.23) with the packages pinned in
`requirements.txt` and `frontend/package-lock.json`. The numbers are copied from the command output. What was **not** tested is listed in §5.

## 1. Results of the final runs

| Command | Result |
|---|---|
| `python -m pytest tests/unit tests/integration` | **257 passed, 2 skipped** in 182 s (working copy with the full BDG2 files present; in an unzipped delivery, which does not contain them, one more test skips: 256 passed, 3 skipped). The 2 skips need PostgreSQL (`pg_dump` restore and the PostgreSQL migration check). Includes the 37 raw-data verification tests of §2. |
| `ENERGIQ_TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest tests/unit tests/integration` (PostgreSQL 16.15, schema recreated before every test) | **Working copy: 259 passed, 0 failed, 0 skipped** in 229 s, recorded in [`../postgres_test_run.txt`](../postgres_test_run.txt). **Clean unzip of the delivery ZIP: 258 passed, 0 failed, 1 skipped** in 217 s, recorded in [`../postgres_test_run_clean_unzip.txt`](../postgres_test_run_clean_unzip.txt); the one skip is `test_full_official_files_pass_all_checks_and_contain_the_subset`, which needs the official BDG2 files that the ZIP does not contain (258 + 1 = 259 tests). The first run of this suite on PostgreSQL failed 8 tests; both causes were defects that SQLite hides and are fixed (see [`../12_deployment.md`](../12_deployment.md) §1a and §2b below). |
| `python scripts/verify_society_end_to_end.py --check-subset` (not part of pytest) | **127 of 127 checks passed**: SHA-256 of the five official BDG2 files, the shipped raw subset against the full file, the independent re-computation of all seven communities against the processed files, and against a live API (24 months and every building per community). Report: [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md); method: [10_raw_data_verification.md](10_raw_data_verification.md). About 50 s. |
| `python -m pytest tests/e2e` | **4 passed** in 51 s: a real uvicorn server over real HTTP (3 tests, one of them the society workflow) and a real Chromium driving the built React app (1 test). |
| `npm test` in `frontend/` | **118 passed** (9 files), of which 26 are the society pages and 16 the sign-in and registration pages. |
| `npm run typecheck`, `npm run lint`, `npm run build` | all clean. |
| `ruff check .` | All checks passed. |
| `bandit -r backend ml_engine scripts -ll` (medium and higher) | no findings. |
| Secret scan (`tests/unit/test_secret_scan.py`, part of the first row) | passed. |
| `python scripts/verify_upload_train.py` (not part of pytest) | upload, clean, store, train, forecast and anomaly storage **succeeded** through the real API on real data; see §3. |
| Real browser against a real backend with all seven communities imported | all twelve society screens rendered from API data; screenshots in `docs/screenshots/society_*.png`. |
| `python scripts/ui_audit.py` (not part of pytest) | axe-core 4.10.2, rule sets WCAG 2 A and AA (includes colour contrast), on the sign-in and registration pages, the eleven society pages, the jobs list and the administration page (15 pages) in Chromium: **0 violations**; no unrounded number, `NaN`, `undefined` or `Infinity` in any page text. |

The e2e folder has to be run on its own (`tests/e2e` and `tests/integration` each have a `conftest.py`, and pytest cannot collect both in one command).

## 2. What the society tests check

The tests assert properties of the real data and the real services, not that "it runs".

| File | Tests | What it pins down |
|---|---|---|
| `tests/unit/test_society_data_integrity.py` | 28 (4 checks x 7 communities) | Read directly from the processed CSV files, independent of the code that built them: the society total equals the sum of its building meters at every hour (to the 3-decimal storage rounding); the total is **missing wherever any meter is missing** (never a partial sum); the hourly grid is complete, sorted and unique; no negative, zero or 48 h-or-longer constant readings remain; the stored valid-hour counts and mean match the data. |
| `tests/unit/test_society_raw_verification.py` | 31 | The **independent raw-data verifier** (`scripts/verify_society_raw_data.py`). The cleaning rules on small known series (negative, short and long zero runs, stuck at 48 vs 47 identical hours, a gap ending a run, the spike limit 4 x p99.5, fewer than 100 readings, a reading hit by two rules counted once); site selection (a hotel label with stray whitespace, a building without a meter, the 8-building and 94 % rules); no partial sums; SHA-256 mismatch and a refused download; the verifier imports only the standard library, numpy and pandas; its thresholds equal the application's defaults; **tamper tests** that change one thing in a copy of the processed data or of the raw subset (a meter value, an uncleaned negative, a partial community sum, a changed total, a missing building, a forgotten excluded meter, a changed count, a changed threshold, a changed raw file, a changed metadata file) and require the matching check to fail; the independent pipeline on the shipped raw subset reproduces all seven communities; the same on the full official files when present; the four layers are consistent; the committed report was produced by the shipped script and passed; the documented thresholds and rejected sites equal the script's and the report's; the disclosures (student residence halls; not family flats; not a registered housing society) are present and no document claims otherwise. |
| `tests/integration/test_society_raw_vs_api.py` | 6 | All seven communities imported into a temporary database and compared with the independent computation **through the real API** (overview totals, 24 months, every building as an administrator); a wrong energy total, a missing month, a wrong building figure, a non-admin account and a society that is not imported must each be reported, while a difference inside the documented rounding tolerance must not. |
| `tests/unit/test_society_db_limits.py` | 11 | Values that SQLite accepts and PostgreSQL rejects: `NaN` in JSON (the shipped Eagle report really contains it), building codes longer than the `VARCHAR(24)` column for keys of any length and for more than 99 meters, meter column names longer than the 120-character column. They check the values to be written, so they fail on SQLite too if the bug returns. |
| `tests/integration/test_society_db_portability.py` | 2 | After all seven communities are imported: every bounded text column of the schema holds only values that fit it, every society's JSON is strict JSON, and Eagle's missing coordinates are stored as unknown. |
| `tests/unit/test_deployment_files.py` | 10 | Static checks of the Dockerfiles, compose file, CloudFormation template and `.env.example` (every `COPY` source exists and is not dockerignored; every `ENERGIQ_*` variable is a real setting; the API image ships and configures the society data) and the real entrypoint script run in a temporary folder (seeds the society volume once, never overwrites, repeats an interrupted copy). Images are **not** built. |
| `tests/unit/test_society_ingest_runner.py` | 13 | Upload parsing and cleaning on small known inputs: quarter-hour kWh is summed and kW averaged (with a coverage rule), incomplete hours are missing, duplicates, gaps and text cells are reported and not filled, unsupported intervals and bad timestamps are refused; the meter-mapping rules; a society total exists only where every retained meter is valid and facility zeros are kept; building zeros are invalid and poor meters are excluded; too few meters or too little overlap is refused. Also: the evaluation plan reproduces the BDG2 protocol and adapts to shorter history (and refuses very short history), and the daily-peak evaluation (value and hour; incomplete days skipped). |
| `tests/integration/test_api_society.py` | 28 | The society API with a real database and the real Fox data and trained models: overview numbers equal the raw data; buildings sum to the society total; consumption resolutions; facilities unavailable when not metered; forecast shape and ordered ranges, a forecast from an earlier origin uses only data up to that origin, input validation; model comparison and backtest agree with the saved evaluation; SHAP; anomaly events, acknowledgement and filters; cost with a demo tariff; recommendations; PDF and CSV reports contain the real numbers; import of every bundled society as a job (and no duplicates on a second import); delete removes buildings, meters, readings, events **and reports**; upload of real meter data behaves like any society; bad uploads are refused with clear messages; admin-only data stay admin-only. |
| `tests/integration/test_security.py` | 16 | Every route requires login (society routes included); the role matrix is exercised for **every** analyst-only and admin-only operation, which checks that viewers and analysts are refused (403) and the permitted roles are not; rate limits; headers; no stack traces in errors. |
| `tests/e2e/test_http_workflow.py::test_society_workflow_over_http` | 1 | Real server process: an analyst cannot import; the administrator imports the bundled societies as a job; the list, detail (no admin-only identifiers for an analyst, present for the admin), overview, 24-hour forecast, anomaly events, a monthly PDF report (`%PDF-` header) and the metrics endpoint. |
| `frontend/src/pages/society/society.test.tsx` | 27 | Every society page rendered from **captured real API payloads** (`frontend/src/test/fixtures/society/`, produced by `scripts/capture_society_fixtures.py`): overview, "Not available" when models are not installed, empty and error states, role-dependent controls (admin import and upload, viewer cannot create reports or acknowledge alerts), forecasting including the 410 case, facilities "not measured", cost, peaks, alerts, recommendations caveats, reports, data sources, upload validation. |

## 2b. What running the suite on PostgreSQL found

SQLite is lenient in two ways that PostgreSQL is not, and the suite had only been run on SQLite for the society code. The first PostgreSQL run (227 passed, 2 failed, 6 errors) traced back to two defects:

* **`NaN` in a JSON column.** BDG2 gives no latitude or longitude for the Eagle site, so Eagle's cleaning report contains `NaN`; Python's `json` module reads it, SQLite stores it, PostgreSQL refuses it (`invalid input syntax for type json`). The import of Eagle, and so "Import bundled communities", failed. Fixed in `backend/app/services/society_import.py` (`json_safe`: `NaN` and infinity become `null`; unknown coordinates are stored as unknown). The shipped data file was not edited, so the verified processed data are unchanged.
* **Codes longer than their column.** Building and meter codes are `<KEY>-B01`, `<KEY>-F01` and so on; for an uploaded society named "Green Park Residency" that was `GREEN-PARK-RESIDENCY-2-B01`, 26 characters in a `VARCHAR(24)` column. Fixed in `ml_engine/society/ingest.py`: the key part is shortened so the code always fits (codes only have to be unique within one society, which they are), and an over-long meter column name is rejected up front with a clear message. The seven bundled communities were not affected (`FOX-B01` and similar).

After the fixes the same suite passed on PostgreSQL, and the regression tests listed in §2 fail on SQLite as well if either defect is reintroduced (checked by removing the fixes once and watching them fail).

## 2c. Corrections made after the first delivery

* This document and the README said that `bandit -r backend ml_engine scripts -ll` had no findings. That was wrong for the delivered ZIP: the two verification scripts had five `urlopen` calls (B310). The independent verifier now refuses any URL that is not `http` or `https` before it opens it, the calls carry a `nosec` marker with the reason, and `bandit` now reports nothing. Because the verifier script changed, its report was regenerated by running it again (`verify_society_end_to_end.py --check-subset`, 127 of 127 checks; only the script hash, the time and the port of the temporary server differ from the previous report).
* "The society tests were run on SQLite only" is no longer true (§6).

## 3. Checks that are not in the pytest suite

* **Uploaded society, trained end to end.** `scripts/verify_upload_train.py` starts the real application, uploads a CSV built from six real Peacock
  meters plus one pump column, trains the society through the admin endpoint (the full evaluation protocol), and reads the forecast. The run
  returned: upload accepted (6 buildings, 1 facility meter, 17,408 of 17,544 hours valid); forecast before training refused with 409; training
  job succeeded in about 3.5 minutes (22,062 backtest rows, 1,653 anomaly events); forecast 200 with 24 hourly points; selected models XGBoost at 1 h and
  Random Forest at 6, 12, 24 and 168 h. **The pump column is a copy of a real meter multiplied by 0.05.** It only exercises the facility mapping and is
  not a measurement, so nothing about pump consumption should be read from that run. It is not in pytest because it takes minutes.
* **Real browser, real data.** `docs/screenshots/society_01..12_*.png` were taken with Chromium against the real backend with all seven communities
  imported (the mobile capture at 390 px width shows the signed-in overview without horizontal scrolling).

## 4. Test isolation

Society training and import write into `artifacts/society/` and read `data/society/processed/`. The shared test settings (`tests/integration/conftest.py`,
`make_settings`) therefore point these two folders at **empty temporary folders** by default; only the tests that need the real data pass the shipped
folders explicitly, and none of them trains. This was added after a full test run was found to have retrained one bundled community inside
the repository (the role-matrix test calls every permitted admin operation). The retraining was deterministic and the regenerated result tables were
byte-identical to the previous ones, and the surplus model folders it left behind were deleted. A later full run changed no file under `artifacts/` or `data/society/`.

## 5. The delivered ZIP

The ZIP was unpacked into a new empty folder and the checks of §1 were run **there** (not in the working copy): Python suites **256 passed, 3 skipped** (the third skip is `test_full_official_files_pass_all_checks_and_contain_the_subset`, which needs the 194 MB BDG2 download that the ZIP leaves out; in the working copy, where the files are present, the same test runs and the total is 257 passed, 2 skipped); `ruff` clean; `npm ci`
from the lock file, `typecheck`, `lint`, **118** frontend tests and the production build; **4** end-to-end tests. The first clean-unpack run found one real problem: the secret-scan
test listed files with `git ls-files`, which fails in a folder with no `.git` (every unzipped copy). `scripts/check_secrets.py` now walks the folder when git is not available.

In the same clean unzip the whole suite was then run against PostgreSQL 16.15 started from an empty data directory: **258 passed, 1 skipped** (the BDG2 test above). A production-mode API on that PostgreSQL, started with the image's entrypoint and file layout but without a container, passed 24 deployment checks, and the raw-data verifier ran against it in full mode (the official files were supplied from outside the ZIP): **127 of 127**. A build of both Docker images was attempted and failed before any Dockerfile instruction ran, because Docker Hub answered `Forbidden` for the base images ([`../12_deployment.md`](../12_deployment.md) §1b).

What the ZIP contains and what it leaves out, so that nothing is a surprise:

* Contains: all source, tests, docs and screenshots; `data/sample`; the **processed real society data** (`data/society/processed`, 4.6 MB); for all seven communities the saved evaluation,
  backtest predictions, SHAP, peak results and alerts; **deployed forecasting models for all seven communities** (installed afterwards with `scripts/society_deploy_bundles.py`, which refits the configuration cross-validation chose and leaves `evaluation.json` and the prediction files byte-for-byte unchanged).
* For Bull, Eagle, Hog, Peacock and Robin the models are not shipped. Checked in the unpacked copy: after "Import bundled communities" these five show as evaluated with models not
  installed. Their overview, model comparison, backtest, SHAP and alert endpoints return 200 and the **live forecast returns 410** (the overview shows "Not available").
  `python scripts/society_train.py --societies <key> --deploy` (a few minutes each on two CPU cores; evaluation alone took 111 to 161 s per community in the delivered runs) installs them.
* Also contains the **raw-data verification**: `scripts/verify_society_raw_data.py`, `verify_society_end_to_end.py`, `society_make_raw_subset.py`, `data/society/raw_subset/` (the official metadata file and the raw electricity readings of every `Lodging/residential` building, unchanged, 6.4 MB), [10_raw_data_verification.md](10_raw_data_verification.md), the generated [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) and `verification_report.json`, and the recorded [test run](verification_test_run.txt).
* Leaves out: the 194 MB raw BDG2 download (the 174 MB electricity file and the weather file; `python scripts/verify_society_raw_data.py --download` fetches it and checks its SHA-256; `scripts/society_prepare.py` also fetches it), the household benchmark models (146 MB, re-created by
  `scripts/reproduce_benchmark.py`), `node_modules`, `frontend/dist`, caches, `.git` and any database or `.env`.

## 6. What was not tested

* **Docker images and the AWS stack**: never built or deployed. A build of both images was attempted and failed before any Dockerfile instruction ran: Docker Hub answered `Forbidden` for the base images (`python:3.11-slim`, `node:22-alpine`). Also unverified: `docker compose up`, the Nginx configuration, GitHub Actions CI and every AWS resource. What was run instead, and how it differs from a container, is in [`../12_deployment.md`](../12_deployment.md) §1a.
* **PostgreSQL for the society tables** was tested on 2026-11-08 (PostgreSQL 16.15, server process on the build machine, not a container): the whole unit and integration suite, including the Alembic-versus-models test, `pg_dump` and restore, and the society import, API and upload tests; 259 passed, 0 failed, 0 skipped in the working copy and 258 passed, 0 failed, 1 skipped in the clean unzip (the one skip needs the official BDG2 files; the two tests that skip on SQLite ran in both). An earlier version of this section said that the society tests had been run on SQLite only; that was true then and is not any more. The run found two defects that only PostgreSQL reveals (§2b). A production-mode API on PostgreSQL also passed the independent raw-data comparison (123 of 123 checks in subset mode, 21 of them against the API, in the working copy; 127 of 127 in full mode in the clean unzip). Not covered: PostgreSQL under load, other PostgreSQL versions, and a managed PostgreSQL (Amazon RDS).
* **Windows.** Only Linux was used.
* **Load and scale.** Seven communities of 8 to 16 buildings each, hourly data. No test with thousands of meters or 1-minute data volumes beyond the parsing unit tests.
* **A real housing society.** No such data were available, so no result says anything about family housing, lifts, pumps, street lights or a real tariff.
* **Anomaly accuracy.** There are no fault labels, so detection is checked for internal consistency and plausibility only, never for precision or recall.
* **The CI workflow** has never run (the repository has not been pushed).
* **Coverage** was not re-measured for the society code; the figure in the main README (95 %) belongs to the household stage.

## 7. Reproduce

```bash
python -m pytest tests/unit tests/integration          # needs data/society/processed and artifacts/society (shipped); the integrity tests skip if absent
python -m pytest tests/e2e -rs                         # needs `npm run build` and Playwright's Chromium (pip install playwright==1.63.0)
cd frontend && npm test && npm run typecheck && npm run lint
ruff check . && bandit -q -r backend ml_engine scripts -ll
python scripts/verify_society_raw_data.py --use-subset  # independent raw-data verification of the processed files, a few seconds, no download
python scripts/verify_society_end_to_end.py --check-subset   # the same with the full official files (after --download) and a live API; rewrites the report
python scripts/verify_upload_train.py                  # about 4 minutes
python scripts/ui_audit.py                             # axe-core accessibility audit of the built interface (see the script header for the prerequisites)
python scripts/capture_society_fixtures.py             # refreshes the frontend fixtures from a running backend
python scripts/make_login_chart_data.py                # regenerates the real week shown on the sign-in page from artifacts/society/fox
```

## 8. Final documentation pass

After the verification above the project was frozen. The final ZIP differs from the ZIP that was verified (SHA-256 `d5fc3211…0a6f`) only in documentation: corrected test figures with the two environments told apart (PostgreSQL: 258 passed and 1 skipped in the clean unzip, 259 passed and 0 skipped in the working copy), the README Quick start, the Docker build status (attempted, failed with `Forbidden`), the list of unverified deployment items, and one added file, `docs/postgres_test_run_clean_unzip.txt` (the clean-unzip PostgreSQL output, with the database password in its command line replaced by `<REDACTED>`). The assembled project report (`docs/academic/EnergiQ_AI_Final_Report.md`, `.docx` and `.pdf`), which embeds these chapters, was regenerated with `scripts/build_report.py` and `scripts/docx_to_pdf.py` so that it agrees with the corrected chapters; it is a report of the household stage with the society extension documented separately (see the scope note in `docs/11_testing.md`). No code, data, model, test, migration or configuration file was changed. What was re-checked on the final ZIP is stated in `FINAL_VERIFICATION_REPORT.md`, delivered next to the ZIPs.
