"""FastAPI application factory.

Run locally:  uvicorn backend.app.main:create_app --factory --reload
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select, text

from .api import admin, anomalies, auth, datasets, ml, optimize, reports
from .config import Settings, get_settings
from .db import Database
from .models import User
from .security import RateLimiter, hash_password
from .services.core import JobRunner, Metrics, job_counts

log = logging.getLogger("energiq")
API_PREFIX = "/api/v1"


def _seed_admin(db: Database, settings: Settings) -> None:
    if not (settings.admin_email and settings.admin_password):
        return
    with db.session() as s:
        email = settings.admin_email.strip().lower()
        if s.scalar(select(User.id).where(User.email == email)) is None:
            s.add(User(email=email, full_name="Administrator", password_hash=hash_password(settings.admin_password), role="admin"))
            s.commit()
            log.info("seeded administrator account %s", email)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_runtime()
    db = Database(settings.database_url)
    if settings.env in {"dev", "test"}:
        db.create_all()  # production schema comes from `alembic upgrade head`
    runner = JobRunner(db, settings.job_workers, sync=settings.jobs_sync)
    runner.recover()
    _seed_admin(db, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        runner.shutdown()

    app = FastAPI(title="EnergiQ AI API", version="1.0.0", lifespan=lifespan,
                  description="Energy forecasting, anomaly detection and optimisation platform.",
                  docs_url="/docs" if settings.env != "prod" else None, redoc_url=None,
                  openapi_url="/openapi.json" if settings.env != "prod" else None)
    app.state.settings, app.state.db, app.state.runner = settings, db, runner
    app.state.limiter, app.state.metrics = RateLimiter(), Metrics()

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
                       expose_headers=["X-Request-ID", "Retry-After"])

    @app.middleware("http")
    async def observe(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled error rid=%s path=%s", rid, request.url.path)
            response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        route = request.scope.get("route")
        template = getattr(route, "path", None) or ("unmatched" if response.status_code in (404, 405) else request.url.path)
        if request.url.path.startswith(API_PREFIX) and template != "unmatched" and not template.startswith(API_PREFIX):
            template = API_PREFIX + template  # sub-router paths are stored relative to their prefix
        app.state.metrics.observe(request.method, template, response.status_code, time.perf_counter() - t0)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(API_PREFIX):
            response.headers["Cache-Control"] = "no-store"
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if settings.env == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    for r in (auth.router, datasets.router, ml.router, anomalies.router, optimize.router, reports.router, admin.router):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        try:
            with db.session() as s:
                s.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
        return {"status": "ok", "database": "up", "environment": settings.env}

    if settings.metrics_enabled:
        @app.get("/metrics", include_in_schema=False)
        def metrics():
            jobs = job_counts(db)
            extra = ["# TYPE energiq_jobs gauge"] + [f'energiq_jobs{{status="{k}"}} {v}' for k, v in sorted(jobs.items())]
            return PlainTextResponse(app.state.metrics.prometheus(extra), media_type="text/plain; version=0.0.4")

    return app

