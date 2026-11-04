# 12. Deployment guide and deployment status

## 1. Status ladder (what has really been done)

| Level | Meaning | Status in this project |
|---|---|---|
| 1. Implemented locally | Runs and is tested on a development machine | **Yes**: API, ML engine and (see the verification matrix) the web UI run and are tested, on Python 3.11 with SQLite and with PostgreSQL 16 |
| 2. Docker-tested | Images built and run as containers | **No.** Dockerfiles and `docker-compose.yml` are written and `docker compose config` accepts the compose file, but the images were **not built or run**: the container runtime starts in the build workspace but cannot pull base images (registry blocked by the workspace's network policy). The CI workflow builds both images and smoke-tests the API image on GitHub-hosted runners; that job has not run either, because the repository has not been pushed. |
| 3. Cloud-configured | Infrastructure-as-code and pipeline files exist and pass static checks | **Yes**: `infrastructure/aws/ecr.yaml` and `energiq-stack.yaml` pass `cfn-lint`; `.github/workflows/ci.yml` and `deploy-aws.yml` parse as valid YAML |
| 4. Actually deployed | A live environment exists | **No.** No AWS account or resources were used. |
| 5. Independently verified | Someone other than the author tested it | **No.** |

Nothing in this repository should be described as "deployed on AWS" or "Docker-tested". Any claim must stay at the level reached above.

## 2. Local development (Windows, macOS, Linux)

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

Serves the UI on `http://localhost:8080`; nginx proxies `/api` to the API container, which waits for PostgreSQL, applies Alembic migrations (`docker/backend-entrypoint.sh`) and starts one Uvicorn worker. Data lives in the named volumes `pgdata` and `appdata`. *This procedure is documented but was not executed here (see §1).*

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
| `MAX_UPLOAD_MB` | 50 | The nginx limit is 210 MB |
| `TRUST_PROXY`, `TRUSTED_PROXY_HOPS` | false, 1 | Enable only behind proxies you control |
| `JOB_WORKERS` | 2 | Background threads |
| `METRICS_ENABLED` | true | Serves `/metrics`; do not expose it publicly (neither nginx nor the ALB rules route it) |
