# overfit_evidence.md — 과적합 물증 (V9-2 산출물)

모델: `model_10ep.pth` (10 에폭 사전 훈련, the-verdict.txt)
시작 문자열: `Every effort moves you` → greedy 50 토큰 생성

## 생성문

```
Every effort moves you?"

"Yes--quite insensible to the irony. She wanted him vindicated--and by me!"








He placed them at my elbow and as I turned, and down the room, when I
```

## 조각별 원문 존재 검색 (7단어 조각, 3단어씩 겹침)

| # | 조각 | 원문 존재 | 원문 위치(문자 오프셋) |
|---|---|---|---|
| 1 | `Every effort moves you?" "Yes--quite insensible to` | X | — |
| 2 | `you?" "Yes--quite insensible to the irony. She` | **O** | 13175 |
| 3 | `to the irony. She wanted him vindicated--and` | **O** | 13204 |
| 4 | `She wanted him vindicated--and by me!" He` | **O** | 13218 |
| 5 | `vindicated--and by me!" He placed them at` | X | — |
| 6 | `He placed them at my elbow and` | **O** | 14294 |
| 7 | `at my elbow and as I turned,` | X | — |
| 8 | `and as I turned, and down the` | X | — |
| 9 | `turned, and down the room, when I` | X | — |

**원문과 일치한 조각: 4 / 9 = 44.4%**

## 가장 긴 연속 일치 구간 (더 강한 물증)

- **13 단어**가 원문과 그대로 일치
- 원문 위치: 문자 오프셋 **13175**

```
you?" "Yes--quite insensible to the irony. She wanted him vindicated--and by me!" He
```

## train 손실 1 미만이 퍼플렉시티로 뜻하는 것

train 손실 < 1 → 퍼플렉시티 = exp(손실) < **e¹ ≈ 2.718** 이하.
즉 모델이 매 순간 **후보 3개 미만에서 고민**하는 수준이다.
5만 개 어휘 중에서 사실상 다음 토큰을 '알고 있다' — 이해가 아니라 암기다.

(실측: 최종 train 손실 0.8908 → 퍼플렉시티 2.44)
