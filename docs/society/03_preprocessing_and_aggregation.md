# 3. Preprocessing and aggregation

Everything below is implemented in `ml_engine/society/{sources,cleaning,aggregate}.py` and run by `scripts/society_prepare.py`.
Every parameter is recorded in `data/society/processed/societies.json` and each community's `cleaning_report.json`, and is
shown on the *Data sources* page.

## Pipeline

1. **Select buildings.** Metadata primary use = `Lodging/residential`, sub-use not `Hotel`.
2. **Regularise time.** Sort, drop duplicate timestamps (keep the first), reindex to a complete hourly grid. For BDG2 this found 0 duplicates and 0 missing timestamps (17,544 rows).
3. **Clean each meter** (rules below). A reading that breaks a rule becomes missing; nothing is replaced.
4. **Keep a meter** if at least 95 % of its hours are valid. The rest are listed (admin-only) with the reason.
5. **Keep a site** if at least 8 meters are kept and the society total is valid in at least 94 % of hours.
6. **Aggregate** (below), then write the processed files.

These steps and thresholds are re-implemented and checked independently against the raw files in [10_raw_data_verification.md](10_raw_data_verification.md) (127 of 127 checks passed).

## Cleaning rules (hourly kWh per meter)

| Rule | Parameter | Why |
|---|---|---|
| Negative reading is invalid | none | Whole-building consumption cannot be negative |
| Exact zero is invalid (buildings) | zero counted separately as "short" (< 24 h) or "long" runs | An occupied residence hall does not draw exactly 0 kWh; in BDG2 zeros appear as dead-meter stretches. For **uploaded facility meters zeros are valid** (street lights are legitimately off by day) |
| Stuck sensor is invalid | same non-zero value for 48 h or more | A real load varies hour to hour |
| Spike is invalid | value above 4 × the meter's own 99.5th percentile | A single hour far outside the meter's range is a logging error, not a load |
| Missing in the source | stays missing | Counted as `missing_in_source` |

For Fox the rules examined 192,984 readings of the 11 retained meters: 37 were missing in the source, 62 were short zero
stretches, none were negative, stuck or spikes, and 192,885 readings (99.95 %) remained valid. The same counts, per community, are
available through the API (`data_card.cleaning_totals`) and the Data sources page.

## Aggregation method

For every hour `t`:

```
society_kWh(t) = Σ meter_kWh(m, t)   over the retained building meters m      if every retained meter is valid at t
               = missing                                                       otherwise
society_kW(t)  = society_kWh(t)  (an hourly mean demand: kWh in one hour = average kW in that hour)
```

* A partial sum is **never** used, because a total that silently omits a building would look like a drop in demand. Hours
  with any invalid meter are missing and are excluded from evaluation, cost and totals.
* Building totals are the same sum restricted to one meter. A building's share is its valid-hour energy in the chosen window divided by the
  sum of all buildings' valid-hour energy in that window; it can differ slightly from a share of the society total, which leaves out hours where any meter is missing.
* Daily, weekly and monthly consumption are **sums** of valid hours with a `complete` flag (an incomplete period shows its valid-hour count). Daily/weekly average and peak demand are the mean and maximum of the hourly values.
* kW and kWh are separate columns in the API (`avg_kw`, `peak_kw`, `energy_kwh`); a peak is the highest hourly mean, not an
  instantaneous maximum, because the source resolution is one hour.

## Processed-data layout

```
data/society/processed/
  societies.json                    # source, licence, file hashes, rule, cleaning parameters, communities, rejected sites
  <key>/
    meters_hourly_kwh.csv.gz        # cleaned hourly kWh per meter (pseudonymous column = building code); missing = empty
    society_hourly.csv.gz           # society_kwh and the number of valid meters per hour
    buildings.csv                   # code, BDG2 id (admin only in the API), sub-use, floor area, year built, floors, valid share
    excluded_meters.csv             # candidate meters rejected by the rule, with reason
    cleaning_report.json            # per-meter counts for every rule, timestamps report, weather gaps
```

Raw downloads are not part of the delivered ZIP (174 MB for the electricity file); `scripts/society_prepare.py` re-downloads
them and checks the stored SHA-256.

## Leakage control

Features at forecast origin `t` use data up to and including `t` only; the target is the demand at `t + h`. Training rows are
those whose **target time** is before the validation block or test start. The expanding-window folds and the test period are
chronological and never shuffled. Rolling windows and seasonal lags are built from the same past values (`ml_engine/features/builder.py`).
The API's live forecast takes an optional origin and refuses one after the end of the stored data (HTTP 422). An integration test
checks that the API's forecast from an earlier origin equals a forecast computed directly on a series cut at that origin, so
nothing after the origin can have influenced it.
