# 9. Viva notes

Short, straight answers. Numbers come from [`RESULTS.md`](RESULTS.md) (generated from the saved evaluation files).

**1. What changed compared with the household project?**
The forecast target is now the *total demand of a community of buildings*, built as the exact hourly sum of real building meters. New:
the society data pipeline, society-level evaluation (peaks, buildings), a society API with its own tables, eleven dashboard pages, alerts per
society and per building, a cost model, recommendations, PDF/CSV reports, and an admin upload path. The household web pages were later removed from the interface; the household API routes, ML library and benchmark stay in the repository.

**2. Are these data from an actual housing society?**
No, and the application says so on every page. No open dataset of a registered housing society with per-building and common-facility meters was available. The data are real hourly
meter readings of 73 residential-use buildings from seven sites of the public BDG2 dataset, summed per site: 56 are labelled `Dormitory` by BDG2, and the other 17 are labelled `Housing` (8) or `Other - Lodging/Residential` (9), which BDG2 does not describe
further. They are student residence halls and similar buildings. They are not family flats, not individual homes and not a registered housing society. If the meter file of a housing society is available, the upload page runs the same pipeline on it.

**3. Where do the data come from, and may we use them?**
Building Data Genome Project 2 (Miller et al., Scientific Data 7:368, 2020), https://github.com/buds-lab/building-data-genome-project-2, CC BY-SA 4.0, downloaded 2026-11-08; file sizes and SHA-256 are recorded. Derived data keep the same licence and attribution.

**4. How exactly is the society consumption computed?**
At each hour, the sum of the cleaned kWh of all retained building meters; if any retained meter is missing or invalid at that hour the society value is *missing*, never a partial sum. kWh in one hour equals the hour's mean kW; peaks are hourly means.

**5. What was removed or changed in the data?**
Only marked missing: negative readings, exact zeros (dead meters), a value repeated for 48 h or more, and values above 4 × the meter's own 99.5th percentile. Nothing was filled or smoothed. Per-community counts are on the Data sources page.

**6. How do you avoid leakage?**
Features use only data up to the forecast origin; training rows are those whose *target time* precedes the validation block or the test period; folds and the test period are chronological. The test period (the last six months) was scored once, after the configuration was chosen by cross-validation.

**7. Which model is best?**
It depends on the horizon and the community, and the answer is a measured one: at 1 h a learned model (Random Forest, XGBoost or linear) beats the best baseline by 17–44 %; at 24 h learned models win in four of seven communities (17–21 %), a baseline is chosen in two, and in Peacock the chosen Random Forest is slightly worse than the naive baseline on the test set; at 7 days "same hour last week" is chosen in five of seven. We do not claim one model wins everywhere.

**8. Why not an LSTM?**
The brief says "if justified". The household benchmark in this project found the LSTM no better than XGBoost (and worse at 1 h), and the society data are only two years long, so we did not train it for societies. It is listed as future work.

**9. Why do the learned models lose at some horizons?**
We measured that they do, but we did not run an experiment that isolates the reason. A plausible explanation is that the weekly and daily repeat already captures most of the pattern in these buildings and the extra features add little, but that is a hypothesis, not a finding. What we do guarantee is the selection rule: cross-validation chooses between learned models and baselines, and the application serves the baseline when it wins.

**10. How do you know the uncertainty band is meaningful?**
It is an empirical 80 % band from out-of-fold cross-validation residuals. Its coverage on the test period is reported in `evaluation.json` and differs from 80 % (for Fox at 24 h: 85.9 % Random Forest, 93.1 % XGBoost). It is a useful range, not a guarantee.

**11. What does the cost figure mean?**
Energy × a time-of-use tariff the user selects. The default is a clearly labelled placeholder tariff; it is not a bill and no saving is promised. The only "saving" appearing in the recommendations is a stated what-if scenario, labelled as such.

**12. How are anomalies detected, and how accurate is it?**
The expected demand for each hour of the week is built from the previous 4 weeks; a reading beyond the 99.5th percentile of past deviations (scaled to the community) and a minimum size is an alert, grouped into events with severity and an explanation naming the buildings that contributed. There are no ground-truth labels, so we claim **no** precision or recall. Many alerts fall at term transitions.

**13. What does SHAP tell us?**
Which inputs the chosen model relies on. For Fox at 24 h, recent consumption and the same time yesterday/last week account for about 88 % of the total importance. It is a description of the model, not of causes.

**14. How is privacy handled?**
Buildings have pseudonymous codes; the dataset's own identifiers, the rejected-meter list and per-meter cleaning counts are admin-only (tested); there are no household identities in the data. Roles: viewer, analyst, admin. Audit log for administrative actions.

**15. What would you do with a real society?**
Upload its meter file (and a mapping that marks lift, pump, street-light and clubhouse meters), train, then compare with these results. With facility meters, the Facilities page and the totals include them.

**16. What is not tested or not done?**
Docker images were never built (the attempt failed: Docker Hub answered `Forbidden` for the base images) and AWS was never used. The training job on an uploaded file was run end to end once with `scripts/verify_upload_train.py` but is not in the automated suite (it takes minutes); its test data included one scaled copy of a real meter standing in for a pump, only to exercise the facility mapping. The live forecast starts from the end of the stored data, not from a real feed; the weekly horizon is weak; the societies are not family housing. See `07_testing_and_verification.md` and `08_limitations_and_future_work.md`.

**17. How do you know the society numbers follow from the raw data?**
A separate program, `scripts/verify_society_raw_data.py`, imports nothing from the application. It checks the SHA-256 of the raw BDG2 files, re-applies the documented selection and cleaning rules to the raw readings, re-aggregates each community, and compares meter by meter and hour by hour with the
stored data and with the running API: 127 of 127 checks passed ([report](VERIFICATION_REPORT.md), [method](10_raw_data_verification.md)). The raw readings, the cleaned readings, the aggregated community demand and the model predictions are four different layers; only the first three are verified this way. It shows that the application applies its documented rules correctly, not that the BDG2 files are error-free or that the communities are typical of any real society.

**18. How can I reproduce the numbers?**
`scripts/society_prepare.py` → `scripts/society_train.py --deploy` → `scripts/society_anomalies.py` → `scripts/make_society_docs.py`. Seeds are fixed; XGBoost version is pinned and recorded in each `evaluation.json`.
