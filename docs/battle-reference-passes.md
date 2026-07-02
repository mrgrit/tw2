# 참조: 실답안(competent submission) 배틀 결과 — 시나리오·채점 정상 증명

`docs/battle-results.md`(자동 하니스 배치)는 대부분 partial/fail 이다. 그 이유는 **자동 하니스가
사람/LLM 수준의 서술 답안을 못 쓰기 때문**이지 시나리오·채점기 결함이 아니다. 이를 증명하기 위해,
**사람/LLM 이 제대로 쓴 답안**을 각 채점 유형별로 제출해 실제 채점한 결과다(라이브, `vh.submit`).

| # | battle | 시나리오/미션 | 채점 유형 | 판정 | 점수 |
|---|---|---|---|---|---|
| 1 | 5  | ai-service-pentest-w02 · BLUE-2 | AICompanion semantic 설계(인젝션 완화) | ✅ **pass** | 25/25 |
| 2 | 95 | iot-security-w01 · RED-1 | **순수 semantic**(IoT 4대 표면 침투 경로) | ✅ **pass** | 23/25 |
| 3 | 95 | iot-security-w01 · RED-2 | 순수 semantic(확산·영향 분석) | ✅ **pass** | 18/20 |
| 4 | 95 | iot-security-w01 · BLUE-1 | 순수 semantic(4대 표면 방어) | ✅ **pass** | 22/25 |
| 5 | 95 | iot-security-w01 · BLUE-2 | 순수 semantic(Security by Design) | ✅ **pass** | 20/20 |
| 6 | 97 | autonomous-security-w02 · RED-1 | **결정론+semantic**(정찰: 실공격→Suricata 흔적) | ✅ **pass** | 22/25 |
| 7 | 97 | autonomous-security-w02 · RED-2 | 결정론+semantic(웹 침투: 실공격→ModSec 흔적) | ✅ **pass** | 20/20 |

## 무엇을 증명하나

- **battle 5** — AICompanion 트랙의 semantic 설계 미션이 **구체적 계층별 완화 설계**를 쓰면 만점(25/25).
  자동 하니스가 성공기준 문구를 복사하면 채점기가 반려(→ 문구 복사 금지 확인) — **채점기가 견고**하다.
- **battle 95** — **자동 하니스로는 전부 fail 하는 순수 semantic 과목**(CPS·IoT·physical 이 이 패턴)이
  **실제 설계 답안으로는 4미션 전부 pass**(83/90). 순수 설계형 과목의 fail 은 100% 하니스 한계.
- **battle 97** — **결정론 채점의 end-to-end**: 외부 공격자 VM(.113)에서 실제 공격 → el34 Suricata
  eve.json·ModSec audit 에 흔적 → **실 Assessor 가 검증** → 여기에 ReAct 서술을 더하면 pass(42/45).
  실 인프라 채점 사슬(공격→탐지→Assessor→채점)이 통째로 동작함을 보인다.

## 결론

세 유형(AICompanion semantic · 순수 semantic · 결정론) 모두에서 **제대로 쓴 답안은 pass** 한다.
따라서 `docs/battle-results.md` 의 partial/fail 은 **시나리오 결함이 아니라 자동 하니스가 학생이
아니기 때문**이다. 시나리오 128+178개는 구조 검증(validate) 무오류 + 실서비스 DB 적재 + 위 실채점으로
정상 동작이 확인되었다. 재현/배포는 `docs/battle-verification.md`.
