# tubewar 운영 가이드 (서비스·코호트·SIEM)

> 2026-06-14 작성. 전체 기능을 무중단으로 운영하기 위한 절차와 **작업 간 의존성**을 정리한다.

## 1. 서비스 (systemd) — 부팅·크래시 자동 재시작

4개 유닛이 `/etc/systemd/system/` 에 등록되어 있고 `enable` 됨(부팅 시 자동 기동).

| 유닛 | 포트 | 역할 | 의존(After/Wants) |
|------|------|------|-------------------|
| `tubewar-opensearch` | 9201 | 중앙 SIEM 저장소(OpenSearch single-node, security off) | network-online |
| `tubewar-dashboards` | 5601 | SIEM 대시보드(OpenSearch Dashboards) | opensearch |
| `tubewar-api` | 9200 | FastAPI(uvicorn). `.env` 를 EnvironmentFile 로 로드 | opensearch |
| `tubewar-ui` | 5173 | React 빌드물(vite preview) | api |

**기동 순서/의존**: opensearch → dashboards / api → ui. api·ui 는 opensearch 가 죽어도 graceful degrade(SIEM 기능만 비활성).

```bash
# 상태 확인
systemctl is-active tubewar-{opensearch,dashboards,api,ui}
# 재시작 / 로그
sudo systemctl restart tubewar-ui          # UI 만
sudo systemctl restart tubewar-api         # API 만 (.env 변경 후엔 필수)
sudo journalctl -u tubewar-api -n 100 -f   # 로그 추적
```

> ⚠️ 이전엔 vite/uvicorn 을 수동 실행해서 셸 종료 시 죽었음 → 이제 systemd 가 `Restart=always` 로 자동 복구.
> ⚠️ **UI 코드 변경 시**: `cd apps/ui && npm run build`(또는 `node_modules/.bin/vite build`) 후 `sudo systemctl restart tubewar-ui`. preview 는 빌드물(dist)을 서빙하므로 재빌드 필요.
> ⚠️ **API `.env` 변경 시**: `sudo systemctl restart tubewar-api`.

## 2. 코호트 (수업 단위) — 등록·구조

코호트는 트리(course → section …) + 다대다 멤버십. **admin 권한**으로 관리.

- **UI**: 관리자 페이지 → `cohorts` 탭. 노드 생성(kind/name/parent/course_ref) + 멤버 배치/이동/제거. SIEM 딥링크 버튼.
- **course_ref** 는 시나리오 `category` 와 느슨히 연결(예: course_ref `soc-adv` ↔ 시나리오 category `soc-adv`).
- **API**: `POST /cohorts`(admin), `POST /cohorts/{id}/members`(admin), `GET /cohorts`, `GET /cohorts/tree`.

현재 등록된 코호트(18개): 기본 4트랙(secuops-easy/secuops/soc/attack) + **신규 5트랙**(soc-adv id9·attack-adv id11·compliance id13·web-vuln id15·cloud-container id17, 각 course+section). 학생 shin(2)/kim(3)/mrgrit(4) 가 신규 5트랙 section 에 배치됨.

## 3. 중앙 SIEM — 테스트 내용 보기

**활성화 조건**: `.env` 의 `OPENSEARCH_URL=http://127.0.0.1:9201` 설정(되어 있음). 미설정 시 no-op.

**데이터가 SIEM 에 쌓이는 조건(중요)**: 배틀을 **코호트를 지정해서**(create 시 `cohort_id`) 돌려야 코호트 인덱스(`tubewar-activity-<course>`)에 적재된다. `cohort_id` 없이 돌리면 `tubewar-activity-identity`(신원-only)로만 가서 코호트 SIEM 화면이 빈다.
- 적재원: ① `lab_monitor`(TUBEWAR_LAB_MONITOR=1) 가 배틀 중 학생 infra assessor `/activity` pull → alert/fim/command/mission_check 문서, ② `grade_submission` 채점 완료 → grade 문서.
- 코호트 객체(데이터뷰/대시보드/RBAC)는 `GET /monitoring/cohorts/{id}/siem` 가 **멱등 생성**(신규 5트랙은 생성 완료).

**보는 법**:
- 관리자 페이지 → `siem` 탭: 코호트/시나리오/기간/kind/학생 필터 + OSD 대시보드 iframe + 통계 + 미션 달성도 + AI 질문.
- 또는 `cohorts` 탭에서 코호트의 **SIEM** 버튼 → OSD Dashboards 딥링크.
- 검증된 API: `GET /monitoring/siem/search?cohort_id=<id>`, `/monitoring/siem/stats?cohort_id=<id>`.

## 4. 작업 간 의존성 (이번 셋업)

```
systemd 서비스 등록(86)
  └─ 코호트 트리 생성/배치(87)         [API 가동 필요]
       └─ 코호트별 SIEM 객체 생성(88)  [코호트 + OpenSearch 가동]
            └─ 코호트 배틀 e2e → SIEM 적재(89)  [86,87,88]
                 └─ 전체 점검·문서화(90)         [전부]
```
- 신규 시나리오 75개(soc-adv/attack-adv/compliance/web-vuln/cloud-container)는 DB 적재됨(총 145). 검증: `python scripts/validate_scenarios.py <prefix> --markers`.
- 코호트 SIEM 가시화는 **코호트 지정 배틀**에 의존(3절 참고).

## 5. 빠른 점검 체크리스트

```bash
systemctl is-active tubewar-{opensearch,dashboards,api,ui}   # 4x active
curl -s -o/dev/null -w '%{http_code}\n' http://127.0.0.1:9200/health   # 200
curl -s -o/dev/null -w '%{http_code}\n' http://127.0.0.1:5173/         # 200 (UI)
curl -s 'http://127.0.0.1:9201/_cat/indices/tubewar-activity*?h=index,docs.count'  # 적재량
```
검증된 흐름(2026-06-14): 로그인→인프라→코호트 배틀(.79)→제출→채점(graded)→워크북(10건)→SIEM 검색(코호트9: alert/grade/mission_check 19건). 시나리오 145, 코호트 18.
