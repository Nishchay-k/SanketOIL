"""Environment-based runtime configuration for local and hosted deployments."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


def sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if os.getenv("APP_ENV", "development").strip().lower() == "production" and url.startswith("postgresql+psycopg://"):
        parts = urlsplit(url)
        parameters = parse_qsl(parts.query, keep_blank_values=True)
        sslmodes = [value.lower() for name, value in parameters if name.lower() == "sslmode"]
        if not sslmodes or any(mode in {"", "disable", "allow", "prefer"} for mode in sslmodes):
            parameters = [(name, value) for name, value in parameters if name.lower() != "sslmode"]
            parameters.append(("sslmode", "require"))
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(parameters), parts.fragment))
    return url


class Settings:
    def __init__(self) -> None:
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/sanket",
        ).strip()
        self.cors_origins = [item.strip() for item in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
        ).split(",") if item.strip()]
        self.auth_mode = os.getenv("AUTH_MODE", "demo").strip().lower()
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
        self.storage_backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
        self.storage_bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "sanket-documents").strip()
        self.seed_demo_data = self._boolean("SEED_DEMO_DATA", self.app_env == "development")
        self.auto_create_schema = self._boolean("AUTO_CREATE_SCHEMA", self.app_env != "production")
        self.vector_dimensions = int(os.getenv("VECTOR_DIMENSIONS", "384"))
        self.dataset_label = os.getenv("DATASET_LABEL", "development").strip() or "development"
        self.embedding_model = os.getenv("NWIS_EMBEDDING_MODEL", "").strip()
        self.upload_max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(12 * 1024 * 1024)))
        self.stream_poll_seconds = float(os.getenv("STREAM_POLL_SECONDS", "2"))
        self.port = int(os.getenv("PORT", os.getenv("NWIS_PORT", "8000")))

    @staticmethod
    def _boolean(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def supabase_jwks_url(self) -> str:
        return self.supabase_url + "/auth/v1/.well-known/jwks.json" if self.supabase_url else ""

    def validate(self) -> None:
        if self.auth_mode not in {"demo", "supabase"}:
            raise RuntimeError("AUTH_MODE must be 'demo' or 'supabase'.")
        if self.storage_backend not in {"local", "supabase"}:
            raise RuntimeError("STORAGE_BACKEND must be 'local' or 'supabase'.")
        if self.vector_dimensions < 1:
            raise RuntimeError("VECTOR_DIMENSIONS must be a positive integer.")
        if self.upload_max_bytes < 1:
            raise RuntimeError("MAX_UPLOAD_BYTES must be positive.")
        if self.is_production:
            if not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise RuntimeError("Production requires DATABASE_URL to point to PostgreSQL.")
            if self.auth_mode != "supabase":
                raise RuntimeError("Production requires AUTH_MODE=supabase.")
            if self.storage_backend != "supabase":
                raise RuntimeError("Production requires STORAGE_BACKEND=supabase.")
            if not (self.supabase_url and self.supabase_anon_key and self.supabase_service_role_key):
                raise RuntimeError("Production requires SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
