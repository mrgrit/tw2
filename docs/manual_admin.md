# tubewar 관리자(admin) 매뉴얼

> 대상: 플랫폼을 운영하는 **관리자(admin)**.
> 설치·환경변수·부트스트랩·관리 콘솔 전 기능·6v6/Assessor 연동·중앙 SIEM·운영/장애 대응을
> 다룹니다. (수업 운영 관점은 교수 매뉴얼, 학생 사용은 학생 매뉴얼 참조.)

- 중앙 서버(tubewar): `http://192.168.0.107:9200` (API) / UI `:5173` / Postgres `:5435`
- 6v6 학생 시스템 예시: `192.168.0.80`, `192.168.0.76`

---

## 1. 아키텍처 한눈에

```
학생 6v6(로컬 Wazuh) ──/assess(pass·fail)──┐
                      ──/activity(lists)──┤
                                          ▼
                                  tubewar (CC, 중앙 두뇌)
   ├─ Postgres : User/Infra/Cohort/Battle/진도/점수/StudentFeedback (플랫폼 로직)
   ├─ 중앙 SIEM(OpenSearch+Dashboards) : 코호트 인덱스/뷰 (강사 육안)
   ├─ check_compiler(생성시) → mission.checks  ── grader 가 채점에 사용
   ├─ lab_monitor → 진도·병목 → 막힌 학생만 CC → feedback
   └─ (옵션) provisioner → 6v6 /provision-rule (기본 OFF)
```

- 데이터 흐름은 **PULL**: tubewar 가 학생 infra 의 Assessor 를 read-only 로 당겨옵니다.
- 6v6/Bastion 은 **불변**. tubewar 는 6v6 의 외부 표면만 호출합니다.
- 채점은 **결정론 우선**(check-spec → Assessor `passed`, LLM 0). 모호한 것만 CC(claude/haiku).

### 컴포넌트
| 컴포넌트 | 경로 | 포트 | 스택 |
|----------|------|------|------|
| api | apps/api/ | 9200 | FastAPI async, SQLAlchemy 2.x async |
| ui | apps/ui/ | 5173 | React 18 + TS strict + Vite |
| postgres | docker compose | 5435→5432 | postgres:15 |
| 중앙 SIEM(옵션) | 별도/동거 | 9200(OS)/5601(Dash) | OpenSearch + Dashboards |

---

## 2. 설치 & 기동

```bash
bash scripts/setup.sh        # postgres 컨테이너 + python venv + npm install + .env 생성
bash scripts/dev.sh api      # FastAPI (autoreload)  http://0.0.0.0:9200
bash scripts/dev.sh ui       # Vite dev server        :5173
bash scripts/dev.sh build-ui # 프로덕션 UI 빌드 (tsc + vite)
bash scripts/dev.sh db       # psql 진입
bash scripts/dev.sh test     # pytest (전체)
```

> 이 저장소가 배포된 호스트에 `python3-venv`/`pip`/`node` 가 없을 수 있습니다. 그 경우
> get-pip 부트스트랩 + 로컬 Node 설치로 환경을 갖춘 뒤 위 명령을 사용하세요.

부팅 시 lifespan 이 자동으로:
1. 테이블 생성(`create_all`) + **기존 DB 호환 컬럼 보강**(`schema_upgrade.ensure_added_columns` —
   예: `battles.cohort_id`),
2. `ADMIN_EMAIL` 관리자 부트스트랩(`ADMIN_PASSWORD` 로 1회 생성),
3. `contents/battle-scenarios/*.yaml` 시나리오 import.

---

## 3. 환경변수 (`.env` / `os.environ`)

> 비밀(.env/SSH/Fernet)은 **절대 커밋 금지**. `.gitignore` 가 `.env`/`*.key`/`.data/` 등을 제외합니다.

### 핵심
| 변수 | 기본 | 설명 |
|------|------|------|
| `TUBEWAR_API_HOST` / `TUBEWAR_API_PORT` | 0.0.0.0 / 9200 | API 바인드 |
| `TUBEWAR_JWT_SECRET` | (dev) | **운영 시 32자+ 로 교체 필수** |
| `TUBEWAR_JWT_EXPIRES_HOURS` | 12 | 토큰 만료 |
| `DATABASE_URL` | postgres asyncpg | DB. (테스트는 sqlite) |
| `TUBEWAR_FERNET_KEY` | 없으면 `.data/fernet.key` 자동생성 | SSH 자격 암호화 키. **운영 시 고정** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` | admin@tubewar.app / … | 부트스트랩 관리자 |
| `TUBEWAR_RATE_LIMIT_DISABLE` | (off) | `1` 이면 rate limiter no-op (테스트용) |

### 채점/AI (claude CLI 기반, 결정론 우선이라 호출 최소)
| 변수 | 기본 | 용도 |
|------|------|------|
| `TUBEWAR_CLAUDE_BIN` / `TUBEWAR_CLAUDE_MODEL` / `TUBEWAR_CLAUDE_TIMEOUT_SEC` | claude / claude-haiku-4-5 / 60 | 시나리오 생성·dry-run·check 정제 |
| `TUBEWAR_GRADER_MODEL` / `TUBEWAR_GRADER_TIMEOUT` | claude-haiku-4-5 / 30 | (legacy probe grader) |
| `TUBEWAR_ANALYZER_MODEL` / `TUBEWAR_ANALYZER_TIMEOUT` | claude-haiku-4-5 / 40 | 이벤트 분석 |
| `TUBEWAR_FEEDBACK_MODEL` / `TUBEWAR_FEEDBACK_TIMEOUT` | claude-haiku-4-5 / 40 | 학생 피드백 작성 |
| `TUBEWAR_HINT_MODEL` / `TUBEWAR_HINT_TIMEOUT` / `TUBEWAR_HINT_COOLDOWN` | … / 60 | 힌트 |

### 연동 토글
| 변수 | 기본 | 설명 |
|------|------|------|
| `TUBEWAR_LAB_MONITOR` | `0`(OFF) | `1` 이면 배틀 시작 시 백그라운드 실습 모니터 자동 기동 |
| `SKIP_PROVISIONER` | skip(OFF) | `0`/`false` 일 때만 룰 무장(`/provision-rule`) 활성 |
| `OPENSEARCH_URL` | (없음=비활성) | 중앙 SIEM. 설정 시 적재·데이터뷰/RBAC 자동 생성 |
| `OPENSEARCH_DASHBOARDS_URL` / `OPENSEARCH_USER` / `OPENSEARCH_PASSWORD` | — | 대시보드 딥링크·saved-object/security API |
| `ASSESSOR_LIVE` | (off) | `1` + 실 vm_ip 일 때만 라이브 통합 테스트 실행 |

---

## 4. 6v6 Assessor 연동 계약

tubewar 가 호출하는 6v6 외부 표면(읽기 전용, 부작용 0):

- **채점** `POST http://{vm_ip}/assess` — header `Host: assessor.6v6.lab` + `X-API-Key`.
  `port_map['assessor']` 가 있으면 직접 포트 우선. body `{battle_id?, checks:[{id,type,target,params}]}`,
  type ∈ `file_exists|file_contains|file_hash|process_running|port_listening|log_contains|wazuh_alert|fim_change|command_ran`.
  resp `{collected_at, results:[{id,passed,evidence,raw?}]}`.
- **모니터링** `POST http://{vm_ip}/activity` — body `{since_sec, limit, want:[commands,fim,alerts,services], filter?}`
  → `{collected_at, commands[], fim[], alerts[], services{}}`.
- **(옵션) 룰 무장** `POST http://{vm_ip}/provision-rule` — 검증 룰 템플릿 적용/회수(기본 OFF).

`X-API-Key` 값은 인프라 등록 시의 `bastion_api_key` 를 사용합니다. NAT 뒤 환경(인바운드 불가)도
`assessor_client` 추상화가 push 모드를 막지 않도록 설계되어 있습니다.

---

## 5. 관리 콘솔 (관리자 메뉴 탭)

로그인 후 상단 **관리자** → 탭: `통계 · 코호트 · 실습 모니터링 · 피드백 · 시나리오 생성 ·
Bastion 스크랩 · 공방전 관리 · 사용자 관리 · 시나리오 관리`.

### 5.1 통계 (`GET /admin/stats`)
사용자/시나리오/공방전/이벤트 집계 + Top scorer. **코호트 필터**로 서브트리 범위 스코프.

### 5.2 코호트 — 교수 매뉴얼 §1 과 동일(트리 CRUD·배치·이동). 노드별 **SIEM** 버튼으로 중앙 SIEM
데이터뷰/대시보드/RBAC 멱등 생성 + 딥링크.

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

## 6. 중앙 SIEM 구축 (선택)

학생 로컬 Wazuh 는 VM 마다 격리되므로, 강사가 한곳에서 보려면 **중앙 활동 스토어**가 필요합니다.

1. 중앙에 **OpenSearch + OpenSearch Dashboards** 배치(자원되면 tubewar 와 동거, 아니면 분리).
2. tubewar env 설정: `OPENSEARCH_URL`, `OPENSEARCH_DASHBOARDS_URL`, `OPENSEARCH_USER`,
   `OPENSEARCH_PASSWORD`.
3. 코호트 등록/활성화 시(또는 코호트 탭의 SIEM 버튼) tubewar 가 **멱등**으로:
   - 데이터뷰(saved-object), 대시보드, RBAC 롤/롤매핑을 생성·reconcile(파라미터 템플릿만, LLM
     free-form 금지 — 인덱스/롤 드리프트 방지).
4. **인덱스 전략**: 물리 인덱스는 **큰 단위(교과목/학기)**만 만들고, 하위(분반/팀)는 **필드 태깅 +
   데이터뷰**로 분리(인덱스 남발 금지). 문서 필드: `student/infra/ts/kind/cohort_path/scenario_step`.
5. **RBAC**: 강사는 자기 코호트 인덱스/뷰만 열람.

미설정(`OPENSEARCH_URL` 없음) 시 SIEM 적재/생성은 **no-op** 이며 플랫폼 로직에 영향 없습니다.

---

## 7. (옵션) 미션별 동적 룰 무장

기본 채점 경로는 **check-spec 온디맨드**(룰 미주입)입니다. 옵션으로:
- 시나리오 미션에 `arm_rule` 템플릿을 선언하면, `SKIP_PROVISIONER=0` 일 때 배틀 시작에
  6v6 `/provision-rule` 로 검증 룰을 **무장**하고 종료 시 **회수**합니다.
- 학생 작성 룰 미션은 무장 없이 `check_compiler` 의 `file_contains`+`wazuh_alert` 로 채점합니다.
- 기본값은 OFF(no-op)이므로 명시적으로 켜지 않는 한 6v6 에 쓰기 호출을 하지 않습니다.

---

## 8. 운영/장애 대응

| 증상 | 점검 |
|------|------|
| 학생 점수 미부여 | 학생 smoke(`healthy`)·6v6 도달성·Assessor reachability(`/assess`)·시나리오 `validated`·미션 성공조건 |
| 채점이 느림/안 옴 | `POST /admin/battles/{id}/monitor-tick` 로 즉시 점검. auto-monitor 폴링은 15s |
| 진도/병목 안 보임 | 실습 모니터링 탭에서 lab-tick 실행. (백그라운드 자동 기동은 `TUBEWAR_LAB_MONITOR=1`) |
| 피드백 품질/실패 | claude 가용성 확인. 미가용 시 결정론 요약으로 대체(날조·정답 없음) |
| SIEM 딥링크 비활성 | `OPENSEARCH_URL` 등 env 확인. 없으면 의도된 no-op |
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

- **Fake Assessor**(`tests/assessor_fake.py`, `scripts/mock_assessor.py`)로 실 6v6 없이 전 파이프라인
  검증이 가능합니다.
- 실 6v6 연동 검증은 `ASSESSOR_LIVE=1` + 실 `vm_ip` 로 별도 실행.
- 기능↔테스트 매핑은 루트의 **`TEST_MATRIX.md`** 참조(누락 0 증명).

---

## 10. 보안 운영 수칙

- 운영 전 `TUBEWAR_JWT_SECRET`(32자+), `ADMIN_PASSWORD`, `TUBEWAR_FERNET_KEY` 를 고정·교체.
- SSH 자격은 DB 에 Fernet 암호화 저장(평문 금지). 비밀은 코드/커밋 금지.
- 토큰/키를 채팅·로그·커밋에 남기지 말 것. 노출 시 즉시 폐기·재발급.
- 6v6/Bastion 변경 금지 — 외부 표면(Assessor/Bastion API)만 호출.
