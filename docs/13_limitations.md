# 13. Limitations and future scope

## 1. Limitations (what a reader should not over-trust)

### Data and modelling
1. **One household, one source.** All benchmark results come from a single French household's 4-year record. They say nothing about other buildings, and the application's per-dataset training is evaluated only on that dataset's own final block.
2. **Modest accuracy at longer horizons.** MAE is 32–42 % of mean load and R² is about 0.40 at 6 and 24 h (`docs/06_model_evaluation.md`). The models beat naive baselines by roughly 18–25 % MAE; they are not precise predictors of individual hours.
3. **Deep learning showed no benefit.** The LSTM equals XGBoost at 6 and 24 h and is worse at 1 h. A larger architecture search, more input channels (sub-metering, weather) or more data could change this; it was not explored.
4. **No exogenous drivers.** No weather, occupancy or public-holiday data is used. Holidays and heat waves are therefore out-of-pattern events for the models.
5. **Anomaly detection has no ground truth.** Only the chosen alert rate (~2 % of hours) and a synthetic injection check exist; moderate drops are often missed (`docs/08_anomaly_detection.md`). Detected events are leads, not diagnoses.
6. **Forecast range is empirical.** The 80 % band comes from hold-out residual quantiles and was not validated for coverage on independent data.
7. **Recommendations are heuristic scenarios.** Savings figures assume fixed percentages and a user-supplied tariff; the built-in DEMO tariff is illustrative only.
8. **An atypical period was kept without a sensitivity check.** The August 2008 ten-day low-use block (`docs/04_eda_report.md`) stayed in the training data; the planned with/without comparison was not run, so its influence on the models is unknown.
9. **Time conventions.** Timestamps are treated as the dataset's own local clock; daylight-saving effects are only checked for the benchmark dataset.

### Software and operations
10. **Single API process.** The rate limiter, the job runner's thread pool and the metrics registry are in memory. Running several API workers or tasks would split rate-limit counters, lose job progress visibility across processes, and give per-process metrics. The deployment is therefore limited to one API instance (the compose file and ECS service are set accordingly). This caps availability (a restart interrupts running jobs) and throughput.
11. **Training is CPU-bound and synchronous in a thread.** Measured on the bundled one-year sample (8,760 hourly rows) on a 2-core, 7 GB machine: training the 24-model bundle took about 25 s, a 24-hour forecast 0.6 s and anomaly detection 0.5 s. Several years of data or a slower machine will take proportionally longer, and training competes with API requests for CPU.
12. **Token model.** Stateless access tokens without refresh or revocation lists; the UI keeps the token in memory/`sessionStorage`.
13. **File storage is local.** Uploads and models are on a mounted volume (EFS in the AWS template), not an object store; there is no virus scanning of uploads (they are only parsed as text numbers).
14. **Not validated at scale.** Tests use datasets of up to a few years of hourly data; there was no load testing beyond functional tests, so no capacity or latency guarantees are made.
15. **Not run in containers or in the cloud here** (`docs/12_deployment.md` §1).
16. **Python versions.** The suite was run on Python 3.11 (supported) and 3.13; other versions are untested.
17. **Browsers.** The UI was exercised in Chromium only.
18. **Results depend on library versions.** Baselines, Random Forest and the LSTM reproduced exactly when the whole benchmark was re-run, but XGBoost's predictions moved by up to 0.0036 kW test MAE between XGBoost builds (3.2.0 pinned here, 3.4.1 in the system Python 3.13). A different build can also change which CV configuration is selected and flip the sign of very small model differences (`docs/06_model_evaluation.md` §8). Results are bit-reproducible only with the pinned `requirements.txt`; every result file records its versions.
19. **Windows is untested.** The commands in the manuals are written to work on Windows (plain npm scripts, no shell-only syntax in Python scripts, path handling via `pathlib`), but nothing was run on Windows; all verification was done on Linux.

## 2. Future scope

* Add weather and calendar (holiday) features and quantify their effect with the same chronological protocol; evaluate on more households (for example other public smart-meter data sets) to test generality.
* Probabilistic forecasting (quantile regression or conformal intervals) with measured coverage, replacing the empirical band.
* Label collection: let users confirm or dismiss anomalies, then evaluate and tune the detector against those labels and consider a supervised or semi-supervised model.
* Appliance-level insights from sub-metering where the data has it.
* Externalise state: Redis (or the database) for rate limiting, a real queue (Celery, RQ or SQS) for jobs, so the API can scale horizontally; object storage for files.
* Scheduled retraining with a champion/challenger comparison and automatic rollback, instead of the current manual retrain recommendation.
* Real tariff integration (time-of-use and dynamic prices), load-shifting optimisation across several devices, and battery/PV scenarios.
* Cookie-based sessions with CSRF protection, refresh tokens, multi-factor authentication, and an independent security review.
* Accessibility audit with assistive technology, internationalisation of the UI.
