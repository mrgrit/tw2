# tw2 운영 가이드 (배포·서비스·코호트·SIEM)

> 전체 기능을 무중단으로 운영하기 위한 절차와 **작업 간 의존성**을 정리한다.

## 0. 배포 — `bootstrap.sh` 한방

새 호스트 배포는 **`sudo bash scripts/bootstrap.sh`** 하나로 끝난다. 내부에서:
시스템 패키지(python3·venv·node·git·sqlite·빌드도구) → python venv + 의존성(aiosqlite 포함)
→ `.env` 생성 → UI 빌드 → DB 시드(스키마·관리자·시나리오는 앱 startup 이 자동 수행)
→ systemd 유닛 `tw2-api`/`tw2-ui` 등록·기동.

```bash
sudo bash scripts/bootstrap.sh                 # 표준 (systemd)
bash scripts/bootstrap.sh --no-systemd         # systemd 없이 nohup
TW2_API_PORT=9301 TW2_UI_PORT=5174 sudo bash scripts/bootstrap.sh   # 포트 override
```

- 포트 기본: **API 9200 / UI 5173** (`TW2_API_PORT`/`TW2_UI_PORT` 로 override).
- 관리자: `TW2_ADMIN_EMAIL`(기본 `admin@tubewar.app`) / `TW2_ADMIN_PASSWORD`(미지정 시 자동생성).
- DB 는 **SQLite**(`.data/tw2.sqlite3`) — postgres/docker-compose/OpenSearch **불필요**.
  구 `setup.sh`(postgres)·`tubewar.sh`(OpenSearch)·docker-compose 는 모두 구식.

> startup(lifespan) 이 `create_all` + 신규 컬럼 보강(`schema_upgrade`) + 관리자 시드 +
> `contents/battle-scenarios/*.yaml` 자동 import 를 수행한다. 별도 마이그레이션 단계 없음.

## 1. 서비스 (systemd) — 부팅·크래시 자동 재시작

2개 유닛이 `/etc/systemd/system/` 에 등록되고 `enable` 됨(부팅 시 자동 기동).

| 유닛 | 포트 | 역할 | 의존(After) |
|------|------|------|-------------|
| `tw2-api` | 9200 | FastAPI(uvicorn). `.env` 를 EnvironmentFile 로 로드 | network-online |
| `tw2-ui` | 5173 | React 빌드물 서빙 | tw2-api |

```bash
# 상태 확인
systemctl is-active tw2-api tw2-ui
# 재시작 / 로그
sudo systemctl restart tw2-ui            # UI 만
sudo systemctl restart tw2-api           # API 만 (.env 변경 후엔 필수)
sudo journalctl -u tw2-api -n 100 -f     # 로그 추적
```

> ⚠️ **UI 코드 변경 시**: `cd apps/ui && npm run build` 후 `sudo systemctl restart tw2-ui`.
> 서빙되는 것은 빌드물(dist)이므로 재빌드 필요.
> ⚠️ **API `.env` 변경 시**: `sudo systemctl restart tw2-api`.
> (`--no-systemd` 로 띄운 경우엔 `.data/api.log`·`.data/ui.log` 확인 후 프로세스 재기동.)

## 2. 코호트 (수업 단위) — 등록·구조

코호트는 트리(course → section …) + 다대다 멤버십. **admin 권한**으로 관리.

- **UI**: 관리자 페이지 → `cohorts` 탭. 노드 생성(kind/name/parent/course_ref) + 멤버 배치/이동/제거. SIEM 딥링크 버튼.
- **course_ref** 는 시나리오 트랙/`category` 와 느슨히 연결(예: course_ref `soc-adv` ↔ 시나리오 `soc-adv`).
- **API**: `POST /cohorts`(admin), `POST /cohorts/{id}/members`(admin), `GET /cohorts`, `GET /cohorts/tree`.

코호트는 9개 트랙(soc/soc-adv/attack/attack-adv/compliance/web-vuln/cloud-container/secuops/secuops-easy)
구조로 course+section 트리를 구성하고 학생을 배치한다.

## 3. SIEM — 테스트 내용 보기

SIEM 은 **el34-siem (Wazuh manager + indexer)** 가 담당한다. 구 중앙 OpenSearch
(`lab_monitor`) 적재는 tw2 에서 **OFF**(`TUBEWAR_LAB_MONITOR=0`, 기본값).

**데이터가 쌓이는 조건**: 배틀을 **코호트를 지정해서**(create 시 `cohort_id`) 돌려야
코호트 단위로 활동/채점 문서가 모인다. `cohort_id` 없이 돌리면 신원-only 로만 가서
코호트 SIEM 화면이 빈다.
- 적재원: ① `lab_monitor` 가 (활성 시) 배틀 중 Assessor `/activity` pull →
  alert/fim/command/mission_check, ② `grade_submission` 채점 완료 → grade 문서.

**보는 법**:
- el34-siem 의 Wazuh 대시보드에서 출처 IP·룰·FIM·alert 를 직접 조회.
- 관리자 페이지 → `siem`/`cohorts` 탭의 필터·통계·미션 달성도.

## 4. 작업 간 의존성

```
bootstrap.sh (systemd tw2-api/tw2-ui + 시나리오 자동 import)
  └─ 코호트 트리 생성/배치              [API 가동 필요]
       └─ 코호트 배틀(cohort_id 지정)   [코호트 + el34 인프라 reachable]
            └─ 제출 → 채점 → SIEM 가시화 [전부]
```
- 시나리오 **128개**(9트랙: soc/soc-adv/attack/attack-adv/compliance/web-vuln/cloud-container/secuops
  ×15, secuops-easy ×6 = 126 + 호환 레거시 2)는 startup 시 자동 import.
  검증: `python scripts/validate_scenarios.py <prefix> --markers`.
- 워크북 생성: `python scripts/gen_workbooks.py`.
- 코호트 SIEM 가시화는 **코호트 지정 배틀**에 의존(3절 참고).

## 5. 빠른 점검 체크리스트

```bash
systemctl is-active tw2-api tw2-ui                                       # 2x active
curl -s -o/dev/null -w '%{http_code}\n' http://127.0.0.1:9200/health     # 200
curl -s -o/dev/null -w '%{http_code}\n' http://127.0.0.1:5173/           # 200 (UI)
# Assessor reachability (el34 타깃)
curl -s -H 'X-API-Key: ccc-api-key-2026' http://192.168.0.80:9201/health
```

## 6. 모니터링 (학생 행동)

`scripts/monitor/gwanje.py` — 무료 deterministic 기본, 읽기전용·한 줄 보고.
상세는 `scripts/monitor/README.md` 참고.

## 7. 채점 한계 (el34 인프라 갭)

el34 는 다음 텔레메트리를 보유하지 않아 **자동 채점이 불가**하다. 해당 미션은
review 보류 또는 수동 확인으로 처리:
- `authentication_failed` (SSH auth 로그)
- Windows / Sysmon 이벤트
- 엔드포인트(endpoint) 텔레메트리
