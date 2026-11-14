# 12. Deployment guide and deployment status

> **Note from the final upgrade.** The PostgreSQL and clean-unzip records below were made *before* the deployed forecasting models of all seven communities were added to the delivery, so they say that only Fox and Rat answered the live forecast. That was true when they were recorded. Today all seven communities answer it. The current test record is in [`../FINAL_TEST_REPORT.md`](../FINAL_TEST_REPORT.md). Docker builds are still **BLOCKED** in the verification workspace (no Docker daemon).

## 1. Status ladder (what has really been done)

| Level | Meaning | Status in this project |
|---|---|---|
| 1. Implemented locally | Runs and is tested on a development machine | **Yes**: API, ML engine and (see the verification matrix) the web UI run and are tested, on Python 3.11 with SQLite; the complete backend suite (unit and integration) was also run against PostgreSQL 16.15, see §1a |
| 2. Docker-tested | Images built and run as containers | **No.** Dockerfiles and `docker-compose.yml` are written and `docker compose config` accepts the compose file, but **no image was built and no container was run**: a build of both images was attempted in the verification workspace and stopped before the first Dockerfile instruction, because Docker Hub answered `Forbidden` when the base images were looked up (§1b). The CI workflow builds both images and smoke-tests the API image on GitHub-hosted runners; that job has not run either, because the repository has not been pushed. |
| 3. Cloud-configured | Infrastructure-as-code and pipeline files exist and pass static checks | **Yes**: `infrastructure/aws/ecr.yaml` and `energiq-stack.yaml` pass `cfn-lint`; `.github/workflows/ci.yml` and `deploy-aws.yml` parse as valid YAML |
| 4. Actually deployed | A live environment exists | **No.** No AWS account or resources were used. |
| 5. Independently verified | Someone other than the author tested it | **No.** |

Nothing in this repository should be described as "deployed on AWS", "Docker-tested" or "production-deployed". Any claim must stay at the level reached above.

## 1a. Database, production mode and container layout: what was run, and what was not

Run on 2026-11-08 (Linux, Python 3.11, PostgreSQL 16.15 installed as a normal server process, not in a container). Results are copied from the command output. Two environments were used, and each result below says which one it came from:

* **Working copy**: the author's project folder. It also holds the official BDG2 download (about 194 MB, not part of the ZIP). Used first, to find and fix the PostgreSQL defects of this section.
* **Clean unzip**: the delivery ZIP (SHA-256 `d5fc3211…0a6f`) unpacked into a new empty folder, so without the BDG2 download, with PostgreSQL started again from an empty data directory. Used afterwards to verify what was actually delivered. The final ZIP differs from that ZIP only in documentation. The complete logs are in `FINAL_VERIFICATION_REPORT.md` and `EnergiQ-AI-Final-Verification-Logs.zip`, delivered next to the ZIPs; the PostgreSQL test output is also in [`postgres_test_run_clean_unzip.txt`](postgres_test_run_clean_unzip.txt).

| Check | Result |
|---|---|
| **Complete backend suite on PostgreSQL 16.15** (`ENERGIQ_TEST_DATABASE_URL=postgresql+psycopg://...`, `python -m pytest tests/unit tests/integration`; the schema is dropped and recreated before every test) | **Working copy: 259 passed, 0 failed, 0 skipped** in 229 s ([`postgres_test_run.txt`](postgres_test_run.txt)). **Clean unzip: 258 passed, 0 failed, 1 skipped** in 217 s ([`postgres_test_run_clean_unzip.txt`](postgres_test_run_clean_unzip.txt)). The one skip is `test_full_official_files_pass_all_checks_and_contain_the_subset` (`tests/unit/test_society_raw_verification.py`), which needs the official BDG2 files; the ZIP does not contain them and the working copy does, so it is the only difference (258 + 1 = 259 tests). The two tests that skip on SQLite (the PostgreSQL migration check and the `pg_dump`/restore test) ran in both. |
| **API started the way the image starts it**: `docker/backend-entrypoint.sh` (database URL assembled from `DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME`, `alembic upgrade head`: 0001 and 0002 applied on an empty PostgreSQL database), then one Uvicorn worker with `ENERGIQ_ENV=prod`, a random 64-character secret and the files laid out as the `COPY` lines of `docker/backend.Dockerfile` place them (application under `app/`, state under `data/`) | started; `/health/ready` reports the database up; `/docs` answers 404; the responses carry `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`; the administrator from `ENERGIQ_ADMIN_EMAIL`/`ENERGIQ_ADMIN_PASSWORD` can sign in (working copy). Repeated in the clean unzip with a folder laid out by the same `COPY` lines and an empty PostgreSQL database: 24 checks OK, 0 mismatches; after a restart with the same secret nothing was copied again, no migration was re-applied, all seven communities were still present and the Fox forecast answered 200 |
| **"Import bundled communities"** on that instance (admin job) | all seven communities imported into PostgreSQL in 34 s (working copy) and 36 s (clean unzip). The live forecast then answered 200 for Fox and Rat and 410 (models not installed) for the other five, as designed |
| **Independent raw-data verifier against that PostgreSQL-backed API** (`scripts/verify_society_raw_data.py --use-subset --api-url ...`) | **Working copy:** 123 of 123 checks passed in `--use-subset` mode, including the 21 comparisons with the API (overview totals, 24 months and every building for each of the seven communities); the 4 checks that need the 174 MB official electricity file are not part of that mode. **Clean unzip:** **127 of 127** in `full` mode (`--raw <official BDG2 files> --check-subset --api-url ...`) against the PostgreSQL-backed production-mode API; the official files were supplied from outside the ZIP. |
| **First-start seeding of the society volume** (`SOCIETY_SEED_DIR` to `ENERGIQ_SOCIETY_DIR`) | `tests/unit/test_deployment_files.py` runs the real entrypoint script: the artifacts are copied once, a later start does not overwrite what the application has stored, an interrupted first copy is repeated |
| **Deployment files, static** | `docker compose config -q` accepts `docker-compose.yml` and rejects it when `ENERGIQ_SECRET_KEY` is missing; `cfn-lint` finds nothing in `ecr.yaml` and `energiq-stack.yaml`; a test checks that every `COPY` source exists and is not excluded by `.dockerignore`, and that every `ENERGIQ_*` variable named in the Dockerfile, compose file, CloudFormation template and `.env.example` is a real setting (an unknown name is otherwise ignored without a message) |
| **Frontend production build** | `npm run build` (after `npm ci`, typecheck and lint) and the browser end-to-end test against the built app passed in the release run recorded in [`society/07_testing_and_verification.md`](society/07_testing_and_verification.md); both were repeated in the clean unzip (typecheck, lint, 118 frontend unit tests, the production build and 4 browser tests passed) |

**What the PostgreSQL run found.** The first full run on PostgreSQL failed 8 tests (6 errors, 2 failures) for two reasons that SQLite hides, and both were real defects:

1. The BDG2 metadata has no coordinates for the Eagle site, so its cleaning report contains `NaN`. SQLite stores that text without complaint; PostgreSQL's `json` type rejects it, so "Import bundled communities" failed at Eagle. Every value written to a JSON column now goes through `json_safe` (`NaN` and infinity become `null`), and the missing latitude and longitude are stored as unknown.
2. For an uploaded society whose name gives a key of 20 or more characters, the generated building codes (for example `GREEN-PARK-RESIDENCY-2-B01`, 26 characters) were longer than the `VARCHAR(24)` column; SQLite does not enforce `VARCHAR` lengths. The code prefix is now shortened so that every code fits, and a meter column name longer than the 120-character `source_id` column is refused with a message (HTTP 422) instead of failing the job.

Both are covered by tests that also fail on SQLite when the bug returns (`tests/unit/test_society_db_limits.py`, `tests/integration/test_society_db_portability.py`). A third finding was a configuration gap, not a code bug: the API image contained neither the processed society data nor the society artifacts, so in a container "Import bundled communities" answered 404. The Dockerfile now copies both, `ENERGIQ_SOCIETY_DATA_DIR` and `ENERGIQ_SOCIETY_DIR` are set in the image, and the entrypoint seeds the writable `/data/society` volume once (§3, §6).

**What was not run.** Do not read the table above as "Docker-tested":

* No image was built and no container was started (§1, level 2; the failed attempt is in §1b), so the `Dockerfile` instructions themselves (base image, `apt-get`, `pip install`, user `energiq` with uid 10001, file permissions on the mounted volume, the `HEALTHCHECK`) are untested. The run above imitates the image: same files, same variable names, same entrypoint script and command, but as the workspace user, without a container, without a read-only application layer and without the uid change.
* `docker compose up`, the nginx configuration (`docker/nginx.conf`; no nginx binary was available to check its syntax) and the web image.
* Any AWS resource: the ECS tasks, the EFS access point, the ALB health checks and the time the first start needs to copy the society artifacts onto EFS (`HealthCheckGracePeriodSeconds` was raised from 120 to 300 s as a precaution; it has not been measured).
* GitHub Actions (the workflow has never run), Windows, and Python 3.13 for the society code.

## 1b. Docker build attempt and deployment items that remain unverified

**The Docker image builds failed.** In the clean-unzip verification of 2026-11-08, `docker build -f docker/backend.Dockerfile` and `docker build -f docker/frontend.Dockerfile` were run against a Docker daemon (Docker 29.9.2, Compose 5.6.1) started in the verification workspace. Both exited with code 1 before executing a single Dockerfile instruction, because Docker Hub answered `Forbidden` when the base images were looked up:

```
ERROR: failed to build: failed to solve: python:3.11-slim: failed to resolve source metadata for docker.io/library/python:3.11-slim: failed to do request: Head "https://registry-1.docker.io/v2/library/python/manifests/3.11-slim": Forbidden
ERROR: failed to build: failed to solve: node:22-alpine: failed to resolve source metadata for docker.io/library/node:22-alpine: failed to do request: Head "https://registry-1.docker.io/v2/library/node/manifests/22-alpine": Forbidden
```

This is a restriction of the verification workspace, not a finding about the Dockerfiles: they are neither shown to work nor shown to be wrong. No image exists and no container was ever started. Nothing was done to get around the restriction. The only Docker-related checks that passed are static: `docker compose config -q` accepts the compose file and refuses it without `ENERGIQ_SECRET_KEY`, and `cfn-lint` finds nothing in the two CloudFormation templates.

**Unverified deployment items** (none of these has been run or tested):

* The Docker runtime: both image builds, `docker compose up`, the container health check, the non-root user (uid 10001), file permissions on the mounted volumes and the read-only application layer.
* The Nginx configuration (`docker/nginx.conf`); no nginx binary was available to check even its syntax.
* Every AWS resource: ECR, ECS Fargate, EFS, RDS, the ALB, Secrets Manager and the CloudWatch alarms. Nothing was created; the templates passed `cfn-lint` only.
* GitHub Actions: the CI and deployment workflows have never run.
* Windows and macOS; behaviour under load; other PostgreSQL versions; a managed PostgreSQL (Amazon RDS).

The application is a locally verified implementation (SQLite and PostgreSQL 16, real server, real browser). It has not been deployed to a production environment, and no document should say that it has.

## 2. Local development (Windows, macOS, Linux)

> **Simplest route.** On Windows, double-click `RUN_PROJECT.bat`; elsewhere `./run_project.sh` or `python run_energiq.py` (see [`START_HERE.md`](../START_HERE.md)). The launcher creates `.venv`, installs what is missing, starts the backend and the web app on `127.0.0.1`, loads the bundled communities and prints the address and a per-installation administrator password. The manual steps below remain valid. The `.bat` files have not been run on Windows (see [`FINAL_TEST_REPORT.md`](../FINAL_TEST_REPORT.md) section 8); `.github/workflows/windows-launcher.yml` can run them on a GitHub Windows computer.

Requirements: Python 3.11, Node.js 22, 8 GB RAM, no GPU.

```
python -m venv .venv
.venv\Scripts\activate                      (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
set ENERGIQ_ENV=dev                         (Linux/macOS: export ...)
set ENERGIQ_ADMIN_EMAIL=admin@example.com
set ENERGIQ_ADMIN_PASSWORD=choose-a-long-password-1
uvicorn backend.app.main:create_app --factory --reload --port 8000

cd frontend
npm ci
npm run dev                                 (http://localhost:5173, proxies /api to port 8000)
```

Development uses SQLite (`data/energiq.db`, created automatically). The LSTM benchmark scripts additionally need `pip install -r requirements-research.txt` (PyTorch CPU).

## 3. Local production-like stack (Docker Compose)

```
copy .env.example .env                      (fill POSTGRES_PASSWORD and ENERGIQ_SECRET_KEY)
docker compose up --build
```

Serves the UI on `http://localhost:8080`; nginx proxies `/api` to the API container, which waits for PostgreSQL, applies Alembic migrations (`docker/backend-entrypoint.sh`) and starts one Uvicorn worker. Data lives in the named volumes `pgdata` and `appdata`. *This procedure is documented but has never been executed: the image builds it starts with failed in the verification workspace because Docker Hub answered `Forbidden` for the base images (§1b).*

**First start of the society module.** The image carries the processed communities (`/app/data/society/processed`, read-only) and their saved evaluation files and models (`/app/artifacts/society`, read-only). On the first start the entrypoint copies the second folder onto the volume (`/data/society`, about 71 MB when built from the delivered ZIP, which contains deployed models for Fox and Rat only; a working copy that has trained all seven communities is about 216 MB); later starts leave it alone, because uploaded societies are trained and stored there. The database starts empty: sign in as the administrator and use *Society admin → Import bundled communities* (or `POST /api/v1/admin/societies/import-bundled`); on PostgreSQL this took 34 s for all seven communities in the run of §1a. Without that step the society pages list no community.

## 4. Database migrations

```
alembic -c backend/alembic.ini upgrade head          # uses ENERGIQ_DATABASE_URL
alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
```

`dev` and `test` environments create tables automatically; **`prod` never does**, it expects `upgrade head`. A test checks that the migration builds exactly the schema the models describe and that it can be downgraded (SQLite and PostgreSQL 16).

## 5. AWS (configuration only)

Two templates, deployed in order, with the AWS CLI or the manual GitHub workflow (`deploy-aws.yml`, `workflow_dispatch` only).

1. `ecr.yaml`: two image repositories (immutable tags, scan on push, lifecycle policy, retained on stack deletion).
2. `energiq-stack.yaml`: VPC with two public and two private subnets (no NAT gateway); ALB (HTTPS only if you pass an ACM certificate ARN, otherwise HTTP with a stated warning); ECS Fargate services (API ×1, web ×2); RDS PostgreSQL 16 (encrypted, 7-day backups, not publicly accessible, password generated and held by RDS in Secrets Manager); EFS (encrypted) for uploads and models; generated JWT secret in Secrets Manager; log groups; alarms (API 5xx, no healthy API task, database CPU and free storage) to an SNS topic.

Before any real use:

* Confirm the PostgreSQL minor version (`aws rds describe-db-engine-versions --engine postgres`) and adjust `EngineVersion`.
* Supply a certificate; restrict `AllowedIngressCidr`; consider `DbMultiAz=true`.
* The stack creates billable resources (ALB, Fargate tasks, RDS, EFS, log storage). Estimate with the AWS Pricing Calculator first; delete the stack when finished (the database takes a final snapshot and the EFS file system and repositories are retained and must be deleted by hand).
* The API service is intentionally limited to one task (see `docs/13_limitations.md`).

No stack was created; no cost was incurred.

## 6. Configuration reference

All variables use the `ENERGIQ_` prefix.

(`SOCIETY_SEED_DIR` is the one exception: it is read only by `docker/backend-entrypoint.sh`, which copies that folder to `ENERGIQ_SOCIETY_DIR` on the first start. In the image it is `/app/artifacts/society`.)

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `dev` | `dev`, `test` or `prod`. `prod` disables `/docs`, enables HSTS and refuses unsafe settings |
| `DATABASE_URL` | `sqlite:///./data/energiq.db` | `postgresql+psycopg://user:pw@host:5432/energiq` in production (the image can also assemble it from `DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT`) |
| `SECRET_KEY` | development placeholder | ≥ 32 random characters in `prod` |
| `ACCESS_TOKEN_MINUTES` | 60 | JWT lifetime |
| `CORS_ORIGINS` | localhost dev origins | JSON list; `*` refused in `prod` |
| `ALLOW_REGISTRATION` | true | Set false to create users only through the administrator |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | unset | If both set, an administrator is created on first start; change the password afterwards |
| `UPLOAD_DIR`, `MODELS_DIR` | `data/uploads`, `artifacts/models` | Must be on persistent storage |
| `SOCIETY_DATA_DIR` | `data/society/processed` | Processed communities that "Import bundled communities" loads (read only). In the image: `/app/data/society/processed`. If `societies.json` is missing there, the import answers 404 |
| `SOCIETY_DIR` | `artifacts/society` | Evaluation files and deployed models of the societies; **written** when an uploaded society is trained, so it must be on persistent storage. In the image: `/data/society` |
| `MAX_UPLOAD_MB` | 50 | The nginx limit is 210 MB |
| `TRUST_PROXY`, `TRUSTED_PROXY_HOPS` | false, 1 | Enable only behind proxies you control |
| `JOB_WORKERS` | 2 | Background threads |
| `METRICS_ENABLED` | true | Serves `/metrics`; do not expose it publicly (neither nginx nor the ALB rules route it) |
