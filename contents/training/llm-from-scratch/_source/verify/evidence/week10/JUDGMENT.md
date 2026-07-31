# Week 10 판정 — 말투를 조절하다

환경: llm-lab 컨테이너 (torch 2.9.1+cu130, NVIDIA GB10) · 2026-07-31

## 프롬프트별 판정

| 프롬프트 | 판정 | 근거 |
|---|---|---|
| P10-0 (준비·체크포인트 로드) | **PASS** | greedy 20토큰이 9주차 50토큰 기록의 접두사로 정확히 일치 |
| P10-1 (temperature 해부) | **PASS** | argmax=forward, T=5 pizza **41회** (교재 "40회 안팎") |
| V10-1 (T→0 = greedy) | **PASS** | T=0.01 에서 **1000/1000** forward, 엔트로피 단조 증가 |
| P10-2 (top-k 마스킹) | **PASS** | top-3 값·단어 일치, softmax 후 6자리 정확히 0.0, 합 1 |
| P10-3 (generate + 그리드) | **PASS** | 9조합 생성, 정량 지표로 최강/최혼란 조합 판별 |
| V10-2 (pytest 3개) | **PASS** | `3 passed` |
| P10-4 (체크포인트 이어 훈련) | **PASS** | 로드 전후 손실 차이 **0.000000** |
| P10-5 (OpenAI 이식) | **PASS (경로 결함 있음)** | 124M val **3.5596** / 355M val **3.3585**. 다만 1차 경로 실행 불가 → 결함 #11 |
| V10-3 (이식 정합성 3종) | **PASS** | `6 passed` (누적) |
| P10-6 (제출) | **PASS** | 필수 7종 전부 존재, 4.02GB 전량 .gitignore |

## 게이트 판정 — 16/16 PASS

| 게이트 | 주장 | 실측 | 판정 |
|---|---|---|---|
| W10-G1 | 로드 후 생성이 9주차와 동일 | 20토큰 생성이 9주차 에폭10 생성문의 **접두사**로 문자 단위 일치 | ✅ PASS |
| W10-G2 | argmax = **forward** (로짓 6.75) | 인덱스 3 → `forward`, 로짓 6.75 | ✅ PASS |
| W10-G3 | T=1 에서 pizza 사실상 **0회** | **0회** / 1000 (이론 확률 0.0101%) | ✅ PASS |
| W10-G4 | T=5 에서 pizza **약 4%(40회 안팎)** | **41회** / 1000 = 4.1% (이론 4.30%) | ✅ PASS |
| W10-G5 | T=0.1 은 사실상 greedy | forward 확률 **0.99098665** | ✅ PASS |
| W10-G6 | T=0.01 에서 1000/1000, 엔트로피 단조 증가 | **1000/1000**. H: 0.0000 < 0.0514 < 0.9127 < 1.9990 | ✅ PASS |
| W10-G7 | top-3 = 6.75/6.28/4.51, 나머지 정확히 0, 합 1 | 값·단어 일치. 0.0 인 자리 **6개**, 합 0.9999999851 (isclose True) | ✅ PASS |
| W10-G8 | 낮은 T·작은 k → 암기 수렴 / 높은 T·큰 k → 붕괴 | 최장일치 6단어(T=0.5) → 3단어(T=1.4). 원문이탈 11% → 38% | ✅ PASS |
| W10-G9 | pytest `3 passed` | `3 passed` | ✅ PASS |
| W10-G10 | 로드 직후 val == 저장 직전 (소수 3~4자리) | 6.2453 == 6.2453, **차이 0.000000** | ✅ PASS |
| W10-G11 | 이어 훈련이 매끄럽게 이어짐 | 4.3738 → **4.0130** (하강 방향, 튐 없음). step 카운터 45 복원 | ✅ PASS |
| W10-G12 | 124M 로드 후 유창한 영어 | `"Every effort moves you forward.\n\nThe first step is to understand the importance of your work."` | ✅ PASS |
| W10-G13 | 124M val 손실 **3점대 중반** | **3.5596** (우리 10에폭 모델 6.3353) | ✅ PASS |
| W10-G14 | qkv_bias=False 로드 시 오류 | `AttributeError: 'NoneType' object has no attribute 'shape'` @ `W_query.bias` | ✅ PASS |
| W10-G15 | 124M val < 5.0 | 3.5596 | ✅ PASS |
| W10-G16 | 4모델 비교표 | 아래 표 | ✅ PASS |

## 최종 산출 — 4모델 비교표 (W10-G16)

같은 조건: the-verdict.txt, 9주차 로더(max_length=256, stride=256), greedy 25토큰.

| 모델 | 파라미터 | train | val | val 퍼플렉시티 |
|---|---|---|---|---|
| ① 7주차 무작위 초기화 | 163,009,536 | 10.9876 | **10.9811** | 58,896 |
| ② 9주차 10에폭 (the-verdict) | 163,009,536 | 0.6830 | **6.3353** | 563.6 |
| ③ OpenAI GPT-2 124M | 163,037,184 | 3.7548 | **3.5596** | 35.2 |
| ④ OpenAI GPT-2 355M | 406,286,336 | 3.5024 | **3.3585** | 28.8 |

생성문:

```
① Every effort moves you rentingetic wasnم refres RexMeCHicular stren Mortgage TT remember gard ACTIONSussedOND Land Engeleddedemate breaths proxies GalaxyForm
② Every effort moves you?"  "Yes--quite insensible to the irony. She wanted him vindicated--and
③ Every effort moves you forward.  The first step is to understand the importance of your work.  The second step is to understand the
④ Every effort moves you forward, but you must be careful. You must not let your guard down. You must not let your guard down."
```

**교재의 핵심 주장이 정량으로 입증되었다.** ②는 이 소설로 10에폭을 돌려 train 손실을
10.99 → 0.68 로 떨어뜨렸지만 val 은 10.98 → 6.34 에서 멈춘다. ③은 **이 소설을 한 번도
본 적이 없는데** val 3.56 이다. 퍼플렉시티로 563.6 → 35.2, **16배** 차이다.
아키텍처도 파라미터 수도 같은 급인데 다른 것은 오직 훈련 데이터의 양이다.
③→④(3.56 → 3.36)의 이득은 ②→③(6.34 → 3.56)에 비하면 훨씬 작다 —
**데이터가 먼저고 모델 크기가 나중이다.**

## P10-3 그리드 상세

| T \ top_k | None | 25 | 50 |
|---|---|---|---|
| **0.5** | 6단어 / 11% | 6단어 / 11% | 6단어 / 11% |
| **1.0** | 3단어 / 31% | 3단어 / 17% | 6단어 / 20% |
| **1.4** | 3단어 / 38% | 4단어 / 18% | 3단어 / 36% |

(원문 최장 연속 일치 단어 수 / 원문에 없는 단어 비율)

- 암기 재현 최강: **T=0.5** (모든 k 동일)
- 가장 혼란: **T=1.4, k=None** — `ConfederingAnnaenez`, `STAT`, `shrimp` 등 소설에 없는 토큰 등장

## P10-4 체크포인트 상세

| 항목 | train | val |
|---|---|---|
| 저장 직전 (5에폭 종료) | 4.0834 | **6.2453** |
| 로드 직후 (새 프로세스) | 4.0834 | **6.2453** |
| 차이 | 0.000000 | **0.000000** |

옵티마이저까지 실렸다는 별도 증거: `exp_avg` 텐서 **161개**, L2 노름 평균 0.018136 (0 이 아님),
`step` 카운터 **45** (= 5에폭 × 9배치).

5+5 이어 훈련 최종 train 0.8394 / val 6.3115 — 9주차 연속 10에폭(0.8908 / 6.3130)과 같은 동네.

---

# 발견된 결함

## 결함 #11 — P10-5 의 가중치 다운로드 경로 3개가 모두 문제가 있다 (**중대**, 교재-프롬프트결함)

**위치**: Week9-10 교재 10.7절 P10-5 1번 항목 + 10.12 트러블슈팅 2행

**교재 서술**:
> 1. 교재 저장소 ch05의 가중치 다운로드 유틸을 가져와 124M 가중치 다운로드

트러블슈팅:
> | 다운로드 유틸의 tensorflow 의존 오류 | 원본 체크포인트가 TF 형식 | 교재 저장소 ch05 보너스의 **대안 로더(TF 불필요)** 사용을 에이전트에게 지시 |

**실측 — 세 경로의 상태**:

| 경로 | 파일 | 결과 |
|---|---|---|
| ① 1차 경로 (교재 지시) | `ch05/01_main-chapter-code/gpt_download.py` | ❌ `ModuleNotFoundError: No module named 'tensorflow'` |
| ② safetensors 대안 | `ch05/02_alternative_weight_loading/weight-loading-hf-safetensors.ipynb` | ⚠️ 동작하나 `pip install safetensors` 필요 (골든 이미지에 없음) |
| ③ pytorch 대안 | `ch05/02_alternative_weight_loading/weight-loading-pytorch.ipynb` | ⚠️ **미션을 무력화** |

①의 실패 출력:
```
$ docker exec llm-lab python3 -c "import tensorflow"
ModuleNotFoundError: No module named 'tensorflow'
```
1주차 골든 이미지 규격에 tensorflow 가 없으므로 **모든 학생이 반드시 이 오류를 만난다.**
트러블슈팅에 예고돼 있으나 P10-5 본문에는 아무 경고가 없다.

②는 동작하지만 **골든 이미지에 `safetensors` 가 없어 두 번째 ModuleNotFoundError 가 난다.**
교재는 이 패키지를 어디에서도 언급하지 않는다. 즉 "대안 로더를 쓰라"는 지시를 따라도
설치 단계에서 다시 막힌다.

③이 진짜 문제다. **이 경로를 쓰면 P10-5 의 학습 목표가 통째로 사라진다.**
```
$ python3 -c "... g.load_state_dict(torch.load('gpt2-small-124M.pth', weights_only=True))"
크기 702 MB
strict=True 로드 성공 — QKV 분할도 전치도 전혀 필요 없었다
```
이 .pth 는 이미 우리 구현의 키 이름(`trf_blocks.N.att.W_query.weight` …)으로 변환돼 있어
**한 줄로 실린다.** P10-5 3번이 요구한
- (a) 합쳐진 QKV 행렬을 셋으로 분할
- (b) Linear 가중치 전치

가 **하나도 필요 없다.** 교재가 "이번 주의 숨은 수확"이라고 부른 규약 맞추기 경험이
사라지는데, 학생 입장에서는 손실 게이트(V10-3 3번)까지 통과하므로 **성공한 것처럼 보인다.**
에이전트에게 "ch05 보너스의 대안 로더를 쓰라"고만 지시하면 세 노트북 중
가장 쉬운 ③을 고를 가능성이 높다.

**권고 (교재 수정안)** — P10-5 1번을 아래로 교체.

```text
 1. 가중치 다운로드 — 경로를 반드시 지정할 것
    ⚠️ ch05/01_main-chapter-code/gpt_download.py 는 tensorflow 를 요구한다.
       llm-lab 골든 이미지에는 없으므로 그대로는 실패한다(정상이다).
    → ch05/02_alternative_weight_loading/**weight-loading-hf-safetensors.ipynb**
       의 방식을 쓴다. 먼저 컨테이너에서 `pip install safetensors` 를 실행할 것.
       HuggingFace 허브에서 model.safetensors(124M 548MB)를 직접 받아
       텐서만 읽는다.
    🚫 같은 폴더의 weight-loading-pytorch.ipynb 는 쓰지 말 것.
       그 .pth 는 이미 우리 구현의 키 이름으로 변환돼 있어 한 줄로 실린다.
       QKV 분할도 전치도 필요 없어져 이번 미션의 학습 목표가 통째로 사라진다.
```

그리고 1주차 골든 이미지 패키지 목록에 `safetensors` 를 추가하거나,
10.2절 준비에 설치 한 줄을 넣는다. 트러블슈팅 표도 아래로 교체:
```
| 다운로드 유틸의 tensorflow 의존 오류 | 원본 체크포인트가 TF 형식 | 정상이다. hf-safetensors 노트북 방식으로 전환하고 `pip install safetensors` |
| safetensors ModuleNotFoundError | 골든 이미지 미포함 | 컨테이너 안에서 `pip install safetensors` |
```

## 보정 권고 #3 — T=0.5 행에서 top_k 가 출력을 전혀 바꾸지 않는다 (경미)

**위치**: Week9-10 교재 10.5절 P10-3 예상 결과

**교재 서술**: "낮은 T·**작은 k**일수록 9주차의 암기 문장에 수렴하고…"

**실측**: T=0.5 행의 top_k None / 25 / 50 **세 출력이 문자 단위로 완전히 동일**하다.

```
[관찰] T=0.5 행의 세 출력이 완전히 동일한가: True
```

**원인**: T=0.5 에서는 분포가 이미 뾰족해 상위 25개가 확률질량을 거의 전부 차지한다.
top-k 마스킹 후 재정규화해도 역누적분포의 착지점이 바뀌지 않아, 같은 시드에서
같은 토큰이 뽑힌다. **정상 동작이다.**

문제는 학생이 이 결과를 보면 **"내 top_k 구현이 안 먹는다"고 오해한다**는 점이다.
실제로 이 시점에서 학생이 할 수 있는 잘못된 조치는 top-k 코드를 "고치는" 것이다.

**권고**: 예상 결과에 한 문장을 추가한다.
```text
⚠️ T=0.5 행에서는 top_k 를 None/25/50 으로 바꿔도 출력이 완전히 같을 수 있다.
   버그가 아니다 — 분포가 이미 뾰족해 상위 25개가 확률질량을 거의 전부 차지하므로,
   마스킹 후 재정규화해도 같은 시드에서 같은 토큰이 뽑힌다.
   top_k 의 효과는 T 가 클 때(1.4 행) 뚜렷해진다. 이것이 "top_k 는 헛소리의
   하한선을 막는 안전장치이고, 문체를 바꾸는 다이얼은 T"라는 말의 실측 근거다.
```
그리고 10.12 트러블슈팅에 한 행 추가:
```
| top_k 를 바꿔도 출력이 그대로 | 낮은 T 에서는 정상 동작 | T=1.4 행에서 비교. 상위 k 확률질량 합을 출력해 확인 |
```

## 보정 권고 #4 — 장난감 어휘를 "알파벳순"이라 했으나 아니다 (경미)

**위치**: Week9-10 교재 10.3절 P10-1 1번

**교재**: "장난감 어휘(**알파벳순**): closer, every, effort, forward, …"

알파벳순이면 `effort` 가 `every` 보다 앞이다(`eff` < `eve`). 교재의 순서는 원서
저장소의 `vocab` 딕셔너리 순서를 그대로 옮긴 것으로, 알파벳순이 아니다.

이 순서로 매긴 인덱스에 로짓이 대응하므로, 학생이 "알파벳순"이라는 말을 믿고
순서를 바로잡으면 `every`(0.89)와 `effort`(−1.90)의 로짓이 뒤바뀐다.
다행히 정답지가 지목하는 `forward`(인덱스 3)와 `pizza`(인덱스 6)는 그대로라
결론은 바뀌지 않지만, 분포표의 두 행이 교재와 달라진다.

**권고**: "알파벳순" 표기를 삭제하고 `(교재 저장소의 vocab 순서 그대로 — 알파벳순이 아니다)`
로 바꾼다.
