# Problem statement

**Context.** Smart meters and loggers produce electricity-use records for homes and small sites. The raw numbers are rarely used: people see a monthly bill but not what drives it, when an unusual period occurred, or when it would be cheaper to run flexible loads.

**Problems addressed.**

1. *Data trust.* Meter exports vary in format, unit, delimiter and time convention, and contain gaps and stuck readings. Forecasts built on unvalidated data are unreliable and users cannot tell why.
2. *Forecasting without leakage.* Many demonstrations evaluate time-series models with random splits or features that quietly contain future information, which overstates accuracy. A credible tool must evaluate chronologically and report honest errors against simple baselines.
3. *Unlabelled anomalies.* Real consumption data has no ground-truth fault labels, so "anomaly detection" is easy to oversell. A credible tool must say what it flags, why, how often, and what it cannot claim.
4. *Opaque models.* A forecast without an explanation is hard to trust or act on.
5. *From insight to action.* Forecasts and alerts matter only if they connect to cost and to decisions the user can make, with assumptions made explicit.
6. *Engineering gap.* Notebooks that show a model are not a system a person can use: they lack authentication, validated upload, job handling, persistence, monitoring, migrations, tests and a deployment path.

**Problem statement.** Design, implement and evaluate a secure, tested, cloud-ready web platform that ingests household electricity data, forecasts its hourly load 1 to 24 hours ahead with honestly measured accuracy, detects and explains unusual consumption without claiming unmeasurable accuracy, explains individual forecasts, and converts the results into tariff-based cost analysis and clearly labelled scenario recommendations, while recording exactly which parts have and have not been deployed or verified.

**Scope.** One-meter, hourly-resolution household data; CPU-only training on an 8 GB machine; a public data set for benchmarking; user-supplied tariffs.

**Out of scope.** Real-time streaming from meters, appliance-level disaggregation, weather and occupancy sensing, grid-scale forecasting, billing integration, a mobile app, and any claim of performance on other households.
