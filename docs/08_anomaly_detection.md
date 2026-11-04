# 08. Anomaly detection

Numbers come from `artifacts/reports/anomaly/` (`scripts/run_anomaly.py`, UCI dataset, 34,151 valid hours).
Code: `ml_engine/anomaly/detector.py`. Tests: `tests/unit/test_anomaly.py` (10 tests) and `tests/integration/test_api_ml.py`.

## 1. The central limitation: there are no labels

The dataset does not say which hours are faulty or unusual. **No precision, recall, F1 or "accuracy" can be computed on the real data, and none is reported.** What this module offers is a transparent statistical definition of "unusual for this household at this time", an explanation for every flag, and a *synthetic* sanity check that is clearly labelled as synthetic (§5). Flags are leads for a person to look at; they are not confirmed faults.

## 2. Method

For every valid hour the detector forms a **causal expectation** and measures how far the reading is from it. "Causal" means the expectation for hour *t* uses only data before *t*, so the same function works on live data.

1. **Expected value.** Median of the same hour-of-week over the previous 8 weeks (at least 4 required). The median ignores earlier spikes.
2. **Residual scale by hour of day.** The empirical distribution of (actual − expected) is built per hour of day over the trailing 26 weeks (at least 56 days), so the 03:00 band is narrow and the 19:00 band is wide. Hours with too little history are not scored.
3. **Alert band.** An hour is a *deviation* candidate if the residual lies beyond the 0.995 empirical quantile of its hour-of-day (upper tail for spikes, lower tail, 0.005, for drops) **and** the absolute deviation is at least 0.5 kW. The second condition removes statistically unusual but practically irrelevant wiggles at low load.
4. **Flat-run rule.** Four or more consecutive hours with an identical hourly value are flagged as a possible stuck sensor or missing-data placeholder. The threshold of 4 was chosen from the empirical run-length distribution of the same dataset, so it is *not* independent evidence.
5. **Isolation Forest corroboration** [4]. An Isolation Forest (150 trees) is fitted on the first 60 % of the series using seven per-hour features (the value, its change from the previous hour, its ratio to the previous-24-hour mean, the band residual, sine/cosine of the hour and a weekend flag); hours it scores above its 0.995 quantile **and** with a residual z ≥ 2.5 are flagged as "unusual pattern". The first 60 % are in-sample for that model (reported in the output). It is used to add pattern-type flags, not to override the band.
6. **Events and severity.** Flagged hours separated by at most one hour are merged into events. Severity is set from the excess ratio of the worst hour (`_severity_from_excess`: ≥ 2.5 high, ≥ 1.5 medium, otherwise low). Each event carries an auto-generated plain-language explanation built from its numbers.

**Sensitivity** in the application maps to the band quantile: low = 0.999, medium = 0.995 (default), high = 0.99.

### Why not a simple z-score?
The first implementation used a MAD z-score; it flagged 12.4 % of all hours and still missed a known 401-minute flat period found in Phase 1. It was replaced by the quantile band above, which respects the heavy, hour-dependent tail of household load. This iteration was guided by the same dataset, which is a form of tuning on the data and is disclosed here.

## 3. Results on the real dataset (medium sensitivity)

| Item | Value |
|---|---|
| Valid hours scored by a baseline | 32,572 of 34,151 valid hours |
| Hours flagged | 695 (2.04 % of valid hours) |
| …by deviation band | 651 |
| …by flat-run rule | 5 |
| …by Isolation Forest only (with z ≥ 2.5) | 39 |
| Events after merging | 484 (376 low, 89 medium, 19 high) |
| Event types | 263 spikes, 186 drops, 36 unusual patterns, 1 flat run |

Cross-check against two irregularities noticed during EDA, *before* the detector was built (these are consistency checks, not accuracy measurements):

* A 401-minute run at a constant 0.360 kW on 2008-10-06 (the 8 hours from 10:00 to 17:00 are touched): **5 of those 8 hours flagged**, all by the flat-run rule.
* A 10-day low-use block in August 2008 (240 hours): **0 hours flagged**. The detector treats a sustained low-use period as the household's new normal after a few days and does not call it an anomaly. Whether that period is a holiday absence or a fault cannot be determined from this data.

The highest-severity events in the saved output are isolated drops (for example 2010-02-19 02:00: 0.31 kW against 0.81 kW expected) and a 12-hour drop on 2009-02-21/22; see `events.csv` and `fig_anomaly_examples.png`.

## 4. Behaviour you should expect

* About 2 % of hours are flagged at the default setting by construction (a 0.995 band on each tail plus extra rules); this is a **chosen alert rate**, not a measured false-alarm rate.
* Slow changes (new appliance, season change) are absorbed after a few weeks because the baseline is a rolling median of recent weeks.
* The first weeks of any dataset cannot be scored (no baseline yet).
* The first run on a new dataset needs at least 12 weeks of valid history; the API refuses shorter data with an explanatory message.

## 5. Synthetic injection check (clearly synthetic)

To see whether the detector responds to anomalies of known size, 60 events of each kind were injected into a copy of the real series at random positions and the detector was run again (`injection_check.json`). Because the underlying series already contains genuine irregularities and because the injected shapes are my own choice, the numbers describe sensitivity to these particular synthetic patterns only:

| Injected pattern | Recall on injected hours | Recall when expected load ≥ 1 kW | Flag rate on untouched hours |
|---|---|---|---|
| Spike to ×3 expected | 61.7 % | 75.0 % | 1.8 % |
| Spike to ×1.6 expected | 31.7 % | 35.0 % | 1.9 % |
| Drop to 5 % of expected | 10.0 % | 30.0 % | 2.0 % |
| 8-hour flat run | 100 % | 100 % | 1.9 % |

Read this honestly: large spikes and flat runs are detected well; **moderate deviations and drops are often missed** (a drop at an hour when the expected load is already low cannot exceed the 0.5 kW minimum deviation). The detector is deliberately conservative. These percentages are not an accuracy figure for real faults.

## 6. In the application

`POST /api/v1/datasets/{id}/anomalies/run` starts a background job; `GET /api/v1/anomalies` lists events with filters (severity, acknowledged, date range); `PATCH /api/v1/anomalies/{id}` acknowledges one; `GET /api/v1/anomalies/summary` returns counts. Only the **latest run per dataset is kept**: starting a new run replaces the previous run's events, so acknowledgements made on the old events are not carried over (the acknowledgement actions themselves remain in the audit log).
