# Installation manual (Windows-first; Linux and macOS notes inline)

Tested on Linux with Python 3.11.15, Node 22 and PostgreSQL 16. **Not yet run on Windows**; the commands are written for Windows PowerShell/cmd and use only cross-platform tools, but treat the first Windows run as a test.

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 | 3.13 also passes the test suite; other versions untested |
| Node.js | 22 LTS (20 LTS should work) | for the web UI |
| Git | any recent | |
| RAM / CPU | 8 GB / any CPU | no GPU needed; training the application's models used about 0.3 GB of memory on the one-year sample |
| Optional | Docker Desktop, PostgreSQL 16, AWS CLI | only for the container/production paths (not exercised in this project's build environment) |

## 2. Get the code and create the environment

```
git clone <your repository URL> EnergiQ-AI
cd EnergiQ-AI
python -m venv .venv
.venv\Scripts\activate                 # Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

With Conda instead: `conda env create -f environment.yml && conda activate energiq` (also installs Node and the research dependencies).

## 3. Run the API

```
set ENERGIQ_ENV=dev
set ENERGIQ_ADMIN_EMAIL=admin@example.com
set ENERGIQ_ADMIN_PASSWORD=use-a-long-password-1
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

PowerShell: `$env:ENERGIQ_ENV="dev"` and so on. Check `http://127.0.0.1:8000/health/ready` and the interactive docs at `http://127.0.0.1:8000/docs` (dev only). The SQLite database is created at `data/energiq.db`.

## 4. Run the web UI

```
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The dev server proxies `/api` and `/health` to port 8000.

## 5. First use

1. Register an account (or sign in with the administrator you configured).
2. Datasets → *Load bundled sample* (one year of hourly data from the UCI household set) or upload your own CSV.
3. Models → *Train*; when the job finishes, the model is active.
4. Forecast, Anomalies, Explain and Optimise become useful from there. See `docs/manuals/user_guide.md`.

## 6. The research benchmark (optional)

The benchmark numbers in `docs/06_model_evaluation.md` come from the full UCI file, which is not stored in the repository (127 MB). Download it from https://doi.org/10.24432/C58K54 and place it at `data\raw\uci_household_power\household_power_consumption.txt`, then, with the pinned environment (**XGBoost results depend on the XGBoost version**, see `docs/06_model_evaluation.md` §8):

```
pip install -r requirements-research.txt        # adds matplotlib and PyTorch (CPU)
python scripts\reproduce_benchmark.py --input data\raw\uci_household_power\household_power_consumption.txt
```

This runs, in order: `run_benchmark.py` (baselines, Random Forest, XGBoost), `run_lstm.py` (three seeds), `evaluate_models.py` (test metrics, bootstrap, figures), `run_explain.py` and `run_anomaly.py`. Each can also be run alone (`--help` shows the options). The whole chain took about 25 minutes on 2 CPU cores; peak memory was about 0.6 GB for the tree benchmark and 1.1 GB for one LSTM seed. Results are written under `artifacts\reports\` (committed) and model files under `artifacts\models\` (not committed); every result file records the library versions that produced it.

## 7. Tests

```
python -m pytest tests\unit tests\integration                 # unit + integration + security (SQLite)
cd frontend && npm test                                       # front-end tests (Vitest)
```

Browser end-to-end tests (real server, real Chromium; they skip with a stated reason if a prerequisite is missing):

```
cd frontend && npm ci && npm run build && cd ..
python -m playwright install chromium
python -m pytest tests\e2e -rs
```

To run the integration tests against PostgreSQL, point `ENERGIQ_TEST_DATABASE_URL` at a throw-away database (its tables are dropped before every test; the backup/restore test also needs `pg_dump` on the PATH):

```
set ENERGIQ_TEST_DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/energiq_test
python -m pytest tests\integration
```

Coverage: `python -m pytest --cov=backend --cov=ml_engine`. Static checks used in CI: `ruff check .`, `bandit -r backend ml_engine -ll`, `pip-audit -r requirements.txt`, `cfn-lint infrastructure\aws\*.yaml`, `python scripts\check_secrets.py`.

## 7a. Containers and cloud

`docker compose up --build` (needs the Docker images to be built on your machine; the images were **not built or run** during this project's development because the build workspace could not pull base images) and the AWS templates are described in `docs/12_deployment.md`, including what has and has not been verified.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `RuntimeError: ENERGIQ_SECRET_KEY must be set...` | You started with `ENERGIQ_ENV=prod`. Generate a key: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| 401 on every request from the UI after a restart | Tokens signed with a different secret are rejected; sign in again |
| Upload rejected with 413/415/422 | File too large (`ENERGIQ_MAX_UPLOAD_MB`), wrong extension (only .csv, .txt, .tsv), or content that is not numeric hourly/minute data; the message says which |
| Training says history is insufficient | At least 4 weeks of valid hours are required (anomaly detection needs 12 weeks) |
| `pip install` of `xgboost` or `torch` is slow or fails | Use the CPU wheel for PyTorch: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| Port already in use | Change `--port`, and tell the UI where the API is: set `VITE_DEV_PROXY_TARGET=http://127.0.0.1:<port>` before `npm run dev` |
