"""Cross-cutting services: audit trail, notifications, background jobs and in-process metrics."""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import Database
from ..models import AuditEvent, Job, Notification, utcnow

log = logging.getLogger("energiq")

USER_FACING = (ValueError, KeyError, FileNotFoundError)


def audit(db: Session, user_id: int | None, action: str, ip: str = "", resource_type: str = "",
          resource_id: str | int = "", detail: dict | None = None) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, ip=ip, resource_type=resource_type,
                      resource_id=str(resource_id), detail=detail or {}))
    db.commit()


def notify(db: Session, owner_id: int, kind: str, message: str, link: str = "") -> None:
    db.add(Notification(owner_id=owner_id, kind=kind, message=message[:300], link=link))
    db.commit()


class JobContext:
    def __init__(self, db: Database, job_id: int):
        self._db, self.job_id = db, job_id

    def progress(self, fraction: float, message: str = "") -> None:
        with self._db.session() as s:
            s.execute(update(Job).where(Job.id == self.job_id).values(progress=max(0.0, min(1.0, fraction)), message=message[:255]))
            s.commit()


class JobRunner:
    """Runs jobs on a small thread pool (or inline in tests). State lives in the ``jobs`` table."""

    def __init__(self, db: Database, workers: int = 2, sync: bool = False):
        self.db, self.sync = db, sync
        self.pool = None if sync else ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")

    def recover(self) -> int:
        """Jobs left queued/running by a previous process can never finish; mark them failed."""
        with self.db.session() as s:
            res = s.execute(update(Job).where(Job.status.in_(("queued", "running"))).values(
                status="failed", error="Interrupted by a server restart", finished_at=utcnow()))
            s.commit()
            return res.rowcount or 0

    def create(self, s: Session, owner_id: int, kind: str, dataset_id: int | None, params: dict | None = None) -> Job:
        job = Job(owner_id=owner_id, dataset_id=dataset_id, kind=kind, params=params or {})
        s.add(job)
        s.commit()
        s.refresh(job)
        return job

    def submit(self, job_id: int, fn: Callable[[Session, JobContext], dict[str, Any]]) -> None:
        if self.sync:
            self._run(job_id, fn)
        else:
            self.pool.submit(self._run, job_id, fn)

    def _run(self, job_id: int, fn: Callable[[Session, JobContext], dict[str, Any]]) -> None:
        with self.db.session() as s:
            s.execute(update(Job).where(Job.id == job_id).values(status="running", started_at=utcnow(), progress=0.0))
            s.commit()
            try:
                result = fn(s, JobContext(self.db, job_id)) or {}
                s.execute(update(Job).where(Job.id == job_id).values(
                    status="succeeded", progress=1.0, result=result, finished_at=utcnow(), message="done"))
            except Exception as exc:  # noqa: BLE001 - every failure must end in a terminal job state
                s.rollback()
                shown = str(exc)[:480] if isinstance(exc, USER_FACING) or type(exc).__name__ == "IngestError" else "Internal error; see server logs"
                if shown == "Internal error; see server logs":
                    log.exception("job %s failed", job_id)
                s.execute(update(Job).where(Job.id == job_id).values(status="failed", error=shown, finished_at=utcnow()))
            s.commit()

    def shutdown(self) -> None:
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)


# ----------------------------------------------------------------------------- metrics
class Metrics:
    BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.latency_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self.latency_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self.recent: list[float] = []

    def observe(self, method: str, route: str, status_code: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, status_code)] += 1
            self.latency_sum[(method, route)] += seconds
            self.latency_count[(method, route)] += 1
            for b in self.BUCKETS:
                if seconds <= b:
                    self.latency_buckets[(method, route, b)] += 1
            self.recent.append(seconds)
            if len(self.recent) > 2000:
                del self.recent[:1000]

    def summary(self) -> dict:
        with self._lock:
            total = sum(self.requests.values())
            errors5 = sum(v for (_, _, s), v in self.requests.items() if s >= 500)
            errors4 = sum(v for (_, _, s), v in self.requests.items() if 400 <= s < 500)
            rec = sorted(self.recent)
            p = lambda q: rec[min(len(rec) - 1, int(q * len(rec)))] if rec else None  # noqa: E731
            return {"uptime_seconds": round(time.time() - self.started, 1), "requests_total": total,
                    "responses_5xx": errors5, "responses_4xx": errors4,
                    "latency_seconds": {"p50": p(0.5), "p95": p(0.95), "max": rec[-1] if rec else None, "window": len(rec)}}

    def prometheus(self, extra_lines: list[str] | None = None) -> str:
        lines = ["# HELP energiq_http_requests_total HTTP requests", "# TYPE energiq_http_requests_total counter"]
        with self._lock:
            for (m, r, s), v in sorted(self.requests.items()):
                lines.append(f'energiq_http_requests_total{{method="{m}",route="{r}",status="{s}"}} {v}')
            lines += ["# HELP energiq_http_request_duration_seconds Request latency", "# TYPE energiq_http_request_duration_seconds histogram"]
            for (m, r), c in sorted(self.latency_count.items()):
                for b in self.BUCKETS:
                    lines.append(f'energiq_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {self.latency_buckets[(m, r, b)]}')
                lines.append(f'energiq_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {c}')
                lines.append(f'energiq_http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {self.latency_sum[(m, r)]:.6f}')
                lines.append(f'energiq_http_request_duration_seconds_count{{method="{m}",route="{r}"}} {c}')
        lines += extra_lines or []
        return "\n".join(lines) + "\n"


def job_counts(db: Database) -> dict[str, int]:
    with db.session() as s:
        rows = s.execute(select(Job.status, Job.id)).all()
    out: dict[str, int] = defaultdict(int)
    for st, _ in rows:
        out[st] += 1
    return dict(out)
