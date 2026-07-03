# Initiative — 적응형 중앙 SIEM 필드 생성 (Adaptive SIEM Fields)

상태: **구현 완료·실검증** (2026-07-03)
관련: `docs/cohort-siem-setup.md`(운영), `docs/initiatives/gwanje-demo.md`(관제 시연)
코드: `apps/api/app/services/siem_export.py`(classify/stamp), `_opensearch_http.py`(refresh),
`scripts/refresh_siem_fields.py`, `scripts/backfill_siem.py`

## 목표

실습·배틀 내용에 **따라** 중앙 SIEM(OpenSearch) 필드가 생성되되:
1. **동적 생성** — 새 종류의 활동이 새 필드를 자동으로 만든다.
2. **중요 지점 분리** — 분석 축(출처·시그니처·명령·단계 등)은 `payload` blob 이 아니라 **top-level 필드**로.
3. **유사건 그룹핑** — 건별로 필드를 다 만들 수 없으니 유사건을 묶고 **필드 그룹 번호(`group_no`)** 부여.
4. **대시보드 자동 반영** — 새 필드가 강사 대시보드 field 목록/필터에 바로 뜬다.

## 문제 (기존)

- 활동 문서가 `{...고정필드, payload: <blob>}` 구조 → 분석 축이 blob 안에 묻혀 필터/집계 불가.
- 인덱스 매핑은 dynamic(새 필드 자동)이지만 **데이터뷰(index-pattern) saved-object 는 필드 스냅샷을 캐시**
  → 새 필드가 대시보드에 안 뜸(정체).
- 코호트 미지정·`LAB_MONITOR=0`·`DASHBOARDS_URL`(공개 터널) 저장객체 API 400 등으로 애초에 적재/뷰 생성 실패.

## 설계

### 1) `classify(kind, payload)` — 필드 분리 + 그룹핑
`stamp()` 가 코호트 stamp 시 `classify()` 결과를 top-level 로 병합(payload 원본 보존):
- **분리 필드**: `evt_src`(출처 시스템) · `evt_signature`/`evt_rule_id`(룰/시그니처) · `evt_cmd`/`evt_rc`(명령/결과) · `evt_path`(FIM).
- **그룹**: `group`(라벨) + `group_no`(고정 번호) + `phase`(킬체인) + `severity`.

**group_no 대역**(확장 시 이 규칙 유지):

| 대역 | 의미 | 예 |
|---|---|---|
| 10~19 | 정찰 | 10 IDS-정찰스캔 |
| 20~29 | 익스플로잇(웹) | 20 WAF-SQLi · 21 WAF-XSS · 22 WAF-스캐너탐지 · 29 WAF-기타차단 |
| 30~39 | 접근/인증 | 30 인증-세션 · 39 SIEM-경보 |
| 40~49 | 실행 | 40 명령실행 · 41 명령실패 |
| 50~59 | 무결성 | 50 파일무결성(FIM) |
| 90~ | 기타 | 90 기타경보 |

새 그룹/필드는 `classify()` 한 곳만 확장(스키마 드리프트 없음). LLM free-form 금지 — 결정론 분류.

### 2) 동적 필드 → 대시보드 반영: `refresh_index_pattern`
- `_opensearch_http.refresh_index_pattern(dv_id, index)` 가 `_fields_for_wildcard` 로 **현재 매핑 기준
  최신 필드**를 받아 데이터뷰 `fields` 를 다시 심는다.
- `ensure_cohort_objects` 가 **매 reconcile(라이브 export tick 포함)** 호출 → 새 필드 자동 반영.
- 주기/수동 보정: `scripts/refresh_siem_fields.py [--cohort N]` (cron/loop).

### 3) 저장객체 ops 는 내부 URL
- 공개 터널(trycloudflare)은 saved-object API 에 **400** → `OPENSEARCH_DASHBOARDS_INTERNAL_URL`(로컬 5602)로
  ops. 공개 터널은 브라우저 딥링크 전용(`dashboard_deeplink`). bootstrap 이 둘 다 기입.

### 4) 코호트별 데이터뷰
- dept/course/section 은 같은 물리 인덱스를 공유하되 **각 노드가 자기 데이터뷰(dv-N)+스코프 저장검색**을 가진다.
- `refresh_siem_fields.py`(인자 없음)로 전 코호트 dv 를 멱등 생성/갱신.

## 실검증 (2026-07-03)

- 코호트3 재적재 3427건 → 문서에 `group/group_no/phase/severity/evt_*` top-level 존재.
- `group_no` 집계: 10 정찰(673) · 29 WAF기타(1816) · 30 인증(628) · 20 SQLi(26) · 40 실행(84) …
- 데이터뷰 dv-1/2/3 모두 생성, 각 **46 필드**(신규 분석필드 포함) 반영.

## 확장·후속

- **새 그룹 추가**: `classify()` 에 조건+`group_no` 추가(대역 규칙 준수). 새 필드는 dynamic 매핑이 자동 생성,
  `refresh_index_pattern` 이 뷰에 반영.
- **주기 새로고침 자동화**: `refresh_siem_fields.py` 를 systemd timer/cron 또는 `/loop` 로.
- **RBAC**: `ensure_role`/`ensure_role_mapping` 로 코호트별 강사 스코프(이미 생성) — 강사 계정 매핑 채우기.
- **집계 대시보드**: `group_no`/`phase`/`severity` 로 킬체인·심각도 패널 추가(현재 표 패널만).
- **성능**: 라이브 tick 마다 refresh 는 로컬 OSD 호출 — 대규모 시 throttle(예: N초 1회) 고려.
