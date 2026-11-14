# 8. Limitations and future work

Read this before relying on any number in the project. These are the limits of the evidence, not apologies.

## About the data

1. **The societies are representative communities, not registered housing societies, and the buildings are not family flats.** BDG2 buildings labelled `Lodging/residential` include **student residence halls**. Of the 73 buildings used, 56 are labelled `Dormitory`, 8 `Housing` (Eagle) and 9 `Other - Lodging/Residential` (Rat); BDG2 does not describe the last two further. The communities are these buildings summed per hour. Occupancy patterns of family housing (cooking peaks, school and office times, festivals, air-conditioner loads in Indian homes) differ, so accuracy figures do not transfer.
2. **BDG2 is mostly non-residential data**, and only two years (2016–2017) of each building. A community's test period is six months, so a single unusual term can move a result. The seasonal pattern is seen twice at most.
3. **No facility meters.** Lifts, water pumps, street lighting and the clubhouse are not measured in this data. The Facilities page says so and shows nothing for them; it fills in only when an administrator uploads such meters.
4. **No real tariff.** The cost estimate uses a placeholder time-of-use tariff unless the user enters their own. It is an estimate for planning, not a bill.
5. **No fault labels.** Anomaly detection cannot be scored for precision or recall; alerts mark readings unusual for the hour of the week. Many alerts sit at term transitions (a residence hall emptying or refilling), which are real changes in occupancy but not faults.
6. **Simple cleaning, no imputation.** A single bad meter makes that hour missing for the whole society, which keeps every number honest but throws data away (for Rat, 5 % of hours).
7. **The "live" forecast is not live.** It starts from the last hour in the stored data (2017-12-31 23:00). The application states the as-of time; connecting a real meter feed is future work.

8. **What the raw-data verification covers.** [`10_raw_data_verification.md`](10_raw_data_verification.md) shows that the stored data and the API follow from the raw BDG2 files by the documented rules (127 of 127 checks). It verifies the raw readings, the cleaned readings and the aggregated community demand; it does **not** verify the model predictions, does not show that BDG2 is free of errors, and does not make the communities representative of any real society. The cleaning thresholds are choices made for this project.

## About the models

1. **Weekly horizon is weak.** "Same hour last week" is the best method for 7 days in five of seven communities; learned models won only in two (13 % lower error).
2. **24 h results are mixed.** In two communities cross-validation selected a baseline; in one (Peacock) the cross-validated choice was worse than the baseline on the test period (RESULTS §2). Cross-validation on one year of data is not a guarantee.
3. **Weather is observed, not forecast**, and gave no consistent gain. A real deployment would use a weather forecast, which has its own error.
4. **Intervals are empirical and approximate.** The 80 % range comes from past cross-validation residuals; its test coverage is not 80 % exactly.
5. **Horizons between the evaluated ones (2–5, 7–11, 13–23 h) reuse the nearest evaluated configuration**; their accuracy is not separately measured.
6. **No LSTM or other deep model for societies**; the household benchmark found none better than XGBoost, but that was a different data set.
7. **Peak timing is only partly predicted**: the level of the daily peak is better than the baseline's, the exact hour is right on roughly a quarter of days (RESULTS §4).
8. **SHAP explains the model, not the building.** A large "yesterday's usage" contribution means the model leans on it, not that yesterday caused today's load.

## About the software

1. **Docker images and the AWS stack were written and linted but never built or deployed** (a build of both images was attempted and failed: Docker Hub answered `Forbidden` for the base images; `docs/12_deployment.md` §1b, `docs/15_verification_matrix.md`). What *was* run: the whole backend test suite and a production-mode API (entrypoint script, Alembic migrations, the society import and the raw-data comparison) on PostgreSQL 16.15, with the file layout the image is meant to have, but not inside a container (`docs/12_deployment.md` §1a). That run found and fixed two PostgreSQL-only defects and a missing society configuration in the images.
2. **Uploaded-society training via the API** (the full evaluation and deployment job on a user-uploaded file) was run end to end once by hand with `scripts/verify_upload_train.py` (upload, clean, store, train, forecast, anomalies; about 3.5 minutes), but it is **not part of the automated pytest suite** because it takes minutes. That check used a file built from six real Peacock meters plus one *scaled copy of a real meter* labelled as a pump to exercise the facility mapping; the pump column is not a measurement. The pytest suite covers the upload and cleaning path, its failure paths and the runner on short data.
3. **Hiding a building** in Society admin removes it from comparisons and alert lists but does not recompute the stored society total.
4. **Only Linux was used.** Windows instructions follow the original project and are untested for the society features.
5. **Delivered models:** the ZIP contains the deployed forecasting models of all seven communities (about 200 MB). They were installed with `scripts/society_deploy_bundles.py` from the evaluation that was already saved; the evaluation and prediction files were not touched (the script checks their SHA-256 before and after). A community whose bundle is missing answers "models not installed" for the live forecast until `python scripts/society_deploy_bundles.py --societies <key>` is run. For two communities (Eagle and Rat) cross-validation chose the simple *naive* baseline at the 24 h horizon, so the deployed 24 h model there is that baseline; the Forecasting page says so.
6. The CI workflow of the original project has never run (the repository has not been pushed).

## Future work

* Replace the representative communities with the meter file of a housing society that has lift, pump, street-light and clubhouse meters (hourly or 15-minute) through the upload page, and re-run the protocol.
* A **live feed** (MQTT or a utility API) feeding the forecast, with a weather forecast service instead of observed weather.
* **Probabilistic and hierarchical forecasting**: forecast the buildings and reconcile them with the society total; quantile models for the peak.
* **Holiday and occupancy features** and a model for the weekly horizon (for example lags of the same weekday across several weeks, or a seasonal-trend decomposition).
* **Labelled anomalies** (maintenance logs) so detection can be scored, and per-meter alert tuning.
* **Real tariffs** per country (including demand charges) and a demand-response what-if driven by measured flexible loads.
* An LSTM or temporal-fusion baseline on a larger, residential, multi-year data set.
* Per-resident privacy controls if household-level meters are added (aggregation thresholds, pseudonyms).
