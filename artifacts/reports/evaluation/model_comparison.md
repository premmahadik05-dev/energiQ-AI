# Model comparison (test period, scored once)

Test period: 2010-01-01 to 2010-11-26. All models are scored on exactly the same rows per horizon. Units: kW (hourly mean Global_active_power). Lower is better for MAE, RMSE, MAPE and sMAPE; higher for R2.

## 1 h ahead  (n = 7233 hours scored; 686 of 7919 test hours excluded for a missing target or missing inputs)

| Model | MAE | RMSE | MAPE % | sMAPE % | R2 |
|---|---|---|---|---|---|
| Naive (last hour) (best baseline by CV) | 0.4080 | 0.6190 | 45.3 | 37.9 | 0.368 |
| Seasonal naive (24 h) | 0.5558 | 0.8210 | 68.7 | 49.8 | -0.112 |
| Seasonal naive (168 h) | 0.5767 | 0.8323 | 74.9 | 52.8 | -0.143 |
| Random Forest | 0.3334 | 0.4846 | 41.9 | 33.1 | 0.613 |
| XGBoost | 0.3357 | 0.4858 | 41.9 | 33.6 | 0.611 |
| LSTM | 0.3533 | 0.5053 | 43.3 | 36.2 | 0.579 |

Mean actual load in these rows: 1.055 kW. MAPE excludes hours with actual < 0.05 kW (0 hours).

Paired day-block bootstrap, MAE(model) - MAE(Naive (last hour)), 95% CI (negative = model better):

- Seasonal naive (24 h): +0.1478 kW  [+0.1258, +0.1722]  (312 days)
- Seasonal naive (168 h): +0.1687 kW  [+0.1461, +0.1929]  (312 days)
- Random Forest: -0.0746 kW  [-0.0838, -0.0650]  (312 days)
- XGBoost: -0.0723 kW  [-0.0820, -0.0626]  (312 days)
- LSTM: -0.0547 kW  [-0.0639, -0.0453]  (312 days)
- XGBoost vs Random Forest: +0.0022 kW  [+0.0002, +0.0045]
- LSTM vs XGBoost: +0.0176 kW  [+0.0134, +0.0218]

## 6 h ahead  (n = 7233 hours scored; 687 of 7920 test hours excluded for a missing target or missing inputs)

| Model | MAE | RMSE | MAPE % | sMAPE % | R2 |
|---|---|---|---|---|---|
| Naive (last hour) | 0.8541 | 1.1151 | 124.2 | 76.4 | -1.051 |
| Seasonal naive (24 h) | 0.5558 | 0.8210 | 68.7 | 49.8 | -0.112 |
| Seasonal naive (168 h) (best baseline by CV) | 0.5767 | 0.8323 | 74.9 | 52.8 | -0.143 |
| Random Forest | 0.4354 | 0.5964 | 60.2 | 43.5 | 0.413 |
| XGBoost | 0.4327 | 0.5970 | 59.0 | 42.8 | 0.412 |
| LSTM | 0.4383 | 0.6096 | 56.9 | 43.4 | 0.387 |

Mean actual load in these rows: 1.055 kW. MAPE excludes hours with actual < 0.05 kW (0 hours).

Paired day-block bootstrap, MAE(model) - MAE(Seasonal naive (168 h)), 95% CI (negative = model better):

- Naive (last hour): +0.2774 kW  [+0.2397, +0.3145]  (312 days)
- Seasonal naive (24 h): -0.0209 kW  [-0.0473, +0.0062]  (312 days)
- Random Forest: -0.1413 kW  [-0.1598, -0.1235]  (312 days)
- XGBoost: -0.1440 kW  [-0.1627, -0.1252]  (312 days)
- LSTM: -0.1384 kW  [-0.1590, -0.1182]  (312 days)

Same comparison against the strongest baseline *in hindsight* on the test rows (Seasonal naive (24 h)), a stricter reference than the CV-chosen one:

- Random Forest: -0.1204 kW  [-0.1402, -0.1014]
- XGBoost: -0.1231 kW  [-0.1443, -0.1032]
- LSTM: -0.1175 kW  [-0.1385, -0.0975]

Pairwise comparisons between learned models:

- XGBoost vs Random Forest: -0.0027 kW  [-0.0065, +0.0009]
- LSTM vs XGBoost: +0.0056 kW  [-0.0018, +0.0129]

## 24 h ahead  (n = 7233 hours scored; 687 of 7920 test hours excluded for a missing target or missing inputs)

| Model | MAE | RMSE | MAPE % | sMAPE % | R2 |
|---|---|---|---|---|---|
| Naive (last hour) | 0.5558 | 0.8210 | 68.7 | 49.8 | -0.112 |
| Seasonal naive (24 h) | 0.5558 | 0.8210 | 68.7 | 49.8 | -0.112 |
| Seasonal naive (168 h) (best baseline by CV) | 0.5767 | 0.8323 | 74.9 | 52.8 | -0.143 |
| Random Forest | 0.4415 | 0.6034 | 62.1 | 44.1 | 0.400 |
| XGBoost | 0.4413 | 0.6043 | 61.8 | 43.9 | 0.398 |
| LSTM | 0.4414 | 0.6258 | 54.4 | 43.8 | 0.354 |

Mean actual load in these rows: 1.055 kW. MAPE excludes hours with actual < 0.05 kW (0 hours).

Paired day-block bootstrap, MAE(model) - MAE(Seasonal naive (168 h)), 95% CI (negative = model better):

- Naive (last hour): -0.0209 kW  [-0.0474, +0.0045]  (312 days)
- Seasonal naive (24 h): -0.0209 kW  [-0.0474, +0.0045]  (312 days)
- Random Forest: -0.1352 kW  [-0.1533, -0.1187]  (312 days)
- XGBoost: -0.1354 kW  [-0.1538, -0.1184]  (312 days)
- LSTM: -0.1353 kW  [-0.1560, -0.1155]  (312 days)

Same comparison against the strongest baseline *in hindsight* on the test rows (Naive (last hour)), a stricter reference than the CV-chosen one:

- Random Forest: -0.1143 kW  [-0.1342, -0.0952]
- XGBoost: -0.1145 kW  [-0.1342, -0.0955]
- LSTM: -0.1144 kW  [-0.1348, -0.0950]

Pairwise comparisons between learned models:

- XGBoost vs Random Forest: -0.0002 kW  [-0.0038, +0.0034]
- LSTM vs XGBoost: +0.0001 kW  [-0.0083, +0.0077]

## LSTM seed robustness (test MAE, kW)

Headline run = seed 42, fixed before looking at test scores. Other seeds are shown for stability only.

| Seed | best epochs | h=1 | h=6 | h=24 |
|---|---|---|---|---|
| 42 | 11 | 0.3533 | 0.4383 | 0.4414 |
| 43 | 6 | 0.3623 | 0.4510 | 0.4512 |
| 44 | 8 | 0.3512 | 0.4405 | 0.4470 |

## Figures

- `fig_mae_by_horizon.png`
- `fig_actual_vs_predicted_week.png`
- `fig_error_by_hour.png`
- `fig_error_by_month.png`
- `fig_residuals.png`
- `fig_actual_vs_predicted_scatter.png`
