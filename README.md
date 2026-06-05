# tubewar — 사이버 공방전 훈련 플랫폼

`6v6` 인프라 (https://github.com/mrgrit/6v6) 를 학생 PC 마다 1세트 배포해두고,
중앙 tubewar 서버가 학생 인프라 간 **공방전 (Red/Blue)** 을 시나리오/미션 단위로
관리·채점·시각화한다.

## 📖 매뉴얼

대상별 사용 설명서: **[docs/manuals.md](docs/manuals.md)**
([학생](docs/manual_student.md) · [교수](docs/manual_instructor.md) · [관리자](docs/manual_admin.md))

## 전체 그림

```
   ┌──────────────────────────────────────────────────────────┐
   │                  tubewar 중앙 서버                       │
   │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐    │
   │  │  api     │  │  ui      │  │  battle_engine       │    │
   │  │ FastAPI  │  │  React   │  │  scenarios / scoring │    │
   │  └──────────┘  └──────────┘  └──────────────────────┘    │
   │       │                                                   │
   └───────┼───────────────────────────────────────────────────┘
           │ SSH(2204/2202) + Bastion API(9100) + Portal(8000)
   ┌───────┴───────────────────────┐
   │                               │
   ▼                               ▼
┌──────────┐                  ┌──────────┐
│ 학생 A    │                  │ 학생 B   │
│ 6v6 VM   │  ◀──── 공방 ────▶ │ 6v6 VM   │
│ 13 cont. │                  │ 13 cont. │
└──────────┘                  └──────────┘
```

## 주요 기능

| 영역 | 설명 |
|------|------|
| 회원/인증 | 학생/관리자 계정. JWT. |
| 인프라 등록 | 학생이 자기 6v6 VM 의 외부 IP + 자격 증명 + Bastion API key 를 등록 → tubewar 가 헬스체크. |
| 공방전 모드 | **solo** (혼자 Red/Blue 둘 다) / **1v1** (Red vs Blue) / **n인** (자율 공방). |
| 시나리오 생성 | (Phase 4) 관리자가 Claude Code 에 "course3 1~3주차로 공방전" → 시나리오 + 미션 자동 생성. |
| Bastion 스크랩 | (Phase 5) 외부 침해사고/AI 위협 분석 → 스크랩 → 관리자 승인 → Claude Code 공방전 자동 생성. |
| 미션 검증 | (Phase 4) Claude Code 가 6v6 인프라에서 미션 실행 가능 여부 + 채점 기준 자동 작성. |
| 모니터링/채점 | 중앙 서버 (또는 Bastion) 가 SSH/API 로 진행 상황 폴링 → 채점 기준 통과 여부 판정. |
| 상황판 | 참가자/Red/Blue 별 점수, 클릭 시 채점 상세 (어느 룰로 몇 점) 표시. |
| 리더보드 | 공방전별 + 사용자 누적. |
| 관리자 페이지 | 진행중 공방전 → 강제 종료/삭제 + 히스토리. |

## 배포 / 운영 (학생 PC 단일 명령)

라이브러리·패키지 설치부터 서버 기동/정지까지 단일 제어 스크립트로 처리한다.
DB 는 sqlite(`.data/tubewar.sqlite3`) 라 **docker/postgres 불필요**, Java 는 OpenSearch
번들 JDK, node/npm 은 설치 시 자동 프로비저닝된다.

```bash
# 1) 최초 1회 — 라이브러리·패키지 전부 자동 설치 (system pkg + venv + npm + UI 빌드 + .env)
bash scripts/tubewar.sh install

# 2) 서버 올리기 (api + ui + SIEM)
bash scripts/tubewar.sh up            # 전체 스택
bash scripts/tubewar.sh up --no-siem  # OpenSearch/Dashboards 없이 api+ui 만
bash scripts/tubewar.sh up --dev      # ui 를 vite dev(자동 리로드)로

# 3) 운영
bash scripts/tubewar.sh status        # 서비스/포트/헬스
bash scripts/tubewar.sh restart       # 내렸다 올리기
bash scripts/tubewar.sh down          # 서버 내리기
bash scripts/tubewar.sh logs api      # 로그 (api|ui|opensearch|dashboards)
```

접속: UI `http://<host>:5173` · API `http://<host>:9200` · OpenSearch `:9201` · Dashboards `:5601`.
PID/로그는 `runtime/` (gitignore). 비밀값(`.env` 의 `ADMIN_PASSWORD` 등)은 운영 전 반드시 수정.

## 빠른 시작 (개발)

전제: docker, docker compose plugin, python ≥ 3.10, node ≥ 18.

```bash
git clone https://github.com/mrgrit/tubewar
cd tubewar

# 1) 의존성 + DB 컨테이너
bash scripts/setup.sh

# 2) 환경 변수
cp .env.example .env
# 필요한 값 수정 (특히 JWT_SECRET / ADMIN_PASSWORD)

# 3) 백엔드
bash scripts/dev.sh api      # http://127.0.0.1:9200

# 4) 프론트엔드 (다른 터미널)
bash scripts/dev.sh ui       # http://127.0.0.1:5173
```

## Phase 1 — 골격 (완료, 2026-05-07)

- [x] repo 골격 + git, FastAPI 백엔드, React UI, PostgreSQL docker-compose
- [x] 회원가입/로그인 (JWT) + 6v6 인프라 등록 + smoke 테스트
- [x] CCC battle_engine / battle_factory / 17 scenarios 이식

## Phase 7 — 관리자 대시보드 (완료, 2026-05-08)

- [x] 통계 / 진행중 공방전 강제 종료 / 사용자 role 토글 / 시나리오 archive
- [x] UI Admin 6 탭, 권한 체크 (self-demote 거부 등) tests/test_admin.py 통과

## Phase 6 — 모니터링 + 채점 detail + 리더보드 (완료, 2026-05-08)

- [x] BattleEvent.detail JSONB scoring evidence + UI "채점 근거 ▼" 펼치기
- [x] `/leaderboard/users` (총점/승/평균) + `/leaderboard/battles/{id}` (rank+이벤트 카운트)
- [x] UI Leaderboard 페이지

## Phase 5 — Bastion 스크랩 게시판 (완료, 2026-05-08)

- [x] seed_demo (3 데모) + fetch_hn_top + 보안 키워드 정규식 매칭
- [x] 관리자 승인 → kg_match 에서 course/weeks 추출 → 자동 generate → spawned_scenario_id 링크

## Phase 4 — Claude 미션 검증 + auto-monitor (완료, 2026-05-08)

- [x] LLM 기반 dry-run 4축 평가 (is_plausible / refined_expect / confidence / notes)
- [x] pass_rate ≥ 0.7 → validated 자동 승격, 미만은 draft 보존
- [x] battle auto-monitor 60s heartbeat + refined_expect probe 매칭 시 자동 BLUE 점수

## Phase 3 — Claude Code 시나리오 생성 (완료, 2026-05-08)

- [x] `services/scenario_gen.py` — `claude -p --output-format json` subprocess
- [x] `services/lecture_context.py` — CCC lecture.md 자동 주입 (env CCC_CONTENT_ROOT)
- [x] `routers/admin.py` + Admin UI — 자연어 입력 → background job → preview / 활성화
- [x] **실 6v6 위에서 풀 e2e**: SQLi+WAF+Wazuh 시나리오 (4 red+4 blue mission) 생성 →
      활성화 → solo battle exploit +20 / detect +15 → 종료 (~$0.07 / 42초)

## Phase 2 — 공방전 MVP (완료, 2026-05-07)

- [x] battle DB persistence (`services/battle_service.py`) + solo/duel/ffa 모드
- [x] 시나리오 17 종 자동 import (lifespan)
- [x] SSH 자격 Fernet 암호화 (`crypto.py`)
- [x] SSE 이벤트 스트림 + UI Battle 페이지 (시나리오 선택 → solo → 이벤트 → 스코어보드)
- [x] 6v6 Bastion API client stub
- [x] 테스트 7/7 PASS, 실제 postgres + uvicorn + UI 빌드 e2e 검증

## 후속 Phase 로드맵

`docs/roadmap.md` 참고. 요약:

- Phase 2 — battle_engine 통합 + solo/1v1/n인 모드 구현 + 실시간 점수판
- Phase 3 — Claude Code SDK 연결 (관리자 자연어 → 시나리오 생성)
- Phase 4 — 미션 자동 검증 + 채점 기준 작성 (실제 6v6 위에서 실행)
- Phase 5 — Bastion 스크랩 (커뮤니티/뉴스/KG 분석 → 스크랩 게시판 → 관리자 승인)
- Phase 6 — 실시간 모니터링 + 상세 채점 viewer (어떤 기준으로 몇 점)
- Phase 7 — 관리자 대시보드 (강제 종료/삭제, 히스토리, 사용자 통계)

## 라이선스

MIT.
