# Sample data

`uci_hourly_2009_sample.csv` is calendar year 2009 of the UCI "Individual household electric power
consumption" data set, aggregated to hourly mean `Global_active_power` (kW). An hour is kept only if at
least 45 of its 60 one-minute readings are valid; other hours are left blank (nothing is imputed).

- Source: Hebrail, G. & Berard, A. (2006). Individual Household Electric Power Consumption. UCI Machine
  Learning Repository. https://doi.org/10.24432/C58K54 - licensed CC BY 4.0.
- Created by `scripts/make_sample.py`. Columns: `timestamp` (logger clock, no timezone), `power_kw`.
