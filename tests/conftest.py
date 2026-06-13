"""테스트 전역 fixture — DB 격리 + rate-limit 격리.

conftest 는 pytest 가 어떤 test module 보다도 먼저 import 하므로, 여기서 환경을
강제로 고정해야 app.db 의 engine 이 실수로 운영 DB 를 잡는 것을 원천 차단한다.

⚠️ 중요(사고 방지): 과거 `dev.sh test`/수동 실행이 .env 를 source 하면 운영 DATABASE_URL
(예: .data/tubewar.sqlite3)이 환경에 노출되고, test 모듈의 `setdefault` 는 그 값을 덮지
못해 테이블 drop_all/create_all 픽스처가 **운영 DB 를 파괴**할 수 있었다. 그래서 여기서
운영값과 무관하게 항상 격리 DB 로 **강제 override** 한다. 의도적으로 다른 테스트 DB 를
쓰려면 TUBEWAR_TEST_DATABASE_URL 로 명시(opt-in)해야만 한다.
"""
from __future__ import annotations
import os

# 운영 DATABASE_URL 이 환경/.env 에 있어도 무시하고 격리 DB 로 강제 고정.
os.environ["DATABASE_URL"] = os.environ.get(
    "TUBEWAR_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"
)
# 테스트는 운영 .env 파일도 읽지 않도록(pydantic-settings env_file) 우회 — 환경변수 우선.
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")

# pytest 가 어떤 test module 을 먼저 import 해도 limiter 가 꺼진 상태로 기동.
os.environ.setdefault("TUBEWAR_RATE_LIMIT_DISABLE", "1")

# 제출 채점을 인라인(동기)으로 — 테스트 결정론. 운영은 미설정(비동기 백그라운드).
os.environ.setdefault("TUBEWAR_GRADE_SYNC", "1")

# 제출 트리거 피드백은 기본 off — 테스트가 claude CLI 서브프로세스를 띄우지 않게(개별 테스트가 opt-in).
os.environ.setdefault("TUBEWAR_SUBMISSION_FEEDBACK", "0")
