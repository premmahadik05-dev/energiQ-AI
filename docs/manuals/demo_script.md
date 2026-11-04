# EnergiQ AI — Demonstration script (about 12 minutes)

Use this for a viva, a lab review or a recorded demo. Every step uses a real feature of the running application with
real data; nothing is mocked. Practise once beforehand so that the one slow step (training, 15–30 s) does not surprise
you. Pre-requisites: the app is running (`installation.md`), the browser is at `http://localhost:5173` (development) or
`http://localhost:8080` (Docker), and **no account exists yet** for the e-mail you will use.

**Honesty rules for the presenter.** Say "forecast", not "prediction of what will happen". Say "unusual", not "faulty".
Say "scenario", not "you will save". If asked something the application cannot answer, say so; the limitations are
listed in `docs/13_limitations.md` and being upfront about them is part of the project.

| # | Minutes | You do | You say (key points) |
|---|---|---|---|
| 1 | 0:00 | Show the login page and the architecture diagram (`docs/diagrams/system_architecture.png`) | Three layers: React interface, FastAPI service, ML engine (a plain Python library), database. Same code runs on a laptop with SQLite and in Docker/AWS with PostgreSQL. |
| 2 | 1:00 | **Create account**: enter a weak password first (e.g. `short`), show the refusal, then a valid one | Validation happens in the browser and again on the server. Passwords are Argon2id-hashed; sign-in is rate-limited. |
| 3 | 2:00 | **Datasets → Load bundled sample dataset** | Real UCI household readings for 2009. Open the **Data quality report**: score, gaps, flat runs. "Nothing is imputed; missing hours stay missing." |
| 4 | 3:00 | **Readings explorer**: drag to zoom, switch to *Table* | Daily and weekly rhythm is visible; gaps are shown as gaps. Every chart has a table view. |
| 5 | 4:00 | **Models → Train a new model** (watch the progress bar) | Training fits on the first 80 % and tests on the last 20 % in time order — never shuffled, so the future cannot leak into the past. Then it refits on everything. |
| 6 | 5:00 | Read the **Hold-out accuracy** table | Model error versus the best simple baseline at 1, 6, 24 h. "Better than the baseline, but not magic: at 6 and 24 h it explains well under half of the variance." Accuracy is past performance on this dataset. |
| 7 | 6:00 | **Forecast → Create forecast**; then pick an *earlier origin* and create a second one | The band is a rough range from hold-out errors, not a guarantee. The look-back forecast lets you compare with what actually happened. **Export CSV**. |
| 8 | 7:30 | **Anomalies → Run detection** (Medium); open the Timeline and one event | Baseline uses only past weeks (causal); band is hour-of-day specific. "There are no fault labels in this dataset, so I do **not** claim an accuracy for detection. About 2 % of hours are flagged by design." Acknowledge one event. |
| 9 | 9:00 | **Explainability → Explain this forecast** | Exact TreeSHAP: contributions add up to the forecast. At 1 h the latest reading dominates; at 24 h the daily rhythm does. "It shows what the model used, not what causes consumption." |
| 10 | 10:00 | **Optimisation → Cheapest-window scheduler** (e.g. 2 h, 1.5 kW) and **Recommendations** | The DEMO tariff is illustrative and labelled so; with a real tariff the numbers become meaningful. Savings are scenarios under stated assumptions. |
| 11 | 11:00 | **Benchmark** page; then `docs/06_model_evaluation.md` | Offline research on the full 4-year dataset: baselines, Random Forest, XGBoost, LSTM, bootstrap intervals. "The deep model gave no demonstrated benefit here; the simpler model is the one deployed." |
| 12 | 11:45 | Show `docs/15_verification_matrix.md` | What was tested and how; what was **not** (Docker images, cloud deployment, Windows). |

## Likely questions and straight answers

* *Why XGBoost and not the LSTM?* Statistically indistinguishable at 6 and 24 h, worse at 1 h, slower, and XGBoost
  supports exact SHAP. (`docs/06_model_evaluation.md` §2.)
* *Is the anomaly detector accurate?* Unknown: no labels. A synthetic injection check shows it finds large spikes and
  flat runs well and misses moderate drops (`docs/08_anomaly_detection.md` §5).
* *Is it deployed on AWS?* No. The CloudFormation templates are written and lint-clean; nothing was deployed and no paid
  resources were created. The deployment ladder in `docs/12_deployment.md` says what level each piece reached.
* *Does it work on my own data?* Upload a CSV; the pipeline is the same. Results for another household must be
  re-evaluated; the benchmark is for one household.
* *How do you know there is no leakage?* Chronological splits only; unit tests that change future values and check the
  forecast does not move; the test period was scored once after every choice was fixed.
* *What if the forecast is wrong?* Expected: MAE is 32–42 % of the mean load in the benchmark. The tool reports its own
  error openly and compares it with baselines.

## Backup plan

If training is slow on the demo machine, train once before the session and start from step 6 with the existing model.
If the network or browser fails, the screenshots in `docs/screenshots/` follow the same order.
