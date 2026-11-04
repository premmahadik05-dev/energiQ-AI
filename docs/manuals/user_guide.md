# EnergiQ AI — User guide

This guide walks through the web application as a person who wants to understand and plan the electricity use of one
building or household. Every screen named here exists in the application; the pictures are in `docs/screenshots/`
(taken against the real backend with the bundled sample data). Setup instructions are in `installation.md`.

**What the application is, and is not.** It forecasts the next 1–24 hours of load from the history you give it,
marks hours that look unusual compared with that history, shows which inputs a forecast relied on, and prices your
use under a tariff you enter. It is a decision aid built on statistics. It does not know *why* consumption changed,
it cannot confirm a fault, and its savings figures are scenarios, never promises.

## 1. Signing in and roles

* **Create account** (`/register`): e-mail and a password of 10–128 characters with letters and digits. Passwords are
  stored only as Argon2id hashes. New accounts are **analysts**.
* **Sign in** (`/login`). After too many failed attempts from one address the server slows you down for a minute; wait
  and try again.
* Roles: **viewer** (read only), **analyst** (can upload, train, forecast, detect, create tariffs), **admin** (also
  sees the *Administration* page). Buttons you may not use are hidden for viewers; the server enforces the rules
  regardless of what the page shows.
* Everything you create belongs to your account. Other users never see your datasets, models or forecasts.

## 2. Getting data in (Datasets)

Two ways, both on **Datasets**:

1. **Load bundled sample dataset** — one year (2009) of hourly readings from the public UCI household dataset. It is the
   quickest way to try every feature. It is real data, labelled as a sample.
2. **Upload a CSV** — drag a file onto the box or use *Choose file* (`.csv`, `.txt`, `.tsv`; the size limit is shown on
   the page). Then describe it:
   * *Dataset name* and *Value column* (the header of the consumption column);
   * *Unit of the values*: kW or W or MW (power), or kWh/Wh/MWh (energy per reading interval; the interval must be
     detectable, and the report states the assumption);
   * *Timestamp layout*: one column, or separate date and time columns; an optional *Timestamp format*
     (e.g. `%d/%m/%Y %H:%M:%S`, leave empty to auto-detect), and *Day comes first in dates* for `31/12/2009` style;
   * *Time convention*: how to read the clock (**Logger clock (as recorded)** keeps the timestamps exactly as in the
     file; nothing is converted).
   Press **Upload and process**. A background job reads the file, rejects what it cannot understand (with a reason)
   and aggregates to **hourly means**. An hour counts only if enough of its readings are valid; the rest stay
   missing — **nothing is filled in or guessed**.

When processing is done you land on the dataset's page:

* **Data quality report** — a 0–100 score, completeness, duplicates, gaps and flat runs. Read the warnings: a long flat
  run is often a stuck meter or a placeholder value.
* **Data profile** — daily, weekly and yearly patterns computed from the valid hours.
* **Readings explorer** — choose a range, drag across the chart to zoom. Gaps are shown as gaps. *Table view* lists the
  numbers.
* **Append newer data** — upload another file with the same columns. Hours for which the new file has a value replace
  the stored value; hours the new file leaves out or leaves blank keep what was stored.
* **Download HTML report** — a printable summary of the dataset, its quality, models and latest results.
* **Use as active dataset** — every other page works on the *active* dataset, also shown in the selector at the
  top of the page. **Delete** removes the dataset together with its models, forecasts and anomaly events (you are asked
  to confirm).

## 3. Training a model (Models)

**Train a new model** starts a background job (tens of seconds for a year of hourly data). It does two things:

1. **Evaluates honestly.** It fits on the first 80 % of the timeline only and scores on the last 20 % (the *hold-out*),
   for 1, 6 and 24 hours ahead, next to simple baselines (last value, same hour yesterday, same hour last week).
2. **Refits for use.** It then refits 24 models (one per hour ahead) on *all* the data, so forecasts use the latest
   information. The accuracy numbers therefore describe the method, not the very last refit.

Read the **Hold-out accuracy** table: *Model MAE (kW)* is the average absolute miss; *Best baseline* is the simplest
method that did best; *Improvement vs best baseline* says how much lower the error is. A model that is not clearly better
than the baseline is not worth trusting; the table shows that plainly. A caveat is attached to the model when the data covers less
than a year, because seasons cannot be validated then. Accuracy is past performance on this dataset, not a guarantee.

Each training run creates a new **model version**. You can *activate* an older one, or delete one. **Monitoring**
(pick a recent window: 7 to 180 days) compares recent inputs with the training data (drift) and, where actual readings
have arrived after past forecasts, shows the real errors.

## 4. Forecasting (Forecast)

Choose a *Model version* (default: the active one) and, optionally, a *Forecast origin*. Empty means "right after the
last reading". An earlier origin is useful for **looking back**: you see what the model would have predicted and the
actual readings that followed. Press **Create forecast**.

You get the forecast **peak** (size and time), a chart of recent actual load, the forecast curve and a shaded band, and
a table view. **The band** is built from the model's hold-out errors (10th to 90th percentile). It is a rough range,
not a guarantee. **Export CSV** gives origin, target time, horizon, forecast and band. Forecasts are saved; the 20 most
recent are listed on the page.

## 5. Anomalies

**Run detection** (choose *Sensitivity*: Low, Medium, High) replaces the previous run for the active dataset. For every
hour the detector builds a *causal* expectation (the median of the same hour of the week over the previous weeks —
it uses only earlier data) and flags hours that are far outside the usual band for that hour of day, runs of identical
values (stuck meter?), and unusual patterns an Isolation Forest finds. Hours near each other become one **event** with
a severity (low, medium, high), the observed and typical values, and a plain-language explanation.

* The summary tiles show the number of events, severities, and how many are still *open*.
* **Timeline** marks each event's peak hour on the load curve; **Events** lists them (filter by severity, status and
  dates, sort by time or severity). **Acknowledge** marks one as reviewed; **Unacknowledge** reopens it.
* Detection needs several weeks of valid history; otherwise the page says so.

**How to read an event.** "Unusual for this household at this time" is all it means. The dataset has no fault labels,
so the detector's accuracy is **unknown**; about 2 % of hours are flagged at Medium by design. Treat events as leads to
look at (was someone away? did a device break?), not as confirmed faults.

## 6. Explainability

Pick a *Model version* and a *Horizon*. **Global importance** shows which input groups the model relies on across the
hold-out period (recent consumption, same time yesterday/last week, recent averages, time of day, day of week,
season). For **Local explanation**, enter a *Forecast origin* (optional) and press **Explain this forecast**: you get
the base value, how many kW each group added or removed, and a one-sentence summary. The values are exact TreeSHAP
numbers from the XGBoost models, so they add up to the forecast. They describe what the *model* used, not what *causes*
consumption.

## 7. Optimisation

Four tabs:

* **Tariffs** — a tariff has 24 weekday and 24 weekend prices per kWh and an optional daily fixed charge. *Fill every
  hour with* helps with flat tariffs. The built-in **DEMO tariff** is labelled as illustrative everywhere: it is **not
  a real utility price**. Enter your own tariff before drawing any cost conclusion.
* **Cost analysis** — total cost, energy, energy charges and average price for a period, under a chosen tariff. Missing
  hours are not costed; the page shows how many valid hours the figure covers.
* **Recommendations** — **Generate recommendations** runs transparent rules: review high-severity anomalies, check
  always-on load, move flexible use out of the dearest hours, note the forecast peak, warn about data gaps. Each shows
  its evidence, and where a saving is shown it is a **scenario** ("if always-on load fell by 10 %") under a stated
  assumption, not a forecast of what you will save. Each run is saved.
* **Cheapest-window scheduler** — enter *Run time (hours)*, *Power draw (kW)* and optionally *Start no earlier than*, then
  **Find the cheapest window**. It tests every start hour in the next 24 hours and shows the best, the cost of starting
  immediately, and the saving. It assumes you can actually move the device.

## 8. Benchmark, jobs, notifications, administration

* **Benchmark** — the offline research results on the full UCI dataset (all forecasting methods, protocol, anomaly
  benchmark, feature importance). These describe the research data, *not your own dataset*.
* **Jobs** (clock icon in the top bar, and the *Jobs* page) — uploads, training and detection run in the background. The
  50 most recent are listed with progress and any error message.
* **Notifications** (bell icon) — messages such as "Model training finished." or "Detection finished."
* **Administration** (admins only) — *Users* (change roles, Deactivate/Reactivate), *Audit log* (who did what, with filters),
  *System* (record counts, jobs by status, API traffic since the server started).
* The sun icon switches light and dark themes; the page also follows your system setting. The interface works with a
  keyboard, shows focus clearly, and every chart has a table view.

## 9. When something goes wrong

| What you see | Likely cause and fix |
|---|---|
| The register form refuses your password | It needs 10–128 characters with letters and digits; nothing is sent until it passes. |
| Upload rejected with a reason | Wrong column name, unparseable timestamps, wrong unit, or a file that is not text. Fix the setting named in the message and retry. |
| Dataset shows a low quality score | Look at the quality report: large gaps and flat runs are the usual cause. Models still train but forecasts near gaps are less reliable. |
| "Train a model for this dataset first." | Forecast and Explainability need a trained model: go to **Models**. |
| Detection says it needs more history | At least about 12 weeks of valid hours are required. |
| A job failed | Open **Jobs**; the message explains in plain words. Technical detail is kept in the server log, not shown in the browser. |
| "Too many requests, slow down" | Wait a minute; rate limits protect the sign-in, registration and upload endpoints. |
| A page shows "not found" or "access denied" | The item belongs to another account, was deleted, or your role cannot see it. |

## 10. Limits to keep in mind

* One dataset is one meter. Results for other households must be re-evaluated; they are not transferred.
* Forecast error is large relative to the load at longer horizons (see the Models page for your own numbers and
  `docs/06_model_evaluation.md` for the benchmark: R² is about 0.4 at 6 and 24 hours).
* No weather, holiday or occupancy information is used; sudden behaviour changes cannot be predicted.
* Costs depend entirely on the tariff you enter.
