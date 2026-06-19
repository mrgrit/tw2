# tubewar — Claude Code 가이드

> 이 파일은 Claude Code (CLI) 가 tubewar 작업 시 따르는 프로젝트별 지침이다.
> CCC `/home/opsclaw/ccc/CLAUDE.md` 와 별개. tubewar 작업 중에는 이 파일 우선.

## 프로젝트 한 줄

**el34** 사이버 훈련 인프라 위에서 학생 **Red/Blue 공방전** 을 관리·채점·시각화하는 중앙 플랫폼.
(구 `6v6` 기반 `tubewar` 의 el34 이식판 = 레포 `tw2`)

## 아키텍처

| 컴포넌트 | 경로 | 포트 | 역할 |
|----------|------|------|------|
| api | apps/api/ | 9200 | FastAPI — 인증/인프라/배틀/시나리오/채점 |
| ui | apps/ui/ | 5173 (vite) | React — 학생/강사/관리자 UI |
| DB | .data/tw2.sqlite3 | - | **SQLite** (postgres/docker 불필요) |
| battle_engine | packages/battle_engine/ | - | 이벤트/점수/상태 머신 |
| battle-scenarios | contents/battle-scenarios/ | - | YAML 시나리오 카탈로그 (128개, 9트랙) |
| 채점 하니스 | scripts/play_scenario.py | - | RED/BLUE 증거 심기 + claude 라이브 채점 (검수용) |

## 외부 의존

- **인프라 el34** (단일 타깃 VM + 외부 공격자 VM):
  - 타깃 `192.168.0.151` (ssh ccc/1) — 패킷흐름 **FW→IPS(Suricata)→WAF(Apache+ModSec)→앱**, 컨테이너 `el34-*`(fw/ips/web/siem + 취약앱 juiceshop·dvwa·neobank·govportal·mediforum·adminconsole·aicompanion + bastion).
  - 외부 공격자 `192.168.0.202` (att/1, **별도 VM**) — 웹 진입 `192.168.0.161` 로 공격, **출처 IP가 Suricata/ModSec/Wazuh 전 계층에 보존**.
  - **Assessor** `192.168.0.151:9201` (헤더 `X-API-Key: ccc-api-key-2026`) — RED/BLUE 결정론 체크(file/log/port/process/wazuh_alert).
  - vhost `*.6v6.lab` 유지(.161 Host 헤더/포트분기), 내부망 10.20.30/31/32/40.x.
- 학생 인프라 등록은 **타깃(el34, .151) + 공격자(.202) 2개**.
- **외부 공격자 명령 로그는 수집 안 됨** → 공격 채점은 `command_ran` 대신 **타깃 인프라의 공격 흔적**
  (ModSec/Suricata/Wazuh + 출처 IP·payload 상관)으로 한다. el34 미보유 텔레메트리(SSH auth·Windows/Sysmon·
  endpoint)는 자동채점 불가 — `contents/battle-scenarios/GRADING-LIMITATIONS.md` 참고.

## 코드 규칙

- Python ≥ 3.10, FastAPI 비동기 핸들러 우선, SQLAlchemy 2.x async.
- TypeScript strict, React 18, Vite, 함수형 컴포넌트만.
- 비밀 (.env / SSH 자격) — 코드/커밋 절대 금지. `os.environ` / Vault 통해서만.
- 학생 자격 증명(SSH 등)은 DB 저장 시 Fernet 대칭 암호화(`apps/api/app/crypto.py`).

## 운영 원칙

- **땜빵 금지**: 임시 우회 대신 근본 원인 수정.
- **테스트 후 완료 선언**: 문자열 수정만으로 완료 X. e2e 흐름 (signup → login → infra 등록 → smoke) 까지 확인.
- **el34 의 표면(외부 노출 API/포트·Assessor)만 의존**: 컨테이너 내부 구조에 직접 묶지 않기. el34 가 버전업돼도 tw2 는 외부 표면만 보면 동작해야. (단 채점 하니스는 검수용으로 docker exec 사용)

## 개발 명령

```bash
bash scripts/bootstrap.sh   # 한방: 패키지+venv+UI빌드+.env(SQLite)+DB시드+systemd
bash scripts/dev.sh api     # uvicorn (autoreload)
bash scripts/dev.sh ui      # vite (dev)
bash scripts/dev.sh test    # pytest
.venv/bin/python scripts/gen_workbooks.py   # 학생 워크북(.docx) 생성
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

## 관제 (학생 행동 모니터링)

"관제 시작 / 관제해줘" → `gwanje` 스킬, 또는 직접:
`.venv/bin/python scripts/monitor/gwanje.py` (무료 deterministic 기본, 읽기전용·한 줄로 끝).
- 에이전트 선택: `--agent deterministic|local|claude` (+`--model`). claude=과금 → 기본 차단(`--allow-billed` 필요). 목록 `--agents`.
- 스마트 트리거(cron 금지): `salience>=5` | heartbeat≥25분 | 이상징후 즉시일 때만 보고.
- 점검: cohort_id NULL(코호트 SIEM 미적재)·고아배틀(active>6h)·grade_fail/assess_bad·새 기능(워크북·AI피드백) 정확성.
- 상세: `scripts/monitor/README.md`, 스킬 `.claude/skills/gwanje/SKILL.md`.

## 현재 Phase

**el34 이식 완료** — 9트랙 128 시나리오 el34 적응·라이브검수·배포 자동화(`scripts/bootstrap.sh`) 완료. 로드맵 `docs/roadmap.md`.
