# tubewar — 사이버 공방전 훈련 플랫폼

`6v6` 인프라 (https://github.com/mrgrit/6v6) 를 학생 PC 마다 1세트 배포해두고,
중앙 tubewar 서버가 학생 인프라 간 **공방전 (Red/Blue)** 을 시나리오/미션 단위로
관리·채점·시각화한다.

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

## Phase 1 (현재) 완료 기준

- [x] repo 골격 + git
- [ ] FastAPI: 회원가입 / 로그인 / JWT
- [ ] FastAPI: 6v6 인프라 등록 + smoke 테스트
- [ ] React: Login / Signup / Dashboard / MyInfra / Battle(placeholder) / Admin(placeholder)
- [ ] PostgreSQL (docker compose) + 모델 + 마이그레이션
- [ ] CCC battle_engine / battle_factory / battle-scenarios 이식
- [ ] dev.sh, setup.sh, CLAUDE.md, docs/architecture.md, docs/roadmap.md

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
