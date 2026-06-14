# scripts/monitor — tubewar 관제(control-room) 도구

"관제 시작" 한 번에 학생 행동 모니터링을 켜기 위한 단일 도구. 이전엔 매번
DB 종류 확인·토큰 발급·헬스체크·스키마 파악을 손으로 했지만, 이제 전부
`gwanje.py` 에 통합돼 **한 줄**이면 된다. 읽기 전용(DB 는 RO 로 오픈).

## 사용
```bash
.venv/bin/python scripts/monitor/gwanje.py            # 델타 스냅샷(deterministic·무료)
.venv/bin/python scripts/monitor/gwanje.py --agents   # 관제 에이전트 목록/가용성
.venv/bin/python scripts/monitor/gwanje.py --json      # 머신용 JSON 만
.venv/bin/python scripts/monitor/gwanje.py --reset    # 커서 초기화
.venv/bin/python scripts/monitor/gwanje.py --agent local --model gemma3:4b   # 로컬 LLM 요약
```
venv 로 실행해야 admin 토큰 발급(jose)·.env 설정 로드가 된다. 커서는
`/tmp/mon/cursor.json` 에 저장돼 매 실행이 "직전 대비 새 것만" 보여준다.

## 관제 에이전트(요금 API 기본 차단)
| agent | 비용 | 설명 |
|-------|------|------|
| `deterministic` | free | 규칙기반 salience/health. LLM 없음. **기본값** |
| `local` | free | 로컬 ollama 요약(`LLM_BASE_URL`). 다운이면 안내만 |
| `claude` | BILLED | `claude -p`. **기본 차단** — `--allow-billed` 필요 |

`--model` 로 모델 지정(local=ollama 모델명, claude=claude-* 모델ID).
정책: **과금 나오는 API 는 명시 허락 전 호출 금지.**

## 스마트 보고 트리거 (cron 아님)
매 사이클 보고는 토큰 낭비, 매분 보고도 낭비. 그래서 `gwanje.py` 가 델타에서
**salience 점수**를 계산하고 `should_report` 를 내준다:
- 보고: `salience>=5` | 마지막 보고 후 `>=25분`(heartbeat) | 이상징후 즉시.
- 침묵: 그 외(커서만 전진).
- salience 가산 예: 새 배틀개설 +5, 신규 고아배틀 +4, 채점적체>3 +4, grade_fail +5,
  fail/partial +2/건, 로그오류 +2/건, 새 채점이벤트 +1/건, 학생활동 50건당 +1.

## 출력 필드
- `활성배틀` + 각 배틀 `cohort=NULL` 이면 ⚠(코호트 SIEM 미적재).
- `고아배틀(active>6h)`: 종료 안 된 채 폴링만 도는 배틀.
- `로그(N줄)`: journalctl tubewar-api 에서 assess/bulk/timeout/grade_fail/err 집계.
- `SIEM 변화`: tubewar-activity-* 인덱스 문서수 델타.
- `salience` / `should_report`: 스마트 트리거 판단 근거.

## 점검 체크리스트(사이클마다)
1. 새 배틀: cohort_id·monitor 모드·시나리오 맞춤 mission_check 적재.
2. 에이전트 오작동: grade_fail / assess_bad / bulk_bad / timeout / 고아배틀.
3. 데이터 충분성: kind 분포·학생별 편차.
4. 새 기능 정확성: AI 피드백 content(날조·정답유출)·워크북 docx·제출 UX.
5. 환경/구조 개선점.

자세한 맥락: 메모리 `ops-services-cohorts-siem`, `e2e-grading-harness`, `docs/operations.md`.
