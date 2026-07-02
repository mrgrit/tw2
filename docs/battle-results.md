# 공방전 배틀 실행 결과표

> `scripts/run_all_battles.py` 가 각 시나리오를 solo 배틀로 **실제 실행**하고 라이브 채점한 결과.
> 채점 = el34 실 Assessor(:9201, docker exec 결정론 체크) + 실공격(공격자 VM→el34) + claude semantic 채점.

## 결과 해석 (중요 — 판정을 오독하지 말 것)

이 표는 **자동 하니스**가 낸 결과다. 채점기·시나리오는 정상이나(아래 근거), 자동 하니스는
**사람/LLM 수준의 서술 답안을 못 쓴다**. 미션은 채점 성격에 따라 3분류:

1. **결정론 채점 미션**(log_contains·wazuh_alert·file·port·process) — Assessor 가 el34 로그/포트를
   실검사 → 공격 흔적이 실제로 남으면 **자동으로도 통과**. (여기가 진짜 인프라 검증의 핵심.)
2. **command_ran 미션**(주로 AICompanion 트랙 RED) — 6v6 원칙상 **외부 공격자 명령은 미수집** →
   자동으론 '명령 0건'으로 **partial 상한**. 타깃 흔적/실추출값으로 부분 인정.
3. **순수 semantic 설계 미션**(CPS·IoT·physical 전부, 각 트랙 BLUE 설계) — 인프라에 심을 게 없고
   **구체적 설계 서술**이 산출물이라 자동 하니스로는 통과 불가(합격기준 문구 복사는 채점기가 반려).

> **채점기·시나리오가 정상이라는 근거**: 사람/LLM 이 **제대로 쓴 답안**은 만점이 난다 —
> 실측 `battle 5` ai-service-pentest-w02 **BLUE-2(semantic 설계) = pass 25/25**. 즉 partial/fail 은
> 시나리오 결함이 아니라 **자동 하니스가 학생이 아니기 때문**. 배포·구조는 `docs/battle-verification.md`.

**집계**: 시나리오 24 · 미션 96 · ✅pass 0 · 🟡partial 71 (생성 시각 2026-07-02 20:12)


## agent-ir  (✅0 🟡22)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| agent-ir-w01 | 88 | 🟡partial | 🟡partial | ❌fail | ❌fail | 30/90 |
| agent-ir-w02 | 89 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 31/90 |
| agent-ir-w03 | 90 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 32/90 |
| agent-ir-w04 | 91 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 30/90 |
| agent-ir-w05 | 92 | 🟡partial | 🟡partial | ❌fail | ❌fail | 27/90 |
| agent-ir-w06 | 93 | 🟡partial | 🟡partial | ❌fail | 🟡partial | 32/90 |
| agent-ir-w07 | 94 | 🟡partial | 🟡partial | ❌fail | ❌fail | 30/90 |
| agent-ir-w08 | 96 | 🟡partial | 🟡partial | ❌fail | ❌fail | 20/95 |
| agent-ir-w09 | 98 | 🟡partial | 🟡partial | ❌fail | ❌fail | 22/90 |

## agent-ir-adv  (✅0 🟡49)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| agent-ir-adv-w01 | 73 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 37/90 |
| agent-ir-adv-w02 | 74 | 🟡partial | ❌fail | 🟡partial | 🟡partial | 27/90 |
| agent-ir-adv-w03 | 75 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 38/90 |
| agent-ir-adv-w04 | 76 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 22/90 |
| agent-ir-adv-w05 | 77 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 22/90 |
| agent-ir-adv-w06 | 78 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 37/90 |
| agent-ir-adv-w07 | 79 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 17/90 |
| agent-ir-adv-w08 | 80 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 22/90 |
| agent-ir-adv-w09 | 81 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 27/90 |
| agent-ir-adv-w10 | 82 | 🟡partial | ❌fail | 🟡partial | ❌fail | 28/90 |
| agent-ir-adv-w11 | 83 | 🟡partial | 🟡partial | ❌fail | 🟡partial | 27/90 |
| agent-ir-adv-w12 | 84 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 23/90 |
| agent-ir-adv-w13 | 85 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 23/90 |
| agent-ir-adv-w14 | 86 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 23/90 |
| agent-ir-adv-w15 | 87 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 16/95 |
