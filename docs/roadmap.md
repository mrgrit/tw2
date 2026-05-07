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

## Phase 5 — Bastion 스크랩 게시판

- [ ] Bastion 외부 RSS/feed crawler (CCC KG 와 매칭)
- [ ] ScrapPost 생성 + 관리자 게시판
- [ ] 승인 → Phase 3 흐름 자동 트리거
- [ ] Mythos 류 신규 위협 모델 등장 시 신속 대응 사이클 검증

---

## Phase 6 — 모니터링 + 상세 채점 viewer

- [ ] 중앙 monitor (Bastion or Claude 선택) 실시간 진행 트래킹
- [ ] BattleEvent 클릭 → 채점 상세 (어떤 룰, 어떤 증거 로그, 몇 점) 표시
- [ ] 공방전별 리더보드 + 사용자 누적 통계
- [ ] Audit log

---

## Phase 7 — 관리자 대시보드 풀

- [ ] 진행중 공방전: 강제 종료 / 삭제
- [ ] 히스토리 + 사용자별 점수 통계
- [ ] 시나리오 카탈로그 관리 (활성/비활성/archive)
- [ ] 사용자 관리 (role 변경, 비활성화)
