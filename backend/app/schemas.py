"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    full_name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserPatch(BaseModel):
    role: Literal["admin", "analyst", "viewer"] | None = None
    is_active: bool | None = None


# ----------------------------------------------------------------------------- datasets
class DatasetOut(ORM):
    id: int
    name: str
    original_filename: str
    status: str
    error: str | None = None
    quality_score: float | None = None
    hours: int
    valid_hours: int
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    created_at: datetime
    config: dict[str, Any] = {}


class DatasetDetail(DatasetOut):
    report: dict[str, Any] = {}


class JobOut(ORM):
    id: int
    kind: str
    status: str
    progress: float
    message: str
    dataset_id: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class UploadAccepted(BaseModel):
    dataset: DatasetOut
    job: JobOut


class ReadingsOut(BaseModel):
    dataset_id: int
    resolution: str
    points: list[dict[str, Any]]


# ----------------------------------------------------------------------------- models / forecasts
class TrainIn(BaseModel):
    activate: bool = True


class ModelOut(ORM):
    id: str
    dataset_id: int
    family: str
    is_active: bool
    train_rows: int
    train_end: datetime | None = None
    created_at: datetime
    evaluation: dict[str, Any] = {}
    explanation: dict[str, Any] = {}


class ForecastIn(BaseModel):
    dataset_id: int
    model_id: str | None = None
    origin: datetime | None = None


class ForecastOut(ORM):
    id: int
    dataset_id: int
    model_id: str
    origin: datetime
    points: list[dict[str, Any]]
    origin_value_missing: bool
    created_at: datetime


class LocalExplainIn(BaseModel):
    model_id: str
    horizon: int = Field(ge=1, le=24)
    origin: datetime | None = None


# ----------------------------------------------------------------------------- anomalies
class AnomalyRunIn(BaseModel):
    sensitivity: Literal["low", "medium", "high"] = "medium"


class AnomalyOut(ORM):
    id: int
    run_id: int
    dataset_id: int
    start_ts: datetime
    end_ts: datetime
    hours: int
    types: list[str]
    severity: str
    severity_level: int
    peak_ts: datetime
    peak_value_kw: float | None
    expected_kw: float | None
    peak_excess_ratio: float | None
    explanation: str
    acknowledged: bool
    acknowledged_at: datetime | None = None


# ----------------------------------------------------------------------------- optimisation
class TariffIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(min_length=1, max_length=8)
    weekday_rates: list[float] = Field(min_length=24, max_length=24)
    weekend_rates: list[float] = Field(min_length=24, max_length=24)
    daily_fixed_charge: float = Field(default=0.0, ge=0, le=1_000_000)

    @field_validator("weekday_rates", "weekend_rates")
    @classmethod
    def _rates(cls, v: list[float]) -> list[float]:
        if any((x < 0 or x > 1_000_000 or x != x) for x in v):
            raise ValueError("rates must be finite numbers between 0 and 1,000,000")
        return v


class TariffOut(ORM):
    id: int | str
    name: str
    currency: str
    weekday_rates: list[float]
    weekend_rates: list[float]
    daily_fixed_charge: float
    is_demo: bool = False
    note: str = ""


class CostIn(BaseModel):
    dataset_id: int
    tariff_id: int | str = "demo"
    start: datetime | None = None
    end: datetime | None = None


class RecommendIn(BaseModel):
    dataset_id: int
    tariff_id: int | str = "demo"
    model_id: str | None = None


class ScheduleIn(BaseModel):
    dataset_id: int | None = None
    tariff_id: int | str = "demo"
    model_id: str | None = None
    duration_h: int = Field(ge=1, le=24)
    power_kw: float = Field(gt=0, le=1000)
    start_after: datetime | None = None


class NotificationOut(ORM):
    id: int
    kind: str
    message: str
    link: str
    is_read: bool
    created_at: datetime


class AuditOut(ORM):
    id: int
    user_id: int | None
    action: str
    resource_type: str
    resource_id: str
    ip: str
    detail: dict[str, Any]
    ts: datetime
