"""런타임 설정 — 환경변수에서 로드."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# tubewar repo root 의 .env 만 읽도록 절대 경로로 고정.
# (CWD 의 .env 를 잡아 다른 프로젝트 설정이 leak 되는 문제 방지)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_prefix="",
        extra="ignore",
    )

    api_host: str = Field("0.0.0.0", alias="TUBEWAR_API_HOST")
    api_port: int = Field(9200, alias="TUBEWAR_API_PORT")
    api_key: str = Field("tubewar-api-key-2026", alias="TUBEWAR_API_KEY")
    jwt_secret: str = Field(
        "dev-secret-change-me-in-prod-please-32-chars",
        alias="TUBEWAR_JWT_SECRET",
    )
    jwt_expires_hours: int = Field(12, alias="TUBEWAR_JWT_EXPIRES_HOURS")

    database_url: str = Field(
        "postgresql+asyncpg://tubewar:tubewar@127.0.0.1:5435/tubewar",
        alias="DATABASE_URL",
    )

    six_default_ssh_user: str = Field("ccc", alias="SIX_DEFAULT_SSH_USER")
    six_default_ssh_pass: str = Field("ccc", alias="SIX_DEFAULT_SSH_PASS")
    six_default_bastion_key: str = Field("ccc-api-key-2026", alias="SIX_DEFAULT_BASTION_KEY")

    llm_base_url: str = Field("http://127.0.0.1:11434", alias="LLM_BASE_URL")
    llm_model: str = Field("gemma3:4b", alias="LLM_MODEL")

    admin_email: str = Field("admin@tubewar.local", alias="ADMIN_EMAIL")
    admin_password: str = Field("change-me-on-first-login", alias="ADMIN_PASSWORD")
    admin_name: str = Field("admin", alias="ADMIN_NAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()
