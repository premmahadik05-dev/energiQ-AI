# EnergiQ AI — Exploratory Data Analysis (Phase 2)

> **Status update (end of project).** This report was written in Phase 2 and is kept as written; the proposals in §4 were resolved as follows.
> Validation: the expanding-window cross-validation was adopted (8 quarterly folds). Features: the final set differs from the §4 proposal
> (lags 0, 1, 2, 3, 5, 11, 23, 47 plus values at the same time yesterday and last week, rolling statistics, calendar features; see `docs/05_ml_methodology.md`).
> The 401-minute flat run led to the identical-readings rule in the anomaly detector (`docs/08_anomaly_detection.md`).
> **Not done:** the with/without sensitivity check for the August 2008 low-use block was never run, so the effect of that atypical period on the models is unquantified.


All numbers come from `scripts/run_eda.py` run on the real UCI file
(`artifacts/reports/eda/eda_stats.json`; figures in `artifacts/reports/eda/`).
The hourly series follows the Phase 1 policy: hourly mean of
`Global_active_power`, kept only when the hour has at least 45 valid minutes
(34,151 hours; 438 hours are left empty, versus 504 under a strict 60-minute rule).
"Logger clock" means the timestamps exactly as stored in the file.

## 1. Headline findings

1. **Level and stability.** Mean hourly load is 1.092 kW (median 0.803, 95th
   percentile 2.866, highest hour 6.561 kW on 2008-11-23 18:00). That is about
   25–27 kWh/day. Over the same calendar window (1 Jan – 25 Nov) the yearly
   means are 25.58 (2007), 25.13 (2008), 25.22 (2009) and 25.44 (2010) kWh/day,
   a spread of under 2%, so there is no visible multi-year trend.
2. **Strong daily routine, different on weekends.**
   [Figure 2](../artifacts/reports/eda/fig02_daily_profile.png) and
   [Figure 3](../artifacts/reports/eda/fig03_weekly_heatmap.png). Weekdays have a
   sharp morning rise to about 1.7 kW at 07:00 and a larger evening peak of
   1.86 kW at 21:00, with a 03:00 trough of 0.41 kW. Weekends have no sharp
   morning peak, a broad midday plateau near 1.4–1.5 kW and an evening peak of
   2.05 kW at 19:00. Weekend mean load is 1.234 kW against 1.036 kW on weekdays
   (about 19% higher).
3. **Strong yearly seasonality.** [Figure 4](../artifacts/reports/eda/fig04_monthly_seasonality.png).
   Mean daily energy is about 33 kWh/day in December–February and about 18 kWh/day
   in June–August (Aug 2008 excluded), roughly 1.8 times higher in winter.
   The data contains no temperature, so the cause (heating, lighting, occupancy)
   cannot be established from this dataset.
4. **Unusual low-use period.** The ten lowest-energy days are all 20–29 August
   2008, at 4.17–4.47 kWh/day, giving an August 2008 monthly mean of 6.6 kWh/day
   (other Augusts: 14–18). This is consistent with the house being largely
   unoccupied, but that is an interpretation, not something the data states.
5. **Memory of the series.** [Figure 5](../artifacts/reports/eda/fig05_autocorrelation.png).
   Hourly autocorrelation is 0.71 at lag 1, 0.44 at lag 24 and 0.46 at lag 168
   (0.37–0.41 at the other daily multiples up to 6 days). The daily rhythm is
   real but day-to-day variation is large, so long-horizon skill is expected to be
   moderate. This is a hypothesis for Phases 4–7, not a result. Long-lag values also
   include the yearly seasonal level, which inflates them slightly.
6. **Skewed, two-mode distribution.** [Figure 6](../artifacts/reports/eda/fig06_distribution.png).
   One mode near 0.3 kW (night and idle hours) and a second near 1.4–1.5 kW, with a
   long right tail. Error metrics must therefore be reported alongside scale-free
   ones (sMAPE) and per-regime, not just RMSE.
7. **About half the energy is not sub-metered.** [Figure 7](../artifacts/reports/eda/fig07_submeter_mix.png).
   51.2% of measured active energy is outside the three sub-meters. Of the
   sub-metered part, sub-meter 3 (water heater and air conditioner) is clearly the
   largest and sub-meter 1 (kitchen) the smallest.
8. **Top demand hours are winter evenings.** All ten highest hours fall between
   November and February, between 17:00 and 21:00.
9. **One suspicious flat run.** Exactly one stretch of 30 minutes or longer has
   identical readings: 401 minutes at 0.360 kW starting 2008-10-06 10:09. Every
   other run of identical readings is 29 minutes or shorter. This is a candidate
   data artifact (for example a stuck sensor), unconfirmed.

## 2. Clock check (the Phase 1 open question)

I tested whether the logger clock follows daylight saving, in two independent ways.

- **Row counts.** On all 8 EU clock-change days (last Sunday of March and October,
  2007–2010) the file has exactly 1,440 rows, and every row in the 02:00 hour has
  a real reading. A clock that follows daylight saving would be missing the 02:00
  hour in spring or repeating it in autumn.
- **Behaviour.** For each change I compared the weekday load profile in the two
  weeks before and after (10-minute resolution, best of ±3 h shifts).
  [Figure 8](../artifacts/reports/eda/fig08_clock_check.png). The estimated shift
  is 0 or +10 minutes at all 8 changes, against −20 to +10 minutes for 16 control
  comparisons between adjacent windows with no clock change. The detector recovers
  injected shifts of ±30 and ±60 minutes exactly, so an hour-long step would have
  been seen.

**Conclusion.** The household's routine sits at the same logger-clock time before
and after every clock change, and the timeline has no skipped or repeated hour.
Hour-of-day features are therefore consistent across the whole year. How the data
provider produced this continuous, routine-aligned clock is not documented and
remains unexplained. It does not block modelling, but ingestion of user uploads
must not assume the same: users will declare their timestamp convention (Phase 3
and Phase 10).

## 3. Data availability by proposed split

| Split | Period | Hours | Valid hours | Excluded | Mean kW | 95th pct kW | Max kW | Mean kWh/day |
|---|---|---|---|---|---|---|---|---|
| Train | 2006-12-16 to 2009-06-30 | 22,255 | 22,127 (99.42%) | 128 | 1.119 | 3.002 | 6.561 | 26.85 |
| Validation | 2009-07-01 to 2009-12-31 | 4,416 | 4,401 (99.66%) | 15 | 1.009 | 2.657 | 5.115 | 24.20 |
| Test | 2010-01-01 to 2010-11-26 | 7,918 | 7,623 (96.27%) | 295 | 1.061 | 2.574 | 5.627 | 25.44 |

Two consequences:

- The validation block (July–December) contains no winter peak months, so
  hyperparameters chosen on it alone would not be tuned for January–March demand.
- The test period has fewer extreme hours than training (95th percentile 2.57 vs
  3.00 kW) and loses 3.7% of its hours to missing data. Part of this is seasonal
  mix, part may be a real difference between years; the data cannot separate them.

## 4. Decisions and proposals

| Item | Status | Detail | Reason |
|---|---|---|---|
| Target | Confirmed (approved in Phase 1) | Hourly mean `Global_active_power` | Regular, strong daily and weekly structure |
| Hour validity | Confirmed (approved in Phase 1) | At least 45 valid minutes | Drops 438 hours; the strict rule would drop 504 |
| Test period | Confirmed (approved in Phase 1) | 2010-01-01 to 2010-11-26, untouched until final evaluation | Chronologically last |
| Validation | **Proposed change** | Replace the single July–December block with expanding-window time-series cross-validation over train plus validation, folds spanning different seasons | One block is not seasonally representative |
| Aug 2008 low-use block | Proposed | Keep in data; run a with/without sensitivity check in Phase 7 | Real household behaviour, but atypical |
| 401-minute flat run | Proposed | Flag as suspect in Phase 3; Phase 8 detector gets an identical-readings rule | Possible sensor artifact, unconfirmed |
| Features | Proposed | Hour, weekday, weekend, month; lags 1, 2, 3, 24, 48, 168; rolling mean and standard deviation over 24 h and 168 h; no weather; no holiday feature unless a documented source is added | Supported by the autocorrelation and by what the data contains |
| Baselines | Per specification | Naive; seasonal naive at 24 h and 168 h | Autocorrelation at both is similar (0.44, 0.46) |

## 5. Limitations

- One household. Nothing here generalises to other homes.
- EDA describes patterns; it does not prove causes (no weather, occupancy or appliance data beyond the three sub-meters).
- The clock behaviour is measured, not explained.
- The figures are static PNGs for the report. The application's charts (Phase 11) will be built from the real API.
- Not yet run on Windows.

## 6. Reproduce

```
python scripts\run_eda.py --input data\raw\uci_household_power\household_power_consumption.txt --outdir artifacts\reports\eda
python -m pytest
```

## 7. Chart palette

Colours come from a validated categorical palette (blue, orange, aqua, yellow, in
that fixed order). The validator passes all hard checks (lightness band, chroma,
colour-blind separation, normal-vision separation). It warns that aqua and yellow
are below 3:1 contrast on the light background, so every chart that uses them also
carries a legend and direct labels, and the underlying numbers are in `eda_stats.json`.
