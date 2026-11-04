# EnergiQ AI — Requirements

Derived from the project specification. Statuses were last updated at the end of the project and only say
what was actually verified; the evidence for each is in `15_verification_matrix.md`.

Status key: PASS, PARTIAL, NOT TESTED, NOT TESTABLE (defined in `15_verification_matrix.md`).

## 1. Functional requirements

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-01 | Register and log in | 10, 11 | PASS |
| FR-02 | Upload electricity consumption datasets (CSV) | 10, 11 | PASS |
| FR-03 | Validate and explore uploaded data (quality report) | 3, 10 | PASS |
| FR-04 | View historical consumption patterns | 11 | PASS |
| FR-05 | Forecast future consumption (1 h, 6 h, 24 h) | 4–7 | PASS |
| FR-06 | Compare forecasting models | 7 | PARTIAL (benchmark compares all models; the app compares with baselines) |
| FR-07 | Detect abnormal consumption | 8 | PASS (function); accuracy NOT TESTABLE, no labels |
| FR-08 | Explain predictions (Explainable AI) | 9 | PASS |
| FR-09 | Estimate cost with editable tariff rules | 9, 10 | PASS |
| FR-10 | Transparent optimisation recommendations, separate from anomalies | 9 | PASS |
| FR-11 | View alerts and historical analysis | 10, 11 | PASS |
| FR-12 | Export reports | 10, 11 | PASS |
| FR-13 | Manage datasets and forecasting experiments | 10, 11 | PASS |
| FR-14 | Monitor model performance | 10, 14 | PASS |
| FR-15 | Admin panel and settings | 11 | PARTIAL (admin yes; no general settings page) |

Dataset-dependent items (FR-05 to FR-10) rest on the supplied dataset, which passed the suitability check (`01_dataset_suitability.md`).

## 2. Non-functional requirements

| ID | Requirement | How it is checked | Status |
|---|---|---|---|
| NFR-01 | Runs on 8 GB RAM, CPU only, Windows | Peak memory measured per pipeline stage and recorded in reports | PASS for memory and CPU (peaks 0.3–1.1 GB); Windows NOT TESTED |
| NFR-02 | No full-dataset loads when avoidable; chunked CSV processing | Profiler and ingestion read in chunks; peak RSS reported | PASS |
| NFR-03 | Small default footprint: SQLite locally, one process, no Redis or Celery unless justified | Default `docker-compose` profile starts only backend, frontend and database | PASS locally; compose NOT TESTED |
| NFR-04 | Reproducible training (fixed seeds, versioned config, data hash) | Re-running training reproduces metrics; test in Phase 7 | PASS with pinned libraries (XGBoost varies across versions) |
| NFR-05 | No data leakage; chronological splits only | Leakage tests in Phase 3 | PASS |
| NFR-06 | Password hashing, authentication, authorisation, per-user data isolation | Security tests in Phase 12 | PASS |
| NFR-07 | Upload limits, safe file handling, CSV validation | Upload security tests in Phase 12 | PASS |
| NFR-08 | No secrets in code, logs or Git | `.env` ignored, `.env.example` only, secret scan in CI | PASS locally; CI job not yet run |
| NFR-09 | Demo data always labelled as demo; no hard-coded statistics in the real UI | Frontend review in Phase 11 | PASS (lint rule, review, tests) |
| NFR-10 | Honest status reporting for deployment levels | Ladder in `03_architecture.md` section 8 | PASS |

## 3. Explicit non-claims

The platform and its report will not:

- present unlabelled anomalies as confirmed faults, theft or equipment failure;
- promise guaranteed energy or cost savings;
- invent weather, tariff or label data that the dataset does not contain;
- claim performance on any data other than the real held-out test split;
- claim cloud deployment without evidence from a successful deployment;
- create paid cloud resources without your explicit approval.

## 4. Environment

| Item | Your machine | This sandbox |
|---|---|---|
| OS | Windows | Linux |
| Python | 3.11 (Anaconda) | 3.13 default; 3.11 also installed |
| RAM | 8 GB | 7 GB |
| GPU | none | none |
| Node | Node 20 or 22 LTS | 22 |
| Docker | needed to build the images | daemon starts, but images could not be built (registry blocked) |

Anything verified only here is reported as "verified on Linux", never as
verified on Windows.
