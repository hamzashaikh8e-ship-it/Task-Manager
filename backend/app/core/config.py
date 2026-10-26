from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseSettings, root_validator, validator
from urllib.parse import urlsplit


class Settings(BaseSettings):
    app_name: str = "TaskFlow AI"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./taskflow.db"
    secret_key: str = "development-only-change-me"
    access_token_minutes: int = 60
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    log_level: str = "INFO"
    run_reminder_scheduler: bool = True
    reminder_cron_secret: str = ""
    priority_weight_deadline: float = 0.30
    priority_weight_importance: float = 0.25
    priority_weight_priority: float = 0.20
    priority_weight_time_fit: float = 0.15
    priority_weight_downstream: float = 0.10
    xp_task_completion: int = 10
    xp_focus_session: int = 5
    xp_focus_min_seconds: int = 300
    xp_level_size: int = 100

    @validator("app_env")
    def valid_app_env(cls, value):
        value = value.strip().lower()
        if value not in ("development", "test", "production"):
            raise ValueError("APP_ENV must be development, test, or production")
        return value

    @validator("access_token_minutes")
    def valid_token_lifetime(cls, value):
        if not 1 <= value <= 1440:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 1440")
        return value

    @validator("log_level")
    def valid_log_level(cls, value):
        value = value.strip().upper()
        if value not in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
            raise ValueError("LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG")
        return value

    @root_validator
    def validate_production_settings(cls, values):
        if values.get("app_env") != "production":
            return values
        secret = values.get("secret_key", "")
        if len(secret) < 32 or any(word in secret.lower() for word in ("replace", "change-me", "development", "placeholder")):
            raise ValueError("Production requires a non-placeholder SECRET_KEY of at least 32 characters")
        if not values.get("database_url", "").startswith("postgresql+psycopg://"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL using the installed psycopg driver")
        origins = [origin.strip() for origin in (values.get("cors_origins") or "").split(",") if origin.strip()]
        if not origins or any(origin == "*" or urlsplit(origin).scheme != "https" or not urlsplit(origin).netloc or urlsplit(origin).path not in ("", "/") or urlsplit(origin).query or urlsplit(origin).fragment for origin in origins):
            raise ValueError("Production CORS_ORIGINS must be explicit HTTPS origins")
        hosts = [host.strip() for host in (values.get("allowed_hosts") or "").split(",") if host.strip()]
        if not hosts or "*" in hosts or any(host in ("localhost", "127.0.0.1", "testserver") for host in hosts):
            raise ValueError("Production ALLOWED_HOSTS must list explicit public hostnames")
        if os.environ.get("VERCEL") == "1" and len(values.get("reminder_cron_secret", "")) < 32:
            raise ValueError("Vercel requires a REMINDER_CRON_SECRET of at least 32 characters")
        return values

    @property
    def cors_origin_list(self):
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self):
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    class Config:
        env_file = str(Path(__file__).resolve().parents[3] / ".env")
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()
