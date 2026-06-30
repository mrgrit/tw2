# 중앙 SIEM — 운영·아키텍처 가이드

학생 활동(명령/알림/파일변경/서비스)을 코호트 위계로 모아 **육안 탐색 + 통계 + AI 분석**하는
가이드. SIEM 의 권위 소스는 **el34 인프라 자체의 Wazuh**(`el34-siem`)이며, 채점(권위)은
tw2 의 SQLite(Battle/점수)다 — 두 트랙이 분리되어 있다.

> **tw2 변경점:** 구 tubewar 는 학생 활동을 **중앙 OpenSearch lake** 로 적재해 탐색했다. tw2 는
> **el34 인프라에 내장된 Wazuh manager+indexer 를 SIEM 으로 사용**하고, 중앙 OpenSearch 적재는
> **비활성**(`TUBEWAR_LAB_MONITOR=0`)이다. 따라서 별도 OpenSearch/Dashboards 배포가 필요 없다.

## 구성 2층

| 레이어 | 정체 | 비고 |
|--------|------|------|
| 저장·검색 엔진 | **el34-siem = Wazuh manager + indexer** | Suricata(IPS)·ModSec(WAF) 로그를 Wazuh 에이전트(`el34-web`·`el34-ips`)가 수집·상관·경보 |
| 조회 경로 | el34 **Assessor `:9201`** (`/assess`·`/activity`) | tw2 가 read-only 로 Wazuh 경보·활동을 당겨옴 |
| 화면(기본) | tw2 네이티브 `중앙 SIEM` 탭 (`SiemTab`) + `/monitoring/siem/*` API | 코호트 RBAC·KST·세션격리를 tw2 가 통제 |

> 네이티브 패널(통계·로그·드릴다운·AI 분석)은 tw2 가 직접 제공한다. 중앙 OpenSearch/Dashboards
> 배포는 tw2 에서 더 이상 사용하지 않는다.

## 데이터 흐름

```
el34 Wazuh(IPS/WAF 상관·경보) ── Assessor /activity·/assess ──▶ tw2
                                          │
                                          └─(lab_monitor.pull_activity_once)─▶ ActivityEvent(SQLite)
  stamp 필드: student / infra / ts(date) / kind / cohort_path / cohort_id / scenario_id / payload / battle_id
  (TUBEWAR_LAB_MONITOR=0 이면 중앙 OpenSearch 로의 _export_to_siem 적재는 OFF)
```

- 외부 attacker(망 외부, VM `192.168.0.202`) 명령은 el34 가 수집 못함 → 타깃 인프라의 공격 흔적
  (ModSec/Suricata/Wazuh + source IP·payload 상관)으로 대체(채점 정책과 동일).

## 배포

별도 SIEM 배포가 없다. el34 인프라가 기동되면 `el34-siem`(Wazuh manager+indexer)이 함께 올라오고,
tw2 는 `bootstrap.sh` 만으로 동작한다(§ `docs/manual_admin.md` 2장).

- Wazuh 경보 확인은 **인프라 측**(el34-siem)에서 한다.
- tw2 는 Assessor(`192.168.0.80:9201`, header `X-API-Key: ccc-api-key-2026`)로 경보·활동을 조회한다.

### tw2 API 환경변수

| 변수 | 값 | 효과 |
|------|-----|------|
| `TUBEWAR_LAB_MONITOR` | `0`(기본) | 중앙 OpenSearch 적재 OFF. `1` 이면 배틀 시작 시 백그라운드 실습 모니터 기동 |

코호트 강사 진입 시 `GET /monitoring/cohorts/{id}/siem` 는 해당 코호트 서브트리의 활동/통계 조회를
준비한다(네이티브 패널 렌더).

## SIEM 페이지 기능 (`관리자 → 중앙 SIEM`)

- **주요 통계(표 위)**: 총 이벤트 / 종류별(클릭=필터) / 활동 많은 학생(클릭=필터) / 일자 수.
- **기간 선택**: 빠른 범위(1·7·30일·1년·전체) + 시작/종료일 직접 지정.
- **코호트 → 시나리오 → 미션 드릴다운**: 코호트 선택 → 그 서브트리 공방전의 시나리오·미션 목록 →
  시나리오로 통계/로그/클리어를 좁힘.
- **학생별 클리어**: 완수 미션 수·완성도(막대)·막힘 상태 (SQLite 권위 채점 기준).
- **로그 테이블**: 행 클릭 → 전체 로그(payload JSON) 모달.
- **AI 로그 분석 Q&A**: 현재 필터의 로그·통계·클리어를 근거로 질문 → `claude` CLI
  (`claude-sonnet-4-6`)가 분석 답변. `POST /monitoring/siem/ask`. (claude CLI 미설치 시 비활성.)

## 관련 API

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | `/monitoring/siem/search` | 로그 조회(cohort/scenario/student/kind/기간 필터, full payload) |
| GET | `/monitoring/siem/stats` | 집계(총/종류별/학생별/일자별) |
| GET | `/monitoring/siem/scenarios` | 코호트 서브트리 시나리오+미션 |
| GET | `/monitoring/siem/clears` | 학생별 클리어/완성도 |
| POST | `/monitoring/siem/ask` | AI 로그 분석(claude CLI, `claude-sonnet-4-6`) |
| GET | `/monitoring/cohorts/{id}/siem` | 코호트 서브트리 활동/통계 조회 준비 |
