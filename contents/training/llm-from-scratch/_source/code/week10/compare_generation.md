# compare_generation.md — 4모델 비교 (P10-5 최종 산출)

같은 프롬프트 `"Every effort moves you"` 에 greedy 25토큰. 손실은 the-verdict.txt 를 9주차 로더(max_length=256, stride=256)로 잰 값이라 네 모델이 **완전히 같은 조건**에서 비교된다.

## 손실 비교

| 모델 | 파라미터 | train 손실 | val 손실 | val 퍼플렉시티 |
|---|---|---|---|---|
| ① 7주차 무작위 초기화 | 163,009,536 | 10.9876 | **10.9811** | 58,753.5 |
| ② 9주차 10에폭 (the-verdict) | 163,009,536 | 0.6830 | **6.3353** | 564.1 |
| ③ OpenAI GPT-2 124M | 163,037,184 | 3.7548 | **3.5596** | 35.2 |
| ④ OpenAI GPT-2 355M | 406,286,336 | 3.5024 | **3.3585** | 28.7 |

## 생성문

**① 7주차 무작위 초기화**

```
Every effort moves you rentingetic wasnم refres RexMeCHicular stren Mortgage TT remember gard ACTIONSussedOND Land Engeleddedemate breaths proxies GalaxyForm
```

**② 9주차 10에폭 (the-verdict)**

```
Every effort moves you?"

"Yes--quite insensible to the irony. She wanted him vindicated--and by me!"


```

**③ OpenAI GPT-2 124M**

```
Every effort moves you forward.

The first step is to understand the importance of your work.

The second step is to understand the
```

**④ OpenAI GPT-2 355M**

```
Every effort moves you forward, but you must be careful. You must not let your guard down. You must not let your guard down."

```

## 한 학기의 서사

①→②: 이 소설로 10 에폭을 돌려 train 손실이 10.99 → 0.68 로 떨어졌다. 그러나 val 손실은 10.98 → 6.34 로 **거의 그대로**다. train 만 떨어지고 val 이 안 떨어지는 것 — 이것이 과적합의 정의다.

②→③: **이 소설을 한 번도 본 적 없는** GPT-2 124M 의 val 손실이 3.5596 다. 이 소설로 훈련한 우리 모델(6.3353)을 2.78 낮은 손실로 압도한다. 퍼플렉시티로는 564 → 35, 약 16배 차이다. **아키텍처는 같다. 파라미터 수도 같은 급이다. 다른 것은 오직 데이터의 양이다.**

③→④: 355M 은 val 3.3585 로 124M(3.5596)보다 0.20 더 낮다. 같은 데이터에서 모델을 키운 이득이며, ②→③ 의 격차(2.78)보다 훨씬 작다. **데이터가 먼저고 모델 크기가 나중이다.**

이 표가 13주차 파인튜닝의 전제다 — 우리는 남이 큰 데이터로 만든 일반화 능력을 출발점으로 빌려 쓰고, 우리 목적에 맞게 조정만 한다.
