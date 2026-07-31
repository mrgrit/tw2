# Week 09 판정 — 내 모델의 첫 학습

환경: llm-lab 컨테이너 (torch 2.9.1+cu130, NVIDIA GB10) · 2026-07-30

## 프롬프트별 판정

| 프롬프트 | 판정 | 근거 |
|---|---|---|
| P9-0 (준비·common.py) | **PASS** | device=cuda, week07 import OK, 왕복 변환 3/3 일치 |
| P9-1 (손실 해부) | **PASS** | 수동 == 자동 == **10.7940**, 퍼플렉시티 48725.82 |
| V9-1 (pytest 2개) | **PASS** | `2 passed` |
| P9-2 (train/val 분리) | **PASS** | 9/1 배치, [2,256], 커버 4,608/512, 훈련 전 손실 **10.98** |
| P9-3 (10 에폭 훈련) | **PASS** | train 0.8908 / val 6.3130, 곡선 발산 확인. 16.4초 |
| V9-2 (과적합 물증) | **PASS** | 조각 4/9 일치 + **13단어 연속 원문 일치**(오프셋 13175) |
| P9-4 (속도 실험) | **부분 FAIL → 결함 #10** | 실험 A PASS. 실험 B 의 **batch=32 가 실행 불가** |
| P9-5 (제출) | **PASS** | 8개 필수 산출물 존재 (model_10ep.pth 포함) |

## 게이트 판정

| 게이트 | 주장 | 실측 | 판정 |
|---|---|---|---|
| W09-G1 | 수동 == 자동 ≈ **10.7940** | 둘 다 10.7940 (소수 4자리 일치, allclose True) | ✅ PASS |
| W09-G2 | 퍼플렉시티 ≈ **48,726** | 48725.82 (상대 오차 **0.00%**) | ✅ PASS |
| W09-G3 | ln(50257) ≈ **10.825** | 10.8249 (측정 손실과 차이 0.0309) | ✅ PASS |
| W09-G4 | 정답 확률 ≈ 1/50257 = 0.00002 근처 | `0.00007454, 0.00003106, 0.00001156, 0.00001034, 0.00005678, 0.00000476` — 6/6 이 균등값의 0.1~10배 안 | ✅ PASS |
| W09-G5 | `2 passed` | `2 passed` | ✅ PASS |
| W09-G6 | train **9** / val **1** 배치, [2,256], 커버 **4,608 / 512** | 9 / 1, (2,256), 4,608 / 512 | ✅ PASS |
| W09-G7 | 훈련 전 손실 **약 10.98** | train **10.9876** / val **10.9811** | ✅ PASS |
| W09-G8 | train **1 아래**, val **6 초반대** 정체 후 미세 상승 | train **0.8908**, val 최소 6.0994(에폭 7.1) → 최종 **6.3130** (+0.2136) | ✅ PASS |
| W09-G9 | 상당수 조각이 원문에 그대로 존재 | 7단어 조각 **4/9 (44.4%)** + **13단어 연속** 일치 | ✅ PASS |
| W09-G10 | train 손실 <1 = 퍼플렉시티 e¹≈2.7 이하 | 2.44 | ✅ PASS |
| W09-G11 | GPU 가 CPU 대비 수 배~수십 배 | **11.50배** (13.60s → 1.18s) | ✅ PASS |
| W09-G12 | bf16 이득이 이 규모에선 크지 않을 수 있다 | fp32 대비 **1.13배** | ✅ PASS |
| W09-G13 | batch 키우면 tokens/sec 상승 | 원문 설정으로는 batch=32 실행 불가 → 정정 설정에서 4,155 → **7,166 (1.72배)** | ⚠️ PASS (정정 후) |
| W09-G14 | val 6.4 → 퍼플렉시티 약 601 | e^6.4 = 601.85 ✓ (우리 val 6.3130 → 551.69) | ✅ PASS |

## 훈련 진행 관찰 (교재가 요구한 "헛소리 → 문장 형태 → 원문 비슷" 변화)

| 에폭 | 생성문 (앞부분) |
|---|---|
| 1 | `Every effort moves you,,,,,,,,,,,,.` |
| 2 | `Every effort moves you, and,, and,,,,,,, and,.` |
| 3 | `Every effort moves you, and, and the to the of the to the to the of the...` |
| 4 | `Every effort moves you, and a. Gisburn. I had the picture. Gisburn...` |
| 5 | `Every effort moves you, I had the picture--as of the picture--as I had been...` |
| 6 | `Every effort moves you know the` |
| 7 | `Every effort moves you know the picture, and pushed one of the deep arm-chairs.` |
| 8 | `Every effort moves you know," was one of the picture. Gisburn--as such--had not to my work` |
| 9 | `Every effort moves you know," was not that my hostess was "interesting": on that I felt...` |
| 10 | `Every effort moves you?"  "Yes--quite insensible to the irony. She wanted him vindicated--and by me!"` |

교재 서술과 정확히 부합한다: 구두점 반복(1~2) → 기능어 반복(3) → 고유명사 등장(4)
→ 구절 단위 암기(5~7) → 원문 문장 재현(8~10).

## V9-2 과적합 물증 상세

생성문:
```
Every effort moves you?"

"Yes--quite insensible to the irony. She wanted him vindicated--and by me!"

He placed them at my elbow and as I turned, and down the room, when I
```

| # | 조각(7단어) | 원문 존재 | 오프셋 |
|---|---|---|---|
| 1 | `Every effort moves you?" "Yes--quite insensible to` | X | — |
| 2 | `you?" "Yes--quite insensible to the irony. She` | **O** | 13175 |
| 3 | `to the irony. She wanted him vindicated--and` | **O** | 13204 |
| 4 | `She wanted him vindicated--and by me!" He` | **O** | 13218 |
| 5 | `vindicated--and by me!" He placed them at` | X | — |
| 6 | `He placed them at my elbow and` | **O** | 14294 |
| 7~9 | (뒤쪽 3개) | X | — |

**가장 긴 연속 일치: 13단어** (오프셋 13175)
```
you?" "Yes--quite insensible to the irony. She wanted him vindicated--and by me!" He
```

주목할 점: 모델이 오프셋 13218 구간을 재현한 뒤 **오프셋 14294 구간으로 건너뛰어** 이어 붙였다.
서로 떨어진 두 원문 구절을 각각 암기하고 봉합한 것 — 이해가 아니라 암기라는 더 강한 증거다.

## 속도 실험 상세

**표 A (batch=2, 1 에폭, 3회 평균)**

| 장치 | 1에폭 시간 | 3회 측정값 | CPU 대비 |
|---|---|---|---|
| CPU | 13.60s | 13.64 / 13.57 / 13.59 | 1.00배 |
| GPU (fp32) | 1.18s | 1.18 / 1.18 / 1.18 | **11.50배** |
| GPU + bf16 | 1.05s | 1.05 / 1.04 / 1.05 | 12.97배 |

측정 편차가 0.01~0.07s 로 매우 작다 — 워밍업·synchronize 규약이 제대로 작동한 증거.

---

# 발견된 결함

## 결함 #10 — P9-4 실험 B 의 `batch_size=32` 가 실행 불가 (**중간**, 교재-수치오류)

**위치**: Week9-10 교재 9.6절 P9-4 실험 B

**교재 서술**:
> [실험 B — GPU 처리량] GPU fp32에서 **batch_size ∈ {2, 8, 32}** 로
>  1 에폭 시간과 초당 처리 토큰 수(tokens/sec) 측정

**실측 — batch=32 는 배치가 0개다**:
```
현상 확인 — 교재 원문 설정 (stride=256, drop_last=True)
  batch= 2 → 배치  9개
  batch= 8 → 배치  2개
  batch=32 → 배치  0개 ← 실행 불가
```

**원인**: P9-2 가 정한 설정이 `max_length=256, stride=256, drop_last=True` 이고
train 데이터는 4,612 토큰이다. 따라서 샘플 수는
`⌈(4612 − 256) / 256⌉ = 18`개. `18 // 32 = 0` → 배치가 하나도 만들어지지 않는다.
루프가 그냥 돌지 않으므로 학생은 "시간 0초, tokens/sec 0" 같은 무의미한 결과를 얻거나
`ZeroDivisionError` 를 만난다.

**정정안 2가지를 실측 비교했다**:

**대안 1 — `drop_last=False`**

| batch | 배치 수 | 시간(s) | 본 토큰 | tokens/sec | batch=2 대비 |
|---|---|---|---|---|---|
| 2 | 9 | 1.097 | 4,608 | 4,200 | 1.00배 |
| 8 | 3 | 0.758 | 4,608 | 6,082 | 1.45배 |
| 32 | **1** | 0.665 | 4,608 | 6,929 | 1.65배 |

**대안 2 — `stride=128` (샘플 18 → 35개, `drop_last=True` 유지)** ← 권고

| batch | 배치 수 | 시간(s) | 본 토큰 | tokens/sec | batch=2 대비 |
|---|---|---|---|---|---|
| 2 | 17 | 2.095 | 8,704 | 4,155 | 1.00배 |
| 8 | 4 | 1.273 | 8,192 | 6,435 | 1.55배 |
| 32 | 1 | 1.143 | 8,192 | **7,166** | **1.72배** |

**대안 2 를 권고하는 이유**:
- batch 2/8/32 세 조건 모두 실행된다
- `drop_last=True` 를 유지하므로 배치 크기가 균일해 비교가 공정하다
- **3주차 그리드 실험과 연결된다** — stride=128 은 3주차 표의 (256,128) 행이고,
  "중복 128 토큰"이라는 성질을 이미 배웠다
- 처리량 배율이 1.72배로 더 선명해 "작은 배치는 GPU를 굶긴다"는 교육 목표를 더 잘 보여준다

**권고 (교재 수정안)** — P9-4 실험 B 를 아래로 교체.

```text
 [실험 B — GPU 처리량] GPU fp32에서 batch_size ∈ {2, 8, 32} 로
  1 에폭 시간과 초당 처리 토큰 수(tokens/sec) 측정
  ⚠️ 이 실험만 stride=128 로 바꿔 로더를 다시 만들 것.
     P9-2 설정(stride=256)으로는 train 샘플이 18개뿐이라 batch=32에서
     drop_last=True 가 배치를 0개로 만든다 — 실험 자체가 돌지 않는다.
     stride=128 이면 샘플이 35개가 되어 세 조건 모두 측정된다.
     (3주차 그리드 표의 (256,128) 행이 바로 이 설정이다 — 중복 128 토큰)
```

그리고 9.10 트러블슈팅 표에 한 행 추가:
```
| batch를 키우니 배치 수가 0이 됨 | 샘플 수보다 batch_size가 큼 + drop_last=True | 샘플 수를 len(dataset)으로 먼저 확인. stride를 줄여 샘플을 늘리거나 drop_last=False |
```

## 보정 권고 #2 — W09-G9 통과 기준을 정량화 (경미)

**위치**: Week9-10 교재 9.5절 V9-2 통과 기준

교재: "**상당수** 조각이 원문에서 그대로 발견됨"

"상당수"가 모호해 학생이 판정하기 어렵다. 실측 기준을 제시하면 좋다.

**권고**: `통과 기준: 7~8단어 조각 중 **3분의 1 이상**이 원문에 그대로 존재하고,
가장 긴 연속 일치 구간이 **10단어 이상**일 것. (참고 실측: 조각 4/9 = 44.4%,
최장 연속 일치 13단어)`

최장 연속 일치 길이를 함께 요구하면 물증이 훨씬 강해진다 — 조각 비율만 보면
"우연히 흔한 표현이 겹친 것"이라는 반론이 가능하지만, 13단어 연속 일치는 우연일 수 없다.
