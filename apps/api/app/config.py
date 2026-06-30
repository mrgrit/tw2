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
    # 표시 타임존 — 기본 Asia/Seoul(UTC+9). 저장/전송은 UTC 유지, 사람용 표기만 KST.
    tz: str = Field("Asia/Seoul", alias="TUBEWAR_TZ")

    database_url: str = Field(
        "postgresql+asyncpg://tubewar:tubewar@127.0.0.1:5435/tubewar",
        alias="DATABASE_URL",
    )

    # 시나리오 미션 IP 치환 기준값 — 학생이 인프라 미등록 시 폴백.
    # 배포 환경마다 다르면 env 로 override. (기본=el34 기준 랩 IP)
    ref_target_ip: str = Field("192.168.0.151", alias="TUBEWAR_REF_TARGET_IP")
    ref_attacker_ip: str = Field("192.168.0.202", alias="TUBEWAR_REF_ATTACKER_IP")
    ref_web_entry: str = Field("192.168.0.161", alias="TUBEWAR_REF_WEB_ENTRY")

    six_default_ssh_user: str = Field("ccc", alias="SIX_DEFAULT_SSH_USER")
    six_default_ssh_pass: str = Field("ccc", alias="SIX_DEFAULT_SSH_PASS")
    six_default_bastion_key: str = Field("ccc-api-key-2026", alias="SIX_DEFAULT_BASTION_KEY")

    llm_base_url: str = Field("http://127.0.0.1:11434", alias="LLM_BASE_URL")
    llm_model: str = Field("gemma3:4b", alias="LLM_MODEL")

    admin_email: str = Field("admin@tubewar.app", alias="ADMIN_EMAIL")
    admin_password: str = Field("change-me-on-first-login", alias="ADMIN_PASSWORD")
    admin_name: str = Field("admin", alias="ADMIN_NAME")

    # ── Google 로그인 (OAuth2 / GIS ID 토큰) ──
    # GOOGLE_CLIENT_ID 가 비어 있으면 구글 로그인 비활성(프론트 버튼도 안 뜸).
    google_client_id: str = Field("", alias="GOOGLE_CLIENT_ID")
    # 허용 도메인(예: ync.ac.kr). 비우면 모든 구글 계정 허용.
    google_allowed_domain: str = Field("", alias="GOOGLE_ALLOWED_DOMAIN")
    # 첫 로그인 시 학생 계정 자동 생성 여부.
    google_auto_provision: bool = Field(True, alias="GOOGLE_AUTO_PROVISION")


@lru_cache
def get_settings() -> Settings:
    return Settings()
