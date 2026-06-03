# 중앙 SIEM — 운영·아키텍처 가이드

학생 활동(명령/알림/파일변경/서비스)을 코호트 위계로 모아 **육안 탐색 + 통계 + AI 분석**하는
중앙 활동 lake. 채점(권위)은 Postgres, 탐색용 lake 는 OpenSearch — 두 트랙이 분리되어 있다.

## 구성 2층

| 레이어 | 정체 | 비고 |
|--------|------|------|
| 저장·검색 엔진 | **OpenSearch 2.18** (`:9201`, security 비활성, 단일 노드) | 물리 인덱스 = "큰 단위"(교과목) 1개, 하위 코호트는 필드 태깅 |
| 화면(기본) | tubewar 네이티브 `중앙 SIEM` 탭 (`SiemTab`) + `/monitoring/siem/*` API | 코호트 RBAC·KST·세션격리를 tubewar 가 통제 |
| 화면(옵션) | **OpenSearch Dashboards 2.18** (`:5601`) iframe/딥링크 | `OPENSEARCH_DASHBOARDS_URL` 설정 시 같은 탭에 함께 표시 |

> 네이티브 패널은 항상 동작(엔진만 있으면). Dashboards 는 더 풍부한 탐색을 위한 보강이며
> 끄거나 켜도 네이티브 패널은 그대로다.

## 데이터 흐름

```
6v6 Assessor /activity ──(lab_monitor.pull_activity_once)──▶ ActivityEvent(Postgres)
                                          │
                                          └─(run_lab_tick → _export_to_siem)─▶ OpenSearch
  stamp 필드: student / infra / ts(date) / kind / cohort_path / cohort_id / scenario_id / payload / battle_id
```

- 물리 인덱스명: `tubewar-activity-<course_ref|name>` (교과목 단위). 하위(분반/팀)은 `cohort_id` 필드로 구분.
- 외부 attacker(망 외부) 명령은 6v6 가 수집 못함 → 타깃 인프라의 공격 흔적으로 대체(채점 정책과 동일).

## 배포 (중앙 서버, tarball)

```bash
# 1) OpenSearch 2.18 (예: /home/ccc/.local/opensearch)
#    config/opensearch.yml: plugins.security.disabled: true, http.port: 9201, single-node
# 2) OpenSearch Dashboards 2.18 (예: /home/ccc/.local/opensearch-dashboards)
./bin/opensearch-dashboards-plugin remove securityDashboards     # 엔진 security 비활성과 정합
cat > config/opensearch_dashboards.yml <<'YML'
server.host: "0.0.0.0"
server.port: 5601
server.name: "tubewar-siem"
opensearch.hosts: ["http://127.0.0.1:9201"]
opensearch.ssl.verificationMode: none
YML
./bin/opensearch-dashboards          # 최초 기동은 번들 최적화로 1~3분
```

### tubewar API 환경변수

| 변수 | 값(예) | 효과 |
|------|--------|------|
| `OPENSEARCH_URL` | `http://127.0.0.1:9201` | SIEM 적재·조회 활성(없으면 no-op, 네이티브/Postgres 만) |
| `OPENSEARCH_DASHBOARDS_URL` | `http://192.168.0.107:5601` | 탭에 Dashboards iframe/딥링크 노출. **브라우저가 닿는 host** 여야 함 |

> iframe 임베드: OSD 2.18 은 기본적으로 `X-Frame-Options`/`frame-ancestors` 를 설정하지 않아 동일망에서 임베드 가능.

코호트 강사 진입 시 `GET /monitoring/cohorts/{id}/siem` 가 데이터뷰(`dv-N`)→저장검색(`se-N`)→
대시보드(`dash-N`)와 RBAC 롤을 멱등 생성한다(실제 OSD saved-object → iframe 즉시 렌더).

## SIEM 페이지 기능 (`관리자 → 중앙 SIEM`)

- **주요 통계(표 위)**: 총 이벤트 / 종류별(클릭=필터) / 활동 많은 학생(클릭=필터) / 일자 수.
- **기간 선택**: 빠른 범위(1·7·30일·1년·전체) + 시작/종료일 직접 지정.
- **코호트 → 시나리오 → 미션 드릴다운**: 코호트 선택 → 그 서브트리 공방전의 시나리오·미션 목록 →
  시나리오로 통계/로그/클리어를 좁힘.
- **학생별 클리어**: 완수 미션 수·완성도(막대)·막힘 상태 (Postgres 권위 채점 기준).
- **로그 테이블**: 행 클릭 → 전체 로그(payload JSON) 모달.
- **AI 로그 분석 Q&A**: 현재 필터의 로그·통계·클리어를 근거로 질문 → **CC 또는 bastion**(채점기 프로필 선택)
  모델이 분석 답변. `POST /monitoring/siem/ask`.

## 관련 API

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | `/monitoring/siem/search` | 로그 조회(cohort/scenario/student/kind/기간 필터, full payload) |
| GET | `/monitoring/siem/stats` | 집계(총/종류별/학생별/일자별) |
| GET | `/monitoring/siem/scenarios` | 코호트 서브트리 시나리오+미션 |
| GET | `/monitoring/siem/clears` | 학생별 클리어/완성도 |
| POST | `/monitoring/siem/ask` | AI 로그 분석(CC/bastion 선택) |
| GET | `/monitoring/cohorts/{id}/siem` | 코호트 데이터뷰/대시보드/RBAC 멱등 생성 + 딥링크 |
