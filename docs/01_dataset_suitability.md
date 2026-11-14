# EnergiQ AI — Dataset Inventory, Quality Report and Suitability Assessment

Phase 1 deliverable. Every number below was measured from the supplied file by
`scripts/profile_dataset.py` (machine-readable output:
`artifacts/reports/dataset_profile.json`). Units, sub-meter coverage and
collection site come from the official UCI dataset page, because the file
itself carries no unit metadata. Nothing here is estimated or invented.

## 1. Verdict

**SUITABLE** for electricity-consumption forecasting, anomaly screening and
tariff-based cost analysis on a single household. It is **not** suitable for
weather-driven modelling, supervised anomaly evaluation, or any claim about
generalising across households (see section 8).

## 2. Provenance

| Item | Value |
|---|---|
| Name | Individual Household Electric Power Consumption |
| Creators | Georges Hebrail, Alice Berard |
| Donated to UCI | 29 August 2012 |
| Licence | Creative Commons Attribution 4.0 International (CC BY 4.0) — attribution required |
| DOI | 10.24432/C58K54 |
| Collection site | One house in Sceaux, about 7 km from Paris, France (per UCI) |
| Period (per UCI) | December 2006 – November 2010 |
| Citation | Hebrail, G. & Berard, A. (2006). *Individual Household Electric Power Consumption* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C58K54 |
| Access | Public download, no registration required |
| Supplied file | `household_power_consumption.txt` (from your zip) |
| SHA-256 | `4259c9d7ece5dbee9ab8d53682baac68d791c864f0f64a52b4043cb3b90894b7` |

Independent check: UCI publishes 2,075,259 instances; `wc -l` on the supplied
file gives 2,075,260 lines including the header, i.e. 2,075,259 data rows.

## 3. File inventory

| Property | Measured value |
|---|---|
| Format | Semicolon-delimited text, one header line |
| Size | 132,960,755 bytes (about 127 MB) |
| Data rows | 2,075,259 |
| Columns | 9 |
| Fields per line | exactly 9 on all 2,075,260 lines (no malformed lines) |
| Header matches expected schema | Yes |
| Unparseable timestamps | 0 |
| Profiling cost | about 15 s, 464–508 MB peak RAM (two runs), chunked read |

## 4. Columns

Date format is `dd/mm/yyyy`; Time is `hh:mm:ss`. Statistics are over the
2,049,280 rows that contain readings.

| Column | Unit (per UCI) | Min | Mean | Max | Notes |
|---|---|---|---|---|---|
| Global_active_power | kW | 0.076 | 1.092 | 11.122 | Primary forecasting target. No zeros, no negatives. |
| Global_reactive_power | kW (as documented) | 0.000 | 0.124 | 1.390 | 481,561 exact zeros (23.5%) |
| Voltage | V | 223.20 | 240.84 | 254.15 | Plausible mains range |
| Global_intensity | A | 0.2 | 4.63 | 48.4 | |
| Sub_metering_1 | Wh | 0 | 1.12 | 88 | Kitchen (dishwasher, oven, microwave). 91.7% zeros. |
| Sub_metering_2 | Wh | 0 | 1.30 | 80 | Laundry (washer, dryer, fridge, light). 70.1% zeros. |
| Sub_metering_3 | Wh | 0 | 6.46 | 31 | Electric water heater and air conditioner. 41.6% zeros. |

All three sub-meter columns contain only whole numbers (1 Wh resolution per
minute), so they are coarse for low loads.

## 5. Time axis

| Property | Measured value |
|---|---|
| First reading | 2006-12-16 17:24:00 |
| Last reading | 2010-11-26 21:02:00 |
| Sampling interval | 60 s; all 2,075,258 consecutive steps are exactly 60 s |
| Chronologically sorted | Yes |
| Duplicate timestamps | 0 |
| Absent timestamps (rows missing from the span) | 0 — span coverage 100% |
| Complete calendar years | 2007, 2008, 2009 only (2006 starts 16 Dec; 2010 ends 26 Nov) |

Clock behaviour (resolved in Phase 2, see `04_eda_report.md` section 2): every
step is exactly 60 s, each of the 8 EU clock-change days has exactly 1,440 rows,
and the household's weekday load profile does not shift by an hour at any of
them. So the timeline has no skipped or repeated hour and the routine stays at
the same logger-clock time all year. How the provider produced this is not
documented.

## 6. Data quality

### 6.1 Missing values

| Property | Measured value |
|---|---|
| Rows with no readings | 25,979 (1.2518% of rows) |
| Pattern | All seven measurement columns are missing together on the same rows; there are no partially missing rows |
| Contiguous missing blocks | 71 |
| Block length | median 1 min, 95th percentile 3,217 min |
| Blocks longer than 1 hour | 9 |
| Blocks longer than 1 day | 6 |

Longest blocks:

| Start | Length |
|---|---|
| 2010-08-17 21:02 | 7,226 min (about 5.0 days) |
| 2010-09-25 03:56 | 5,237 min |
| 2007-04-28 00:21 | 3,723 min |
| 2009-06-13 00:30 | 3,305 min |
| 2010-01-12 14:53 | 3,129 min |
| 2010-03-20 03:52 | 2,027 min |

Missing rows as a share of rows present, by year:

| 2006 | 2007 | 2008 | 2009 | 2010 |
|---|---|---|---|---|
| 0.018% | 0.748% | 0.026% | 0.814% | 3.711% |

Four of the six longest blocks fall in 2010. The most natural chronological
test period is therefore the worst-quality period; test scoring must report how
many hours were excluded (section 9).

**Documentation vs. file.** The UCI page says missing values appear as empty
fields. In this file the missing marker is `?` in the first six numeric columns
and an empty field in `Sub_metering_3` (the trailing field). The ingestion
parser must accept both tokens.

### 6.2 Invalid and unusual values

| Check | Result |
|---|---|
| Non-numeric tokens other than the missing markers | 0 |
| Negative readings | 0 in every column |
| Global_active_power at or below zero | 0 |
| Global_active_power above the 1.5×IQR fence (3.358 kW) | 95,070 readings (4.6%) |
| Global_active_power above the 3×IQR fence (5.188 kW) | 14,413 readings (0.70%) |
| Energy bookkeeping: minutes where sub-meters exceed total active energy | 1,050 of 2,049,280 (0.051%) |

The IQR counts are a screen, not a finding: high household load is expected
when several appliances run together, so these are not treated as errors.
The 1,050 bookkeeping minutes are small metering or rounding inconsistencies.

### 6.3 Energy coverage of the sub-meters

Using UCI's formula (`Global_active_power × 1000 / 60 − Sub_metering_1 − _2 − _3`,
in Wh per minute), the mean unmetered energy is 9.31 Wh/min against a mean total
of 18.19 Wh/min: about **51% of measured active energy is not attributed to any
sub-meter**. Appliance-group explanations must not be presented as a full
breakdown of household use.

### 6.4 Usable data after aggregation to hourly means

| Property | Measured value |
|---|---|
| Hours in span | 34,589 |
| Hours with all 60 minutes valid | 34,085 (98.5%) |
| Hours with at least 45 valid minutes | 34,151 (98.7%) |
| Hours with zero valid minutes | 421 |
| Days in span | 1,442 |
| Days with at least 95% valid minutes | 1,416 (98.2%) |
| Days with no valid minutes | 9 |

## 7. Requirement-by-requirement suitability

| Spec requirement | Supported by this data? | Basis |
|---|---|---|
| Timestamps | Yes | 100% parseable, regular 60 s grid |
| Consumption target | Yes | `Global_active_power` (kW); hourly energy in kWh = mean kW × 1 h |
| Horizons: next hour, 6 h, 24 h | Yes | 34,151 hourly points with at least 45 valid minutes |
| Seasonal naive baselines (24 h, 168 h) | Yes | Three complete calendar years |
| Hour, day, weekday, month, weekend, lags, rolling statistics | Yes | Derived from the timestamp and target |
| Weather features | **No** | No weather column; none will be created |
| Tariff-based cost and savings | **No data** | Dataset has no tariff; tariffs will be user-entered. Any default tariff is labelled demo and is not a savings claim |
| Verified anomaly labels | **No** | No labels; evaluation is unsupervised only |
| Calendar features such as public holidays | Possible | Needs a documented French holiday source; **not implemented** (listed as future work) |
| Multiple households or users | **No** | One household |

## 8. Limitations that must appear in the final report

1. One household: results say nothing about other homes, and cross-household
   generalisation cannot be claimed.
2. Anomalies found without labels are unconfirmed unusual readings, not faults,
   theft or equipment failure.
3. About half of active energy is unmetered, so sub-meter explanations are
   partial.
4. 2010 has the most missing data (3.7%), including a block of about 5 days
   whose cause is unknown.
5. Data ends in November 2010, so patterns reflect that period only.

## 9. Preprocessing policy (proposed in Phase 1; applied in Phase 3, see `docs/05_ml_methodology.md`)

- Canonical series: hourly mean of `Global_active_power`, built only from hours
  with at least 45 valid minutes; other hours stay missing.
- Missing values are never filled in the evaluation target. Short gaps may be
  interpolated for model inputs only, never for scored values.
- Chronological split (proposal): train 2006-12-16 to 2009-06-30, validation
  2009-07-01 to 2009-12-31, test 2010-01-01 to 2010-11-26. The test set lacks
  December, and the report must state the number of excluded test hours.
- All scalers and encoders are fitted on the training split only.

## 10. Reproduce

```
python scripts\profile_dataset.py --input data\raw\uci_household_power\household_power_consumption.txt --output artifacts\reports\dataset_profile.json
```

Phase 2 adds exploratory plots (daily and weekly profiles, seasonality,
missing-block timeline, the daylight-saving check).
