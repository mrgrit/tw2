# tubewar 로드맵

각 Phase 의 **Definition of Done** 과 핵심 결과물.

## Phase 1 — 골격 (현재)

- [x] 모노레포 구조 + git
- [x] FastAPI 백엔드 (auth, infras, battles placeholder)
- [x] PostgreSQL 모델 (User/Infra/Scenario/Battle/BattleParticipant/BattleEvent/ScrapPost)
- [x] 6v6 smoke 테스트 (TCP probe + Bastion API)
- [x] React UI (Login/Signup/Dashboard/MyInfra/Battle/Admin placeholder)
- [x] CCC battle_engine + battle_factory + scenarios 이식
- [x] dev/setup 스크립트, CLAUDE.md, architecture, roadmap

DoD: `bash scripts/setup.sh && bash scripts/dev.sh api/ui` 후 회원가입 → 인프라 등록 → smoke
까지 e2e 클릭 동작.

---

## Phase 2 — 공방전 MVP (현재)

- [x] battle_engine 의 in-memory dict → DB persistence (`services/battle_service.py`)
- [x] solo / duel / ffa 모드 백엔드 로직 (validate_participants + 권한 체크)
- [x] 점수 evaluator (BattleEvent.points → BattleParticipant.score 즉시 반영)
- [x] SSE 이벤트 스트림 (`/battles/{id}/stream`, 폴링 기반 — Phase 6 에서 redis pubsub 으로 대체)
- [x] 학생 SSH 자격 Fernet 암호화 (`crypto.py`, env `TUBEWAR_FERNET_KEY`)
- [x] 시나리오 17 종 DB import (lifespan 부트스트랩)
- [x] UI Battle 페이지: 시나리오 선택 → solo 시작 → 이벤트 push → 스코어보드
- [x] 6v6 Bastion API 클라이언트 stub (`services/six_client.py`)
- [x] e2e: signup → infra 등록 → 시나리오 선택 → solo battle 생성/시작/이벤트/종료
- [ ] **Phase 2 잔여** — Bastion API push (미션 spec), pull (run-history) 자동화. 자동
      monitor 폴링 task. (Phase 4 의 Claude monitor 와 합쳐서 진행 예정.)
- [ ] **Phase 2 잔여** — duel/ffa 모드 UI (현재는 solo 만 UI 구현. duel/ffa 는 API 만)

---

## Phase 3 — Claude Code 시나리오 생성 (완료)

- [x] Claude CLI subprocess 통합 (`services/scenario_gen.py`, `claude -p --output-format json`)
- [x] 관리자 콘솔: 자연어 → Scenario draft (background job, 폴링)
- [x] 컨텍스트 attach: CCC `contents/education/courseN/weekM/lecture.md` 자동 주입
- [x] 생성된 mission_red/blue 의 pydantic schema validation
- [x] Infra port_map 확장 (학생별 .env override 수용)
- [x] e2e 검증 (실 6v6 위에서): SQLi+WAF+Wazuh 시나리오 생성 → solo battle 통과

---

## Phase 4 — 미션 자동 검증 (완료)

- [x] Claude Code (haiku) 가 각 미션을 4축 평가 (`services/dry_run.py`):
      is_plausible / refined_expect / confidence / notes
- [x] 6v6 Bastion API `/exec` 화이트리스트로 reachability probe (curl)
- [x] pass_rate ≥ 0.7 → status: validated 자동 승격, 미만은 draft 유지
- [x] 자동 트리거 (scenario_gen 직후) + 수동 트리거 (`POST /admin/scenarios/{id}/dry-run`)
- [x] Battle auto-monitor (`services/auto_monitor.py`) — 60s 간격 heartbeat,
      blue 미션 refined_expect 가 probe 응답에 매칭되면 자동 BLUE 점수 부여
- [x] battle start 시 auto-monitor 시작, end/cancel 시 정지
- [x] e2e 검증 (실 6v6): course3 1-3주 시나리오 dry-run pass_rate 0.68 → draft
      유지, 활성화 후 solo battle 시작 → 65초 후 heartbeat 이벤트 확인

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
