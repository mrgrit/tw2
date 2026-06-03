# tubewar — 전체 재구축 프롬프트 (Rebuild Prompt)

> 작성일: 2026-06-03 · 대상 커밋: `3e94288` (Phase 9.3 까지 반영)
> 이 문서 **하나만 보고** tubewar 를 처음부터 동일하게 재구축할 수 있도록 모든 세부사항을 담는다.
> 아래를 그대로 LLM/개발자에게 주면 동일한 시스템이 나와야 한다.
> 코드 주석·UI 문자열은 한국어, JSON/코드 식별자는 영어를 유지한다.

---

## 0. 한 줄 정의 & 미션

학생마다 1세트 배포된 **6v6 인프라**(단일 VM Docker-Compose, 13 컨테이너) 위에서
**시나리오 기반 Red/Blue 사이버 공방전**을 운영·채점·시각화하는 중앙 플랫폼.

- 학생 각자가 자기 PC 의 VMware Bridge VM 에 6v6(https://github.com/mrgrit/6v6)을 직접 운영한다.
- tubewar 는 그 6v6 의 **외부 공개 포트(surface)만** 본다 — docker 내부 구조에 묶이지 않는다.
  6v6 가 버전업되어도 tubewar 는 외부 API 만 보면 동작해야 한다.
- 학생 ↔ 학생 공방전을 관리자가 시나리오/미션 단위로 매칭·채점·시각화한다.

### 핵심 운영 원칙 (반드시 지킬 것)
1. **땜빵 금지**: 임시 우회 대신 근본 원인 수정.
2. **테스트 후 완료 선언**: 문자열 수정만으로 완료 X. e2e 흐름(signup → login → infra 등록 → smoke → battle)까지 확인.
3. **6v6 의 외부 노출 포트만 의존**: docker 내부에 직접 묶지 않기.
4. **비밀 절대 커밋 금지**: `.env` / SSH 자격은 `os.environ` 또는 Vault 만.

---

## 1. 6v6 외부 의존 표면 (Surface)

학생 6v6 VM 마다 다음 포트가 외부에서 reachable 해야 한다(학생이 `.env` 로 override 가능 → tubewar 는 `port_map` 으로 수용):

| 포트 | key (port_map) | 용도 |
|------|----------------|------|
| 80   | `http`         | 7 vhost (juice, dvwa, neobank, govportal, mediforum, admin, ai) |
| 443  | `https`        | HTTPS |
| 2204 | `bastion_ssh`  | bastion SSH 점프 |
| 2202 | `attacker_ssh` | attacker SSH (pentest 도구 + 공격 발사대) — smoke **필수** |
| 8000 | `portal`       | portal (관리 대시보드) |
| 5601 | `siem_lite`    | siem-lite (Wazuh alert viewer) |
| 9100 | `bastion_api`  | Bastion API, header `X-API-Key` — smoke **필수** |

### 6v6 내부 컨테이너 맵 (시나리오/probe 가 참조하는 표준 실습 대역 10.20.30.0/24)
```
secu         10.20.30.1     nftables + Suricata + Wazuh agent
web          10.20.30.80    Apache + ModSecurity reverse proxy
juiceshop    10.20.30.81    OWASP Juice Shop
dvwa         10.20.30.82
neobank      10.20.30.83    Flask, 30 vulnerabilities
govportal    10.20.30.84    Flask, 25 vulnerabilities
mediforum    10.20.30.85    Flask
adminconsole 10.20.30.86    Flask (RCE / XXE / SSRF / pickle)
aicompanion  10.20.30.87    OWASP LLM Top 10 targets (mock LLM ok)
siem         10.20.30.100   Wazuh manager
bastion      10.20.30.201   SSH jump + Bastion API :9100
attacker     10.20.30.202   nmap / hydra / sqlmap / nikto
```
> 주의: 일부 시나리오 hint 는 web VM 의 `:8080`(DVWA), `:3000`(JuiceShop) 같은 컨테이너 직접 포트를 쓰기도 한다(레거시 YAML 유지).

### Bastion API 사용 계약
- `GET  http://<ip>:<bastion_api>/health` (header `X-API-Key`) — smoke 헬스체크.
- `POST http://<ip>:<bastion_api>/exec` body `{"target": "...", "command": "..."}` (header `X-API-Key`)
  — auto_monitor / dry-run 의 **안전 화이트리스트 probe** 전용 (`curl http://...`, `ping`, `nslookup`, `dig`).
  응답은 `{stdout, stderr, ...}` 또는 `{text}` 형태를 가정하고 둘 다 합산해서 파싱.
- (stub) `POST .../run` — 향후 명령 실행 endpoint placeholder.

---

## 2. 기술 스택 & 버전

| 컴포넌트 | 경로 | 포트 | 스택 |
|----------|------|------|------|
| api | `apps/api/` | 9200 | Python ≥3.10, FastAPI 비동기, SQLAlchemy 2.x async, asyncpg |
| ui | `apps/ui/` | 5173 (vite) | TypeScript strict, React 18, Vite 5, react-router-dom 6, 함수형 컴포넌트만 |
| postgres | docker compose | 5435→5432 | postgres:15 (tubewar 전용 DB, CCC 와 격리) |
| battle_engine | `packages/battle_engine/` | - | 이벤트/점수/상태 머신 (CCC 이식, in-memory 참조 구현) |
| battle_factory | `packages/battle_factory/` | - | CVE/CTI → 시나리오 생성기 (CCC 이식, 원본 보존) |
| battle-scenarios | `contents/battle-scenarios/` | - | YAML 시나리오 카탈로그 17종 |

### 코드 규칙
- Python: FastAPI 비동기 핸들러 우선, SQLAlchemy 2.x async (`Mapped`/`mapped_column`), `from __future__ import annotations`.
- TypeScript strict, 함수형 컴포넌트, 인라인 스타일 + 소수 CSS 유틸 클래스.
- 비밀(.env / SSH 자격)은 코드/커밋 금지.
- 학생 SSH 자격은 DB 저장 시 Fernet 대칭 암호화 (prefix `fernet:`).

### `apps/api/pyproject.toml`
```toml
[project]
name = "tubewar-api"
version = "0.1.0"
description = "tubewar central API — 6v6-based cyber battle platform"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic[email]>=2.5",
    "pydantic-settings>=2.1",
    "email-validator>=2.1",
    "bcrypt>=4.0",
    "python-jose[cryptography]>=3.3",
    "python-multipart>=0.0.7",
    "httpx>=0.26",
    "asyncssh>=2.14",
    "pyyaml>=6.0",
    "cryptography>=42.0",
]
[project.optional-dependencies]
dev = ["pytest>=7.4", "pytest-asyncio>=0.23", "aiosqlite>=0.19"]
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### `apps/ui/package.json`
```json
{
  "name": "tubewar-ui", "private": true, "version": "0.1.0", "type": "module",
  "scripts": { "dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview" },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1", "react-router-dom": "^6.26.0" },
  "devDependencies": {
    "@types/react": "^18.3.3", "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1", "typescript": "^5.5.3", "vite": "^5.4.0"
  }
}
```

---

## 3. 리포지토리 레이아웃 (정확히 재현)

```
tubewar/
├── CLAUDE.md                       # 프로젝트별 Claude Code 지침
├── README.md
├── .env.example                    # (커밋) / .env 는 gitignore
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── roadmap.md
│   └── rebuild_prompt_250603.md    # (이 문서)
├── infra/docker-compose.yml        # postgres 단독
├── scripts/{setup.sh, dev.sh, e2e_full_duel.sh}
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   └── app/
│   │       ├── __init__.py          (빈 파일)
│   │       ├── main.py              # FastAPI app + lifespan
│   │       ├── config.py            # pydantic-settings
│   │       ├── db.py                # async engine/session
│   │       ├── models.py            # ORM 8 테이블
│   │       ├── schemas.py           # pydantic I/O
│   │       ├── security.py          # bcrypt + JWT
│   │       ├── crypto.py            # Fernet envelope
│   │       ├── routers/{__init__.py(빈), auth, infras, scenarios, battles, leaderboard, users, admin}.py
│   │       └── services/{__init__.py(빈), audit, auto_monitor, battle_service, dry_run,
│   │                      event_analyzer, grader, hints, lecture_context, rate_limit,
│   │                      scenario_gen, scenario_jobs, scenario_loader, scrap_crawler,
│   │                      six_client, six_smoke}.py
│   └── ui/
│       ├── index.html, package.json, vite.config.ts, tsconfig.json
│       └── src/
│           ├── main.tsx, App.tsx, api.ts, auth.ts, styles.css
│           └── pages/{Login, Signup, Dashboard, MyInfra, Profile, Battle, Leaderboard, Admin}.tsx
├── packages/
│   ├── battle_engine/{__init__.py, README.md}
│   └── battle_factory/{__init__.py(빈), README.md, generator.py, threat_special.py}
├── contents/battle-scenarios/*.yaml   # 17 시나리오
└── tests/{__init__.py(빈), conftest.py, test_smoke, test_battle, test_lobby,
           test_battle_options, test_admin, test_audit, test_rate_limit, test_profile}.py
```

---

## 4. 환경 변수 & 인프라

### `.env.example` (그대로)
```bash
# ── API ──
TUBEWAR_API_HOST=0.0.0.0
TUBEWAR_API_PORT=9200
TUBEWAR_API_KEY=tubewar-api-key-2026
TUBEWAR_JWT_SECRET=change-me-please-make-it-32-chars-or-more
TUBEWAR_JWT_EXPIRES_HOURS=12
# ── DB (docker compose postgres:5435 와 동일) ──
DATABASE_URL=postgresql+asyncpg://tubewar:tubewar@127.0.0.1:5435/tubewar
# ── 6v6 인프라 기본값 (학생이 register 시 override) ──
SIX_DEFAULT_SSH_USER=ccc
SIX_DEFAULT_SSH_PASS=ccc
SIX_DEFAULT_BASTION_KEY=ccc-api-key-2026
# ── LLM (Phase 3+, ollama fallback 참조용) ──
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=gemma3:4b
# ── Admin bootstrap (최초 기동 시 1회) ──
ADMIN_EMAIL=admin@tubewar.app
ADMIN_PASSWORD=change-me-on-first-login
ADMIN_NAME=admin
```

### 코드에서만 읽는(런타임) 추가 env
- `TUBEWAR_FERNET_KEY` — Fernet 키. 없으면 `.data/fernet.key` 자동 생성(dev) + stderr 경고.
- `TUBEWAR_CLAUDE_BIN` (default `claude`), `TUBEWAR_CLAUDE_MODEL` (default `claude-haiku-4-5`), `TUBEWAR_CLAUDE_TIMEOUT_SEC` (180) — 시나리오 생성/dry-run.
- `TUBEWAR_GRADER_MODEL` / `TUBEWAR_GRADER_TIMEOUT` (claude-haiku-4-5 / 30) — auto_monitor grader.
- `TUBEWAR_ANALYZER_MODEL` / `TUBEWAR_ANALYZER_TIMEOUT` (claude-haiku-4-5 / 40) — event_analyzer.
- `TUBEWAR_HINT_MODEL` / `TUBEWAR_HINT_TIMEOUT` / `TUBEWAR_HINT_COOLDOWN` (claude-haiku-4-5 / 30 / 60).
- `TUBEWAR_RATE_LIMIT_DISABLE` = `1|true|yes` → rate limiter no-op (테스트용).
- `CCC_CONTENT_ROOT` (default `/home/opsclaw/ccc/contents`) — lecture.md 컨텍스트 루트.

### `.gitignore` 핵심
```
__pycache__/  *.py[cod]  *.egg-info/  .venv/  venv/
.env  .env.*  !.env.example
node_modules/  dist/  .vite/
.idea/ .vscode/ *.swp .DS_Store
*.sqlite3 *.db data/ runtime/
*.log logs/
*.pem *.key secrets/
```

### `infra/docker-compose.yml`
```yaml
services:
  postgres:
    image: postgres:15
    container_name: tubewar-postgres
    environment:
      POSTGRES_DB: tubewar
      POSTGRES_USER: tubewar
      POSTGRES_PASSWORD: tubewar
    ports:
      - "127.0.0.1:5435:5432"
    volumes:
      - tubewar-pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tubewar -d tubewar"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped
volumes:
  tubewar-pg:
```

### `scripts/setup.sh` (1회 셋업)
`set -euo pipefail` + repo 루트로 cd. 단계: (1) `docker compose -f infra/docker-compose.yml up -d postgres` + pg_isready 30회 대기, (2) `.venv` 생성 + `pip install -e "apps/api[dev]"`, (3) `cd apps/ui && npm install --silent`, (4) `.env` 없으면 `.env.example` 복사. 끝에 dev 명령 안내 출력.

### `scripts/dev.sh` (dispatcher, `set -euo pipefail`, repo 루트로 cd)
- `api`: venv 활성화 + `.env` source + `cd apps/api` + `uvicorn app.main:app --host $TUBEWAR_API_HOST --port $TUBEWAR_API_PORT --reload --reload-dir app`
- `ui`: `cd apps/ui && npm run dev`
- `build-ui`: `npm run build`
- `db`: `docker exec -it tubewar-postgres psql -U tubewar -d tubewar`
- `pg-up`/`pg-down`: compose up/down
- `test`: venv 활성화 + `.env` source + `python -m pytest tests/ -v`
- `help|*`: 사용법 출력

---

## 5. 백엔드 — 공통 인프라 (`apps/api/app/`)

### `config.py`
`pydantic-settings` `Settings(BaseSettings)`. **중요**: `.env` 경로를 repo root 절대경로로 고정
(`Path(__file__).resolve().parents[3] / ".env"`) — CWD 의 .env 가 leak 되는 것 방지.
`env_prefix=""`, `extra="ignore"`. 필드(alias → default):
`api_host`(TUBEWAR_API_HOST,"0.0.0.0"), `api_port`(TUBEWAR_API_PORT,9200), `api_key`(TUBEWAR_API_KEY,"tubewar-api-key-2026"),
`jwt_secret`(TUBEWAR_JWT_SECRET,"dev-secret-change-me-in-prod-please-32-chars"), `jwt_expires_hours`(TUBEWAR_JWT_EXPIRES_HOURS,12),
`database_url`(DATABASE_URL, postgres asyncpg url), `six_default_ssh_user/pass/bastion_key`,
`llm_base_url`/`llm_model`, `admin_email`/`admin_password`/`admin_name`. `@lru_cache def get_settings()`.

### `db.py`
`class Base(DeclarativeBase)`. `engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)`.
`SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`.
`async def get_session()` — `async with SessionLocal() as session: yield session`.

### `crypto.py` (Fernet envelope)
- `PREFIX = "fernet:"`, 키파일 `.data/fernet.key` (`parents[3]`).
- `_load_key()`: env `TUBEWAR_FERNET_KEY` 우선 → 없으면 키파일 읽기 → 없으면 `Fernet.generate_key()` 저장(chmod 600) + stderr 경고.
- `encrypt(plain)` → `"fernet:" + token`. `None`→`""`.
- `decrypt(ct)`: 빈값→"". prefix 없으면 평문 그대로 반환(Phase1 마이그레이션 호환). prefix 있으면 decrypt, 실패 시 `ValueError`.
- `is_encrypted(v)`: prefix 로 시작하는지.

### `security.py` (인증)
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)`, `ALGORITHM="HS256"`, bcrypt 72-byte truncate (`_BCRYPT_MAX=72`).
- `hash_password`/`verify_password` (bcrypt, ValueError→False).
- `issue_token(user)`: payload `{sub:str(id), email, role, iat, exp(now+jwt_expires_hours)}`, HS256.
- `decode_token(token)`: JWTError → 401.
- `get_current_user`: 토큰 없으면 401("missing token"), decode 후 `session.get(User, id)`, 없거나 `not is_active` → 401.
- `require_admin`: `role != "admin"` → 403("admin only").

### `main.py`
`lifespan`: (1) `Base.metadata.create_all` (Phase1; alembic 미사용), (2) admin 부트스트랩 — `admin_email` 없으면 User(role=admin) 생성, (3) `import_scenarios(s)` 로 YAML 17종 import. `FastAPI(title="tubewar API", version="0.1.0")`. CORS allow_origins=`["http://127.0.0.1:5173","http://localhost:5173"]`, credentials/methods/headers="*". `GET /health` → `{"status":"ok","service":"tubewar-api","version":"0.1.0"}`. 라우터 include 순서: auth, infras, scenarios, battles, leaderboard, users, admin.

---

## 6. 데이터 모델 (`models.py`) — 8 테이블

`utcnow()` 헬퍼. 모든 `created_at`/`ts` 는 `DateTime(timezone=True), server_default=func.now()`.

### `User` (`users`)
`id` PK, `email` String(255) unique index, `name` String(120), `password_hash` String(255),
`role` String(16) default `"student"` (student|admin), `is_active` Bool default True, `created_at`.
rel `infras` (cascade all,delete).

### `Infra` (`infras`) — 학생 1인 = 1세트 6v6 VM
`id`, `owner_id` FK users CASCADE index, `name` String(80), `vm_ip` String(45),
`ssh_user` String(40) default "ccc", `ssh_password_enc` String(255) (Fernet, TODO 평문 호환),
`bastion_api_key` String(120), `port_map` JSON default dict (keys: http, https, bastion_ssh, attacker_ssh, portal, siem_lite, bastion_api),
`status` String(24) default "registered" (registered|healthy|degraded), `last_smoke_at` DateTime?, `last_smoke_result` JSON?, `created_at`.
rel `owner`.

### `Scenario` (`scenarios`)
`id`, `title` String(200), `description` Text default "", `source` String(40) default "admin" (admin|claude|bastion-scrap),
`course_ref` String(120)? (slug 또는 "course3 / w01-w03"), `mission_red` JSON, `mission_blue` JSON, `scoring` JSON,
`time_limit_sec` Int default 1800, `status` String(24) default "draft" (draft|validated|active|archived),
`created_by` FK users SET NULL?, `created_at`.
> mission_red/blue 구조: `{"missions": [<mission>], "battle_type": "1v1"}`. mission: `{order, instruction, hint, points, target_vm, verify:{type, expect, semantic:{intent, success_criteria[], acceptable_methods[], negative_signs[]}}}`.

### `Battle` (`battles`)
`id`, `scenario_id` FK SET NULL?, `mode` String(16) (solo|duel|ffa), `status` String(16) default "pending" (pending|active|completed|cancelled),
`monitor` String(16) default "bastion" (bastion|claude), `target_apps` JSON default list, `hint_enabled` Bool default False,
`started_at`?, `ended_at`?, `time_limit_sec` Int default 1800, `created_by` FK SET NULL?, `created_at`.
rel `participants`, `events` (cascade all,delete).

### `BattleParticipant` (`battle_participants`)
`id`, `battle_id` FK CASCADE index, `user_id` FK CASCADE index, `infra_id` FK SET NULL?, `role` String(16) (red|blue|observer|admin|solo|free), `score` Int default 0. rel `battle`.

### `BattleEvent` (`battle_events`)
`id`, `battle_id` FK CASCADE index, `actor_user_id` FK SET NULL?, `event_type` String(24),
`target` String(120) default "", `description` Text default "", `detail` JSON default dict,
`reasoning` Text? (LLM 자연어 채점 근거 markdown), `points` Int default 0, `ts`. rel `battle`.

### `BattleHint` (`battle_hints`)
`id`, `battle_id` FK CASCADE index, `requested_by` FK SET NULL?, `mission_side` String(8) default "any" (red|blue|any),
`mission_order` Int?, `probe_hash` String(64)? index, `text` Text default "", `model` String(40) default "",
`cost_usd` (Integer 컬럼에 micro-cents 저장), `created_at`.

### `AuditLog` (`audit_logs`)
`id`, `actor_user_id` FK SET NULL? index, `actor_email` String(255)?, `action` String(80) index,
`target_type` String(40)?, `target_id` String(80)?, `ip` String(64)?, `user_agent` String(255)?, `detail` JSON default dict, `ts` index.

### `ScrapPost` (`scrap_posts`)
`id`, `source` String(80), `source_url` String(500), `title` String(400), `summary` Text default "",
`relevance` JSON default dict (kg_match[], keywords[], education_score, spawned_job_id),
`status` String(16) default "pending" (pending|approved|rejected), `decided_by` FK SET NULL?, `decided_at`?,
`spawned_scenario_id` FK scenarios SET NULL?, `created_at`.

---

## 7. Pydantic 스키마 (`schemas.py`)

- **Auth**: `SignupIn{email:EmailStr, password:8..128, name:1..120}`, `LoginIn{email,password}`,
  `TokenOut{access_token, token_type="bearer", user:UserOut}` (+ `model_rebuild()` 끝에),
  `UserOut{id,email,name,role,is_active,created_at}` from_attributes.
- **Infra**: `InfraIn{name:1..80, vm_ip:3..45, ssh_user="ccc", ssh_password:1..255, bastion_api_key="ccc-api-key-2026", port_map:dict[str,int]}`,
  `InfraOut{id,name,vm_ip,ssh_user,bastion_api_key,port_map,status,last_smoke_at,last_smoke_result,created_at}`,
  `SmokeResult{ok:bool, checks:list[dict], summary:str}`.
- **Scenario**: `ScenarioOut{id,title,description,source,status,time_limit_sec,created_at}`.
- **Battle**: `BattleOut{id,scenario_id,mode,status,monitor,target_apps,hint_enabled,started_at,ended_at,time_limit_sec,created_at}`,
  `BattleParticipantIn{user_id, role:^(red|blue|solo|free|observer)$, infra_id?}`,
  `BattleParticipantOut{id,user_id,infra_id,role,score}`,
  `BattleCreateIn{scenario_id, mode:^(solo|duel|ffa)$, monitor:^(bastion|claude)$="bastion", target_apps:list(max8), hint_enabled=False, participants:list(max16)}`,
  `BattleEventIn{event_type:1..24, target<=120, description<=2000, points:-100..200, mission_order:1..99?, mission_side:^(red|blue)$?, what_i_did<=4000, what_happened<=4000, detail:dict}`,
  `BattleEventOut{id,actor_user_id,event_type,target,description,detail,reasoning,points,ts}`,
  `MissionOut{side, order, title?, instruction, target_vm?, points=0, hint?, verify_expect?, semantic_intent?, success_criteria[], solved=False}`,
  `BattleDetail{battle, scenario_title?, participants[], events[], elapsed_sec, remaining_sec, my_role?, my_missions[], opponent_missions[]}`,
  `BattleJoinIn{role:^(red|blue|free)$, infra_id?}`.

---

## 8. 라우터 (엔드포인트 명세)

### `auth.py` (`/auth`)
- `POST /signup` → `rate_limit.enforce_signup`, 중복 email 409, User(role=student) 생성, `audit auth.signup`, `TokenOut`.
- `POST /login` → email lower, `rate_limit.enforce_login`, 실패 시 `audit auth.login_fail` + 401("invalid email or password"), inactive 시 403 + login_fail("account_disabled"), 성공 `audit auth.login`, `TokenOut`.
- `GET /me` → `UserOut`.
- `PATCH /me` (`UpdateProfileIn{name}`) → 이름 변경 + `audit user.update_profile`.
- `POST /me/password` (`ChangePasswordIn{current_password, new_password:8..}`) → 현재 비번 틀리면 400 + audit fail, new==current 400, 변경 + `audit user.change_password`, `{"ok":True}`.

### `infras.py` (`/infras`) — 학생 1인 = 인프라 1개(Phase1 단순화)
- `GET ""` → 본인 인프라 목록(id desc).
- `POST ""` → 이미 있으면 409, `ssh_password` 를 `encrypt()` 해서 저장, status="registered".
- `DELETE /{id}` → owner 또는 admin 만, 204.
- `POST /{id}/smoke` → `six_smoke.run_smoke(ip, bastion_api_key, port_map)`, `last_smoke_at/result/status(healthy|degraded)` 갱신, `SmokeResult`.

### `scenarios.py` (`/scenarios`) — read는 학생/관리자 모두
- `GET ""` → status in (validated, active) 만, id asc, `ScenarioOut[]`.
- `GET /{id}` → `ScenarioOut` + `course_ref, mission_red, mission_blue, scoring` 전체 dict.

### `battles.py` (`/battles`) — 핵심
- `GET ""` → 최근 100 (id desc) `BattleOut[]`.
- `GET /{id}` → `_serialize_with_missions` (viewer 의 role 에 따라 my/opponent missions 분기).
- `POST ""` (201) — solo 는 lobby 불가(본인 강제, 비admin 은 자기만), duel/ffa 비admin 은 자기 포함 필수, admin 은 참가자 0명 lobby 허용(`allow_lobby`). `bs.create_battle`.
- `POST /{id}/start` → 참가자/admin 만, `bs.start_battle` + `auto_monitor.start(id)` (monitor in bastion|claude).
- `POST /{id}/join` (`BattleJoinIn`) → `bs.join_battle`.
- `POST /{id}/leave` → `bs.leave_battle`.
- `POST /{id}/events` (201) — 참가자/admin 만. mission_side 미지정 시 event_type 으로 추정(attack/exploit→red, defend/detect/block/alert→blue). `_build_mission_context`/`_build_scenario_context` → `event_analyzer.analyze_event(monitor, report, mission, scenario)`. detail 에 `report`(what_i_did/what_happened/mission_order/mission_side) + `analysis`(model/cost_usd/criteria_met/criteria_missing/negative_signs_hit) 보존. `bs.add_event(reasoning=analysis.reasoning)`.
- `POST /{id}/end` → 참가자/admin, `bs.end_battle` + `auto_monitor.stop`.
- `DELETE /{id}` → admin 만, 204.
- `POST /{id}/cancel` → admin 만, `bs.cancel_battle` + stop.
- `POST /{id}/hint` (`HintIn{mission_side:^(red|blue|any)$="any", note<=500}`) → 참가자/admin, `hints.request_hint`. cooldown 이면 429 + Retry-After:60. `HintOut{text, model, cache_hit, cost_usd, cooldown_remaining_sec}`.
- `GET /{id}/stream` (SSE `text/event-stream`, `poll_interval=1.0`) — 인증된 사용자 누구나 read-only 관전. snapshot 1회(scoreboard by role) → 폴링 루프로 새 event(`id>last`) + scoreboard 매 사이클 push. 종료/삭제 시 `end` 이벤트. helper `_sse(event,data)`, `_event_payload(e)`.

`_serialize_with_missions` 내부: `_solved_orders(events, "blue")` = detail.source=="auto_monitor" & blue_mission_order 가진 order 집합(red 는 비움). `_missions_for_side` = mission_red/blue 의 missions, dry_run.review.{red|blue}_review 의 refined_expect 우선, expect list→join. my_role 에 따라: red→(red,blue), blue→(blue,red), solo/free→(red+blue,[]), 관전/admin→([],red+blue).

### `leaderboard.py` (`/leaderboard`)
- `GET /users` → User × sum(participant.score) (left join, group, total desc, limit 50). win_count = completed battle 별 최고점 participant(동점 무시, top.score>0, ties==1). `UserRankRow{user_id,name,email,role,battle_count,total_score,win_count,avg_score}`.
- `GET /battles/{id}` → 참가자 ranking(score desc) + red/blue 이벤트 카운트(red: attack/exploit & role in red,solo; blue: defend/detect/block & role in blue,solo). `BattleLeaderboard{battle_id,scenario_title,mode,status,rows:[BattleRankRow{user_id,name,role_in_battle,score,rank,events_red,events_blue}]}`.

### `users.py` (`/users`)
- `GET /lookup?email=` → 활성 사용자 1명 (duel/ffa 초대용). 잘못된 email 400, 없으면 404. `UserLookupOut{id,email,name,role}`.

### `admin.py` (`/admin`) — 전부 `require_admin`
시나리오 생성·검증:
- `POST /scenarios/generate` (202, `GenerateIn{request:8..2000, course_ref?, weeks_spec?}`) → `scenario_jobs.start_job` + `audit scenario.generate`. `GenerateOut{job_id,status}`.
- `GET /scenarios/jobs` / `GET /scenarios/jobs/{job_id}` → `JobOut{id,status,request,course_ref,weeks_spec,queued_at,started_at?,finished_at?,scenario_id?,preview?,meta?,error?}`.
- `POST /scenarios/{id}/dry-run` → infra 1대 잡아 `dry_run.review_scenario`, scoring["dry_run"]=result, passed 면 status=validated, `audit scenario.dry_run`.
- `POST /scenarios/{id}/activate` (`ActivateIn{activate=True}`) → status validated|draft, audit.
- `GET /scenarios/drafts` → status=="draft" 목록.
- `PATCH /scenarios/{id}` (`ScenarioPatchIn{title:4..200?, description<=4000?, time_limit_sec:300..7200?, status:^(draft|validated|active|archived)$?}`) → 갱신 + `audit scenario.patch`.
- `DELETE /scenarios/{id}` (204) → `audit scenario.delete`.

스크랩 게시판:
- `GET /scrap?status_filter=` → `ScrapOut[]` (id desc 100). `ScrapOut.from_row`.
- `POST /scrap/seed` → `seed_demo` + `fetch_hn_top(n=5)` → `{inserted_demo, inserted_hn}`.
- `POST /scrap/{id}/approve` (`ScrapDecisionOut{scrap, job_id?}`) → status approved, kg_match[0] 에서 course/weeks 추출("course3-web-vuln/week04"→course3 / 4), request 문구 합성 후 `scenario_jobs.start_job(scrap_id=id)`, relevance["spawned_job_id"]=job_id, `audit scrap.approve`.
- `POST /scrap/{id}/reject` → status rejected, `audit scrap.reject`.

대시보드:
- `GET /stats` → `StatsOut{user_count, student_count, admin_count, scenario_total, scenario_validated, scenario_draft, scrap_pending, battles_total, battles_active, battles_completed, events_total, top_scorers:[{user_id,name,total_score}]}` (top 5).
- `GET /battles?status_filter=` → `AdminBattleOut{id,scenario_id,scenario_title,mode,status,monitor,started_at,ended_at,time_limit_sec,elapsed_sec,participant_count,event_count,monitor_running,created_at}[]` (id desc 200). monitor_running = `auto_monitor.is_running`.
- `POST /battles/{id}/force-end` → `bs.cancel_battle` + stop + `audit battle.force_end`, `AdminBattleOut`.
- `DELETE /battles/{id}` (204) → stop + delete + `audit battle.delete`.

사용자 관리:
- `GET /users` → `AdminUserOut[]` (id asc).
- `PATCH /users/{id}` (`UserPatchIn{role:^(student|admin)$?, is_active?}`) → 자기 자신 demote/deactivate 400, 갱신 + `audit user.patch`.

감사 로그:
- `GET /audit?action_prefix=&actor_user_id=&target_type=&limit=100` (limit clamp 1..500, id desc) → `AuditOut[]`.

---

## 9. 서비스 레이어 (`services/`)

### `battle_service.py` — DB-backed 상태머신
- `validate_participants(mode, parts, allow_lobby=False)`: 빈 목록은 allow_lobby 면 통과(로비), 아니면 ValueError. user_id 중복 거부. solo=정확히1 & role=="solo". duel≤2 & role in red/blue & role 중복 금지. ffa role in free/red/blue.
- `validate_can_start(mode, parts)`: 빈 목록 불가. solo==1, duel==2, ffa≥2.
- `VALID_TARGET_APPS = {juiceshop, dvwa, neobank, mediforum, govportal, aicompanion, adminconsole, web}`.
- `create_battle(...)`: validate → scenario 존재 & status in (validated, active) → 참가자 user/infra(owner 일치) 검증 → target_apps: `["random"]` 이면 `random.sample(sorted(VALID), randint(2,4))`, 아니면 검증(unknown→ValueError, >5→ValueError) → Battle(status="pending", time_limit=scenario.time_limit_sec) + participants + system event "battle created" → commit → `load_battle`.
- `load_battle(s, id)`: selectinload participants/events.
- `join_battle(...)`: status=="pending" 만, 중복 user 거부, solo 는 lobby 없음, duel 풀(2)/role 중복("already taken") 검증, ffa role/16max, infra owner 일치. participant 추가 + system event "joined as {role}".
- `leave_battle(...)`: pending 만, participant 삭제 + system "left".
- `is_participant(s,bid,uid)`.
- `start_battle(...)`: pending 만, `validate_can_start`, status=active, started_at=now, system "battle started".
- `add_event(...)`: status=="active" 만(ValueError). BattleEvent 추가 + (points≠0 이면 actor participant.score += points). 시간 만료(elapsed≥time_limit_sec) 시 status=completed + ended_at + system "time expired". commit+refresh.
- `end_battle`: status=completed + ended_at + system "battle ended (manual)" + detail.final_scores.
- `cancel_battle`: status=cancelled + system "battle cancelled (admin)".
- `battle_elapsed(b)` → (elapsed, remaining). `_aware()` 로 naive→UTC 정규화(sqlite 호환).

### `six_smoke.py`
`DEFAULT_PORTS` = {http:80, https:443, bastion_ssh:2204, attacker_ssh:2202, portal:8000, siem_lite:5601, bastion_api:9100}.
`PORT_SPEC` = [(label,key,required)] — attacker-ssh & bastion-api 만 required=True, 나머지 옵셔널.
`_tcp_probe(ip,port,3s)`, `_bastion_health(ip,port,key,5s)` (GET /health X-API-Key).
`resolve_ports(port_map)` 로 override(1..65535만). `run_smoke`: 모든 포트 TCP probe(gather) + bastion health. required 실패 또는 bastion status≠200 이면 ok=False. `SmokeResult(ok, checks, summary)`.

### `six_client.py` — Bastion/Portal HTTP 클라이언트 (stub)
`SixClient(ip, bastion_api_key, timeout=5)`: `bastion_health()`(GET :9100/health +key), `portal_health()`(GET :8000/), `bastion_run(cmd)`(POST :9100/run). 실패는 dict 반환(raise X). `_wrap(url,r)` → `{url, ok(2xx), status_code, body}`.

### `scenario_loader.py` — YAML → DB import (lifespan)
`_SCENARIO_DIR = parents[4] / contents/battle-scenarios`. `_normalize(raw, slug)`: title/description/course_ref(id 또는 slug)/mission_red{missions, battle_type}/mission_blue{missions}/scoring{red,blue summary, battle_type_hint, difficulty}/time_limit_sec(or 1800)/status="validated"/source="admin". `import_scenarios`: `*.yaml` 정렬 순회, course_ref 기준 idempotent(존재 시 skip), 새것만 insert. 반환 = 새 개수.

### `scenario_gen.py` — 자연어 → 시나리오 (claude CLI)
출력 schema: `GeneratedScenario{title:4..200, description:20..4000, difficulty:^(easy|medium|hard)$, time_limit_sec:600..7200, battle_type_hint:^(1v1|ffa|solo)$="1v1", red_missions:2..10, blue_missions:2..10}`, `_Mission{order, instruction, hint="", points:1..100, target_vm="attacker", verify:dict default {type:output_contains, expect:""}}`.
`_invoke_claude(system,user)`: `claude -p --output-format json --model <model>` subprocess(stdin=full prompt), env `TUBEWAR_CLAUDE_BIN/MODEL/TIMEOUT_SEC`. FileNotFound/timeout/returncode≠0/non-JSON → `ScenarioGenerationError`. `_SYSTEM_TEMPLATE` 에 6v6 컨테이너 맵 + hard requirements(JSON only, schema 정확히, red↔blue mirror, 구체 명령/로그 경로, 4-6 missions/side, 한국어 instruction OK·JSON key 영어). `generate_scenario`: weeks_spec → `parse_week_range`, course+weeks → `build_context_block`, prompt → invoke → `_extract_json_object`(fence/prose robust) → validate. 반환 (scenario, meta{duration_ms, model_usage, cost_usd, lecture_chars, course_ref, weeks}).

### `lecture_context.py` — CCC lecture.md 컨텍스트
`DEFAULT_ROOT="/home/opsclaw/ccc/contents"`, env `CCC_CONTENT_ROOT`. `find_course_dir(ref)` (norm 후 education/ 하위 prefix 매칭). `parse_week_range(spec)` ("1-3"/"1,3,5"/"week01..week03" → [int]). `load_lectures(ref, weeks, max_chars_per_week=6000)` → [{course,week,title,body,truncated}]. `build_context_block(ref, weeks, max_chars_total=24000)` (총 길이 cap).

### `dry_run.py` — 미션 정합성 검증 (Phase4)
schema: `_MissionReview{order, is_plausible, refined_expect<=400, confidence:0..1, notes<=1000}`, `ScenarioReview{summary, red_review[], blue_review[], overall_pass_rate:0..1}`.
`_REVIEW_SYSTEM` = 6v6 baseline + 각 미션 4축(is_plausible/refined_expect/confidence/notes) JSON only. `review_scenario(scenario, infra=None)`: `_invoke_claude` → `_extract_json` → validate. `passed = overall_pass_rate >= 0.7`. infra 있으면 `_probe_via_bastion`(/exec 로 `curl http://10.20.30.80/`, `curl http://10.20.30.100/`) reachability. 반환 {summary, passed, pass_rate, review, claude_meta, executor?}.

### `scenario_jobs.py` — background job tracker (in-memory dict)
`start_job(request, course_ref, weeks_spec, created_by, scrap_id=None)` → token_urlsafe(8) job_id, `asyncio.create_task(_run_job)`. `_run_job`: status running→`generate_scenario`→ Scenario(source=claude, course_ref or "claude-generated", mission_red{missions, battle_type}, mission_blue{missions}, scoring{red,blue,battle_type_hint,difficulty,claude_meta}, status=draft) insert → scrap_id 있으면 spawned_scenario_id 갱신 → status completed + preview/meta → `_run_dry_run` fire-and-forget. `_run_dry_run`: infra 1대 잡아 review_scenario, scoring["dry_run"]=result, passed 면 status=validated, job.dry_run_status/dry_run 갱신. `get_job`/`list_jobs(50)`.

### `scrap_crawler.py` — 외부 스크랩 (Phase5)
`DEMO_POSTS` 3개(krcert Citrix, hackernews Mythos AI Worm, github FastAPI CSRF) — 각 source/source_url/title/summary/relevance{keywords,education_score,kg_match}. `SECURITY_KEYWORDS` regex (cve|vuln|exploit|rce|sqli|xss|csrf|ransomware|phishing|llm|prompt-injection|zero-day|backdoor|breach|auth-bypass|escalation|deserial|sso|oauth). `seed_demo(s)` idempotent on source_url. `fetch_hn_top(s, n=10)`: HN topstories → 보안 키워드 매칭만 ScrapPost(status=pending), 네트워크 실패 silent(0).

### `event_analyzer.py` — 학생 보고 채점 분석 (Phase 9.3, 핵심)
**원칙**: 단순 echo/템플릿 금지. 학생 보고 텍스트 ↔ 미션 기준 실제 비교.
- dataclass `StudentReport{user_name,event_type,target,points_claimed,description,what_i_did,what_happened}` (+ `combined_text()` lowercased), `MissionContext{side,order,instruction,target_vm,points,hint,verify_expect,semantic_intent,success_criteria[],acceptable_methods[],negative_signs[]}`, `ScenarioContext{title,description,course_ref}`, `AnalysisResult{reasoning(markdown), model, cost_usd, criteria_met[], criteria_missing[], negative_signs_hit[]}`.
- heuristic(bastion): `_tokens`(영숫자+한글, len≥3), `_STOPWORDS` 제거, `_criterion_match_score`(crit keyword 가 학생 텍스트에 든 비율 + 매칭 단어). `_evaluate_criteria(threshold=0.34)` met/missing. `_evaluate_negative_signs(threshold=0.5)`. `_judge_score`(과대보고/감점부적절/적정/부분인정/근거부족/오답신호/재검토 verdict). `_learning_recommendation`(course_ref + MITRE T코드 + semantic_intent nutshell). `_bastion_analyze` → markdown 섹션(학생보고/성공조건 대비✅❌/negative_signs⚠️/점수적정성/다시시도/📚학습권장). mission None 이면 "특정 미션과 연결되지 않음" 안내.
- claude: `_CLAUDE_SYSTEM`(한국어 markdown 5섹션, 사실 날조 금지·payload 통째 금지) + `_claude_analyze`(claude -p --output-format json --model --append-system-prompt, JSON payload, total_cost_usd 파싱).
- `analyze_event(monitor, report, mission, scenario)`: 항상 base(heuristic) 계산. monitor≠claude → base. claude → `_claude_analyze`, 실패/빈응답(`_` prefix)이면 heuristic fallback(명시), 성공이면 LLM reasoning + base 의 구조화 필드.

### `grader.py` — auto_monitor probe 매칭 (Phase 9 / 9.3)
`JudgeResult{matched, reasoning, model, cache_hit=False, cost_usd=0}`. `_judge_cache[(battle_id,order,probe_hash)]`. `_heuristic_match(probe_text, expect)` = expect.lower() in probe_text.lower(). `judge(monitor, battle_id, mission, expect, probe_text, probe_command, scenario_title, course_ref, ...)`: order/hash/key, matched=heuristic. cache hit → 재사용. matched=False → 짧은 noted("점수 미부여"). matched=True → `event_analyzer.analyze_event`(probe_command→what_i_did, probe_text→what_happened, auto_actor_label) 로 진짜 분석. `clear_cache(battle_id)`.

### `auto_monitor.py` — battle background 자동 모니터 (Phase 4/9/9.1)
- `APP_PROBES`(8앱 → /exec curl 화이트리스트), `DEFAULT_PROBES`(web/juiceshop/siem), `_resolve_probes(target_apps)`.
- `POLL_INTERVAL_SEC=15`, `HEARTBEAT_EVERY_N_TICKS=4`(=60s). state: `_tasks`, `_seen_blue_hits`, `_last_probe_hash`.
- `_exec_probe(infra, command)`: POST :{port_map.bastion_api|9100}/exec X-API-Key, body {target:"monitor", command}. 응답 stdout+stderr+text 합산.
- `_refined_expects_from_blue(scenario)`: blue 미션별 (order, points, refined_expect(dry_run 우선) 또는 verify.expect, raw mission). points & expect 있는 것만.
- `_tick(battle_id, tick_idx)`: battle active 아니면 StopAsyncIteration. participants→infras, scenario, target_apps, monitor_mode 로드. tick%4==0 이면 `_emit_heartbeat`. infra/scenario/expects 없으면 return. blue_user(또는 solo/free) 첫 participant. 각 probe 실행 → body_text → probe_hash(직전과 동일=unchanged → LLM 스킵, effective_monitor="bastion"). expect 가 body 에 없으면 skip. `grader.judge(effective_monitor,...)` matched 면 seen.add(order) + `bs.add_event(event_type="detect", points, detail{source:auto_monitor, probe, matched_expect, blue_mission_order, scenario_id, monitor, model, cache_hit, cost_usd, probe_hash}, reasoning=verdict.reasoning)`.
- `_emit_heartbeat`: 직전 event 가 collapsible heartbeat(system/target=monitor/detail.kind=heartbeat_range/points=0)면 **in-place UPDATE**(ticks+1, start_ts 보존, end_ts/description/reasoning 갱신) → DB row 1개로 collapse. 아니면 새 row(ticks=1). 한국어 시간표시 `_fmt_korean_time`(오전/오후 H시 MM분). 점수 이벤트가 끼면 다음 heartbeat 부터 새 row.
- `_loop(battle_id)`: tick 증가 → `_tick` (StopAsyncIteration→break, Exception→log) → sleep. finally 정리(_tasks/_seen/_last_probe_hash/grader.clear_cache).
- `start(id)`/`stop(id)`/`is_running(id)`.

### `hints.py` — 명시 요청 힌트 (Phase 9)
- per-(battle,user) 60s cooldown(`_last_request` monotonic, `cooldown_remaining`/`_mark`). hint_enabled=False → ValueError("hint disabled"). status≠active → ValueError. cache key `side={side}|last_event={last_event_id}` → BattleHint 재사용(cache_hit).
- bastion: `_bastion_static_hint`(LLM 0, 미완료 미션 todo 2개 안내). claude: `_claude_hint`(claude -p, `_CLAUDE_SYSTEM` 한국어 코치, payload/정답 금지, 미션번호 명시). cost 는 micro-cents(int) 로 저장. `HintResult{text,model,cache_hit,cost_usd}`.

### `audit.py` — 감사 로그 (best-effort)
`_client_ip`(x-forwarded-for 첫 항목 우선), `_user_agent`(<=255). `record(session, actor, action, target_type?, target_id?, detail?, request?, actor_email?)`: AuditLog insert + commit, 실패해도 본 작업 막지 않음(rollback).

### `rate_limit.py` — in-memory sliding-window (Phase 8)
`_buckets` defaultdict(deque) + threading.Lock. `_disabled()` = env `TUBEWAR_RATE_LIMIT_DISABLE` in (1,true,yes). `_hit(key, limit, window)` → (ok, retry_after). `reset()`(테스트). `enforce_signup`: per-IP 5/300s → 429 + Retry-After. `enforce_login`: per-IP 10/300s + per-email 5/300s → 429.

---

## 10. 공방전 모드 & 채점 모델 요약

| 모드 | 참가자 | 인프라 매핑 | role |
|------|--------|-------------|------|
| solo | 1명 (red+blue 둘 다 본인) | 자기 6v6 | role="solo", lobby 불가 |
| duel | 2명 (A=red, B=blue) | A↔B 6v6 | red/blue 각 1 |
| ffa  | 2~16명 | 각자 6v6 | free(또는 red/blue) |

- **monitor=bastion**: heuristic 채점(LLM 0, 비용 0).
- **monitor=claude**: probe diff 발생 시에만 Claude CLI 1회 호출(probe_hash 캐시), 자연어 분석.
- 점수: BattleEvent.points → 해당 participant.score 즉시 반영. 미션별 max points 는 시나리오 mission.points.
- 채점 근거: 모든 score 이벤트에 `reasoning`(markdown) 첨부 — "어디를 어떻게 했기에 정답/오답 + 학습 권장".

---

## 11. 시나리오 카탈로그 (`contents/battle-scenarios/`) — 17종

각 YAML 표준 키: `id, title, description, difficulty(easy|medium|hard), time_limit(sec), battle_type(1v1), red_missions[], blue_missions[]`.
mission 키: `order, instruction, hint, points, target_vm(attacker|web|secu|siem|...), verify:{type:output_contains, expect, semantic:{intent, success_criteria[3+], acceptable_methods[3~4], negative_signs[3]}}`.

| 파일 | id | title | diff | tl(s) | red/blue |
|------|----|-------|------|-------|----------|
| apt-phase1 | apt-phase1 | APT 1단계: 정찰 + 초기 침투 | hard | 3600 | 7/7 |
| apt-phase2 | apt-phase2 | APT 2단계: 거점 확보 + 측면 이동 | hard | 3600 | 7/7 |
| apt-phase3 | apt-phase3 | APT 3단계: 데이터 탈취 + 흔적 삭제 | hard | 3600 | 7/7 |
| bruteforce-vs-lockout | bruteforce-vs-lockout | 패스워드 공격 vs 계정 보호 | medium | 2700 | 6/6 |
| championship | championship | 종합 대전: 전체 킬체인 | hard | 3600 | 8/8 |
| dos-vs-resilience | dos-vs-resilience | DoS 공격 vs 서비스 복원력 | medium | 2700 | 6/6 |
| exfil-vs-dlp | exfil-vs-dlp | 데이터 유출 vs DLP | medium | 2700 | 6/6 |
| incident-response | incident-response | 인시던트 대응 시뮬레이션 | hard | 3600 | 6/7 |
| lateral-vs-segmentation | lateral-vs-segmentation | 측면 이동 vs 네트워크 분리 | medium | 2700 | 6/6 |
| precinct6-data-theft | precinct6-data-theft | Precinct 6 Data Theft 재현 | hard | 3600 | 5/5 |
| precinct6-phishing | precinct6-phishing | Precinct 6 Phishing 재현 | hard | 3600 | 5/5 |
| privesc-vs-hardening | privesc-vs-hardening | 권한 상승 vs 시스템 경화 | medium | 2700 | 6/6 |
| purple-team | purple-team | Purple Team: MITRE ATT&CK 매핑 | hard | 3600 | 7/7 |
| recon-vs-detect | recon-vs-detect | 네트워크 정찰 vs IDS 탐지 | easy | 1800 | 6/6 |
| sqli-vs-waf | sqli-vs-waf | SQL Injection vs WAF 방어 | easy | 1800 | 5/6 |
| webshell-vs-integrity | webshell-vs-integrity | 웹셸 업로드 vs 파일 무결성 | medium | 2700 | 6/6 |
| xss-vs-filter | xss-vs-filter | XSS 공격 vs 입력 필터링 | easy | 1800 | 6/6 |

### 예시 — `sqli-vs-waf.yaml` 구조(완전체로 작성할 것; 발췌)
```yaml
id: "sqli-vs-waf"
title: "SQL Injection vs WAF 방어"
description: "내부 감사 결과 ... Red Team은 JuiceShop과 DVWA를 대상으로 SQLi ... Blue Team은 ModSecurity WAF 로그를 분석 ..."
difficulty: "easy"
time_limit: 1800
battle_type: "1v1"
red_missions:
  - order: 1
    instruction: "sqlmap을 사용하여 DVWA(http://10.20.30.80:8080)의 로그인 페이지에 SQLi 취약점이 있는지 테스트하라."
    hint: "sqlmap -u 'http://10.20.30.80:8080/vulnerabilities/sqli/?id=1&Submit=Submit' --cookie='security=low; PHPSESSID=test' --batch --level=1"
    points: 15
    target_vm: attacker
    verify:
      type: "output_contains"
      expect: "sqlmap"
      semantic:
        intent: "DVWA SQLi 취약 파라미터(id) 자동 탐지 — sqlmap boolean/error/time-based ... OWASP A03 (Injection)."
        success_criteria:
          - "sqlmap 실행 + DVWA URL 대상 (id 또는 Submit 파라미터)"
          - "PHPSESSID + security=low 쿠키 전달 (인증된 컨텍스트)"
          - "출력에 'parameter ... is vulnerable' 또는 'available techniques'"
        acceptable_methods: ["sqlmap -u <url> --cookie=... --batch", "sqlmap -r <request.txt> --batch", "manual fuzzing"]
        negative_signs: ["sqlmap 미설치/alias 누락", "쿠키 누락 → redirect", "--batch 없이 interactive 대기"]
  # ... red order 2~5 (JuiceShop 인증우회, DB 열거, UNION SELECT, 검색 SQLi) ...
blue_missions:
  - order: 1
    instruction: "ModSecurity 감사 로그에서 SQL Injection 탐지 이벤트를 확인하라."
    hint: "cat /var/log/apache2/modsec_audit.log | grep -i 'sql' | tail -20"
    points: 15
    target_vm: web
    verify: { type: "output_contains", expect: "SQL", semantic: { intent: "...942xxx...", success_criteria: [...], acceptable_methods: [...], negative_signs: [...] } }
  # ... blue order 2~6 (Apache error.log, custom SecRule 추가, apache reload, Wazuh alerts.json, suricata fast.log) ...
```
> 17개 모두 동일한 깊이(semantic 채점 메타 포함)로 작성한다. expect 는 실제 명령 출력에 verbatim 으로 나올 substring (`200 OK`, `available databases`, `ModSecurity`, `sql` 등). blue order 3 처럼 expect="" 인 경우도 있음(룰 추가류).

---

## 12. 이식 패키지 (`packages/`)

### `battle_engine/__init__.py` (CCC 원본 in-memory 참조 구현)
- `EventType(str, Enum)`: ATTACK/DEFEND/DETECT/BLOCK/EXPLOIT/ALERT/SCORE/SYSTEM.
- `@dataclass BattleEvent{event_type, actor, target, description, detail, points, timestamp}` (+ to_dict/to_json).
- `@dataclass BattleState{battle_id, battle_type="1v1", mode="manual", status="pending", challenger_id, defender_id, challenger_score, defender_score, events[], rules, started_at, time_limit=300, elapsed}` (+ time_remaining/is_expired/to_dict).
- 모듈 함수(in-memory `_battles` dict): create_battle/start_battle/add_event/end_battle/get_battle/get_events/get_active_battles/get_all_battles/generate_battle_hash/battle_stats.
> tubewar 는 이 enum/모드 개념을 차용하되 실제 상태는 `battle_service.py`(DB) 가 관리. 이 파일은 참조용으로 보존.

### `battle_factory/` (CCC 원본 보존, 경로 하드코딩 → **그대로 실행 X**)
- `generator.py`: CVE/CTI JSON → battle YAML 생성. Anthropic API 우선(`ANTHROPIC_API_KEY`, default model `claude-opus-4-7`), Ollama(`LLM_BASE_URL`, `gpt-oss:120b`) fallback. CLI `--cve/--latest/--day [--verify]`. 출력 schema(steps: order/instruction/hint/category/points/answer/verify.semantic/target_vm/script/risk_level/bastion_prompt).
- `threat_special.py`: 승인 CVE/news → 과목별 latest-threats lecture.md + lab.yaml 생성. COURSE_DIRS 매핑, news_to_cve_like, infer_courses_from_news.
- README: Phase4 리팩터 계획(경로 상수 주입, 출력처 DB, 호출처 /admin/scenarios/generate). 현재 tubewar 는 `scenario_gen.py`(claude CLI) 가 실질 생성기.

---

## 13. 프론트엔드 (`apps/ui/`)

### 기반
- `vite.config.ts`: react plugin, server host 0.0.0.0 port 5173, proxy → `http://127.0.0.1:9200` (`/auth /infras /scenarios /leaderboard /admin /users /health`, `/battles`는 `{changeOrigin:false, ws:false}`).
- `tsconfig.json`: ES2022, strict, jsx react-jsx, moduleResolution bundler, allowImportingTsExtensions, noEmit.
- `index.html`: lang ko, title "tubewar — 사이버 공방전 플랫폼", `#root` + `/src/main.tsx`.
- `main.tsx`: StrictMode + BrowserRouter + App + styles.css.
- `api.ts`: `api<T>(path, {json?, ...RequestInit})` — getToken() Bearer, json→JSON.stringify+content-type, 응답 text→JSON parse, !ok 면 `detail`/문자열로 Error throw.
- `auth.ts`: localStorage `tubewar.token`/`tubewar.user`. `getToken/getUser/login/logout/isAuthed/isAdmin`. User{id,email,name,role,is_active,created_at}.
- `styles.css`: dark theme CSS vars (`--bg #0d1117, --bg-2 #161b22, --border #30363d, --fg #c9d1d9, --fg-dim #8b949e, --primary #f97316(orange), --accent #58a6ff, --green #3fb950, --red #f85149, --yellow #d29922`). 클래스: `.card .row .col .badge(.green/.red/.yellow/.blue)`, button(+ghost/danger), input/select/textarea.

### `App.tsx` — 라우팅 + NavBar
NavBar(로그인 시만): 로고 tubewar / 대시보드 / 내 인프라 / 공방전(클릭 시 `window.dispatchEvent(new Event('tubewar:battle:reset'))`) / 리더보드 / [admin]관리자 / 우측 프로필(name(role)) + 로그아웃. `RequireAuth`/`RequireAdmin` 래퍼. 라우트: /login /signup /(→/dashboard) /dashboard /myinfra /profile /battle /leaderboard /admin(admin전용). main maxWidth 1100.

### 페이지
- **Login.tsx**: email/password → POST /auth/login → login() → /dashboard. signup 링크.
- **Signup.tsx**: email/name/password(8+) → POST /auth/signup → /myinfra.
- **Dashboard.tsx**: infra/battle/scenario 카운트 카드 + "시작하기" 안내(6v6 배포 → /myinfra 등록 → smoke → 공방전).
- **MyInfra.tsx**: 인프라 0개일 때 등록 폼(name/vm_ip/ssh_user/ssh_password/bastion_api_key + 포트 override 체크박스 → port_map). 등록된 인프라 카드(status badge, smoke 테스트 버튼, 삭제, last_smoke_result checks 테이블). PORT_HINTS 7개.
- **Profile.tsx**: 계정 정보(email/role/user_id), 표시 이름 변경(PATCH /auth/me + localStorage 갱신), 비밀번호 변경(POST /auth/me/password, 확인 일치/8자 검증).
- **Leaderboard.tsx**: 사용자 누적 테이블(/leaderboard/users: 총점/battle/승/평균) + battle 목록 클릭 → /leaderboard/battles/{id} 드릴다운(순위 🥇🥈🥉, 역할 badge, red/blue 이벤트).
- **Battle.tsx** (가장 큼): 로비(pending & mode≠solo) 목록 + admin 의 `LobbyCreateDialog`(시나리오/모드(duel/ffa)/monitor(bastion/claude)/hint/target_apps(8 카탈로그, max5 또는 🎲랜덤) → POST /battles participants:[]). `SoloRow`(시나리오 카탈로그 → solo 즉시 생성+start). 진행중/완료 목록(관전/열기). `BattleView`: 미션 패널(my_missions `MissionCard` — side 색, solved, 상세▼: 의도/성공조건/검증패턴/힌트(스포일러 details)), opponent_missions(details), 모드/채점/경과/잔여 카드, duel 팀 합계, 스코어보드(본인 강조), 시작/강제종료/새로고침(canControl=참가자|admin), 로비 join/leave 패널, 힌트 패널(side/note → POST /hint, 60s cooldown 카운트다운), 이벤트 보고 폼(① 미션 선택 자동채움 ② what_i_did ③ what_happened → POST /events), 이벤트 타임라인(`EventRow` — event_type 색 badge, points, 채점 근거▼: reasoning + raw detail JSON). active battle 1.5s 폴링. `eventTypePalette`, `TARGET_APPS_CATALOG`(juiceshop/dvwa/neobank/mediforum/govportal/aicompanion/adminconsole/web).
- **Admin.tsx**: 6탭 `['stats','generate','scrap','battles','users','scenarios']`. **StatsTab**(카드 + top scorer). **GenerateTab**(course_ref/weeks_spec/request → POST /admin/scenarios/generate, jobs 폴링 3s while queued/running/dry_run running, drafts 승인=activate). **ScrapTab**(목록 + seed + approve/reject, kg_match 표시). **BattlesTab**(status_filter, force-end/delete, monitor_running ● 표시). **UsersTab**(role 토글/active 토글 PATCH). **ScenariosTab**(/scenarios + /admin/scenarios/drafts 합쳐서 archive/복원/delete).

---

## 14. 테스트 (`tests/`) — pytest-asyncio, in-memory aiosqlite

`conftest.py`: `os.environ.setdefault("TUBEWAR_RATE_LIMIT_DISABLE","1")` (기본 limiter off). 각 테스트 모듈: `DATABASE_URL=sqlite+aiosqlite:///:memory:`, `TUBEWAR_JWT_SECRET`, (대부분)`TUBEWAR_FERNET_KEY=ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=`. autouse fixture 로 create_all/import_scenarios/drop_all. ASGITransport + AsyncClient.

- **test_smoke.py**: /health, signup→me→login 사이클.
- **test_battle.py**: 시나리오 import ≥17(WAF 포함), solo battle 전체 lifecycle(infra→scenario→create(pending)→start(active)→event(+20 점수반영)→end(completed)), duel 권한(외부인 403), solo 2명 거부, infra password Fernet 암호화(평문 미저장, `fernet:` prefix).
- **test_lobby.py**: admin lobby(참가자0) → 참가자 없이 start 400 → alice red join → 중복/role taken 거부 → bob blue join → start. role 별 미션 노출(red→red my/blue opp, 관전자 my=0/opp=양쪽). leave/rejoin. solo 본인 강제.
- **test_battle_options.py**: target_apps 검증(bogus 400, 6개 400, 3개 정상, random 2~4), hint disabled 400 / enabled 200(bastion 모델, cache_hit False, cost 0) / 즉시 재요청 429. 관전자 view 200 + event/hint 403. heartbeat collapse(3회→1 row ticks=3 "무변화 구간", 점수 이벤트 후 새 row ticks=1). event reasoning roundtrip(mission_order 없음→"특정 미션 미연결", 있음→success_criteria 100% 충족→criteria_met==전체, ✅).
- **test_admin.py**: stats + battle 관리(force-end 학생 403/admin cancelled, delete 204), self-demote/deactivate 400, scenario archive(학생 목록 제외) + delete.
- **test_audit.py**: signup/login/login_fail 기록, 학생 audit 403, action_prefix 필터, X-Forwarded-For ip 캡처(첫 항목) + actor_email + target_id.
- **test_rate_limit.py** (limiter 활성): signup per-IP 5/5분(6번째 429 + Retry-After), login per-email 5(다른 IP 여도 막힘), IP별 bucket 격리.
- **test_profile.py**: 비번 변경 happy/wrong-current/must-differ, 이름 변경.

실행: `bash scripts/dev.sh test` 또는 `cd apps/api 없이 PYTHONPATH=apps/api python -m pytest tests/ -v` (테스트가 `from app...` import 하므로 `apps/api` 가 sys.path 에 있어야 — pyproject `pip install -e` 로 해결).

---

## 15. 빌드 / 검증 / DoD

### 빠른 시작
```bash
git clone https://github.com/mrgrit/tubewar && cd tubewar
bash scripts/setup.sh          # postgres + venv + npm
cp .env.example .env           # JWT_SECRET / ADMIN_PASSWORD 수정
bash scripts/dev.sh api        # http://127.0.0.1:9200
bash scripts/dev.sh ui         # http://127.0.0.1:5173  (다른 터미널)
```

### 검증 커맨드
```bash
curl http://127.0.0.1:9200/health
curl -X POST http://127.0.0.1:9200/auth/signup -H 'content-type: application/json' \
  -d '{"email":"alice@test","password":"alice1234","name":"Alice"}'
curl -X POST http://127.0.0.1:9200/auth/login -H 'content-type: application/json' \
  -d '{"email":"alice@test","password":"alice1234"}'
bash scripts/dev.sh test       # pytest 전체 green 이어야
```

### e2e (`scripts/e2e_full_duel.sh`)
admin 로비 개설(duel, juiceshop+dvwa, hint=on) → 참가자 없이 start 400 → alice(red)/bob(blue) self-join → 중복 join 거부 → start → RED/BLUE 전 미션 매뉴얼 보고(점수 검증) → reasoning 샘플 → 힌트(bastion=무료) → end → leaderboard 반영. env: BASE/ADMIN_EMAIL/ADMIN_PW/RED_*/BLUE_*/SCN. 사전: alice/bob 회원가입 + infra 등록 필요.

### Definition of Done (재구축 완료 기준)
1. `bash scripts/setup.sh && dev.sh api/ui` 후 회원가입 → 인프라 등록 → smoke → solo/duel battle 생성·시작·이벤트·종료가 UI 클릭으로 동작.
2. `pytest tests/` 전부 green (시나리오 ≥17 import 포함).
3. admin 6탭 동작 + 권한 체크(self-demote 거부, archive 후 학생 노출 차단, 관전자 read-only).
4. 자동 모니터 heartbeat collapse + monitor=claude 일 때만 LLM 호출 + 모든 score 이벤트에 reasoning.
5. SSH 자격 Fernet 암호화(평문 미저장).

---

## 16. Phase 히스토리 (참고 — 모두 완료 상태로 재구축)

- **Phase 1 — 골격** (2026-05-07): 모노레포 + git, FastAPI(auth/infras/battles placeholder), PG 모델 8테이블, 6v6 smoke(TCP+Bastion API), React UI(Login/Signup/Dashboard/MyInfra/Battle/Admin), battle_engine/factory/scenarios 이식, dev/setup 스크립트.
- **Phase 2 — 공방전 MVP** (2026-05-07): battle_engine in-memory → DB persistence(`battle_service.py`), solo/duel/ffa + 권한, 점수 evaluator, SSE 스트림, SSH Fernet 암호화, 시나리오 17 import(lifespan), Battle UI(solo), Bastion client stub, e2e + test 7/7.
- **Phase 3 — Claude 시나리오 생성** (2026-05-08): `scenario_gen.py`(claude -p --output-format json), 자연어→draft background job + 폴링, lecture.md 컨텍스트(`lecture_context.py`, CCC_CONTENT_ROOT), pydantic schema 검증, port_map 확장. 실 6v6 e2e(SQLi+WAF+Wazuh, ~$0.07/42s).
- **Phase 4 — 미션 자동 검증 + auto-monitor** (2026-05-08): `dry_run.py` 4축 평가(haiku), /exec reachability probe, pass_rate≥0.7→validated 자동, auto-monitor 60s heartbeat + refined_expect probe 매칭 → BLUE 자동 점수.
- **Phase 5 — Bastion 스크랩 게시판** (2026-05-08): `scrap_crawler.py`(seed_demo 3 + fetch_hn_top + 키워드 regex), /admin/scrap list/seed/approve/reject, 승인 → kg_match course/weeks 추출 → 자동 generate → spawned_scenario_id 링크.
- **Phase 6 — 모니터링 + 채점 viewer + 리더보드** (2026-05-08): BattleEvent.detail JSONB scoring evidence, UI "채점 근거 ▼", `/leaderboard/users`+`/battles/{id}`, Leaderboard 페이지.
- **Phase 7 — 관리자 대시보드** (2026-05-08): /admin/stats, /admin/battles(+force-end/delete), /admin/users(+PATCH self-demote 거부), /admin/scenarios PATCH/DELETE, UI Admin 6탭, test_admin.py.
- **Phase 8 — audit + rate limit + 프로필** : `audit.py`/AuditLog, `rate_limit.py`(signup 5/login 10+email 5 per 5분), 프로필(이름/비번 변경), test_audit/test_rate_limit/test_profile.
- **Phase 9 — 취약 웹 선택 + 관전 + 힌트 + 자연어 채점** : battle.target_apps(1~5 또는 random) + hint_enabled + monitor(bastion/claude), 관전 모드(인증자 누구나 read-only), `hints.py`, `grader.py`(probe→mission 자연어 채점 + probe_hash 캐시).
  - **9.1**: nav 리셋 이벤트, heartbeat in-place collapse, 매뉴얼 이벤트 자연어 채점.
  - **9.2**: admin 로비 + 학생 self-join + role 별 미션 가시화, e2e_full_duel.sh.
  - **9.3**: `event_analyzer.py` — 채점 근거를 입력 echo → success_criteria 실제 비교 분석(criteria_met/missing/negative_signs_hit), what_i_did/what_happened 보고 필드 추가.

---

## 17. 보안/마이그레이션 잔여 항목 (재구축 시 인지)
- [x] Infra.ssh_password_enc Fernet 암호화 (Phase 2 완료).
- [ ] alembic 마이그레이션(현재 create_all). prod 전 도입.
- [ ] JWT in-localStorage → httpOnly cookie 검토(CSRF).
- [ ] scenario_jobs/rate_limit in-memory → redis(멀티 노드 시).
- [ ] SSE 폴링 → redis pubsub.
- [ ] CORS prod 화이트리스트 정확화.

— 끝 —
