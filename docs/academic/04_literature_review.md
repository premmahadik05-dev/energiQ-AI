# Literature review

Numbers in square brackets refer to `docs/references.md`, where each source was checked against a public record.
The review is deliberately short and covers only what the project relies on. The project is an engineering integration of established methods; it does **not** claim a new algorithm.

## 1. Load forecasting

Electric load forecasting is a long-established field. Hong and Fan [13] give a tutorial review of probabilistic load forecasting and stress that point forecasts alone hide uncertainty and that evaluation must match the use of the forecast. Hyndman and Athanasopoulos [8] provide the standard practical reference for forecasting methods and for benchmarking against simple methods such as the naive and seasonal-naive forecast, which this project adopts as baselines. Hyndman and Koehler [7] review accuracy measures and warn that percentage errors behave badly near zero; this is why the project reports mean absolute error in kW as the headline and lists MAPE only for completeness. (Their scaled measure, MASE, is a reasonable alternative that this project does not report.)

Individual-household load is harder to forecast than aggregated load because it is dominated by a few occupants' routines and appliances. Kong et al. [12] proposed an LSTM recurrent network [3] for short-term forecasting of individual households and reported good results on their data, which motivated including an LSTM here.

## 2. Models for tabular time-series features

Random forests [1] and gradient-boosted trees as implemented in XGBoost [2] are standard supervised learners for tabular data. Grinsztajn et al. [10] report that tree-based models remain very competitive with, and often better than, deep networks on typical medium-sized tabular data sets. This is consistent with the project's finding that the LSTM did not outperform the tree models. The project frames forecasting as supervised learning on lagged, rolling and calendar features and trains one model per horizon (direct strategy), implemented with scikit-learn [15] and XGBoost [2]; the LSTM was written with PyTorch [16].

## 3. Evaluating time-series models

Random shuffling lets a model train on the future of the period it is tested on. Bergmeir and Benítez [9] study how cross-validation can be applied to time-series predictors and compare it with out-of-sample evaluation, and Cerqueira et al. [11] compare performance-estimation methods empirically across many series, reporting that the best choice depends on the properties of the series (notably stationarity) and that methods which respect temporal order are the safer choice when the series changes over time. The project therefore uses expanding-window cross-validation for model selection and a final, chronologically later test period scored once, and it reports uncertainty with a paired day-block bootstrap so that autocorrelation within a day is respected.

## 4. Anomaly detection

Chandola et al. [14] survey anomaly detection and distinguish point, contextual and collective anomalies. A household reading is typically *contextual*: 2 kW may be normal at 19:00 and unusual at 03:00. The project's detector therefore measures deviation from a causal, hour-of-week baseline and compares it with the empirical residual distribution for that hour of day. Isolation Forest [4], which isolates unusual points by random partitioning and needs no labels, is used as corroborating evidence. The survey also underlines a difficulty this project meets directly: without labelled anomalies, detection quality cannot be measured on real data, so only the alert rate and a synthetic injection test are reported.

## 5. Explainability

SHAP [5] attributes a prediction to features using Shapley values from cooperative game theory, and TreeSHAP [6] computes these exactly and efficiently for tree ensembles. This is why the explained model in the application is XGBoost and why the project can verify additivity numerically. SHAP explains the model, not the household: attribution is not causation.

## 6. Data

The UCI "Individual household electric power consumption" data [17] contains about four years of one-minute readings from one house near Paris, with missing values marked in the file. It is widely used, public, and licensed CC BY 4.0, and it is the only data used for the benchmark. Its limitations (one household, one location) are discussed in `docs/13_limitations.md`.

## 7. Gap addressed by this project

The cited work provides methods and evaluation principles, but a user wanting to apply them to their own meter data must assemble ingestion, quality control, leak-free evaluation, explanation, cost translation, security, operations and deployment themselves. EnergiQ AI is an attempt to integrate those pieces transparently and to be explicit about what each piece can and cannot claim. Its contribution is engineering integration and honest evaluation on one public data set, not a new forecasting method.
