# sampling_grid.md — (temperature × top_k) 그리드 (P10-3 산출물)

모델: 9주차 `model_10ep.pth` (the-verdict 10에폭) / 시작 문자열 `"Every effort moves you"` / 30 토큰 / 각 조합 직전 `torch.manual_seed(123)`

## 3 × 3 생성 결과

| T \ top_k | None | 25 | 50 |
|---|---|---|---|
| **T=0.5** | Every effort moves you as terrace.  I glanced after him, with a single one in the house."        " a smile | Every effort moves you as terrace.  I glanced after him, with a single one in the house."        " a smile | Every effort moves you as terrace.  I glanced after him, with a single one in the house."        " a smile |
| **T=1.0** | Every effort moves you as studio dear, and rather aenez," he had been with that Doyleed therefore consum curiosity--as you lou, I blocked the usualwing had | Every effort moves you as terrace. I turned--and told that lifted the of such a laugh: "Yes, andache, I saw that, in the | Every effort moves you as terrace. I turned--and told that lifted the of such a laugh: "ident m; and fact, becoming the man of the |
| **T=1.4** | Every effort moves you as studio were, ConfederingAnnaenez,"STAT that_> downed of Doyle between therefore consumRolefix sketch; lou flash I blocked the usual shrimp do | Every effort moves you as terr what one of the pale yellow," he that lifted the of last word. Victor Grindle was;ache, I saw to what a t | Every effort moves you as terr the easel- bear ins genius-- that with a curious of destruction--just itident m;ache, I blocked the what a t |

## 정량 지표 — 원문 최장 연속 일치(단어) / 원문에 없는 단어 비율

| T \ top_k | None | 25 | 50 |
|---|---|---|---|
| **T=0.5** | 6단어 / 11% | 6단어 / 11% | 6단어 / 11% |
| **T=1.0** | 3단어 / 31% | 3단어 / 17% | 6단어 / 20% |
| **T=1.4** | 3단어 / 38% | 4단어 / 18% | 3단어 / 36% |

- 암기 재현이 가장 강한 조합: **T=0.5, top_k=None** (최장 연속 6단어, 원문 이탈 11%)
- 가장 창의적(=혼란한) 조합: **T=1.4, top_k=None** (최장 연속 3단어, 원문 이탈 38%)

## 관찰

**아래로 갈수록(T 증가) 문장이 무너진다.** top_k=None 열의 원문 이탈률이 11% → 31% → 38% 로 오른다. T=1.4·k=None 출력에는 `ConfederingAnnaenez`, `STAT`, `Role`, `shrimp` 같이 이 소설에 존재할 수 없는 토큰이 섞인다 — 로짓 차이가 눌리면서 확률 0.01% 짜리 토큰까지 추첨 대상이 되기 때문이다. 한 번 궤도를 벗어나면 그 토큰이 다음 스텝의 문맥이 되어 이탈이 연쇄된다.

**옆으로 갈수록(k 증가) 효과는 T 에 종속된다.** T=0.5 행은 top_k None/25/50 세 출력이 **완전히 동일**하다(측정 확인). 분포가 이미 뾰족해 상위 25개가 확률질량을 거의 전부 차지하므로, 마스킹을 해도 같은 시드에서 같은 토큰이 뽑힌다. 반대로 T=1.4 행에서는 k=None(이탈 38%) 과 k=25(이탈 18%) 가 뚜렷이 갈린다. **top_k 는 헛소리의 하한선을 막는 안전장치이고, 문체를 바꾸는 다이얼은 T 다.**

**과적합 모델의 '창의성'은 대부분 '덜 정확한 암기'다.** T=1.4·k=None 조합의 출력도 새 아이디어가 아니라 원문 구절 조각(`I blocked the usual`, `as terrace`)을 잘못 이어 붙인 결과다. 이 모델이 본 데이터는 소설 한 권뿐이므로 '새 조합'을 만들 재료 자체가 없다 — 온도를 올려 얻는 것은 창의성이 아니라 손상이다.
