# Objectives and where each is delivered

| # | Objective | Success criterion (stated before evaluation) | Delivered in | Outcome |
|---|---|---|---|---|
| O1 | Validated ingestion and quality scoring | Wrong header, unparseable time, non-numeric value, binary file and oversize file are rejected with a reason; gaps and flat runs reported; nothing imputed silently | `ml_engine/data/`, `backend/app/services/data.py`; tests `test_loading`, `test_api_core` | Met (automated tests) |
| O2 | Leak-free forecasting benchmark | Chronological splits only; features use data at or before the origin; test period scored once; common evaluation rows; baselines included | `docs/05_ml_methodology.md`; `test_features_splits`, `test_forecasting`, `test_forecast_uses_only_data_up_to_the_origin` | Met |
| O3 | Models that beat baselines, with uncertainty | Learned models beat the cross-validation-chosen baseline at 1, 6 and 24 h, with a bootstrap interval excluding zero | `docs/06_model_evaluation.md` | Met for XGBoost, Random Forest and LSTM at all three horizons. Accuracy is modest (R² ≈ 0.40 at 6 and 24 h) |
| O4 | Compare a lightweight deep model | CPU PyTorch LSTM trained under the same protocol, three seeds, headline seed fixed in advance | `ml_engine/forecasting/lstm.py`, `scripts/run_lstm.py` | Done. Result: no demonstrated benefit over trees |
| O5 | Anomaly detection with honest evaluation | Explained events, stated alert rate, synthetic check labelled as synthetic, no accuracy claim | `docs/08_anomaly_detection.md` | Delivered; accuracy on real faults is **not measurable** with this data |
| O6 | Explainable forecasts | Exact TreeSHAP with verified additivity; plain-language groups | `docs/07_…`; `test_explain_optimize` | Met |
| O7 | Cost analysis and recommendations | Tariff-based cost, scenario savings with assumptions, cheapest-window scheduler; demo tariff labelled | `ml_engine/optimization/` | Met (scenario estimates, not measured savings) |
| O8 | Secure multi-user backend | Authentication, roles, ownership checks, validated uploads, rate limits, audit | `docs/09_…`, `docs/10_security.md`; 16 security tests | Met, no external penetration test |
| O9 | Usable web interface using only real API data | All main workflows available; no hard-coded numbers | `frontend/` | See `docs/15_verification_matrix.md` |
| O10 | Reproducible deployment path | Migrations, Docker files, CI, AWS templates validated statically | `docs/12_deployment.md` | Configured and statically checked; **not built or deployed here** |
| O11 | Monitoring and operations | Health, metrics, drift and realised-error checks, backups tested | `docs/14_mlops_monitoring.md`; `test_backup_restore` | Met locally |
| O12 | Honest reporting | Limitations and unverified items stated; deployment status ladder | `docs/13_limitations.md`, `docs/15_verification_matrix.md` | Met |
