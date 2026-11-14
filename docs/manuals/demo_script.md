# EnergiQ AI — Demonstration script (about 12 minutes)

Use this for a viva, a lab review or a recorded demo. Every step uses a real feature of the running application with
real data; nothing is mocked. Practise once beforehand. Pre-requisites: the app is running (`installation.md`), the browser is at `http://localhost:5173` (development) or
`http://localhost:8080` (Docker), the administrator account exists (`installation.md`), and **no account exists yet** for the e-mail you will use.

**Honesty rules for the presenter.** Say "forecast", not "prediction of what will happen". Say "unusual", not "faulty".
Say "scenario", not "you will save". If asked something the application cannot answer, say so; the limitations are
listed in `docs/13_limitations.md` and being upfront about them is part of the project.

| # | Minutes | You do | You say (key points) |
|---|---|---|---|
| 1 | 0:00 | Show the login page and the architecture diagram (`docs/diagrams/system_architecture.png`) | Three layers: React interface, FastAPI service, ML engine (a plain Python library), database. Same code runs on a laptop with SQLite and in Docker/AWS with PostgreSQL. |
| 2 | 1:00 | **Create account**: enter a weak password first (e.g. `short`), show the refusal, then a valid one | Validation happens in the browser and again on the server. Passwords are Argon2id-hashed; sign-in is rate-limited. |
| 3 | 2:00 | Sign in as the administrator; **Society admin → Import bundled communities** (once), then open **Society overview** | Real hourly meters of residential buildings of public BDG2 sites, summed per hour; the community total is exactly the sum of its meters. Say plainly: "a research-based representative community, not a registered housing society." |
| 4 | 3:00 | **Consumption**: switch the resolution (hourly, daily, weekly, monthly), then *Table* | Daily and weekly rhythm is visible; gaps are shown as gaps, never filled. Every chart has a table view. |
| 5 | 4:30 | **Forecasting** (Fox): read the accuracy tiles and the model comparison | Scored once on the last six months, which the models never saw; the best baseline sits next to every figure. "Better than the baseline, but accuracy is past performance on this data." |
| 6 | 6:00 | **Live forecast**: the next 24 hours with the 80 % range; then pick an *earlier origin* | The range comes from hold-out errors; it is a rough range, not a guarantee. An earlier origin lets you compare with what actually happened. |
| 7 | 7:00 | **What drives the forecast** (SHAP), global and for this forecast | Exact TreeSHAP: contributions add up to the forecast. "It shows what the model used, not what causes consumption." |
| 8 | 8:00 | **Alerts**: click a marker, read the explanation, **Acknowledge** one | Baseline uses only past weeks (causal). "There are no fault labels in this data, so I do **not** claim an accuracy for detection. Term breaks and holidays raise alerts too." |
| 9 | 9:00 | **Buildings**, then **Cost and peaks** and **Recommendations** | Compare buildings by energy, energy per m² and peak. The demo tariff is a labelled placeholder; recommendations carry their evidence and make no unverified savings claim. |
| 10 | 10:15 | **Reports → Create report** (monthly PDF) and **Download** | The PDF is generated on the server from the same numbers as the screens. |
| 11 | 11:00 | **Data sources**; then `docs/society/02_data_sources.md` | Publisher, licence (CC BY-SA 4.0), download date, cleaning rules and the five sites that failed the rule. "Cite Miller et al. (2020)." |
| 12 | 11:45 | Show `docs/15_verification_matrix.md` | What was tested and how; what was **not** (Docker images, cloud deployment, Windows). |

## Likely questions and straight answers

* *Why XGBoost and not an LSTM?* In the household benchmark of this project the LSTM was statistically indistinguishable at 6 and 24 h, worse at 1 h and slower, and XGBoost
  supports exact SHAP (`docs/06_model_evaluation.md` §2). No LSTM was trained for the societies (`docs/society/04_models_and_evaluation.md`).
* *Is the alert detector accurate?* Unknown: no labels. The household detector's synthetic injection check shows it finds large spikes and
  flat runs well and misses moderate drops (`docs/08_anomaly_detection.md` §5).
* *Is it deployed on AWS?* No. The CloudFormation templates are written and lint-clean; nothing was deployed and no paid
  resources were created. The deployment ladder in `docs/12_deployment.md` says what level each piece reached.
* *Does it work on my own data?* An administrator uploads the society's meter CSV on **Society admin**; it goes through the same cleaning, evaluation and training
  (`docs/society/06_admin_and_upload_guide.md`). Accuracy for another society must be re-evaluated; the bundled figures are for residence halls.
* *How do you know there is no leakage?* Chronological splits only; unit tests that change future values and check the
  forecast does not move; the test period was scored once after every choice was fixed.
* *What if the forecast is wrong?* Expected: the Forecasting page shows the real error (MAE, MAPE, R²) per horizon and compares it with baselines. The tool reports its own
  error openly.

## Backup plan

If the import is slow on the demo machine, run it once before the session (step 3). All seven communities ship with their deployed forecasting models, so the live forecast works for each.
If the network or browser fails, the screenshots in `docs/screenshots/` follow the same order.
