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
