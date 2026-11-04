# 05. Machine-learning methodology

Citation numbers in square brackets refer to `docs/references.md`.
Every number in this document is read from a file under `artifacts/reports/` that a script in `scripts/` produced.

## 1. Problem statement for the models

Predict the **hourly mean of `Global_active_power` (kW)** of one household for horizons of 1, 6 and 24 hours ahead, using only information available at the forecast origin.

* Data: UCI "Individual household electric power consumption" [17], 1-minute readings from December 2006 to November 2010 (CC BY 4.0).
* Target: the mean of the minute readings in each clock hour. An hour is **valid** only if at least 45 of its 60 minutes are valid. Hours with fewer valid minutes stay missing; **nothing is imputed**. 34,151 hours are valid (data-quality score 98.75, see `docs/04_eda_report.md`).
* The unit is kW (power), not kWh. A mean of 1.0 kW over one hour equals 1.0 kWh of energy; cost calculations use that identity and say so.

## 2. Forecasting framework

**Direct multi-horizon forecasting.** One model per horizon h is trained to predict the value at time t+h from features known at time t. This avoids feeding a model its own predictions (no error accumulation) and lets each horizon use the features that matter for it. The application bundles 24 XGBoost models (h = 1…24) so that a 24-hour curve can be produced; the published benchmark uses h = 1, 6 and 24.

### 2.1 Features (all built from data at or before the origin)

| Group | Features |
|---|---|
| Recent consumption | `lag_0, lag_1, lag_2, lag_3, lag_5, lag_11, lag_23, lag_47` (value k hours before the origin) |
| Same time yesterday / last week | `seasonal_24`, `seasonal_168` aligned to the **target** time (only allowed when h ≤ 24, enforced in code) |
| Recent averages and variability | `roll_mean_24, roll_std_24, roll_mean_168, roll_std_168` |
| Time of day | `hour, hour_sin, hour_cos` of the target time |
| Day of week | `dow, is_weekend, dow_sin, dow_cos` |
| Season | `month, month_sin, month_cos` |

Calendar features describe the **target** time, not the origin. Missing lags are left as NaN: XGBoost handles NaN natively, and Random Forest rows with missing inputs are excluded from scoring on the common evaluation mask (see §4). No public-holiday feature is used because the dataset has no declared country of residence beyond "near Paris"; holiday effects are listed as future work.

### 2.2 Chronological splitting and leakage control

* All splits are by time. There is **no shuffling anywhere**.
* Model selection uses an **expanding-window cross-validation** with 8 quarterly folds from 2008-Q1 to 2009-Q4. Each fold trains on everything before the fold start and is scored on the fold.
* The **test period, 2010-01-01 to 2010-11-26, is scored once**, after all choices (model families, hyper-parameters, the "best baseline by CV", the LSTM epoch count and seed) are fixed. Scaling parameters, fill values and the LSTM's early-stopping set come only from data before the cut-off.
* Unit tests prove the key properties on synthetic data (`tests/unit/test_features_splits.py`, `test_forecasting.py`): features use only past values, training never sees data after the cut-off, and an end-to-end API test (`test_forecast_uses_only_data_up_to_the_origin`) changes the future and confirms the forecast does not move.

## 3. Models

| Model | Role | Notes |
|---|---|---|
| Naive (last hour) | baseline | Predicts the origin value. At h = 24 it is identical to seasonal-naive-24 (the origin is exactly 24 h before the target), so the two rows in the h = 24 table are the same numbers. |
| Seasonal naive 24 h / 168 h | baselines | Value at the same hour yesterday / last week |
| Random Forest [1] | learned model | scikit-learn; 2 candidate settings tried in CV |
| XGBoost [2] | learned model | 3 candidate settings tried in CV; the application's production model |
| LSTM [3] | learned model | PyTorch, CPU only: hidden size 32, look-back 168 h, one network with three outputs (h = 1, 6, 24). Training scales with train-only mean/std, fills gaps with train-only hour-of-week means plus a missing-flag input, stops early on a validation block, then **refits on the full pre-test history for the selected number of epochs**. Seeds 42, 43, 44; seed 42 was declared the headline run before test scores existed. |

Hyper-parameter search is deliberately small (the machine has 8 GB RAM and no GPU). The selected settings per horizon are stored in `artifacts/reports/benchmark/cv_results.json`:
Random Forest `n_estimators=150, min_samples_leaf=10, max_features=0.5`; XGBoost `n_estimators=400, max_depth=6, learning_rate=0.03` for h = 6 and `n_estimators=300, max_depth=4, learning_rate=0.05` for h = 1 and 24 (the latter is also the single fixed configuration used by the application). The selection depends on the XGBoost version; see `docs/06_model_evaluation.md` §8.

The strongest baseline is chosen **by cross-validation, not by test score**; the evaluation also reports the comparison against the best baseline in hindsight, which is stricter.

## 4. Evaluation protocol

* **Common evaluation mask.** For each horizon every model is scored on exactly the same rows: those whose target is valid and whose inputs are available to *all* models. 7,233 hours are scored per horizon; about 686–687 of the 7,919–7,920 test hours are excluded for a missing target or missing inputs. A model never gets an easier subset than another.
* **Metrics.** MAE and RMSE in kW, MAPE and sMAPE in % (MAPE excludes hours with actual < 0.05 kW; none occur in the test rows), and R². MAE is the headline metric because it is in the unit of interest and robust to the heavy right tail of household load; the choice follows [7].
* **Uncertainty.** The paired difference of MAE between two models is estimated with a **day-block bootstrap** (resampling whole days, 312 days in the test span) to respect within-day autocorrelation; 95 % percentile intervals are reported. A difference whose interval excludes zero is called significant here; otherwise the models are called indistinguishable on this sample.
* **No claim beyond the data.** One household, one location, ~11 months of test data: the results say nothing about other households or years.

## 5. Reproducing the benchmark

```
python scripts/reproduce_benchmark.py --input data/raw/uci_household_power/household_power_consumption.txt
```

runs the five steps in order; each is also a script of its own (`--input` is the raw file, `--help` shows the options):

1. `scripts/run_benchmark.py`: features, cross-validation, baselines, Random Forest and XGBoost, written to `artifacts/reports/benchmark/`.
2. `scripts/run_lstm.py --seeds 42 43 44`: the LSTM with three seeds, written to `artifacts/reports/benchmark/`.
3. `scripts/evaluate_models.py`: test metrics, bootstrap intervals and figures, written to `artifacts/reports/evaluation/`.
4. `scripts/run_explain.py`: TreeSHAP summaries, tariff cost and recommendations, written to `artifacts/reports/explain/`.
5. `scripts/run_anomaly.py`: anomaly summary and synthetic injection check, written to `artifacts/reports/anomaly/`.

The raw UCI file is not committed (`data/raw/` is git-ignored); download it from the DOI in [17] and place `household_power_consumption.txt` there. Use an interpreter built from `requirements.txt`: **XGBoost results depend on the XGBoost version** (`docs/06_model_evaluation.md` §8), and every output file records the versions that produced it. On the development machine (2 CPU cores) the tree benchmark took 743 s and the LSTM with three seeds 667 s in the final run (`runtime_seconds` in the result files) (both while other jobs were also using the machine; an earlier solo run of the tree benchmark took 455 s); the full chain took about 25 minutes.
