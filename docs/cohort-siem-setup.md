# 코호트 ↔ 중앙 SIEM 설정 가이드 (새 서버 배포 안전)

학생 활동을 **중앙 SIEM(OpenSearch + Dashboards)** 의 **코호트 뷰**로 보이게 하는 설정.
새 서버에 배포할 때 이 순서대로 하면 "코호트 설정 안 됨 → 로그 안 보임" 문제가 없다.

## 왜 안 보였나 (핵심 함정 3가지)

1. **`TUBEWAR_LAB_MONITOR=0`** → 배틀 중 lab_monitor 가 안 떠서 `/activity` 를 **pull·export 안 함**.
   → bootstrap 이 이제 `.env` 에 **`=1`** 로 쓴다.
2. **배틀 `cohort_id=NULL`** → 활동이 코호트가 아니라 `tubewar-activity-identity`(캐치올)로 감.
   → `play_scenario`/`run_all_battles` 가 **`TW_COHORT_ID`** 로 코호트 아래 배틀 생성(적용됨).
3. **`OPENSEARCH_DASHBOARDS_URL` 미로딩** → 인덱스엔 데이터가 차도 **dataview(저장객체)가 안 만들어져**
   대시보드에서 코호트가 안 보임. → `backfill_siem.py` 가 이제 `.env` 의 **모든 `OPENSEARCH_*`** 를 로드(수정됨).

## 새 서버 배포 순서

```bash
# 1) 플랫폼 부트스트랩(.env 에 LAB_MONITOR=1 + OPENSEARCH_URL/DASHBOARDS_URL 자동 기입)
bash scripts/bootstrap.sh

# 2) 중앙 SIEM 스택 기동(OpenSearch :9210 + Dashboards :5602) + .env 배선
bash scripts/setup_siem.sh

# 3) 데모/수업 코호트 시드(코호트 트리 + 멤버십 + 활동을 DB 에 심음, 멱등)
.venv/bin/python scripts/seed_demo_cohort.py

# 4) 코호트 활동을 중앙 SIEM 으로 적재 + dataview/대시보드 생성(코호트 id 는 seed 로그의 section id)
.venv/bin/python scripts/backfill_siem.py --cohort <SECTION_ID> --reset

# 5) (선택) 실제 배틀을 코호트 아래에서 실행 → 라이브 활동이 코호트 SIEM 으로 자동 적재
TW_COHORT_ID=<SECTION_ID> VH_ATT_IP=<공격자> VH_ATT_USER=ccc VH_ATT_PASS=1 \
  .venv/bin/python scripts/run_all_battles.py     # 또는 play_scenario.py <sid> solo
```

> `DASHBOARDS_URL` 은 **저장객체(dataview) 생성용**이라 로컬(`http://127.0.0.1:5602`)로 두는 게 안전하다.
> 공개 브라우저 접근용 터널(trycloudflare 등)은 별개 — UI/iframe 에서 쓴다.

## 검증

```bash
# 인덱스에 데이터?
curl -s 'http://127.0.0.1:9210/_cat/indices/tubewar-activity*?v'
# dataview 저장객체 존재?(코호트 N → dv-N)
curl -s -H 'osd-xsrf: true' http://127.0.0.1:5602/api/saved_objects/index-pattern/dv-<N> | head
```
- `index-pattern/dv-<N>` 가 200 이면 대시보드에서 코호트 뷰가 보인다.
- 라이브 배틀 후 `tubewar-activity-*` 의 `_count` 가 증가하면 lab_monitor 실시간 적재가 도는 것.

## 이벤트 필드 스키마 (동적 생성 + 유사건 그룹핑)

인덱스 매핑은 **dynamic** 이라 배틀/실습 내용마다 새 필드가 자동 생긴다. 단 원본을 `payload` 에만
두면 분석이 어려우므로, `siem_export.classify()` 가 **중요 지점을 top-level 필드로 분리**하고
**유사건을 고정 `group_no` 로 그룹핑**한다(건별 필드 폭증 방지). payload 원본도 보존.

| 필드 | 뜻 |
|---|---|
| `group` / `group_no` | 이벤트 그룹 라벨 + **필드 그룹 번호**(고정). 대역: 10 정찰 · 20 익스플로잇(웹) · 30 접근/인증 · 40 실행 · 50 무결성 · 90 기타 |
| `phase` | 킬체인 단계(recon/exploit/access/persistence/detection) |
| `severity` | info/low/medium/high |
| `evt_src` | 출처 시스템(suricata/modsec/wazuh/apache/command/fim) |
| `evt_signature` / `evt_rule_id` | 룰/시그니처 · 룰 id |
| `evt_cmd` / `evt_rc` | 실행 명령 · 반환코드 |
| `evt_path` | FIM 대상 경로 |

그룹 번호 예(집계 가능): 10 IDS-정찰스캔 · 20 WAF-SQLi · 21 WAF-XSS · 22 WAF-스캐너탐지 ·
29 WAF-기타차단 · 30 인증-세션 · 39 SIEM-경보 · 40 명령실행 · 41 명령실패 · 90 기타.
새 그룹/필드가 필요하면 `classify()` 만 확장하면 된다.

### dynamic 필드가 대시보드에 안 뜰 때 (중요)

인덱스 매핑은 동적이어도 **데이터뷰(index-pattern) saved-object 는 필드 스냅샷을 캐시**한다 →
새 필드가 대시보드 field 목록에 안 뜬다. 해결:
- 라이브 경로: `ensure_cohort_objects` 가 매 reconcile 때 `refresh_index_pattern` 호출(자동).
- 수동/주기: `.venv/bin/python scripts/refresh_siem_fields.py [--cohort N]` (cron/loop 가능).
- 저장객체 API 는 **공개 터널이 400** 을 준다 → `OPENSEARCH_DASHBOARDS_INTERNAL_URL`(로컬 5602)로
  ops, 공개 터널은 브라우저 딥링크 전용. bootstrap 이 둘 다 기입.

## 동작 원리

- 배틀 start → (`TUBEWAR_LAB_MONITOR=1` 이면) `lab_monitor.start(battle_id)` 백그라운드 기동.
- lab_monitor 가 학생 infra 의 Assessor `/activity` 를 N초 간격 pull → `battle.cohort_id` 로
  `cohort_service.ancestor_chain` → `siem_export.export_events(client, events, chain)`.
- `siem_export`: 코호트 stamp + `physical_index_for(chain)` 인덱스 적재 + `ensure_cohort_objects`
  로 dataview/search/dashboard/RBAC 멱등 생성.
- 배틀 없이 기존 DB 활동만 밀어넣을 땐 `backfill_siem.py`(위 4단계).

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| 대시보드에 코호트 뷰 없음 | dataview 미생성(DASHBOARDS_URL 미로딩) | `backfill_siem.py`(수정본) 재실행, `dv-<N>` 200 확인 |
| 인덱스 비어 있음 | LAB_MONITOR=0 또는 배틀 cohort_id NULL | `.env =1`+API 재시작, 배틀 `TW_COHORT_ID` |
| `identity` 인덱스에만 쌓임 | 배틀 cohort_id NULL | `TW_COHORT_ID` 로 배틀 생성 |
| siem_export no-op | OPENSEARCH_URL 미설정 | `setup_siem.sh` + `.env` 확인 |
