"""기존 DB 호환 경량 마이그레이션 (alembic 미도입 경로).

신규 테이블(cohorts, cohort_memberships)은 `Base.metadata.create_all` 이 자동 생성한다.
하지만 **기존 테이블에 추가된 컬럼**(`battles.cohort_id`)은 create_all 이 ALTER 하지
않으므로, 부팅 시 1회 컬럼 존재 여부를 검사해 없으면 idempotent 하게 ADD COLUMN 한다.

이 방식으로 새 설치(create_all 로 전부 생성)와 기존 Postgres DB(컬럼만 추가) 모두를
호환한다. 본격적인 마이그레이션 관리가 필요해지면 alembic 으로 전환할 것
(rebuild §17 잔여항목).
"""
from __future__ import annotations
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

log = logging.getLogger(__name__)

# (table, column, DDL type) — 기존 테이블에 나중에 추가된 컬럼들.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("battles", "cohort_id", "INTEGER"),
    ("scenarios", "grader_profile_id", "INTEGER"),
    ("scenarios", "category", "VARCHAR(40)"),
    # 구글 로그인 — 기존 users 테이블에 추가. NOT NULL 은 DEFAULT 동반(기존 행 보강).
    ("users", "auth_provider", "VARCHAR(16) DEFAULT 'local' NOT NULL"),
    ("users", "google_sub", "VARCHAR(64)"),
    # 개인 GPU(Ollama) 서버 설정 — 드래그-질문 AI 튜터.
    ("users", "llm_url", "VARCHAR(255)"),
    ("users", "llm_model", "VARCHAR(120)"),
]


def ensure_added_columns(sync_conn: Connection) -> list[str]:
    """create_all 이 처리하지 못하는 '기존 테이블의 신규 컬럼'을 보강한다.

    `conn.run_sync(ensure_added_columns)` 형태로 호출. 반환=실제로 추가한 컬럼 목록.
    """
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    for table, column, ddl_type in _ADDED_COLUMNS:
        if table not in existing_tables:
            continue  # 테이블 자체가 없으면 create_all 이 새로 만들었을 것
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column in cols:
            continue
        sync_conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
        added.append(f"{table}.{column}")
        log.info("schema upgrade: added column %s.%s (%s)", table, column, ddl_type)
    return added
