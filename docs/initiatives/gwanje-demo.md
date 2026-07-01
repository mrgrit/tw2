# 이니셔티브 — tw2 AI 관제(모니터링·피드백) 시연 영상

> **한 줄 목표**: el34 실습 로그를 **AI 에이전트(Claude Code)가 교수 대신 분석**해, 교수에겐 전체
> 현황 대시보드를, 학생에겐 개인 진도·통합 피드백·추천 직무를 만들어주는 흐름을 **영상으로 시연**한다.

---

## 1. 시연 컨셉 — 3주체

| 주체 | 역할 |
|------|------|
| **학생** | el34로 실습 → 활동이 **중앙 SIEM(Wazuh) → tw2 DB**에 로그로 남음 |
| **교수** | 중앙 SIEM 로그로 학생 실습 상황을 모니터링·분석 |
| **AI 에이전트(Claude Code)** | 교수 대신 로그 분석 → **교수용 전체 대시보드** + **학생용 진도·피드백·추천 직무** 자동 생성 |

- **교수에게**: 전체 현황 대시보드(화려한 시각화), 학생별 통계 → 클릭 시 그 학생이 보는 화면(진도·피드백)까지 드릴다운.
- **학생에게**: 개인 진도, 학습 히스토리·통계, 병목 지점, 건건 평가 → **통합 피드백**, 개인 대시보드, **AI 추천 직무**.
- **촬영 핵심**: CC가 (a) **학생처럼 실습을 진행**해 로그를 만들고, (b) 그 로그를 **분석**해 위 정보들을 산출하는 과정을 보여준다.

---

## 2. 현재 시스템 자산 (이미 있음 — 재사용, 재구축 금지)

시연에 필요한 골격은 **대부분 이미 구현돼 있고, 데이터만 비어 있다.** 신규 개발보다 **시드+시각화+오케스트레이션**이 핵심.

### 데이터 모델 (SQLite, 현재 rows=0 → 시드 필요)
- `activity_events` — SIEM 학생 활동(kind·scenario_step·payload·ts·cohort/user/infra).
- `progress_snapshots` — 진도(completion·steps_done/total·**bottleneck_flags**).
- `student_feedback` — 피드백(**scope**=건건/통합, **trigger**=manual/auto, content_md, basis, model, cost_usd, **delivered_to**).
- `student_submissions` — 채점 기록(verdict·awarded/max_points·**criteria_met/missing**·feedback·grader_model).

### API (이미 구현)
- `/monitoring/siem/{search,stats,scenarios,accomplishment,mission-checks,clears}` — 로그·통계·클리어.
- `/monitoring/siem/ask` — **AI 로그 분석 Q&A**(claude CLI, sonnet). ← 교수 분석의 핵심.
- `/monitoring/battles/{id}/{progress,activity,lab-tick}`.
- `/feedback/{me,'',students/{id},{id}/regenerate}` — 개인 피드백 조회·생성·**재생성(통합)**.
- `/cohorts`, `/battles`, `/scenarios`, `/leaderboard`, `/initiative`.

### UI 페이지 (이미 있음)
- `Dashboard.tsx`(83줄, 학생 홈 — 확장 필요), `Training.tsx`, `MyWork.tsx`, `Battle.tsx`, `Leaderboard.tsx`, `Admin.tsx`(중앙 SIEM 탭 `SiemTab`), `Initiative.tsx`.

### 스크립트·스킬
- `scripts/play_scenario.py` — RED/BLUE 증거 심기 + claude 라이브 채점(학생 실습 시뮬에 활용).
- `.claude/skills/gwanje/` + `scripts/monitor/gwanje.py` — 관제 에이전트(deterministic/local/claude).

> **결론**: SIEM·AI분석·피드백·채점·대시보드 골격은 존재. **비어있는 데이터를 채우고, 시각화를 강화하고, CC 오케스트레이션을 붙이면 시연 가능.**

---

## 3. 갭 & 시스템 수정 항목 (시연 위해 손볼 것)

| # | 항목 | 현재 | 시연 위해 필요 | 규모 |
|---|------|------|----------------|------|
| G1 | **시연 데이터** | 코호트0·배틀0·활동0 | 코호트1 + 학생 6~8명 + 배틀 + 현실적 활동/진도/제출 시드 | 필수·중 |
| G2 | **건건→통합 피드백** | `scope`·`regenerate` 존재 | 건건 피드백 N개 → **통합 피드백** 자동 생성 파이프라인·UI | 소 |
| G3 | **AI 추천 직무** | 없음 | 실습 이력·강점 태그 → 직무 추천(예: 웹 침해대응 분석가/레드팀 오퍼레이터) API+카드 | 중(신규) |
| G4 | **교수 대시보드 시각화** | SiemTab 표 위주 | 코호트 히트맵·진도 분포·병목 랭킹·**학생 카드 그리드**(클릭→드릴다운) | 중 |
| G5 | **학생 개인 대시보드** | Dashboard 83줄(빈약) | 진도·히스토리·통계·**통합 피드백**·**추천 직무**를 한 화면 | 중 |
| G6 | **CC 오케스트레이션** | 개별 스크립트 | ①학생 시뮬(로그 생성) ②분석가(피드백·통계·추천 산출) 2역할 러너 | 중 |

---

## 4. 시연 시나리오 (영상 스토리보드)

- **Scene 0 — 세팅(사전, 영상 밖)**: 코호트 개설 + 학생 6~8명 등록 + 시나리오/배틀 배정.
- **Scene 1 — 학생 실습(CC 시뮬)**: CC가 학생 여러 명을 흉내내 el34에서 실습 진행(`play_scenario`/워크북 실습) → 활동이 SIEM→DB로 유입. *화면: 터미널에서 실습 명령 + 대시보드에 활동 실시간 카운트 증가.*
- **Scene 2 — AI 분석(CC)**: CC가 SIEM 로그를 분석(`/monitoring/siem/ask` + 채점) → `progress_snapshots`·`student_feedback`(건건→통합)·**추천 직무** 산출. *화면: CC 분석 로그 + "학생 3명 병목: SQLi 미션" 같은 인사이트.*
- **Scene 3 — 교수 대시보드**: 전체 코호트 현황(히트맵·진도 분포·병목 랭킹) → **학생 카드 클릭** → 그 학생의 진도·피드백·추천 직무까지 드릴다운. *화면: 화려한 시각화, 클릭 인터랙션.*
- **Scene 4 — 학생 대시보드**: 개인 진도·학습 히스토리·통계·**통합 피드백**·**AI 추천 직무** 한 화면. *화면: 학생 로그인 관점.*
- **Scene 5 — 마무리**: "교수 1명이 못 보던 N명을 AI가 실시간 분석·피드백" 가치 강조.

---

## 5. CC 오케스트레이션 (2역할)

1. **학생 러너** — 학생별로 배정 시나리오를 실제 실습(el34 명령/워크북) → SIEM 로그 생성. *진도 편차를 위해 일부는 완주, 일부는 특정 미션에서 막히게.*
2. **분석 러너** — 코호트 로그를 읽어 학생별 (a)진도 스냅샷 (b)건건 피드백 (c)통합 피드백 (d)추천 직무를 생성·저장. `/monitoring/siem/ask`·`/feedback/*` 활용.

> 실제로는 리허설 때 데이터를 미리 쌓아두고, 촬영 땐 "실시간처럼" 재생하는 편이 안정적.

---

## 6. 촬영·제작 실무

- **분할 화면**: 좌(CC 작업 터미널) / 우(브라우저 대시보드 실시간 갱신).
- **데이터 리허설**: 시드→분석을 미리 1회 돌려 스냅샷 확보 후 촬영.
- **내레이션 스크립트**: 각 Scene 1~2문장(주체 전환 명확히).
- **길이 목표**: 3~5분(개론 30초 → 학생실습 → AI분석 → 교수뷰 → 학생뷰 → 마무리).

---

## 7. 실행 단계 (우선순위)

- **Phase 0 (필수)**: G1 시연 데이터 시드 스크립트(`scripts/seed_demo_cohort.py`) — 코호트·학생·배틀·활동·진도·제출.
- **Phase 1**: G4 교수 대시보드 시각화 강화(SiemTab 확장 또는 신규 `MonitorDashboard`).
- **Phase 2**: G5 학생 대시보드 + G2 통합 피드백 + G3 추천 직무.
- **Phase 3**: G6 CC 오케스트레이션 러너(학생 시뮬 + 분석).
- **Phase 4**: 리허설 → 촬영 → 편집.

---

## 8. 결정 필요 (오픈 이슈)

1. **실습 실제 실행 vs 시드 목업**: 촬영 안정성 위해 어디까지 실제 el34 실행? (권장: Scene 1만 실제, 나머지 시드 재생)
2. **추천 직무 분류 체계**: 직무 카탈로그(예: SOC 분석가/침해대응/레드팀/취약점 진단/AI보안) + 강점 태그 매핑 규칙.
3. **통합 피드백 트리거**: 건건 N개 누적 시 자동? 교수 버튼 클릭 시?
4. **교수 대시보드 위치**: 기존 Admin→중앙 SIEM 탭 확장 vs 별도 "관제 대시보드" 메뉴.
5. **AI 분석 비용**: claude CLI 과금 — 시연은 사전 생성(캐시)로, 라이브 1건만 실연.

---

---

## 9. Phase 0 완료 노트 (v2)

**`scripts/seed_demo_cohort.py`** 로 시연 데이터 시드 완료(멱등 재실행 가능, `--purge` 로 제거).

- 코호트: `정보보안학과 > AI 서비스 모의해킹 > 2026-1 관제시연 A반`(section) — course_ref 마커 `demo:gwanje`.
- 계정(비번 `demo1234`, 도메인 `@demo.ac.kr`): 교수 `prof`, 학생 `s1~s7`.
  - fast(김민수·이서연 100%) / mid(박지훈·최유진·정하늘 50~75%) / **stuck(강도현·윤예은 병목 플래그)**.
- 배틀 1개(active), 활동 116·진도 스냅샷 7·제출 13·피드백 7.

### ⚠ 대시보드 데이터 소스 (Phase 1 설계 필수 사항)
시드 중 확인한 계산 경로 — **교수 대시보드는 아래 로컬 엔드포인트로 구성해야 데이터가 나온다.**

| 신호 | 계산 소스 | 시드가 채운 것 |
|------|-----------|----------------|
| **진도**(steps_done/completion) | `battle_events`(points>0 + `detail.report.mission_side/order`) | BattleEvent 로 완료 미션 심음 |
| **병목**(bottleneck_flags) | `activity_events`(실패 명령≥3·alert/log≥5·무진전 300s) | stuck 학생만 실패명령/경보 누적 |
| 학생별 클리어 | `/monitoring/siem/clears`(로컬 DB) | 제출/이벤트로 산출 |
| 피드백 | `/feedback`(로컬 DB) | 건건+병목 피드백 |
| 활동 타임라인 | `/monitoring/battles/{id}/activity` | ActivityEvent |

- **주의**: `/monitoring/siem/{search,stats,ask}` 는 **중앙 OpenSearch** 경로라 `TUBEWAR_LAB_MONITOR=0`(기본)에서 `enabled:false`. 데모 대시보드는 **OpenSearch가 아니라 로컬 엔드포인트**(progress/clears/activity/feedback) 위에 만든다.
- 검증 완료: `GET /monitoring/battles/1/progress` 가 학생별 완성도(100/75/50/25%)+병목 플래그를 정확히 반환.

---

## 10. Phase 1 완료 노트 (v3) — 교수 관제 대시보드

**신규 메뉴 `관제 대시보드`(`/monitor`, admin 게이팅)** 추가 — `apps/ui/src/pages/Monitor.tsx`.

- **접근**: `prof@demo.ac.kr`(admin) 로그인 → 상단 `관제 대시보드` 메뉴. (정식 instructor-RBAC 는 후속 — 지금은 교수를 admin 역할로.)
- **화면 구성**(로컬 엔드포인트 기반, 차트 라이브러리 없이 순수 CSS):
  - 배틀 선택 드롭다운(`/battles`).
  - **KPI 4카드**: 학생 수 · 평균 완성도 · 완주 수 · 병목 학생 수.
  - **완성도 분포**(버킷 막대) + **🚧 병목 랭킹**(클릭 시 드릴다운).
  - **학생 카드 그리드**: 완성도 **링(conic-gradient)** + 미션 x/y + 병목/완주/진행중 배지. 카드 클릭 → 드릴다운.
  - **드릴다운**: 병목 플래그 칩 + **피드백**(Markdown 렌더) + **활동 타임라인**(CMD/ALERT/LOG 배지, 실패 명령 빨강).
- **데이터 소스**: `/battles`, `/monitoring/battles/{id}/progress`, `/monitoring/battles/{id}/activity?user_id=`, `/feedback?user_id=`.
- **검증**: `tsc -b` 통과, 4개 엔드포인트 교수 토큰 E2E 확인(학생 7·병목 2·실패명령 5·피드백), UI 빌드·재기동 후 새 번들 서빙.

### 다음(Phase 2 후보)
학생 개인 대시보드(진도·히스토리·**통합 피드백**·**AI 추천 직무**) + G2 통합 피드백 파이프라인 + G3 추천 직무 API/카드.

---

## 11. Phase 2 완료 노트 (v4) — 학생 대시보드 · 통합 피드백 · AI 추천 직무

- **G3 AI 추천 직무**: `app/services/reco.py` — 채점 통과 제출의 mission_side/event_type + 시나리오 category → 강점 태그 → 직무 카탈로그(웹모의해킹·레드팀·SOC·DFIR·취약점진단·AI보안) 매칭·랭킹(근거 포함). `GET /me/recommendations`.
  - 검증: s1(공격)→**웹 모의해킹 99% · 레드팀 89%**, s2(방어)→**SOC 99% · DFIR 95%**. 성향을 정확히 반영.
- **G2 통합 피드백**: `feedback.integrate_feedback` — 건건(lab) 피드백 + 제출 통계 + 진도 + 추천 직무 → `scope=periodic` 통합 피드백. `POST /feedback/students/{id}/integrate`(교수, use_ai 옵션). 시드가 use_ai=False(결정론)로 학생마다 1건 생성.
- **G5 학생 개인 대시보드**: `Dashboard.tsx` 재작성 — 완성도 링 + 통계(완료/통과율/점수) · **AI 추천 직무 카드**(적합도 막대·근거 칩) · **통합 피드백**(Markdown) · 세부 피드백(접이식) · **학습 히스토리**(미션·판정·점수). 데이터 없으면 온보딩.
  - 데이터 소스: `/feedback/me`(통합의 basis.stats 로 진도) · `/me/recommendations` · `/me/submissions`.
- 검증: `tsc -b` 통과, 백엔드 E2E(추천·통합·제출), UI 빌드·재기동, **터널 URL 유지**(Requires 제거 효과) 확인.
- 교수 관제 대시보드 드릴다운의 피드백에 통합 피드백(추천 직무 포함)이 함께 노출 → 교수도 학생 추천 직무 확인 가능.

### 남은 후속(선택)
정식 instructor-RBAC(교수를 admin 대신 강사 역할로) · 통합 피드백/추천의 라이브 AI 생성(use_ai=True) 시연 · CC 오케스트레이션(G6, 학생 시뮬 러너).

---

## 12. G6 완료 노트 (v5) — CC 오케스트레이션 러너

**`scripts/orchestrate_demo.py`** — 영상의 "CC가 학생처럼 실습 → CC가 분석" 흐름을 스크립트화(시드 상수·헬퍼 재사용, 시드 무손상). 증분(live 느낌) + 실제 분석 파이프라인.

| 명령 | 역할 | 동작 |
|------|------|------|
| `setup` | 준비 | 코호트+교수+학생+배틀 생성(**활동 0, 빈 상태**) |
| `student` | 학생 러너 | **1 틱 증분** — 일부는 다음 미션 통과(battle_event+제출+활동), 병목 학생은 WAF 실패 누적. 여러 번 누르면 대시보드가 점점 채워짐 |
| `analyze [--ai]` | 분석가 | **실제 파이프라인** — `lab_monitor.snapshot_progress`(진도 재계산)·병목 피드백·`integrate_feedback`(통합)·`reco`(추천) 산출, 내레이션 |
| `run [--ticks N] [--ai]` | 전체 | setup → student×N → analyze 한 번에 |

- **검증**(`run --ticks 3`): setup(빈) → tick1 전원 미션1 통과 → tick2 fast/mid 미션2·병목 2명 WAF 실패 → tick3 일부 미션3 → analyze(평균 61%·완주 1·병목 2, 학생별 통합 피드백+추천 직무). API 반영 확인(활성 배틀 progress·s1 통합 피드백). `--ai` 로 통합 피드백을 claude 라이브 작성(라이브 분석 장면용).

### 두 가지 데이터 준비 경로
- `seed_demo_cohort.py` — **원샷 풀 시드**(정적 최종 상태, 리허설/빠른 세팅).
- `orchestrate_demo.py` — **CC 오케스트레이션**(setup → student 틱 라이브 → analyze, 촬영용).

### 촬영 러너(권장)
1. `orchestrate_demo.py setup` — 교수 관제 대시보드 열어두면 "학생 0/빈 상태".
2. `orchestrate_demo.py student` 를 3~5회 — 대시보드 새로고침마다 완성도·병목이 **실시간처럼** 채워짐(Scene 1: 학생 실습).
3. `orchestrate_demo.py analyze --ai` — CC가 분석·피드백·추천 생성(Scene 2). 콘솔 내레이션을 화면에.
4. 교수 관제 대시보드 드릴다운(Scene 3) → 학생 로그인 개인 대시보드(Scene 4).

---

## 13. 실제 공방전 플로우 검증 + 버그 수정 (v6) — 촬영 전 점검

실제 학생 계정으로 solo 공방전(시나리오 63 RED-1)을 API로 완주 재현하며 제출→채점→피드백→대시보드를 점검.

### 🔧 발견·수정한 치명 버그 — AI 채점/피드백 전면 실패
- **증상**: 학생 제출 시 채점이 `verdict=review, 0점, "AI 채점기 호출 실패(타임아웃/오류)"`. 모든 제출이 그러함.
- **원인**: **systemd `tw2-api` 프로세스 PATH 에 `~/.local/bin` 없음** → `shutil.which("claude")=None`, fallback `/usr/local/bin/claude` 부재 → claude CLI 실행 실패. (셸에선 PATH 에 claude 있어 정상이라 안 드러났음.)
- **수정**: (1) 즉시 — `.env` 에 `PATH=/home/ccc/.local/bin:...` 추가(EnvironmentFile 로 로드). (2) 영구 — `bootstrap.sh` tw2-api 유닛에 `Environment=PATH=$RUN_HOME/.local/bin:...` 추가(재배포 대비).
- **검증 후**: 채점이 실제 claude 로 동작 — `grader=cc:claude-sonnet-4-6`, 상세 한국어 근거. fail 제출 시 제출 피드백(lab/submission)도 정상 생성.

### ⚠ 촬영 필수 인지 — 공격 미션은 **인프라 흔적으로 채점**
- 시나리오 63 **RED-1(Host Discovery)** 등 공격 미션은 **대상 Suricata/Wazuh 흔적을 직접 점검**해 채점(외부 공격자 명령은 미수집·불신). **무인프라 학생은 `can_inspect:false` → 아무리 구체적 자가 보고도 공정성상 0점**("검증 불가"). 버그 아님(정상·엄격).
- 온카메라에서 **점수/통과**를 보이려면: **① 실제 el34 인프라(타깃+공격자) 등록 + el34 기동 + 실제 공격 수행**(그러면 흔적 남아 채점 인정) — 가장 현실적. ② 아니면 대시보드 데이터는 seed/orchestrator 로 채우고, 실제 제출은 **AI 피드백 파이프라인 시연**(fail 이어도 피드백은 생성됨)으로.
- 참고: 관제/피드백 데모 자체는 학생 통과가 필수 아님(fail 제출도 피드백 트리거).

### ⏱ 채점 지연
- 채점기 `TUBEWAR_ANALYZER_MODEL=claude-sonnet-4-6` → 1건 ~40s. 빠른 시연 원하면 `TUBEWAR_ANALYZER_MODEL`/`TUBEWAR_GRADER_MODEL=claude-haiku-4-5`(~10s, 덜 상세). `.env` 수정 후 tw2-api 재기동.

### 데모 상태
- 재시드로 클린 복구(배틀 #11 ffa, 완주 2·병목 2). 테스트용 solo 배틀 전부 제거.

_작성: Claude Code. 상태: Phase 0·1·2 + G6 + 실제 플로우 검증/버그수정(v6). PATH 버그 수정으로 AI 채점·피드백 정상화._
