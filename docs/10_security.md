# 10. Security design, controls and evidence

Scope: the web application and API in this repository. Standards used as a checklist: OWASP Top 10 (2021) and OWASP API Security Top 10 (2023); neither is a certification and no external penetration test was performed.
Tests: `tests/integration/test_security.py` (16 tests), `test_api_core.py`, `test_api_ml.py`, `test_migrations.py`.

## 1. Controls and where they are verified

| Area | Control | Evidence |
|---|---|---|
| Passwords | argon2id (library defaults); 10–128 characters, letters and digits required, a short list of common passwords and trivially repetitive values refused; hashes never returned by any endpoint | `test_password_hashes_never_leave_the_server`, `test_api_core` |
| Login | Generic failure message; the same CPU time is spent for unknown e-mails as for wrong passwords (no timing oracle for account existence); 10 attempts/minute per IP and 5 per 5 minutes per IP+e-mail → 429 with `Retry-After` | `test_api_core` login tests |
| Tokens | HS256 JWT, `exp` and `sub` required, 60-minute lifetime, secret ≥ 32 random characters enforced in production; the user row is re-read on every request so a deactivated user or changed role takes effect immediately; token in the query string is rejected | `test_token_in_query_string_is_not_accepted`, tampering and expiry tests in `test_api_core` |
| Authentication coverage | Every `/api/v1` operation except register and login returns 401 without a token | `test_every_api_route_requires_authentication` (iterates the OpenAPI schema; ≥ 40 operations) |
| Authorisation | Roles `admin`, `analyst`, `viewer`. Viewer is read-only. Admin endpoints need admin. | `test_role_matrix_…` derives the expected access from the route dependencies and calls each restricted operation as each role |
| Object-level access | Every dataset, model, forecast, anomaly, tariff and notification lookup filters by `owner_id`; a foreign id returns **404**, not 403, so ids are not confirmable | `test_idor_on_tariffs_notifications_and_anomalies`, `test_api_core` ownership tests |
| Mass assignment | Registration ignores client-supplied `role` / `is_active` (always `analyst`); role changes are admin-only and audited; an admin cannot demote or deactivate themselves | `test_mass_assignment_cannot_set_role`, admin tests |
| Injection | Only parametrised SQLAlchemy queries; enum-like filters are regex-validated query parameters; a dataset named `x'; DROP TABLE datasets; --` is stored as plain text and the table survives | `test_injection_strings_are_data_not_code` |
| XSS | The API returns JSON with `default-src 'none'`; the downloadable HTML report escapes every user-controlled string and ships a CSP without scripts; the React UI never uses `dangerouslySetInnerHTML` | `test_report_escapes_user_text` |
| Uploads | Extension whitelist, streamed size cap, NUL/binary rejection, uuid file names, per-user storage directory, upload rate limit (30/hour) | `test_api_core` upload tests, `test_upload_rate_limit` |
| Path traversal | Benchmark figures are served from a fixed whitelist of group and file names | `test_api_ml` figure tests |
| Rate limiting | Registration 10/hour per IP, login as above, upload 30/hour per user | `test_register_rate_limit`, `test_upload_rate_limit` |
| Client IP | With `ENERGIQ_TRUST_PROXY=true`, the address is the entry *N* places from the **right** of `X-Forwarded-For` (N = `ENERGIQ_TRUSTED_PROXY_HOPS`, default 1). A client-forged left entry cannot dodge a limit. With the option off the header is ignored. | `test_forged_forwarded_for_…`, `test_client_ip_hops_unit` |
| Transport / headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and a restrictive CSP on API responses, HSTS in production; nginx adds a CSP for the UI | `test_security_headers_and_cors` |
| CORS | Explicit origin list, no credentials, only needed methods and headers; a foreign origin gets no CORS headers; wildcard refused in production | `test_security_headers_and_cors`, `test_api_core` |
| Error hygiene | Unhandled exceptions return `{"detail":"Internal server error","request_id":…}` (the details are only in the server log); job errors are filtered the same way | `test_internal_errors_do_not_leak_details`, `test_job_errors_hide_internal_exceptions` |
| Secrets | No secrets in the repository; `.env` is git-ignored; compose refuses to start without `POSTGRES_PASSWORD` and `ENERGIQ_SECRET_KEY`; on AWS the database password is generated and managed by RDS/Secrets Manager and injected as a container secret | `.gitignore`, `docker-compose.yml`, `infrastructure/aws/energiq-stack.yaml` |
| Audit | Registration, login success/failure, uploads, deletions, role changes, training, anomaly runs, tariff changes are written to `audit_events` with user, IP and resource | `test_api_core`, `GET /api/v1/admin/audit` |
| Containers | Non-root user (uid 10001), no build tools in the runtime image, one process, health check, read-only application code | `docker/backend.Dockerfile` (**not built here**, see §3) |
| Cloud network | Database and file system in subnets with no internet route, reachable only from the API security group; load balancer drops invalid header fields; EFS and RDS encrypted | `infrastructure/aws/energiq-stack.yaml` (cfn-lint clean; **not deployed**) |

## 2. Static and dependency scans (run in this project)

| Tool | Scope | Result |
|---|---|---|
| `bandit -r backend ml_engine -ll` | Python source, medium+ severity | **No issues.** With all severities: 1 low-severity note (B105) for the documented development placeholder secret, which production start-up rejects. |
| `pip-audit --path <Python 3.11 environment>` | The packages installed from `requirements*.txt` | **No known vulnerabilities found** (checked 2026-11-03 against the public vulnerability database the tool queries). |
| `ruff check .` | Lint (pycodestyle, pyflakes, bugbear, isort, pyupgrade) | Clean |
| `cfn-lint` | CloudFormation templates | Clean |
| `npm audit` | Front-end dependencies | See `docs/15_verification_matrix.md` |

A clean scan is the absence of *known* issues at one point in time, not proof of absence of vulnerabilities. The CI workflow repeats the scans on every push.

## 3. What was not done

* No external penetration test, no fuzzing campaign, no formal threat-modelling workshop.
* **Docker images were not built in this environment** (the container runtime starts, but the registry holding the base images is not reachable from the workspace), so the container hardening items above are reviewed, not machine-verified. The CI workflow builds and smoke-tests both images on GitHub-hosted runners.
* Nothing was deployed to AWS; the cloud controls are configuration that passed a linter.
* The login throttle, the sliding-window rate limiter and the token model are per process and stateless (no token revocation list, no refresh tokens): a stolen token works until it expires (60 min) unless the user is deactivated.
* Tokens are held in memory and `sessionStorage` by the UI, so a successful XSS could read them; mitigations are the CSP, the absence of `dangerouslySetInnerHTML`, and a short lifetime. Cookie-based sessions would remove that exposure at the cost of CSRF handling.
* TLS is terminated by the load balancer; without a certificate the AWS template serves HTTP and says so.

## 4. Privacy

Uploaded data is household electricity data and is personal data in many jurisdictions. It is stored per user, never shared between users, deletable by its owner (the delete endpoint removes readings, models and files), and never sent to a third party by the application. The bundled sample dataset is a one-year slice of a published research dataset (CC BY 4.0). There is no analytics or tracking code.
