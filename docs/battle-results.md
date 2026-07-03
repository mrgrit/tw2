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

> **채점기·시나리오가 정상이라는 근거**: 실답안(competent submission)은 세 채점 유형 모두에서
> pass 한다 — 실측 battle 5(AICompanion semantic 25/25) · battle 95(순수 semantic 4미션 83/90) ·
> battle 97(결정론: 실공격→Assessor→pass 42/45). 상세는 **`docs/battle-reference-passes.md`**.
> 즉 partial/fail 은 시나리오 결함이 아니라 자동 하니스가 학생이 아니기 때문. 배포는 `docs/battle-verification.md`.

**집계**: 시나리오 191 · 미션 802 · ✅pass 22 · 🟡partial 167 (생성 시각 2026-07-03 02:36)


## agent-ir  (✅0 🟡33)

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
| agent-ir-w10 | 99 | 🟡partial | ❌fail | ❌fail | ❌fail | 11/90 |
| agent-ir-w11 | 100 | 🟡partial | 🟡partial | ❌fail | ❌fail | 25/90 |
| agent-ir-w12 | 101 | 🟡partial | 🟡partial | ❌fail | ❌fail | 19/90 |
| agent-ir-w13 | 102 | 🟡partial | 🟡partial | ❌fail | ❌fail | 19/90 |
| agent-ir-w14 | 103 | 🟡partial | 🟡partial | ❌fail | ❌fail | 20/95 |
| agent-ir-w15 | 104 | 🟡partial | ❌fail | 🟡partial | ❌fail | 15/95 |

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

## ai-agent  (✅0 🟡4)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-agent-w01 | 105 | 🟡partial | ❌fail | ❌fail | ❌fail | 8/90 |
| ai-agent-w02 | 106 | 🟡partial | ❌fail | ❌fail | ❌fail | 5/90 |
| ai-agent-w03 | 107 | 🟡partial | 🟡partial | ❌fail | ❌fail | 23/90 |
| ai-agent-w04 | 108 | ❌fail | ❌fail | 🔁review | 🔁review | 0/90 |
| ai-agent-w05 | 109 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w06 | 110 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w07 | 111 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w08 | 112 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| ai-agent-w09 | 113 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w10 | 114 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w11 | 115 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w12 | 116 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w13 | 117 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w14 | 118 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-agent-w15 | 119 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |

## ai-safety  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-safety-w01 | 135 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w02 | 136 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w03 | 137 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w04 | 138 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w05 | 139 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w06 | 140 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w07 | 141 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w08 | 142 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| ai-safety-w09 | 143 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w10 | 144 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w11 | 145 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w12 | 146 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w13 | 147 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w14 | 148 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-w15 | 149 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |

## ai-safety-adv  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-safety-adv-w01 | 120 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w02 | 121 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w03 | 122 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w04 | 123 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w05 | 124 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w06 | 125 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w07 | 126 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w08 | 127 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w09 | 128 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w10 | 129 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w11 | 130 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w12 | 131 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w13 | 132 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w14 | 133 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-safety-adv-w15 | 134 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |

## ai-security  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-security-w01 | 150 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w02 | 151 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w03 | 152 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w04 | 153 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w05 | 154 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w06 | 155 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w07 | 156 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w08 | 157 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| ai-security-w09 | 158 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w10 | 159 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w11 | 160 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w12 | 161 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w13 | 162 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w14 | 163 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-security-w15 | 164 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |

## ai-service-pentest  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| ai-service-pentest-w01 | 165 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w02 | 166 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w03 | 167 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w04 | 168 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w05 | 169 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w06 | 170 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w07 | 171 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w08 | 172 | 🔁review | 🔁review | 🔁review | 🔁review | 0/100 |
| ai-service-pentest-w09 | 173 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w10 | 174 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w11 | 175 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w12 | 176 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w13 | 177 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w14 | 178 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| ai-service-pentest-w15 | 179 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |

## aisec  (✅0 🟡3)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| aisec-w01 | 180 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| aisec-w02 | 181 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| aisec-w03 | 182 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| aisec-w04 | 183 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| aisec-w05 | 184 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| aisec-w06 | 185 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w07 | 186 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w08 | 187 | ❌fail | ❌fail | ❌fail | ❌fail | 0/95 |
| aisec-w09 | 188 | 🟡partial | 🟡partial | ❌fail | ❌fail | 31/90 |
| aisec-w10 | 189 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w11 | 190 | 🟡partial | ❌fail | ❌fail | ❌fail | 15/90 |
| aisec-w12 | 191 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w13 | 192 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w14 | 193 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |
| aisec-w15 | 194 | ❌fail | ❌fail | ❌fail | ❌fail | 0/90 |

## attack  (✅11 🟡28)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| attack-w01 | 210 | ✅pass | 🟡partial | ❌fail | 🟡partial | 41/65 |
| attack-w02 | 211 | ✅pass | 🟡partial | ❌fail | ❌fail | 35/75 |
| attack-w03 | 212 | ✅pass | ✅pass | ❌fail | ❌fail | 37/75 |
| attack-w04 | 213 | ✅pass | 🟡partial | ✅pass | ❌fail | 44/90 |
| attack-w05 | 214 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 39/90 |
| attack-w06 | 215 | ✅pass | 🟡partial | 🟡partial | ❌fail | 48/100 |
| attack-w07 | 216 | 🟡partial | ✅pass | 🟡partial | ❌fail | 48/100 |
| attack-w08 | 217 | ✅pass | ❌fail | 🟡partial | ❌fail | 29/100 |
| attack-w09 | 220 | 🟡partial | ✅pass | ❌fail | ❌fail | 43/100 |
| attack-w10 | 221 | 🟡partial | 🟡partial | ❌fail | ❌fail | 31/100 |
| attack-w11 | 222 | ❌fail | ❌fail | ❌fail | ❌fail | 0/100 |
| attack-w12 | 223 | ❌fail | ❌fail | ❌fail | ❌fail | 10/100 |
| attack-w13 | 224 | 🟡partial | ❌fail | 🟡partial | ❌fail | 31/100 |
| attack-w14 | 225 | ✅pass | ❌fail | 🟡partial | ❌fail | 26/100 |
| attack-w15 | 226 | 🟡partial | ❌fail | 🟡partial | ❌fail | 27/100 |

## attack-adv  (✅11 🟡15)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| attack-adv-w01 | 195 | 🟡partial | ❌fail | ❌fail | ❌fail | 18/100 |
| attack-adv-w02 | 196 | ✅pass | ❌fail | ❌fail | ❌fail | 25/100 |
| attack-adv-w03 | 197 | ✅pass | ❌fail | ❌fail | ❌fail | 27/100 |
| attack-adv-w04 | 198 | ✅pass | ❌fail | ❌fail | ❌fail | 27/100 |
| attack-adv-w05 | 199 | ✅pass | ❌fail | ❌fail | ❌fail | 27/100 |
| attack-adv-w06 | 200 | ✅pass | ❌fail | ❌fail | ❌fail | 25/100 |
| attack-adv-w07 | 201 | ❌fail | ❌fail | ❌fail | ❌fail | 4/100 |
| attack-adv-w08 | 202 | ❌fail | ❌fail | ❌fail | ❌fail | 3/100 |
| attack-adv-w09 | 203 | ✅pass | ❌fail | ❌fail | ❌fail | 26/100 |
| attack-adv-w10 | 204 | ✅pass | ❌fail | ❌fail | ❌fail | 28/100 |
| attack-adv-w11 | 205 | 🟡partial | ❌fail | ❌fail | ❌fail | 23/100 |
| attack-adv-w12 | 206 | ✅pass | ❌fail | ❌fail | ❌fail | 27/100 |
| attack-adv-w13 | 207 | ✅pass | ❌fail | ❌fail | ❌fail | 22/100 |
| attack-adv-w14 | 208 | ✅pass | ❌fail | ❌fail | ❌fail | 23/100 |
| attack-adv-w15 | 209 | ✅pass | ❌fail | ❌fail | ❌fail | 24/100 |

## autonomous-security  (✅0 🟡35)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| autonomous-security-w01 | 227 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 39/90 |
| autonomous-security-w02 | 228 | 🟡partial | 🟡partial | ❌fail | ❌fail | 23/90 |
| autonomous-security-w03 | 229 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 23/90 |
| autonomous-security-w04 | 230 | 🟡partial | 🟡partial | ❌fail | ❌fail | 15/90 |
| autonomous-security-w05 | 231 | 🟡partial | 🟡partial | ❌fail | ❌fail | 13/90 |
| autonomous-security-w06 | 232 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 26/90 |
| autonomous-security-w07 | 233 | 🟡partial | ❌fail | 🟡partial | ❌fail | 23/90 |
| autonomous-security-w08 | 234 | 🟡partial | ❌fail | ❌fail | ❌fail | 8/95 |
| autonomous-security-w09 | 235 | 🟡partial | 🟡partial | ❌fail | ❌fail | 23/90 |
| autonomous-security-w10 | 236 | 🟡partial | 🟡partial | 🟡partial | 🟡partial | 27/90 |
| autonomous-security-w11 | 237 | 🟡partial | 🟡partial | ❌fail | ❌fail | 11/90 |
| autonomous-security-w12 | 238 | 🟡partial | 🟡partial | 🟡partial | ❌fail | 18/95 |
| autonomous-security-w13 | 239 | 🟡partial | 🟡partial | ❌fail | ❌fail | 7/90 |
| autonomous-security-w14 | 240 | 🟡partial | 🟡partial | ❌fail | ❌fail | 10/90 |
| autonomous-security-w15 | 241 | 🟡partial | 🟡partial | ❌fail | ❌fail | 25/95 |

## autonomous-systems  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| autonomous-systems-w01 | 242 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w02 | 243 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w03 | 244 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w04 | 245 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w05 | 246 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w06 | 247 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w07 | 248 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w08 | 249 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| autonomous-systems-w09 | 250 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w10 | 251 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w11 | 252 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w12 | 253 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w13 | 254 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w14 | 255 | 🔁review | 🔁review | 🔁review | 🔁review | 0/90 |
| autonomous-systems-w15 | 256 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |

## cloud-container  (✅0 🟡0)

| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |
|---|---|---|---|---|---|---|
| cloud-container-w01 | 257 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w02 | 258 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w03 | 259 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w04 | 260 | 🔁review | 🔁review | 🔁review | 🔁review | 0/98 |
| cloud-container-w05 | 261 | 🔁review | 🔁review | 🔁review | 🔁review | 0/98 |
| cloud-container-w06 | 262 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w07 | 263 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w08 | 264 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w09 | 265 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w10 | 266 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
| cloud-container-w11 | 267 | 🔁review | 🔁review | 🔁review | 🔁review | 0/95 |
