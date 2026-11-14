"""SQLAlchemy models. Every user-scoped table carries ``owner_id`` (indexed) and is always queried with it."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # stored as naive UTC


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="analyst")  # admin | analyst | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="processing")  # processing | ready | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[dict] = mapped_column(JSON, default=dict)  # full ingestion report incl. quality
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hours: Mapped[int] = mapped_column(Integer, default=0)
    valid_hours: Mapped[int] = mapped_column(Integer, default=0)
    start_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    readings = relationship("Reading", cascade="all, delete-orphan", passive_deletes=True)


class Reading(Base):
    """Hourly canonical readings. The raw sub-hourly file stays on disk, not in the database."""

    __tablename__ = "readings"
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    value_kw: Mapped[float | None] = mapped_column(Float, nullable=True)  # NULL = missing hour
    valid_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24))  # ingest | train | anomaly
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | succeeded | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(255), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelVersion(Base):
    """A trained forecaster bundle: one XGBoost model per horizon 1..24 plus evaluation and explanation summaries."""

    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    family: Mapped[str] = mapped_column(String(24), default="xgboost")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    horizon_model_ids: Mapped[dict] = mapped_column(JSON, default=dict)  # "1" -> registry id
    train_rows: Mapped[int] = mapped_column(Integer, default=0)
    train_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_hash: Mapped[str] = mapped_column(String(32), default="")
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)  # holdout metrics vs baselines, residual quantiles
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)  # global SHAP summary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Forecast(Base):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), index=True)
    origin: Mapped[datetime] = mapped_column(DateTime)
    points: Mapped[list] = mapped_column(JSON, default=list)  # [{ts, kw, lower_kw, upper_kw, horizon}]
    origin_value_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnomalyRun(Base):
    __tablename__ = "anomaly_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    sensitivity: Mapped[str] = mapped_column(String(8), default="medium")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("anomaly_runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime)
    end_ts: Mapped[datetime] = mapped_column(DateTime)
    hours: Mapped[int] = mapped_column(Integer)
    types: Mapped[list] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(8))
    severity_level: Mapped[int] = mapped_column(Integer)
    peak_ts: Mapped[datetime] = mapped_column(DateTime)
    peak_value_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_excess_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_anomalies_dataset_start", "dataset_id", "start_ts"),)


class Tariff(Base):
    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(8))
    weekday_rates: Mapped[list] = mapped_column(JSON)
    weekend_rates: Mapped[list] = mapped_column(JSON)
    daily_fixed_charge: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_tariff_owner_name"),)


class RecommendationSnapshot(Base):
    __tablename__ = "recommendation_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    tariff_name: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(String(300))
    link: Mapped[str] = mapped_column(String(200), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # no FK: events outlive users
    action: Mapped[str] = mapped_column(String(40), index=True)
    resource_type: Mapped[str] = mapped_column(String(24), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ============================================================================= society level
# Societies are shared, read-only research data (real BDG2 meters or an admin-uploaded meter file), so these
# tables are not owner-scoped: every signed-in user may read them; only admins (and analysts for reports and
# acknowledgements) may change anything. Building ``source_id`` (the dataset's own identifier) is returned to
# admins only.


class Society(Base):
    __tablename__ = "societies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(160), default="")
    source_url: Mapped[str] = mapped_column(String(300), default="")
    license: Mapped[str] = mapped_column(String(200), default="")
    timezone: Mapped[str] = mapped_column(String(40), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hours: Mapped[int] = mapped_column(Integer, default=0)
    valid_hours: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ready")  # ready | failed
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # data card: cleaning rules and counts, provenance
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(24))  # pseudonymous label shown to everyone, e.g. FOX-B04
    source_id: Mapped[str] = mapped_column(String(120), default="")  # dataset identifier, admin only
    sub_use: Mapped[str] = mapped_column(String(80), default="")
    floor_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("society_id", "code", name="uq_building_society_code"),)


class Meter(Base):
    __tablename__ = "meters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(12), default="building")  # building | facility
    facility_category: Mapped[str | None] = mapped_column(String(24), nullable=True)  # lift | pump | streetlight | clubhouse | other
    meter_type: Mapped[str] = mapped_column(String(16), default="electricity")
    unit: Mapped[str] = mapped_column(String(8), default="kWh")  # energy per interval
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    valid_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("society_id", "code", name="uq_meter_society_code"),)


class ConsumptionRecord(Base):
    """Cleaned hourly energy per meter (kWh in that hour). NULL = invalid or missing; never filled."""

    __tablename__ = "consumption_records"
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    kwh: Mapped[float | None] = mapped_column(Float, nullable=True)


class SocietyHourly(Base):
    """Society total per hour (sum of the retained meters; NULL unless all are valid) with matched site weather."""

    __tablename__ = "society_hourly"
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_valid_meters: Mapped[int] = mapped_column(Integer, default=0)
    air_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class SocietyModel(Base):
    """The trained forecasting bundle of a society plus its measured evaluation (see ml_engine/society)."""

    __tablename__ = "society_models"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    artifact_key: Mapped[str] = mapped_column(String(80))  # folder under the society artifacts directory
    bundle: Mapped[dict] = mapped_column(JSON, default=dict)  # horizon -> family, band, selected-from horizon
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)  # protocol and per-horizon CV/test metrics
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)  # global SHAP summary
    peaks: Mapped[dict] = mapped_column(JSON, default=dict)  # daily-peak forecast evaluation
    trained_through: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ForecastResult(Base):
    """Held-out (test period) predictions of the selected model: real out-of-sample forecasts next to what happened."""

    __tablename__ = "forecast_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("society_models.id", ondelete="CASCADE"), index=True)
    horizon_h: Mapped[int] = mapped_column(Integer)
    origin: Mapped[datetime] = mapped_column(DateTime)
    target_ts: Mapped[datetime] = mapped_column(DateTime)
    actual_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_kw: Mapped[float] = mapped_column(Float)
    lower_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("ix_forecast_results_lookup", "society_id", "horizon_h", "target_ts"),)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(10), default="society")  # society | building
    start_ts: Mapped[datetime] = mapped_column(DateTime)
    end_ts: Mapped[datetime] = mapped_column(DateTime)
    hours: Mapped[int] = mapped_column(Integer)
    types: Mapped[list] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(8))
    severity_level: Mapped[int] = mapped_column(Integer)
    peak_ts: Mapped[datetime] = mapped_column(DateTime)
    peak_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    top_contributors: Mapped[list] = mapped_column(JSON, default=list)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (Index("ix_anomaly_events_society_start", "society_id", "start_ts"),)


class SocietyReport(Base):
    __tablename__ = "society_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    society_id: Mapped[int] = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # monthly | consumption | forecast | anomalies | cost | buildings
    format: Mapped[str] = mapped_column(String(8))  # pdf | csv
    title: Mapped[str] = mapped_column(String(160))
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    filename: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column(LargeBinary)
