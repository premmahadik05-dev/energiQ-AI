"""Shared helpers for routers: settings access, ownership checks, audit shortcut."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Dataset, Job, ModelVersion, User
from ..security import client_ip, current_user_dep, get_session, require_roles
from ..services.core import audit

WRITERS = require_roles("analyst", "admin")


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def runner_of(request: Request):
    return request.app.state.runner


def ip_of(request: Request) -> str:
    s = request.app.state.settings
    return client_ip(request, s.trust_proxy, s.trusted_proxy_hops)


def owned_dataset(db: Session, user: User, dataset_id: int) -> Dataset:
    ds = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user.id))
    if ds is None:  # 404 (not 403) so other users' ids are not revealed
        raise HTTPException(404, "Dataset not found")
    return ds


def owned_model(db: Session, user: User, model_id: str) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.id == model_id, ModelVersion.owner_id == user.id))
    if mv is None:
        raise HTTPException(404, "Model not found")
    return mv


def owned_job(db: Session, user: User, job_id: int) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.owner_id == user.id))
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def active_or_given_model(db: Session, user: User, dataset_id: int, model_id: str | None) -> ModelVersion:
    if model_id:
        mv = owned_model(db, user, model_id)
        if mv.dataset_id != dataset_id:
            raise HTTPException(422, "That model was trained on a different dataset")
        return mv
    mv = db.scalar(select(ModelVersion).where(ModelVersion.dataset_id == dataset_id, ModelVersion.owner_id == user.id,
                                              ModelVersion.is_active.is_(True)))
    if mv is None:
        raise HTTPException(409, "No active model for this dataset; train one first")
    return mv


__all__ = ["Depends", "WRITERS", "audit", "current_user_dep", "get_session", "settings_of", "runner_of", "ip_of",
           "owned_dataset", "owned_model", "owned_job", "active_or_given_model"]
