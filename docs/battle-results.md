# 공방전 배틀 실행 결과표

> `scripts/run_all_battles.py` 가 각 시나리오를 solo 배틀로 실제 실행하고 라이브 채점한 결과.
> 채점 = el34 실 Assessor(:9201, 결정론 체크) + AICompanion 실공격 + claude semantic 채점.
> 자동 하니스의 보고서는 최소본이라 semantic 만점이 어려움 → partial 다수는 하니스 보고 품질 한계이지 시나리오 결함 아님.

**집계**: 시나리오 48 · 미션 192 · ✅pass 0 · 🟡partial 68 (생성 시각 2026-07-02 17:43)


## agent-ir  (✅0 🟡29)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| agent-ir-w01 | 22 | 🟡partial | 🟡partial | ❌fail | ❌fail | 27/90 |
| agent-ir-w02 | 23 | 🟡partial | 🟡partial | ❌fail | ❌fail | 25/90 |
| agent-ir-w03 | 24 | 🟡partial | 🟡partial | ❌fail | ❌fail | 26/90 |
| agent-ir-w04 | 25 | 🟡partial | 🟡partial | ❌fail | ❌fail | 25/90 |
| agent-ir-w05 | 26 | 🟡partial | 🟡partial | ❌fail | ❌fail | 18/90 |
| agent-ir-w06 | 27 | 🟡partial | 🟡partial | ❌fail | ❌fail | 22/90 |
| agent-ir-w07 | 28 | 🟡partial | 🟡partial | ❌fail | ❌fail | 22/90 |
| agent-ir-w08 | 29 | 🟡partial | 🟡partial | ❌fail | ❌fail | 21/95 |
| agent-ir-w09 | 30 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 13/90 |
| agent-ir-w10 | 31 | 🟡partial | ❌fail | ❌fail | ❌fail | 9/90 |
| agent-ir-w11 | 32 | 🟡partial | 🟡partial | ❌fail | ❌fail | 21/90 |
| agent-ir-w12 | 33 | 🟡partial | 🟡partial | ❌fail | ❌fail | 16/90 |
| agent-ir-w13 | 34 | 🟡partial | ❌fail | ❌fail | ❌fail | 18/90 |
| agent-ir-w14 | 35 | 🟡partial | 🟡partial | ❌fail | ❌fail | 11/95 |
| agent-ir-w15 | 36 | 🟡partial | ❌fail | 🟡partial | ❌fail | 9/95 |

## agent-ir-adv  (✅0 🟡37)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| agent-ir-adv-w01 | 7 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 19/90 |
| agent-ir-adv-w02 | 8 | 🟡partial | ❌fail | 🟡partial | ❌fail | 22/90 |
| agent-ir-adv-w03 | 9 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 17/90 |
| agent-ir-adv-w04 | 10 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 17/90 |
| agent-ir-adv-w05 | 11 | 🟡partial | ❌fail | 🟡partial | ❌fail | 15/90 |
| agent-ir-adv-w06 | 12 | 🟡partial | 🟡partial | ❌fail | ❌fail | 14/90 |
| agent-ir-adv-w07 | 13 | 🟡partial | 🟡partial | ❌fail | ❌fail | 17/90 |
| agent-ir-adv-w08 | 14 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 16/90 |
| agent-ir-adv-w09 | 15 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 16/90 |
| agent-ir-adv-w10 | 16 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 16/90 |
| agent-ir-adv-w11 | 17 | 🟡partial | 🟡partial | ❌fail | ❌fail | 10/90 |
| agent-ir-adv-w12 | 18 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 17/90 |
| agent-ir-adv-w13 | 19 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 27/90 |
| agent-ir-adv-w14 | 20 | 🟡partial | ❌fail | 🟡partial | ❌fail | 20/90 |
| agent-ir-adv-w15 | 21 | ❌fail | 🟡partial | ❌fail | ❌fail | 8/95 |

## ai-agent  (✅0 🟡1)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-agent-w01 | 37 | ❌fail | ❌fail | ❌fail | ❌fail | 5/90 |
| ai-agent-w02 | 38 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w03 | 39 | 🟡partial | ❌fail | ❌fail | ❌fail | 5/90 |
| ai-agent-w04 | 40 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w05 | 41 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w06 | 42 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w07 | 43 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w08 | 44 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| ai-agent-w09 | 45 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w10 | 46 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w11 | 47 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w12 | 48 | 🔁review | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w13 | 49 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w14 | 50 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-agent-w15 | 51 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |

## ai-safety-adv  (✅0 🟡1)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-safety-adv-w01 | 52 | 🟡partial | ❌fail | ❌fail | ❌fail | 3/90 |
| ai-safety-adv-w02 | 53 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| ai-safety-adv-w03 | 54 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
