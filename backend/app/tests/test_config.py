import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_settings_reject_unsafe_defaults():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_production_settings_accept_explicit_secure_configuration():
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="sufficiently-long-example-secret-that-is-not-a-real-secret",
        database_url="postgresql+psycopg://user:password@db.example.test:5432/taskflow",
        cors_origins="https://app.example.test",
        allowed_hosts="api.example.test",
    )
    assert settings.app_env == "production"
    assert settings.cors_origin_list == ["https://app.example.test"]
    assert settings.allowed_host_list == ["api.example.test"]


def test_vercel_requires_a_scheduler_secret(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValidationError, match="REMINDER_CRON_SECRET"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="sufficiently-long-example-secret-that-is-not-a-real-secret",
            database_url="postgresql+psycopg://user:password@db.example.test:5432/taskflow",
            cors_origins="https://app.example.test",
            allowed_hosts="api.example.test",
        )
