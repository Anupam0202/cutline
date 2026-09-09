from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


class ConfigurationError(RuntimeError):
    """Raised when deployment configuration is incomplete or unsafe."""


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    mode: Literal["fixture", "live"]
    data_backend: Literal["memory", "firestore"]
    google_cloud_project: str
    google_cloud_location: str
    model_id: str
    parallel_api_key: str
    session_secret: str
    cookie_secure: bool
    allowed_hosts: tuple[str, ...]
    project_ttl_hours: int
    provider_timeout_seconds: int
    max_body_bytes: int
    max_projects_per_session: int

    @property
    def live_ready(self) -> bool:
        return self.mode == "live"

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.getenv("APP_MODE", "fixture").strip().lower()
        if mode not in {"fixture", "live"}:
            raise ConfigurationError("APP_MODE must be fixture or live")

        default_backend = "firestore" if mode == "live" else "memory"
        backend = os.getenv("DATA_BACKEND", default_backend).strip().lower()
        if backend not in {"memory", "firestore"}:
            raise ConfigurationError("DATA_BACKEND must be memory or firestore")

        hosts = tuple(
            item.strip()
            for item in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            if item.strip()
        )
        if not hosts:
            raise ConfigurationError("ALLOWED_HOSTS must include at least one host")

        settings = cls(
            mode=mode,  # type: ignore[arg-type]
            data_backend=backend,  # type: ignore[arg-type]
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip(),
            model_id=os.getenv("MODEL_ID", "gemini-3.5-flash").strip(),
            parallel_api_key=os.getenv("PARALLEL_API_KEY", "").strip(),
            session_secret=os.getenv("SESSION_SECRET", "local-development-only-change-me").strip(),
            cookie_secure=_flag("COOKIE_SECURE", mode == "live"),
            allowed_hosts=hosts,
            project_ttl_hours=_integer("PROJECT_TTL_HOURS", 72, 1, 720),
            provider_timeout_seconds=_integer("PROVIDER_TIMEOUT_SECONDS", 30, 5, 90),
            max_body_bytes=_integer("MAX_BODY_BYTES", 32_768, 1_024, 262_144),
            max_projects_per_session=_integer("MAX_PROJECTS_PER_SESSION", 5, 1, 25),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.mode == "live":
            missing = []
            if not self.google_cloud_project:
                missing.append("GOOGLE_CLOUD_PROJECT")
            if not self.google_cloud_location:
                missing.append("GOOGLE_CLOUD_LOCATION")
            if not self.model_id:
                missing.append("MODEL_ID")
            if not self.parallel_api_key:
                missing.append("PARALLEL_API_KEY")
            if len(self.session_secret) < 32:
                missing.append("SESSION_SECRET (minimum 32 characters)")
            if self.data_backend != "firestore":
                missing.append("DATA_BACKEND=firestore")
            if not self.cookie_secure:
                missing.append("COOKIE_SECURE=true")
            if missing:
                raise ConfigurationError("Live configuration is incomplete: " + ", ".join(missing))

        if self.data_backend == "firestore" and not self.google_cloud_project:
            raise ConfigurationError("Firestore requires GOOGLE_CLOUD_PROJECT")
