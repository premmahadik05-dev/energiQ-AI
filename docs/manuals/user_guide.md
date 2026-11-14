# EnergiQ AI — User guide

This guide walks through the web application as a person who wants to understand and plan the electricity use of a
residential community: several buildings whose meters are summed per hour. Every screen named here exists in the
application; the pictures are in `docs/screenshots/` (taken against the real backend). Setup instructions are in `installation.md`.

**What the application is, and is not.** It shows how much electricity the community uses, forecasts the next hours and days
from its history with honest out-of-sample accuracy, marks hours that look unusual, compares the buildings, estimates cost
under a tariff, gives evidence-based recommendations and produces reports. It is a decision aid built on statistics. It does not know *why*
consumption changed, it cannot confirm a fault, and cost figures are estimates, never bills.

**What the data are.** The bundled communities are *research-based representative communities*: the real hourly meters of the
residential-use buildings (mostly student residence halls) of seven public Building Data Genome Project 2 sites, summed per hour.
They are not registered housing societies, and every society page says so. See *Data sources* in the application and
`docs/society/02_data_sources.md`.

## 1. Signing in and roles

* **Create account** (`/register`): full name (optional), e-mail address, and a password of 10–128 characters with letters and
  digits, typed twice. A checklist under the password ticks off the rules as you type, and the eye button shows or hides what you typed.
  Passwords are stored only as Argon2id hashes. New accounts are **analysts**; the first screen after creating one says so.
* **Sign in** (`/login`). After too many failed attempts from one address the server slows you down for a minute; wait
  and try again. "Remember my e-mail on this device" stores only the e-mail address in this browser (never the password or the
  session) and fills it in next time; untick it and sign in once to forget it. **Forgot password?** explains that this version has no
  password reset: ask the person who manages the installation, or create a new account with another e-mail address.
* The left side of the sign-in page shows a real week of the Fox community: measured demand and the forecast made 24 hours earlier
  (hover for the values of an hour). It is data, not decoration, and the caption says which week and how far off the forecast was.
* Roles: **viewer** (read only), **analyst** (also acknowledges alerts and creates reports), **admin** (also imports, uploads and
  trains societies on *Society admin*, and sees the *Administration* page). Buttons you may not use are hidden for viewers; the
  server enforces the rules regardless of what the page shows.
* Societies and their results are shared by every signed-in user. A report you create is listed for everybody and anyone can download it.

## 2. Choosing a society

The top bar shows which society the page is about and the period of its data. When more than one society is loaded, every
society page has a **Society** box in its header; the choice is remembered for the browser tab. A society with no trained
model (five of the seven bundled ones) still has every page except the live forecast, which says "Not available" instead of guessing.

Every chart has a **Chart / Table** switch: the table lists the same values, and the legend names every line.

## 3. The society pages

| Page | What it shows | Good to know |
|---|---|---|
| **Society overview** | Last 7 days of measured demand and the next 24 hours with an 80 % range; latest demand; energy for 24 hours, 7 and 30 days; predicted energy and peak; estimated cost; open alerts | The "Tariff" box on the page changes the cost figures only |
| **Consumption** | Total demand and energy at hourly, daily, weekly or monthly resolution for a date range | Hours without a valid reading stay gaps and are never filled |
| **Forecasting** | Out-of-sample accuracy (MAE, RMSE, MAPE, R²) against the best baseline for 1, 6, 12, 24 hours and 7 days; model comparison; a live 24-hour forecast from an origin you may pick; SHAP importance of the inputs | The accuracy is scored once on the last six months, which the models never saw. Pick another **Forecast origin** to see the forecast a few days earlier |
| **Buildings** | Energy, share of the total, energy per m², average and peak demand per building; one building's demand over time | Buildings have codes such as FOX-B01; the dataset's own names are visible to administrators only |
| **Common facilities** | Lifts, pumps, street lighting and clubhouse, only where a separate meter exists | The bundled data have none of these meters, and the page says "Not measured in this dataset" |
| **Cost and peaks** | Cost estimate for a period under the chosen tariff; peak-demand shape, load factor and how well the daily peak is forecast | The **demo tariff** is a labelled placeholder, not a utility price |
| **Alerts** | Unusual demand on the whole society or on one building, with time, severity, size and an explanation | An alert is *unusual for that hour of the week*, not a confirmed fault; the data have no fault labels, so no detection accuracy is claimed |
| **Recommendations** | Observations with the evidence behind each | No unverified savings claims |
| **Reports** | A monthly PDF report and CSV exports (consumption, forecast results, alerts, cost, buildings) | Analysts and admins create them; anyone signed in downloads them |
| **Data sources** | Provenance, licence, cleaning rules and aggregation method of the selected society, with its data-quality counts | Cite the dataset paper when you use results |

**Alerts, step by step.** Filters narrow the list by level (attention = medium and high, or all), scope (whole society or one
building), status and building. Click a time or a marker on the timeline to read the explanation. Analysts and admins press
**Acknowledge** to mark an alert as seen; **Reopen** reverses it.

**Tariffs.** The "Tariff" boxes list the built-in demo tariff and any tariff saved in the system. The web application has no
form to create a tariff; an analyst or admin adds one through the API (`POST /api/v1/tariffs`, 24 weekday and 24 weekend hourly rates,
see `docs/society/05_api_and_database.md`) and then appears in every Tariff box.

## 4. Society administration (admins)

**Society admin** imports the bundled communities, uploads the meter CSV of a real society, trains its models and manages
buildings and meters. The steps, file layout and checks are in `docs/society/06_admin_and_upload_guide.md`.

## 5. Jobs, notifications, administration

* **Jobs** (clock icon in the top bar, and the *Jobs* page) — imports, uploads and training run in the background. The
  50 most recent are listed with progress and any error message.
* **Notifications** (bell icon, and the *Notifications* page) — messages that background jobs leave for you. The society jobs leave none in this version, so the list is normally empty ("You are all caught up").
* **Administration** (admins only) — *Users* (change roles, Deactivate/Reactivate), *Audit log* (who did what, with filters),
  *System* (record counts, jobs by status, API traffic since the server started).
* The interface works with a keyboard, shows focus clearly, and every chart has a table view.

## 6. When something goes wrong

| What you see | Likely cause and fix |
|---|---|
| The register form refuses your password | It needs 10–128 characters with letters and digits, and the confirmation must match; nothing is sent until it passes. |
| "No society loaded yet" | An administrator has not imported or uploaded one: open **Society admin** and import the bundled communities. |
| The forecast says "Not available" | That society has no trained model; an administrator can train one on **Society admin**. |
| A job failed | Open **Jobs**; the message explains in plain words. Technical detail is kept in the server log, not shown in the browser. |
| "Too many requests, slow down" | Wait a minute; rate limits protect the sign-in, registration and upload endpoints. |
| A page shows "not found" or "access denied" | The address does not exist (the older single-meter pages were removed), or your role cannot see it. |

## 7. Limits to keep in mind

* The bundled societies are representative communities of residence halls. Accuracy figures do not transfer to family housing.
* Forecast error grows with the horizon; the Forecasting page shows the real numbers and the baseline next to them.
* Holidays, term breaks and occupancy are not inputs, so sudden behaviour changes cannot be predicted.
* Costs depend entirely on the tariff, and the demo tariff is a placeholder.
