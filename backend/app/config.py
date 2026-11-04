"""Application settings, read from environment variables (prefix ENERGIQ_) or a local .env file.

Secrets are never hard-coded. In ``prod`` the app refuses to start with the development secret.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENERGIQ_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev | test | prod
    database_url: str = "sqlite:///./data/energiq.db"
    secret_key: str = DEV_SECRET
    access_token_minutes: int = 60
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    allow_registration: bool = True
    admin_email: str | None = None
    admin_password: str | None = None

    upload_dir: Path = Path("data/uploads")
    models_dir: Path = Path("artifacts/models")
    reports_dir: Path = Path("artifacts/reports")
    sample_dataset: Path = Path("data/sample/uci_hourly_2009_sample.csv")
    max_upload_mb: int = 50

    jobs_sync: bool = False  # run jobs inline (tests)
    job_workers: int = 2
    trust_proxy: bool = False
    trusted_proxy_hops: int = 1  # number of reverse proxies in front of the API that append to X-Forwarded-For
    metrics_enabled: bool = True

    login_per_minute: int = 10
    register_per_hour: int = 10
    upload_per_hour: int = 30

    @field_validator("env")
    @classmethod
    def _env(cls, v: str) -> str:
        if v not in {"dev", "test", "prod"}:
            raise ValueError("env must be dev, test or prod")
        return v

    def validate_for_runtime(self) -> None:
        if self.env == "prod":
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                raise RuntimeError("ENERGIQ_SECRET_KEY must be set to a random value of at least 32 characters in prod")
            if "*" in self.cors_origins:
                raise RuntimeError("Wildcard CORS origins are not allowed in prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()
