# tw2 관리자(admin) 매뉴얼

> 대상: 플랫폼을 운영하는 **관리자(admin)**.
> 설치·환경변수·부트스트랩·관리 콘솔 전 기능·el34/Assessor 연동·SIEM·운영/장애 대응을
> 다룹니다. (수업 운영 관점은 교수 매뉴얼, 학생 사용은 학생 매뉴얼 참조.)

- 중앙 서버(tw2): `http://0.0.0.0:9200` (API) / UI `:5173`. DB 는 **SQLite**(`.data/tw2.sqlite3`) —
  Postgres·docker 불필요.
- el34 인프라(구 6v6): 타깃 VM `192.168.0.151`, 웹 진입 `192.168.0.161`, 외부 공격자 VM `192.168.0.202`.
- Assessor: `192.168.0.151:9201` (header `X-API-Key: ccc-api-key-2026`) — RED/BLUE 결정론 체크.

---

## 1. 아키텍처 한눈에

```
el34 인프라(자체 Wazuh SIEM) ──/assess(pass·fail)──┐  (Assessor :9201)
                              ──/activity(lists)──┤
                                                  ▼
                                          tw2 (CC, 중앙 두뇌)
   ├─ SQLite : User/Infra/Cohort/Battle/진도/점수/StudentFeedback (플랫폼 로직)
   ├─ check_compiler(생성시) → mission.checks  ── grader 가 채점에 사용
   ├─ claude CLI(claude-sonnet-4-6) 의미채점 + Assessor 결정론 체크
   ├─ lab_monitor → 진도·병목 → 막힌 학생만 CC → feedback (기본 OFF)
   └─ (옵션) provisioner → el34 /provision-rule (기본 OFF)
```

- 데이터 흐름은 **PULL**: tw2 가 el34 인프라의 Assessor 를 read-only 로 당겨옵니다.
- el34/Bastion 은 **불변**. tw2 는 el34 의 외부 표면(Assessor/Bastion API)만 호출합니다.
- 채점은 **결정론(Assessor) 체크 + claude CLI(claude-sonnet-4-6) 의미채점**. `claude` CLI 가 없으면
  채점은 review 보류 상태로 남고 플랫폼은 정상 동작합니다.

### 컴포넌트
| 컴포넌트 | 경로 | 포트 | 스택 |
|----------|------|------|------|
| api | apps/api/ | 9200 | FastAPI async, SQLAlchemy 2.x async |
| ui | apps/ui/ | 5173 | React 18 + TS strict + Vite |
| db | `.data/tw2.sqlite3` | — | SQLite (aiosqlite, docker 불필요) |
| el34 SIEM | el34-siem 컨테이너 | — | Wazuh manager + indexer (인프라 자체) |

---

## 2. 설치 & 기동

초기 리눅스에서 **한방 부트스트랩**으로 플랫폼(API+UI+DB)을 통째로 구축합니다.

```bash
sudo bash scripts/bootstrap.sh        # 권장: 전체 자동
```

`bootstrap.sh` 가 순서대로:
1. 시스템 패키지(`python3`·`venv`·`pip`·Node 20·`git`·`sqlite3`·빌드도구) 설치,
2. `.env` 자동 생성(SQLite·랜덤 JWT·관리자·`0.0.0.0` 바인딩) — 관리자 비번은 `.admin-credentials.txt` 에 기록,
3. python venv + 의존성(`pip install -e apps/api[dev]`, aiosqlite 포함),
4. UI 의존성 설치 + 프로덕션 빌드,
5. DB 초기화(앱 startup 이 스키마+관리자+시나리오 자동 시드),
6. systemd 서비스 **`tw2-api` / `tw2-ui`** 등록·기동(systemd 없으면 `nohup`).

옵션·env override:

```bash
bash scripts/bootstrap.sh --no-systemd        # systemd 없이 nohup 으로 기동
bash scripts/bootstrap.sh --demo-users        # 데모 학생(shin/kim/mrgrit) 시드
bash scripts/bootstrap.sh --dev-ui            # UI 를 빌드 대신 vite dev 로
TW2_API_PORT=9301 TW2_UI_PORT=5174 \
  TW2_ADMIN_PASSWORD=secret bash scripts/bootstrap.sh
```

서비스 상태/로그·재기동:

```bash
systemctl status tw2-api tw2-ui
journalctl -u tw2-api -f
sudo systemctl restart tw2-api
```

> (구) `scripts/setup.sh`(postgres 컨테이너)·`scripts/tubewar.sh`(OpenSearch 포함)·docker compose 는
> **구식**이며 `bootstrap.sh` + systemd 로 대체되었습니다.

부팅 시 앱 lifespan 이 자동으로:
1. 테이블 생성(`create_all`) + **기존 DB 호환 컬럼 보강**(`schema_upgrade.ensure_added_columns` —
   예: `battles.cohort_id`),
2. `ADMIN_EMAIL` 관리자 부트스트랩(`ADMIN_PASSWORD` 로 1회 생성),
3. `contents/battle-scenarios/*.yaml` 시나리오 import(현재 **128개**).

---

## 3. 환경변수 (`.env` / `os.environ`)

> 비밀(.env/SSH/Fernet)은 **절대 커밋 금지**. `.gitignore` 가 `.env`/`*.key`/`.data/` 등을 제외합니다.

> `bootstrap.sh` 가 `.env` 를 자동 생성합니다. 아래는 그 핵심 키이며, 운영 전 비밀 키만 점검하면 됩니다.

### 핵심
| 변수 | 기본 | 설명 |
|------|------|------|
| `TUBEWAR_API_HOST` / `TUBEWAR_API_PORT` | 0.0.0.0 / 9200 | API 바인드 |
| `TUBEWAR_JWT_SECRET` | (자동 랜덤 hex32) | bootstrap 이 생성. **수동 운영 시 32자+ 유지** |
| `TUBEWAR_JWT_EXPIRES_HOURS` | 720 | 토큰 만료 |
| `DATABASE_URL` | `sqlite+aiosqlite:///<repo>/.data/tw2.sqlite3` | SQLite 단일 파일 DB |
| `TUBEWAR_FERNET_KEY` | 없으면 `.data/fernet.key` 자동생성 | SSH 자격 암호화 키. **운영 시 고정** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` | admin@tubewar.app / (자동) / admin | 부트스트랩 관리자. 비번은 `.admin-credentials.txt` |
| `TUBEWAR_API_KEY` | `tw2-api-key-<연도>` | 내부 서비스 API 키 |
| `TUBEWAR_RATE_LIMIT_DISABLE` | (off) | `1` 이면 rate limiter no-op (테스트용) |

### 채점/AI (claude CLI 기반)
의미채점은 `claude` CLI(기본 `claude-sonnet-4-6`)로 수행하고, 결정론 체크는 Assessor 가 담당합니다.
**`claude` CLI 가 설치돼 있지 않으면 채점은 review 보류 상태로 남습니다(플랫폼은 정상).**

| 변수 | 기본 | 용도 |
|------|------|------|
| `TUBEWAR_ANALYZER_MODEL` | claude-sonnet-4-6 | 이벤트 분석·의미채점 모델 |
| `TUBEWAR_GRADE_TIMEOUT` | 200 | 채점(claude CLI) 타임아웃(초) |
| `TUBEWAR_GRADE_ROUNDS` | 1 | 채점 라운드 수 |

### 연동 토글
| 변수 | 기본 | 설명 |
|------|------|------|
| `TUBEWAR_LAB_MONITOR` | `0`(OFF) | `1` 이면 배틀 시작 시 백그라운드 실습 모니터 자동 기동. **tw2 는 중앙 OpenSearch 적재를 끔(0).** el34 자체 Wazuh 가 SIEM 역할(§6) |
| `SKIP_PROVISIONER` | skip(OFF) | `0`/`false` 일 때만 룰 무장(`/provision-rule`) 활성 |
| `ASSESSOR_LIVE` | (off) | `1` + 실 vm_ip 일 때만 라이브 통합 테스트 실행 |

---

## 4. el34 Assessor 연동 계약

tw2 가 호출하는 el34 외부 표면(읽기 전용, 부작용 0). 기준 엔드포인트는
**`http://192.168.0.151:9201`**, header `X-API-Key: ccc-api-key-2026` 입니다(vhost `*.6v6.lab` 유지):

- **채점** `POST http://{vm_ip}/assess` — header `Host: assessor.6v6.lab` + `X-API-Key`.
  `port_map['assessor']`(예: `:9201`) 가 있으면 직접 포트 우선. body `{battle_id?, checks:[{id,type,target,params}]}`,
  type ∈ `file_exists|file_contains|file_hash|process_running|port_listening|log_contains|wazuh_alert|fim_change|command_ran`.
  resp `{collected_at, results:[{id,passed,evidence,raw?}]}`.
- **모니터링** `POST http://{vm_ip}/activity` — body `{since_sec, limit, want:[commands,fim,alerts,services], filter?}`
  → `{collected_at, commands[], fim[], alerts[], services{}}`.
- **(옵션) 룰 무장** `POST http://{vm_ip}/provision-rule` — 검증 룰 템플릿 적용/회수(기본 OFF).

`X-API-Key` 값은 인프라 등록 시의 `bastion_api_key`(el34 는 `ccc-api-key-2026`)를 사용합니다. NAT 뒤
환경(인바운드 불가)도 `assessor_client` 추상화가 push 모드를 막지 않도록 설계되어 있습니다.

### 4.1 2-attacker 모델 과 외부 공격 채점 — ★ 중요
el34 는 두 공격자 페르소나를 둡니다:
- `attacker` (insider, el34-attacker 컨테이너) — 내부 라우팅/DNS 로 직접 공격.
- `attacker-ext` (outsider, 별도 VM `192.168.0.202`, ssh `att/1`) — **망 밖에서 공개 포트
  (80/443 등) + `Host:` 헤더로만** 공격(내부 직접 접근 불가). source IP 가 보존됩니다. cross-infra
  (상대 VM 공격)의 기본 모델.

**채점 함의(공정성)**: el34 는 **외부 attacker(attacker-ext)의 명령 로그를 신뢰성 있게 수집하지 못합니다.**
따라서 tw2 의 AI 채점기는 **외부/cross-infra 공격을 `command_ran(attacker-ext)` 로 판정하지 않고**,
타깃(상대) 인프라의 **공격 흔적**(ModSec/Suricata 로그, Wazuh 알림, 접근로그 + source IP·payload 상관)으로
판정하도록 지시받습니다(`event_analyzer._CLAUDE_GRADE_SYSTEM`). 내부(insider) 공격은 본인 인프라의
`command_ran` 이 신뢰 가능한 증거입니다. 외부 공격 시나리오는 `assess_target: opponent` + 타깃 측
verify(log_contains/wazuh_alert)로 작성하세요(`contents/battle-scenarios/cohort-cross-infra-demo.yaml` 참고).

---

## 5. 관리 콘솔 (관리자 메뉴 탭)

로그인 후 상단 **관리자** → 탭: `통계 · 코호트 · 실습 모니터링 · 피드백 · 시나리오 생성 ·
Bastion 스크랩 · 공방전 관리 · 사용자 관리 · 시나리오 관리`.

### 5.1 통계 (`GET /admin/stats`)
사용자/시나리오/공방전/이벤트 집계 + Top scorer. **코호트 필터**로 서브트리 범위 스코프.

### 5.2 코호트 — 교수 매뉴얼 §1 과 동일(트리 CRUD·배치·이동). 노드별 **SIEM** 버튼은
코호트별 활동 조회로 연결됩니다(중앙 SIEM 상세는 §6 — tw2 는 el34 자체 Wazuh 를 SIEM 으로 사용).

### 5.3 실습 모니터링 / 피드백 — 교수 매뉴얼 §3·§4 참조.
- `GET /monitoring/battles/{id}/progress` · `/activity` · `POST .../lab-tick?with_feedback=` ·
  `GET /monitoring/cohorts/{id}/siem`.

### 5.4 시나리오 생성·검증
- **생성**(`POST /admin/scenarios/generate`): 자연어 요청 + (과목/주차)로 claude 가 Red/Blue 미션
  시나리오를 생성(백그라운드 job). `GET /admin/scenarios/jobs[/{id}]` 로 진행 확인.
- **dry-run**(`POST /admin/scenarios/{id}/dry-run`): infra 1대에 **실제 `/assess`** 로 check-spec
  reachability·정합성 확인 → pass_rate ≥ 0.7 이면 `validated` 승격. (claude 정합성 리뷰 병행.)
- **활성화/보관/수정/삭제**: `POST /admin/scenarios/{id}/activate`, `PATCH/DELETE /admin/scenarios/{id}`,
  `GET /admin/scenarios/drafts`.
- 시나리오 미션의 `verify` 는 `check_compiler` 가 Assessor check-spec 으로 컴파일해
  `mission.verify.checks` 에 캐시합니다(런타임 채점은 AI 0).

### 5.5 공방전 관리 (`GET /admin/battles`)
상태/코호트 필터, 모니터 실행 여부 표시.
- **즉시 점검** `POST /admin/battles/{id}/monitor-tick` — auto-monitor 1 tick 강제 실행(폴링 대기 없이
  Assessor 채점). 결정론이라 안전.
- **강제 종료** `POST /admin/battles/{id}/force-end`, **삭제** `DELETE /admin/battles/{id}`
  (auto-monitor/lab-monitor 정지 + 감사 로그).

### 5.6 사용자 관리 (`GET /admin/users`, `PATCH /admin/users/{id}`)
- 역할 변경(student↔admin), 활성/비활성. **본인 강등·비활성화는 차단**.
- **교수에게 권한 부여**: 교수 계정을 여기서 `admin` 으로 승격하면 코호트/모니터링/피드백/출제가
  가능해집니다(교수 매뉴얼 권한 안내).

### 5.7 Bastion 스크랩 (`/admin/scrap…`)
외부 위협 스크랩 → 승인 시 시나리오 생성 job 으로 연결. (선택 기능.)

### 5.8 감사 로그 (`GET /admin/audit`)
관리자 행동·보안 이벤트(생성/수정/삭제/권한변경/코호트/피드백 등) 추적. `action_prefix`,
`actor_user_id`, `target_type` 필터.

---

## 6. SIEM — el34 자체 Wazuh

tw2 는 **el34 인프라에 내장된 Wazuh SIEM** 을 사용합니다(별도 중앙 SIEM 배포 불필요).

- **`el34-siem` = Wazuh manager + indexer.** Suricata(IPS)·ModSec(WAF) 로그가 Wazuh 에이전트
  (`el34-web`·`el34-ips`)로 수집되어 Wazuh 에서 상관·경보됩니다.
- 채점/모니터링은 이 Wazuh 의 경보를 Assessor `/assess`(`wazuh_alert`·`log_contains`)·`/activity` 로
  read-only 조회해 활용합니다.
- (구) tubewar 의 **중앙 OpenSearch 적재 방식(`lab_monitor` → OpenSearch)은 tw2 에서 비활성**입니다
  (`TUBEWAR_LAB_MONITOR=0`). 즉 중앙 OpenSearch/Dashboards 를 띄울 필요가 없습니다.
- 강사는 **공방전 관리·실습 모니터링·코호트 SIEM 버튼**(관리 콘솔)에서 활동·진도를 봅니다.

> 자세한 SIEM 운영/데이터 흐름은 `docs/central_siem.md` 참조.

---

## 7. (옵션) 미션별 동적 룰 무장

기본 채점 경로는 **check-spec 온디맨드**(룰 미주입)입니다. 옵션으로:
- 시나리오 미션에 `arm_rule` 템플릿을 선언하면, `SKIP_PROVISIONER=0` 일 때 배틀 시작에
  el34 `/provision-rule` 로 검증 룰을 **무장**하고 종료 시 **회수**합니다.
- 학생 작성 룰 미션은 무장 없이 `check_compiler` 의 `file_contains`+`wazuh_alert` 로 채점합니다.
- 기본값은 OFF(no-op)이므로 명시적으로 켜지 않는 한 el34 에 쓰기 호출을 하지 않습니다.

---

## 8. 운영/장애 대응

| 증상 | 점검 |
|------|------|
| 학생 점수 미부여 | 학생 smoke(`healthy`)·el34 도달성·Assessor reachability(`192.168.0.151:9201/assess`)·시나리오 `validated`·미션 성공조건 |
| 채점이 review 에 멈춤 | `claude` CLI 설치/가용 확인(미설치 시 의미채점 보류). `TUBEWAR_GRADE_TIMEOUT=200` |
| 채점이 느림/안 옴 | `POST /admin/battles/{id}/monitor-tick` 로 즉시 점검. auto-monitor 폴링은 15s |
| 진도/병목 안 보임 | 실습 모니터링 탭에서 lab-tick 실행. (백그라운드 자동 기동은 `TUBEWAR_LAB_MONITOR=1`) |
| 피드백 품질/실패 | claude 가용성 확인. 미가용 시 결정론 요약으로 대체(날조·정답 없음) |
| 일부 미션 자동채점 불가 | el34 미보유 텔레메트리(SSH auth·windows/sysmon·endpoint). `contents/battle-scenarios/GRADING-LIMITATIONS.md` 참조 |
| 기존 DB 에 cohort 컬럼 없음 | 부팅 시 `ensure_added_columns` 가 `battles.cohort_id` 를 멱등 추가 |

### 동시성 주의
auto-monitor 는 **배틀별 lock** 으로 백그라운드 폴링과 `monitor-tick` 을 직렬화하고, 점수 부여 성공
후에만 dedupe 마킹합니다(누락/중복 채점 방지).

---

## 9. 테스트 & 검증 (배포 전 필수)

```bash
bash scripts/dev.sh test                 # 전체 pytest (신규+기존). 100% green 이어야 함
bash scripts/e2e_identity_only.sh        # 신원-only(solo) 정상
bash scripts/e2e_cohort_cross_infra.sh   # 코호트 + cross-infra + (mock)Assessor 채점 + 모니터링/피드백/SIEM
bash scripts/e2e_full_duel_run.sh        # 1v1 풀 미션 (legacy 흐름)
```

- **Fake Assessor**(`tests/assessor_fake.py`, `scripts/mock_assessor.py`)로 실 el34 없이 전 파이프라인
  검증이 가능합니다.
- 실 el34 연동 검증은 `ASSESSOR_LIVE=1` + 실 `vm_ip`(`192.168.0.151:9201`)로 별도 실행.
- 기능↔테스트 매핑은 루트의 **`TEST_MATRIX.md`** 참조(누락 0 증명).

---

## 10. 보안 운영 수칙

- `bootstrap.sh` 가 `TUBEWAR_JWT_SECRET`(랜덤 hex32)·`ADMIN_PASSWORD` 를 자동 생성합니다. 비번은
  `.admin-credentials.txt` 에서 확인 후 안전히 보관·삭제. `TUBEWAR_FERNET_KEY` 는 운영 시 고정.
- SSH 자격은 DB(SQLite)에 Fernet 암호화 저장(평문 금지). 비밀은 코드/커밋 금지(`.env`/`*.key`/`.data/` gitignore).
- 토큰/키를 채팅·로그·커밋에 남기지 말 것. 노출 시 즉시 폐기·재발급.
- el34/Bastion 변경 금지 — 외부 표면(Assessor/Bastion API)만 호출.
