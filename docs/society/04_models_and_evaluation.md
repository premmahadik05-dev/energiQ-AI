# 4. Models, evaluation and the other analytics

All numbers quoted here are produced by code and stored in `artifacts/society/<key>/`. The complete tables are in
[`RESULTS.md`](RESULTS.md) (generated). This document explains the protocol and how to read them.

## Target and horizons

The target is the **total society demand** (hourly mean kW). One model is trained **per horizon** (direct forecasting):
**1, 6, 12, 24 hours and 7 days (168 h)**. For the live forecast, all 24 hourly horizons plus 168 h are deployed; horizons
that were not evaluated (2–5, 7–11, 13–23 h) reuse the configuration of the nearest evaluated horizon, and the application
says that accuracy was measured only at the evaluated horizons.

## Models

| Family | Notes |
|---|---|
| Naive (last value) | Persistence |
| Seasonal naive 24 h / 168 h / 336 h | Same hour yesterday, last week, two weeks ago (336 h only at 7 days) |
| Linear regression | Ordinary least squares on the same features (nothing to tune) |
| Random Forest | Two lean configurations, 100 trees (small enough to ship: 1–3 MB per model) |
| XGBoost | Three configurations (depth 3 / 4 / 6, learning rate 0.03–0.08, 250–400 trees) |
| XGBoost + observed weather | Same, plus air temperature, dew temperature, wind speed at the origin and their 24 h mean. These are *observed*, not forecast, values, so this family shows what weather could add at best |

An LSTM was **not** trained for the societies. The household benchmark of this project (`docs/06_model_evaluation.md`) already
compared an LSTM with XGBoost and found it no better at 6 and 24 h and worse at 1 h, and the brief asks for an LSTM only "if
justified". `scripts/run_lstm.py` exists for the household data and was not rerun for societies.

## Features

Built only from data up to the forecast origin: lags of 0, 1, 2, 3, 5, 11, 23 and 47 hours, the same hour 24 h and 168 h earlier
(168 h and 336 h for the 7-day horizon), rolling mean and standard deviation over 24 h and 168 h, and calendar features (hour
and day of week with sine/cosine encodings, weekend flag, month). Public holidays and occupancy are not used because the data
carry neither.

## Splits and selection

* **Test period**: the last six months of the data (2017-07-01 to 2017-12-31 for the bundled communities), scored **once**.
* **Cross-validation**: four expanding-window blocks of three months (2016-07 .. 2017-06). For each block the training rows are those whose *target* time is before the block.
* **Selection**: per horizon, the configuration with the lowest mean MAE over the four blocks, *baselines included*. When a baseline wins, the application deploys that baseline instead of a worse learned model and says so.
* **Uploaded societies** use the same logic with a plan derived from their own data end (test = last 6 months, or 3 if the history is short; up to four 3-month CV blocks; at least 90 days of training before the first block). They need about nine months of valid hours.
* Every model, baselines included, is scored on exactly the same rows.

## Metrics

MAE and RMSE in kW, MAPE in % (hours with an actual demand below 1 kW are excluded and counted, so a near-zero hour cannot
explode the percentage), R², and the coverage of the 80 % band. The **paired day-block bootstrap** gives a 95 % interval for the difference in
mean absolute error between the selected model and the best baseline. Peak evaluation (below) is reported separately.

## The forecast range

The range around each prediction is `prediction + q10 .. prediction + q90` of the **out-of-fold cross-validation residuals** (an
empirical 80 % band, linearly interpolated between evaluated horizons). It is not a guarantee: on the test period its
coverage differs from 80 % (it is reported in `evaluation.json`; for Fox at 24 h it is 85.9 % for the Random Forest and 93.1 % for XGBoost).

## What the results say (read RESULTS.md for the numbers)

1. **Short horizons: learned models clearly beat the baselines.** At 1 h the selected model lowers test MAE by roughly a fifth to
   nearly a half (17–44 % across the seven communities), and the paired bootstrap interval excludes zero in every community.
2. **24 h is mixed.** In four communities the selected model beats the best baseline by 17–21 %; in Eagle and Rat cross-validation
   chose a *baseline* and the application serves it; in Peacock cross-validation chose the Random Forest but on the test period it is
   about 6.5 % *worse* than the naive baseline (interval above zero). That is a real result, reported as it is.
3. **7 days: "same hour last week" is usually best.** It was chosen in Bull, Eagle, Fox, Hog and Peacock; a learned model won only in
   Rat, Robin (Random Forest, 13 % gain). A 7-day forecast from a hand-sized feature set is a weak spot of this study.
4. **Weather helped some horizons and not others.** The weather family won cross-validation at some horizons (for example Bull 6 h, Rat 6 h,
   Robin 6 and 12 h) but it is not better in general (Fox 24 h: 41.7 kW versus 38.5 kW without it). It also uses *observed* weather, which a real
   deployment would not have.
5. **Communities differ, and the metrics disagree.** At 24 h, R² is highest for Fox (0.93), Robin (0.92) and Bull (0.91) and lowest for Eagle (0.79), Rat (0.82) and Peacock (0.84). MAPE ranks them differently
   (Robin has R² 0.92 but MAPE 16 %), so read MAE, R² and MAPE together rather than one number.

The numbers refer to student residence halls over two years. They should not be read as an expected accuracy for a family housing society.

## Peak demand

For each held-out test day with at least 22 scored hours, the day's highest forecast hour (forecast issued 24 h ahead) is compared with
the day's highest measured hour: peak MAE in kW and the share of days on which the forecast peak is in the right hour, within 1 h and within 2 h.
Table: RESULTS §4. In Fox the model's peak MAE is 45.3 kW against 57.6 kW for the baseline (21 % lower) with the exact peak hour right
on 27 % of days (30 % for the baseline), and within two hours on 89 %. The model finds the *level* of the peak better than the rule does, but not the exact hour.

## Explainability

SHAP values (exact TreeSHAP for XGBoost and Random Forest; closed-form contributions for the linear model) explain the best learned model
at each horizon. *Global*: mean |SHAP| per feature and per group on the test rows (`shap_global.json`, shown on the Forecasting page).
*Local*: `POST /societies/{id}/explain/local` explains the live forecast at an origin; the contributions add up to the prediction and the code checks it.
At 24 h in Fox, recent consumption and the same time yesterday/last week carry about 88 % of the total. SHAP describes what the model uses, not physical causes.

## Anomaly detection

The household detector is reused with thresholds scaled to the community's size (`society_config` in `anomalies.json`): an
expected value from the same hour of week over the previous 4 weeks, a robust scale from 26 weeks, an alert when the deviation passes the 99.5th percentile
of past deviations (and a minimum absolute size); a run of 4 or more identical hours is flagged as flat; an Isolation Forest can add an hour only where the deviation is also at least
2.5 scale units; flagged hours separated by a gap of at most 1 h are merged into events. Each event has a timestamp,
severity (low / medium / high), scope (whole society or one building), the size relative to normal, a plain-language explanation and the buildings contributing most.
For Fox the whole society has 169 events (127 low, 23 medium, 19 high) flagging 4.1 % of valid hours, plus per-building events.
There are **no ground-truth fault labels**, so no precision or recall is claimed. Alerts cluster at term transitions (holidays, when a residence hall empties), which
the detector reads as unusual; an operator should treat them as prompts to look, not confirmed faults.

## Cost estimate

Cost = hourly energy × a **time-of-use tariff chosen by the user** (weekday and weekend rate per hour, daily fixed charge). The shipped
default is a **demo tariff with placeholder rates** (EUR 0.12 / 0.20 / 0.30 per kWh); it is labelled as such everywhere and is
never presented as a bill. The forecast cost applies the same tariff to the predicted energy.

## Recommendations

Rules applied to the most recent 90 days of valid data (`ml_engine/society/recommendations.py`), each returned with its evidence and caveats:

* **Load shifting out of the dearest tariff hours**: only if the tariff has price differences *and* a large, concentrated share of the energy falls in the dearest hours. It carries a stated what-if (a fixed share of that energy moved to the cheapest hours) labelled *an estimate, not a measured saving*, because the meter data does not show which loads are flexible.
* **High always-on base load** (minimum demand relative to the average).
* **Typical peak hour** of the day.
* **Buildings with energy per square metre far above the community median** (one entry per building).
* **High demand expected in the next 24 h** when the live forecast peak is above the recent 90th percentile.
* **High-severity alerts in the last 30 days** (to be inspected, not confirmed faults; term breaks are flagged too).
* **Data gaps** when fewer than 90 % of the last 7 days have a valid total.

No saving is claimed beyond that labelled scenario.
