# tw2 로드맵

각 Phase 의 **Definition of Done** 과 핵심 결과물.
**Phase 1~7 및 el34 이식·콘텐츠 적응·배포 자동화 완료.** 현재 단계는 맨 아래 참고.

## Phase 1 — 골격 (완료)

- [x] 모노레포 구조 + git
- [x] FastAPI 백엔드 (auth, infras, battles placeholder)
- [x] 데이터 모델 (User/Infra/Scenario/Battle/BattleParticipant/BattleEvent/ScrapPost)
- [x] 인프라 smoke 테스트 (TCP probe + Assessor API)
- [x] React UI (Login/Signup/Dashboard/MyInfra/Battle/Admin placeholder)
- [x] battle_engine + battle_factory + scenarios 이식
- [x] 스크립트, CLAUDE.md, architecture, roadmap

DoD: 부팅 후 회원가입 → 인프라 등록 → smoke 까지 e2e 클릭 동작. *(설치는 현재
`scripts/bootstrap.sh` 로 일원화 — operations.md 참고.)*

---

## Phase 2 — 공방전 MVP (완료)

- [x] battle_engine 의 in-memory dict → DB persistence (`services/battle_service.py`)
- [x] solo / duel / ffa 모드 백엔드 로직 (validate_participants + 권한 체크)
- [x] 점수 evaluator (BattleEvent.points → BattleParticipant.score 즉시 반영)
- [x] SSE 이벤트 스트림 (`/battles/{id}/stream`, 폴링 기반 — Phase 6 에서 redis pubsub 으로 대체)
- [x] 학생 SSH 자격 Fernet 암호화 (`crypto.py`, env `TUBEWAR_FERNET_KEY`)
- [x] 시나리오 DB import (lifespan 부트스트랩)
- [x] UI Battle 페이지: 시나리오 선택 → solo 시작 → 이벤트 push → 스코어보드
- [x] 인프라 Assessor 클라이언트 (`services/assessor_client.py`)
- [x] e2e: signup → infra 등록 → 시나리오 선택 → solo battle 생성/시작/이벤트/종료
- [x] Assessor push (미션 spec) / pull (`/activity`) 자동화 + monitor 폴링 task
      (`lab_monitor`·`auto_monitor`)
- [x] duel/ffa 모드 백엔드 로직

---

## Phase 3 — Claude Code 시나리오 생성 (완료)

- [x] Claude CLI subprocess 통합 (`services/scenario_gen.py`, `claude -p --output-format json`)
- [x] 관리자 콘솔: 자연어 → Scenario draft (background job, 폴링)
- [x] 컨텍스트 attach: CCC `contents/education/courseN/weekM/lecture.md` 자동 주입
- [x] 생성된 mission_red/blue 의 pydantic schema validation
- [x] Infra port_map 확장 (학생별 .env override 수용)
- [x] e2e 검증 (실 인프라 위에서): SQLi+WAF+Wazuh 시나리오 생성 → solo battle 통과

---

## Phase 4 — 미션 자동 검증 (완료)

- [x] Claude CLI 가 각 미션을 4축 평가 (`services/dry_run.py`):
      is_plausible / refined_expect / confidence / notes
- [x] Assessor reachability probe (RED/BLUE 결정론 체크)
- [x] pass_rate ≥ 0.7 → status: validated 자동 승격, 미만은 draft 유지
- [x] 자동 트리거 (scenario_gen 직후) + 수동 트리거 (`POST /admin/scenarios/{id}/dry-run`)
- [x] Battle auto-monitor (`services/auto_monitor.py`) — 60s 간격 heartbeat,
      blue 미션 refined_expect 가 probe 응답에 매칭되면 자동 BLUE 점수 부여
- [x] battle start 시 auto-monitor 시작, end/cancel 시 정지
- [x] e2e 검증 (실 인프라): course3 1-3주 시나리오 dry-run → draft 유지,
      활성화 후 solo battle 시작 → heartbeat 이벤트 확인

---

## Phase 5 — Bastion 스크랩 게시판 (완료)

- [x] `services/scrap_crawler.py` — `seed_demo()` (3개 데모) + `fetch_hn_top()`
      (HackerNews top + 보안 키워드 정규식 매칭). idempotent on source_url.
- [x] `routers/admin.py` — `/admin/scrap` list/seed/approve/reject. 승인 시
      kg_match 첫 항목에서 course/weeks 자동 추출 + scenario_jobs.start_job.
- [x] `services/scenario_jobs.py` — scrap_id 전달, 완료 시 `spawned_scenario_id`
      back-link.
- [x] UI Admin 의 새 "Bastion 스크랩 게시판" 섹션.
- [x] e2e: Mythos AI Worm 게시글 승인 → scenario 19 생성 → spawned_scenario_id=19,
      dry-run pass_rate 0.22 → draft 보존 (양쪽 자동 + 보호 모두 작동).

---

## Phase 6 — 모니터링 + 상세 채점 viewer (완료)

- [x] BattleEvent.detail JSONB 에 source/probe/matched_expect/rule_id 등
      scoring evidence 누적 (auto_monitor + manual 모두)
- [x] UI Battle 의 이벤트 row → "채점 근거 ▼" 펼치기 → JSON pretty-print
- [x] `routers/leaderboard.py` — `/leaderboard/users` (총점/battle/승/평균),
      `/leaderboard/battles/{id}` (참가자 ranking + red/blue 이벤트 카운트)
- [x] UI Leaderboard 페이지 (전체 + battle 드릴다운)
- [x] e2e: Alice solo battle 70점 (exploit+detect+block 이벤트) → leaderboard
      반영 (total=70, wins=1, avg=70.0)

---

## Phase 7 — 관리자 대시보드 (완료)

- [x] `routers/admin.py` — `/admin/stats` (사용자/시나리오/battle/이벤트/top scorer
      집계), `/admin/battles` (필터링 + 메타 + monitor_running),
      `/admin/battles/{id}/force-end`, `/admin/battles/{id}` DELETE,
      `/admin/users` + PATCH (role / is_active 토글, self-demote 거부),
      `/admin/scenarios/{id}` PATCH (archive 등) + DELETE
- [x] UI Admin 6 탭: 통계 / 시나리오 생성 / Bastion 스크랩 / 공방전 관리 /
      사용자 관리 / 시나리오 관리
- [x] tests/test_admin.py 3 cases (stats + battle 관리 권한, self-demote 거부,
      archive 후 학생 노출 차단)
- [x] e2e 검증: 활성 battle 생성 → 강제 종료 → cancelled + monitor 정지 →
      scenario archive → 학생 목록에서 사라짐 → battle delete → 204

---

## 현재 단계 — el34 이식 + 전 트랙 콘텐츠 적응·검수·배포 자동화 (완료)

- [x] 인프라 전환 6v6 → **el34**: 타깃 단일 VM(192.168.0.80) + 별도 외부 공격자
      VM(192.168.0.202) + 웹 진입(192.168.0.161). FW→IPS(Suricata)→WAF→앱.
      출처 IP 가 Suricata/ModSec/Wazuh 전 계층 보존. vhost `*.el34.lab` 유지.
- [x] 저장소 postgres/docker → **SQLite**(`.data/tw2.sqlite3`). startup 이
      create_all + 컬럼 보강 + 관리자 시드 + 시나리오 자동 import.
- [x] 배포 자동화 **`scripts/bootstrap.sh`** + systemd `tw2-api`/`tw2-ui`
      (구 setup.sh/tubewar.sh/docker-compose 폐기).
- [x] 채점 = `claude` CLI(`claude-sonnet-4-6`) 의미 채점 + Assessor 결정론
      (file_contains/log_contains/port_listening/process_running/wazuh_alert).
      claude 없으면 review 보류.
- [x] SIEM 을 el34-siem(Wazuh)로 일원화, 중앙 OpenSearch 적재 OFF
      (`TUBEWAR_LAB_MONITOR=0`).
- [x] 시나리오 **128개**(9트랙 ×15 / secuops-easy ×6 + 호환 레거시 2) 적응·검수,
      모드 solo/1v1(duel)/ffa, 워크북 생성기(`scripts/gen_workbooks.py`).

---

## 향후

- [ ] **인프라 갭 텔레메트리 보강** — el34 에 부재한 `authentication_failed`(SSH auth)·
      Windows/Sysmon·엔드포인트 텔레메트리 도입 → 현재 review 보류인 미션의 자동 채점화.
- [ ] **레거시 `output_contains` 시나리오 포팅**(옵션) — Assessor 결정론 체크 체계로 정렬.
- [ ] 운영 강화 — CORS 화이트리스트, rate limiting, audit log (architecture.md 보안 노트).
