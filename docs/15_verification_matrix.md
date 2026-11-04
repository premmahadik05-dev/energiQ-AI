# 15. Verification matrix

Status values: **PASS** (checked by an automated test or a measurement that was run, evidence named), **PARTIAL**
(works, with a stated scope limit), **NOT TESTED** (written but never run or exercised), **NOT TESTABLE** (cannot be
measured with the data available). Nothing is marked PASS on the basis of "it should work". Test counts and commands
are in `docs/11_testing.md`. Everything was verified on Linux in the build workspace.

## 1. Deployment level (the ladder from `docs/03_architecture.md` §8)

| Level | Status | Evidence / reason |
|---|---|---|
| Implemented locally | **YES** | Runs on Linux with SQLite and PostgreSQL 16, real HTTP, real browser (`tests/e2e`). |
| Docker-tested | **NO** | Dockerfiles and compose file are written; `docker compose config -q` validates. The images were never built or run (base images could not be pulled in the build workspace). |
| Cloud-configured | **YES** | CloudFormation templates and a manual-only deploy workflow exist and pass `cfn-lint`. |
| Actually deployed | **NO** | Nothing was deployed; no AWS resources were created. |
| Independently verified | **NO** | No one other than the author and an AI assistant has run the project; CI has never executed on GitHub. |

## 2. Functional requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| FR-01 | Register and log in | **PASS** | `test_api_core.py`, `test_security.py` (rate limits, hashing), HTTP e2e, browser e2e (weak-password refusal and registration), frontend auth tests (18) |
| FR-02 | Upload CSV datasets | **PASS** | 16 ingest + 14 loading unit tests, upload API tests, UI upload verified live by the frontend author (upload, append, delete) |
| FR-03 | Validate and explore data (quality report) | **PASS** | Quality report unit tests; API returns report; dataset page shows it (browser e2e checks the dataset summary against the API) |
| FR-04 | View historical consumption patterns | **PASS** | Readings (hourly/daily) and profile endpoints tested; explorer and table view verified live by the frontend author; not covered by the repository's browser e2e |
| FR-05 | Forecast 1 h, 6 h, 24 h (and 1–24 h curve) | **PASS** | Benchmark at 1/6/24 h (`docs/06`); API forecast tests incl. leakage canary; browser e2e creates a forecast and checks its peak |
| FR-06 | Compare forecasting models | **PARTIAL** | The research benchmark compares 3 baselines, Random Forest, XGBoost and LSTM with bootstrap intervals and is shown on the Benchmark page. Inside the application each trained model is compared with the baselines only, not with Random Forest or LSTM |
| FR-07 | Detect abnormal consumption | **PASS** (function) / **NOT TESTABLE** (accuracy) | 10 unit tests, API flow, synthetic injection check (`docs/08` §5); the real dataset has no labels, so no accuracy is claimed |
| FR-08 | Explain predictions | **PASS** | TreeSHAP additivity ≤ 3.8×10⁻⁶ kW on 7,233 rows; local and global API tests; explainability page verified live |
| FR-09 | Cost with editable tariffs | **PASS** | Tariff/cost unit and API tests (validation, DEMO labelling, ownership); tariff create/delete verified live. Costs are only as good as the tariff the user enters |
| FR-10 | Transparent optimisation, separate from anomalies | **PASS** | Rule-based recommendations carry evidence and assumptions (unit + API tests); scheduler is an exhaustive search (unit tests) |
| FR-11 | Alerts and historical analysis | **PASS** | Anomaly events with acknowledge, notifications, jobs, audit log (API tests; UI verified live) |
| FR-12 | Export reports | **PASS** | HTML report (escaped, CSP; test_security) and CSV export (API tests); authenticated downloads verified live |
| FR-13 | Manage datasets and experiments | **PASS** | Create/append/activate/delete datasets and models; deletion cascades (test_delete_dataset_removes_everything) |
| FR-14 | Monitor model performance | **PASS** | Drift (PSI/KS) and realised-error monitoring (API tests); monitoring card verified live. No scheduled retraining |
| FR-15 | Admin panel and settings | **PARTIAL** | Admin users/roles, audit log and system stats exist and are role-protected (tests, verified live). Per-user settings are limited to theme, active dataset and tariffs; there is no general settings page |

## 3. Non-functional requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| NFR-01 | 8 GB RAM, CPU only, Windows | **PASS** (memory, CPU) / **NOT TESTED** (Windows) | Peak 294 MB (API workflow), 600 MB (tree benchmark), 1.1 GB (LSTM seed), 508 MB (profiling); no GPU used. Never run on Windows |
| NFR-02 | Chunked loading, no needless full loads | **PASS** | Streaming CSV reader; profiling a 2.08-million-row file peaked at 508 MB |
| NFR-03 | Small footprint (SQLite, one process, no Redis/Celery) | **PASS** (local) / **NOT TESTED** (compose) | Default run is one process on SQLite; compose file validated but not run |
| NFR-04 | Reproducible training | **PASS** (with pinned libraries) | Repeat-training test; benchmark re-run reproduces baselines, RF and LSTM exactly; XGBoost differs across XGBoost versions, hence the pins and recorded versions (`docs/06` §8) |
| NFR-05 | No leakage, chronological splits only | **PASS** | Feature/split unit tests, API canary that rewrites the future, test period scored once |
| NFR-06 | Hashing, authn, authz, isolation | **PASS** | Argon2id; 16 security tests incl. role matrix over every route and IDOR checks |
| NFR-07 | Upload limits, safe handling, CSV validation | **PASS** | Size/extension/content tests; client file name never used on disk; rate limit on uploads |
| NFR-08 | No secrets in code, logs or Git | **PASS** (local) | Secret scan 0 findings, tests for the scanner, production refuses the dev secret. The CI job that repeats it has not run |
| NFR-09 | Demo data labelled; no hard-coded statistics in the UI | **PASS** (by lint rule, review and tests) | DEMO tariff labelled in API and UI; lint forbids `Math.random`; UI tests run against captured API responses. There is no automated scan for numeric literals in components |
| NFR-10 | Honest deployment status | **PASS** | §1 above and `docs/12_deployment.md` |

## 4. Phases of the specification

| Phase | Deliverable | Status | Where |
|---|---|---|---|
| 1 | Requirements, dataset suitability, architecture, repository | Done | `docs/01–03`, repository layout |
| 2 | Dataset profiling and EDA | Done | `docs/04`, `artifacts/reports/eda`, `dataset_profile.json` |
| 3 | Preprocessing and feature engineering | Done, tested | `ml_engine/data`, `ml_engine/features`; unit tests |
| 4 | Baseline forecasting | Done, tested | `ml_engine/forecasting`; `docs/05–06` |
| 5 | ML models (Random Forest, XGBoost) | Done, tested | CV protocol in `docs/05`; results `docs/06` |
| 6 | Lightweight LSTM | Done, tested | `ml_engine/forecasting/lstm.py`; 3 seeds, exact reproduction |
| 7 | Model evaluation | Done | `docs/06`, figures; regenerated under pinned environment |
| 8 | Anomaly detection | Done (no labels) | `docs/08` |
| 9 | Explainability and optimisation | Done, tested | `docs/07` |
| 10 | Backend and database | Done, tested (SQLite and PostgreSQL) | `docs/09`, Alembic migration |
| 11 | Frontend | Done, tested (Chromium) | `docs/16` |
| 12 | Integration and security | Done, tested | `docs/10`, security tests; defects found and fixed (`docs/11` §6) |
| 13 | Testing and cloud deployment | Testing done; **cloud deployment not done** by design (no paid resources without approval) | `docs/11`, `docs/12`, `infrastructure/` |
| 14 | Monitoring and academic deliverables | Done (monitoring implemented; no external monitoring stack deployed) | `docs/14`, `docs/academic/`, report and slides |

## 5. Academic deliverables (spec §12)

| Deliverable | Where |
|---|---|
| Abstract, problem statement, objectives | `docs/academic/01–03` |
| Literature review (17 verified references only) | `docs/academic/04_literature_review.md`, `docs/references.md` |
| System requirements | `docs/02_requirements.md` |
| Architecture, ER, UML, data-flow diagrams | `docs/03_architecture.md`, `docs/diagrams/` (ER diagram generated from the ORM) |
| ML methodology, comparison report, results | `docs/05`, `docs/06`, `docs/07`, `docs/08` |
| Security documentation | `docs/10_security.md` |
| API documentation | `docs/api/API_REFERENCE.md` (generated from the live OpenAPI, 47 operations), `openapi.json` |
| Installation, user manual, deployment guide | `docs/manuals/installation.md`, `docs/manuals/user_guide.md`, `docs/12_deployment.md` |
| Limitations and future scope | `docs/13_limitations.md` |
| Final report | `docs/academic/EnergiQ_AI_Final_Report.docx` (assembled from the chapters by `scripts/build_report.py`) |
| Presentation slides | Published as a Slides artifact (see the delivery message) |
| Live demonstration script | `docs/manuals/demo_script.md` |

## 6. Things only you can do

1. Push the repository to GitHub and look at the first CI run (it has never run).
2. Build and run the Docker images (`docker compose up --build`) and then update `docs/12_deployment.md`.
3. Run the installation steps once on Windows and note any difference.
4. Replace the DEMO tariff with a real one before drawing cost conclusions.
5. Decide whether to approve any AWS deployment (it creates paid resources); nothing was created.
6. Have someone else review the literature review and the claims in the final report.
