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

## Phase 2 — 공방전 MVP

- [ ] battle_engine 의 in-memory dict → DB persistence
- [ ] solo / duel / ffa 모드 백엔드 로직
- [ ] Bastion API 연동: 미션 spec push, run-history pull
- [ ] 점수 evaluator (시나리오 scoring rule → BattleEvent + score)
- [ ] SSE 이벤트 스트림 → Battle 상황판
- [ ] 학생 SSH 자격 암호화 (Fernet, key in env)
- [ ] 시나리오 17 종 (CCC 카탈로그) DB import
- [ ] e2e: 시나리오 선택 → battle 생성 → solo 모드 1회 완료까지

---

## Phase 3 — Claude Code 시나리오 생성

- [ ] Claude Code SDK 통합 (anthropic-sdk-python or CLI 자동화)
- [ ] 관리자 콘솔: 자연어 → Scenario draft
- [ ] 컨텍스트 attach: CCC `contents/education/courseN/weekM/lecture.md` 자동 주입
- [ ] 생성된 mission_red/blue 의 schema validation

---

## Phase 4 — 미션 자동 검증

- [ ] Claude Code 가 6v6 인프라 1대 잡아 dry-run
- [ ] 채점 기준 자동 작성 (acceptable_methods + verify.semantic 패턴 차용)
- [ ] 검증 결과 → Scenario.status: draft → validated

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
