# tubewar — Claude Code 가이드

> 이 파일은 Claude Code (CLI) 가 tubewar 작업 시 따르는 프로젝트별 지침이다.
> CCC `/home/opsclaw/ccc/CLAUDE.md` 와 별개. tubewar 작업 중에는 이 파일 우선.

## 프로젝트 한 줄

`6v6` 인프라 (단일 VM Docker-Compose 13 컨테이너) 를 학생 PC 마다 배포해두고,
**학생 ↔ 학생 6v6 간 공방전** 을 관리·채점·시각화하는 중앙 플랫폼.

## 아키텍처

| 컴포넌트 | 경로 | 포트 | 역할 |
|----------|------|------|------|
| api | apps/api/ | 9200 | FastAPI — 인증/인프라/배틀/시나리오 |
| ui | apps/ui/ | 5173 (vite) | React — 학생/관리자 UI |
| postgres | docker compose | 5435 | tubewar 전용 DB (CCC 와 격리) |
| battle_engine | packages/battle_engine/ | - | 이벤트/점수/상태 머신 (CCC 에서 이식) |
| battle_factory | packages/battle_factory/ | - | 시나리오 → 미션 생성기 (Phase 4) |
| battle-scenarios | contents/battle-scenarios/ | - | YAML 시나리오 카탈로그 |

## 외부 의존

- 학생 6v6 VM 마다 다음 포트가 외부에서 reachable:
  - 80/443 (HTTP/HTTPS — 7 vhost)
  - 2204 (bastion SSH 점프)
  - 2202 (attacker SSH)
  - 8000 (portal)
  - 5601 (siem lite)
  - 9100 (Bastion API, header `X-API-Key`)

## 코드 규칙

- Python ≥ 3.10, FastAPI 비동기 핸들러 우선, SQLAlchemy 2.x async.
- TypeScript strict, React 18, Vite, 함수형 컴포넌트만.
- 비밀 (.env / SSH 자격) — 코드/커밋 절대 금지. `os.environ` / Vault 통해서만.
- 학생 자격 증명은 DB 저장 시 대칭 암호화 (Phase 1 은 평문 → Phase 2 마이그레이션 예정 — TODO 주석 표시).

## 운영 원칙

- **땜빵 금지**: 임시 우회 대신 근본 원인 수정.
- **테스트 후 완료 선언**: 문자열 수정만으로 완료 X. e2e 흐름 (signup → login → infra 등록 → smoke) 까지 확인.
- **6v6 의 표면 (외부 노출 포트) 만 의존**: docker 내부 구조에 직접 묶지 않기. 6v6 가 버전업되어도 tubewar 는 외부 API 만 보면 동작해야.

## 개발 명령

```bash
bash scripts/setup.sh       # postgres 컨테이너 + python venv + npm install
bash scripts/dev.sh api     # uvicorn (autoreload)
bash scripts/dev.sh ui      # vite (dev)
bash scripts/dev.sh db      # psql 진입
bash scripts/dev.sh test    # pytest
```

## 검증 명령

```bash
# 헬스
curl http://127.0.0.1:9200/health

# 회원가입
curl -X POST http://127.0.0.1:9200/auth/signup \
  -H 'content-type: application/json' \
  -d '{"email":"alice@test","password":"alice1234","name":"Alice"}'

# 로그인 → JWT
curl -X POST http://127.0.0.1:9200/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"alice@test","password":"alice1234"}'
```

## 현재 Phase

**Phase 1 — 골격**. 다음 단계는 `docs/roadmap.md` 참고.
