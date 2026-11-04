# 06. Forecast evaluation results

Source of every number: `artifacts/reports/evaluation/evaluation.json` and `model_comparison.md`
(produced by `scripts/evaluate_models.py`). Test period: **2010-01-01 to 2010-11-26**, scored once.
Protocol and definitions: `docs/05_ml_methodology.md`. Units are kW; the mean load in the scored rows is 1.055 kW.

## 1. Headline table (test MAE, kW; lower is better)

| Horizon | Best baseline chosen by CV | Random Forest | XGBoost | LSTM (seed 42) |
|---|---|---|---|---|
| 1 h | Naive (last hour) 0.4080 | **0.3334** | 0.3357 | 0.3533 |
| 6 h | Seasonal naive 168 h 0.5767 | 0.4354 | **0.4327** | 0.4383 |
| 24 h | Seasonal naive 168 h 0.5767 | 0.4415 | **0.4413** | 0.4414 |

n = 7,233 scored hours per horizon, identical rows for every model. Bold marks the lowest value in a row; differences of a few thousandths of a kW between the three learned models are within the noise discussed in §2 and §8.

Reduction of MAE relative to the CV-chosen baseline, computed from the table above:

| Horizon | Random Forest | XGBoost | LSTM |
|---|---|---|---|
| 1 h | 18.3 % | 17.7 % | 13.4 % |
| 6 h | 24.5 % | 25.0 % | 24.0 % |
| 24 h | 23.4 % | 23.5 % | 23.5 % |

Against the **strongest baseline in hindsight** (a stricter reference that uses test information to pick the baseline) XGBoost's reduction is 17.7 % at 1 h, 22.1 % at 6 h and 20.6 % at 24 h.

Full metrics (RMSE, MAPE, sMAPE, R²) for all six methods are in `model_comparison.md`. For XGBoost: RMSE 0.486 / 0.597 / 0.604 kW and R² 0.611 / 0.412 / 0.398 at 1 / 6 / 24 h.

## 2. What the statistics support

Paired day-block bootstrap of the MAE difference (95 % interval, 312 test days):

| Comparison | h = 1 | h = 6 | h = 24 |
|---|---|---|---|
| XGBoost − best CV baseline | −0.0723 [−0.0820, −0.0626] | −0.1440 [−0.1627, −0.1252] | −0.1354 [−0.1538, −0.1184] |
| Random Forest − best CV baseline | −0.0746 [−0.0838, −0.0650] | −0.1413 [−0.1598, −0.1235] | −0.1352 [−0.1533, −0.1187] |
| LSTM − best CV baseline | −0.0547 [−0.0639, −0.0453] | −0.1384 [−0.1590, −0.1182] | −0.1353 [−0.1560, −0.1155] |
| XGBoost − Random Forest | **+0.0022 [+0.0002, +0.0045]** | −0.0027 [−0.0065, +0.0009] | −0.0002 [−0.0038, +0.0034] |
| LSTM − XGBoost | **+0.0176 [+0.0134, +0.0218]** | +0.0056 [−0.0018, +0.0129] | +0.0001 [−0.0083, +0.0077] |

Conclusions that the data supports:

1. **All three learned models beat the best baseline at every horizon**; every interval excludes zero.
2. **XGBoost and Random Forest are practically equivalent.** At 6 h and 24 h their paired intervals include zero. At 1 h Random Forest is better by 0.0022 kW [+0.0002, +0.0045]: the interval only just excludes zero and the gap is 0.7 % of the error, smaller than the shift caused by changing the XGBoost library version (§8). XGBoost is the one deployed in the application because it supports exact TreeSHAP and handles missing inputs natively, not because it is more accurate.
3. **At 1 h the LSTM is worse than XGBoost** by about 0.018 kW (interval excludes zero). **At 6 h and 24 h the LSTM and XGBoost are statistically indistinguishable.** The deep model gives no demonstrated benefit on this dataset, in line with the tabular-data findings in [10].
4. The 168-h seasonal baseline is *not* clearly different from the 24-h one at 6 h (−0.0209 [−0.0473, +0.0062]), so the "best baseline" choice matters little there.

## 3. Seed robustness of the LSTM

| Seed | Selected epochs | MAE h = 1 | MAE h = 6 | MAE h = 24 |
|---|---|---|---|---|
| 42 (headline) | 11 | 0.3533 | 0.4383 | 0.4414 |
| 43 | 6 | 0.3623 | 0.4510 | 0.4512 |
| 44 | 8 | 0.3512 | 0.4405 | 0.4470 |

Seed-to-seed spread (≈0.01 kW) is about half the 1-h gap to XGBoost and comparable to the differences between models at 6 and 24 h, so no ranking of the LSTM against the tree models at those horizons should be read into a single seed.

## 4. Honest reading of the error level

* The MAE of 0.33–0.44 kW is **32–42 % of the mean load**. Household load is spiky (cooking, heating, appliances) and a single-meter series carries little information about what the occupants will do. R² is 0.61 at 1 h but only **about 0.40 at 6 h and 24 h**: the models explain a minority of the variance at longer horizons.
* The improvement over simple baselines is real but modest in absolute terms (≈0.08–0.14 kW MAE).
* MAPE is large (42–62 %) because hourly values near zero inflate percentage errors; it is reported for completeness, not as the headline.
* The forecast range shown in the application is an **80 % band built from the 10th and 90th percentiles of each horizon's residuals on the application's own chronological hold-out block** (`residual_q10_kw`, `residual_q90_kw`). It is an empirical, horizon-wise band, not a validated prediction interval: its coverage was not measured on the 2010 benchmark test period, and it assumes the error distribution does not change between the hold-out block and the forecast date.

## 5. Application models versus the benchmark

The numbers above are the **research benchmark** (full UCI data, tuned configurations, 2010 test period). The **application** trains its own models per dataset with a fixed XGBoost configuration, evaluates them on the last 20 % of that dataset's timeline, and refits on all data for deployment (`docs/09_backend_and_api.md` §5). On the bundled one-year sample (8,760 hourly rows, 2009) the application reported hold-out MAE of 0.392 / 0.516 / 0.513 kW at 1 / 6 / 24 h (measured in a real end-to-end run; training took 12 to 25 s on the development machine). These figures use a different period and much less history than the benchmark and **must not be compared with it**: a one-year dataset shows each calendar month only once, so yearly seasonality cannot be validated across years (the application attaches a caveat to the model only when the data spans fewer than 360 days, so this one-year sample carries no warning; treat its season-dependent forecasts with that in mind).

## 6. Figures

All in `artifacts/reports/evaluation/`: `fig_mae_by_horizon.png`, `fig_actual_vs_predicted_week.png`, `fig_error_by_hour.png`, `fig_error_by_month.png`, `fig_residuals.png`, `fig_actual_vs_predicted_scatter.png`. The web application serves the same images through the authenticated Benchmark page.

## 7. Threats to validity

* One household, one site, one test year: results do not transfer to other homes without re-evaluation.
* The 11-month test period does not include a full second winter; seasonal behaviour in the test period is inferred from earlier years.
* Hyper-parameter search was intentionally small; a larger search could change absolute numbers, though the CV differences between candidates were small.
* The clock-change check (`docs/04_eda_report.md`) found the data to be in a single local-time convention; if that is wrong for some hours, calendar features are slightly off for those hours.

## 8. Reproducibility and library versions

Every result file written by the research scripts records the interpreter and library versions that produced it
(`environment` in `cv_results.json`, `lstm_results.json`, `evaluation.json`, `shap_global.json`, `anomaly_summary.json`).
All numbers in this chapter come from one run of `scripts/reproduce_benchmark.py` under the **pinned** environment of
`requirements.txt` (Python 3.11.15, numpy 2.4.6, pandas 3.1.0, scikit-learn 1.9.1, xgboost 3.2.0, torch 2.15.0, CPU only, 2 threads).

**A correction made during final verification.** The first version of these results had been produced earlier in the
project, before the environment was pinned and recorded. Re-running the whole chain from the raw file under the pinned
environment showed:

* The naive and seasonal baselines, Random Forest (to about 10⁻¹⁵ kW) and the LSTM (all three seeds: same selected
  epochs, same validation history, same test metrics) **reproduced exactly**.
* **XGBoost did not**: its predictions depend on the XGBoost build. Test MAE moved from 0.3321 / 0.4354 / 0.4432 kW to
  0.3357 / 0.4327 / 0.4413 kW at 1 / 6 / 24 h (at most 0.0036 kW), the cross-validation chose a different configuration
  for h = 1 (300 trees, depth 4, learning rate 0.05, instead of 400 / 6 / 0.03), and the 1-hour XGBoost–Random Forest
  comparison changed from "indistinguishable" to "Random Forest marginally better". The conclusions that matter did not
  change: all learned models beat the baseline at every horizon, XGBoost and Random Forest are within 0.003 kW of each
  other, and the LSTM gives no demonstrated benefit. The documents, figures and SHAP numbers were regenerated and
  updated to the pinned-environment values; the superseded numbers remain in the Git history.
* The anomaly results (events, summary, synthetic injection check) and the recommendation example were **identical**
  after the re-run, because they do not involve XGBoost.
* The same effect shows in the application: on the bundled sample, the hold-out MAE at 1 / 6 / 24 h is
  0.3915 / 0.5157 / 0.5128 kW with xgboost 3.2.0 (pinned; identical on repeated runs and with 1 or 2 threads) and
  0.3895 / 0.5117 / 0.5171 kW with xgboost 3.4.1 (the system Python 3.13 of the build workspace).

So: results are **bit-reproducible on the same library versions** and move by up to a few thousandths of a kW when only the
XGBoost version changes. Differences of that size between models should never be read as a ranking. Reproduction from raw data took about 25
minutes on 2 CPU cores (peak memory: 600 MB for the tree benchmark, 1.1 GB for one LSTM seed; measured, see `docs/11_testing.md`).
