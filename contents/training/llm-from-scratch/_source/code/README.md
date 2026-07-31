# 밑바닥부터 만들면서 배우는 LLM — 한 학기의 기록

이 저장소는 GPT-2급 LLM을 밑바닥부터 구현·훈련·튜닝한 한 학기의 기록이다. **모든 코드는 코딩 에이전트 지휘로 작성했다** — 사람의 역할은 명세하고, 검증하고, 해석하는 것이었다.

실행 환경: `llm-course:v1` 컨테이너 (aarch64 / NVIDIA GB10 / CUDA 13.0 / torch 2.9.1+cu130). 호스트에 pip 설치하지 않는다.

## 주차별 산출물 지도

| 주차 | 주제 | 핵심 파일 | 대표 결과 |
|---|---|---|---|
| [week01](week01/) | 인프라와 골든 이미지 | [spec-report.md](week01/spec-report.md) · [hardening-checklist.md](week01/hardening-checklist.md) · [smoke-test.log](week01/smoke-test.log) | aarch64 / GB10 / CUDA 13.0 확인. ch02 스모크 테스트는 의도된 KeyError 셀 때문에 `--allow-errors` 필요 |
| [week02](week02/) | 토크나이저와 BPE | [tokenizer_v1.py](week02/tokenizer_v1.py) · [tokenizer_v2.py](week02/tokenizer_v2.py) · [test_tokenizer.py](week02/test_tokenizer.py) · [bpe_compare.md](week02/bpe_compare.md) | GPT-2 BPE 어휘 50,257. 한국어는 영어 대비 문자당 토큰 3.73~7.17배 |
| [week03](week03/) | 배치와 임베딩 | [dataset.py](week03/dataset.py) · [embedding_pipeline.py](week03/embedding_pipeline.py) · [test_pipeline.py](week03/test_pipeline.py) | 슬라이딩 윈도우 (max_length, stride) 그리드. 입력·타깃 한 칸 밀림 검증 |
| [week04](week04/) | 어텐션 | [attention_v1v2.py](week04/attention_v1v2.py) · [test_attention.py](week04/test_attention.py) · [scaling_experiment.md](week04/scaling_experiment.md) · [attention_heatmap.png](week04/attention_heatmap.png) | v1→v2 전치 이식. √d 스케일링이 softmax 분포를 바꾸는 것을 실측 |
| [week05](week05/) | 코잘 어텐션과 멀티헤드 | [causal_attention.py](week05/causal_attention.py) · [multihead.py](week05/multihead.py) · [test_mha.py](week05/test_mha.py) · [heads_experiment.md](week05/heads_experiment.md) | 인과성 성질 테스트 통과. 헤드 수 1→12 에서 시간 2.90배 (교재 '대체로 비슷'과 불일치) |
| [week06](week06/) | 레이어와 트랜스포머 블록 | [layers.py](week06/layers.py) · [transformer_block.py](week06/transformer_block.py) · [test_layers.py](week06/test_layers.py) · [gelu_plot.png](week06/gelu_plot.png) | 테스트 10개를 구현보다 먼저 작성. LayerNorm·GELU·FeedForward·잔차 연결 |
| [week07](week07/) | GPT 조립 | [gpt_model.py](week07/gpt_model.py) · [generate.py](week07/generate.py) · [test_gpt.py](week07/test_gpt.py) · [param_breakdown.md](week07/param_breakdown.md) | 파라미터 **163,009,536** 개. 무작위 가중치 생성문이 교재와 문자 단위 일치 |
| [week08](week08/) | 중간고사 대비 — 버그 은행 | [bug_bank_validation.py](week08/bug_bank_validation.py) · [bug_bank_recheck.py](week08/bug_bank_recheck.py) | 버그 10종을 직접 심고 검출. #8·#10 은 교재 서술로는 검출 불가임을 규명 |
| [week09](week09/) | 첫 사전 훈련 | [pretrain.py](week09/pretrain.py) · [loss_anatomy.py](week09/loss_anatomy.py) · [test_loss.py](week09/test_loss.py) · [overfit_evidence.md](week09/overfit_evidence.md) | 초기 손실 **10.7940** (ln 50257 = 10.8249). 10에폭 후 train 0.8908 / val 6.3130. 원문 13단어 연속 암기 확인 |
| [week10](week10/) | 디코딩 전략과 가중치 이식 | [decoding.py](week10/decoding.py) · [openai_load.py](week10/openai_load.py) · [test_decoding.py](week10/test_decoding.py) · [sampling_grid.md](week10/sampling_grid.md) | T=5 에서 pizza 41/1000. OpenAI 124M val **3.5596** vs 우리 10에폭 6.3353 |
| [week11](week11/) | 분류기가 된 GPT | [spam_data.py](week11/spam_data.py) · [spam_finetune.py](week11/spam_finetune.py) · [test_spam.py](week11/test_spam.py) · [confusion.md](week11/confusion.md) | test 정확도 **95.67%** — 교재 정답지와 소수점까지 일치. 매트릭스 6조합 |
| [week12](week12/) | 지시 데이터 파이프라인 | [instr_data.py](week12/instr_data.py) · [test_collate.py](week12/test_collate.py) · [collate_evolution.md](week12/collate_evolution.md) · [quality_report.md](week12/quality_report.md) | collate 3단계 진화. -100 손실 제거 실증(차이 0.00e+00). 완전 중복 20그룹 발견 |
| [week13](week13/) | 지시 튜닝·심판·LoRA | [instr_finetune.py](week13/instr_finetune.py) · [judge.py](week13/judge.py) · [lora.py](week13/lora.py) · [test_sft.py](week13/test_sft.py) | 355M 튜닝 val 3.8172 → **0.6131**. LoRA 훈련가능 1.94%, 저지 평균 60.92 vs 60.87 |
| [week14](week14/) | 팀 프로젝트 | [proposal.md](week14/proposal.md) · [premortem.md](week14/premortem.md) · [check_premortem.py](week14/check_premortem.py) · [check_rubrics.py](week14/check_rubrics.py) | 제안서 + 사전 부검. 루브릭 합계 100 / 기말 배분 100% 검산 |
| [week15](week15/) | 발표회 | [demo_scenario.md](week15/demo_scenario.md) · [dryrun.py](week15/dryrun.py) · [archive_readme.py](week15/archive_readme.py) | 시연 드라이런 2회 (13.56s / 10.81s, 10분 제한의 2.3%) |

## 재사용 자산

### 성질 테스트

| 파일 | 내용 |
|---|---|
| [`week05/test_mha.py`](week05/test_mha.py) | 인과성 불변 — 위치 t 출력은 t+1 이후를 바꿔도 불변 |
| [`week10/test_decoding.py`](week10/test_decoding.py) | top-k 제약 — 선택 토큰이 항상 상위 k 안 |
| [`week12/test_collate.py`](week12/test_collate.py) | ignore_index 동등성 — -100 위치는 손실에서 사라진다 |
| [`week13/test_sft.py`](week13/test_sft.py) | LoRA 항등 — B=0 이면 적용 직후 출력이 원본과 동일 |

### 품질 게이트

| 파일 | 내용 |
|---|---|
| [`week10/test_decoding.py`](week10/test_decoding.py) | 이식 품질 — the-verdict val 손실 < 5.0 |
| [`week11/spam_finetune.py`](week11/spam_finetune.py) | 재현 게이트 — test 정확도 교재 값 ±1%p |
| [`week13/lora.py`](week13/lora.py) | 훈련 전 게이트 — LoRA 적용 직후 val 손실 == 원본 |

### 실패 테스트 (오류가 나야 정상)

| 파일 | 내용 |
|---|---|
| [`week10/test_decoding.py`](week10/test_decoding.py) | qkv_bias=False 로 124M 로드 → AttributeError |
| [`week05/mha_trap.py`](week05/mha_trap.py) | softmax(dim=-2) 함정을 심고 검출 |
| [`week08/bug_bank_validation.py`](week08/bug_bank_validation.py) | 버그 10종 심기·검출 |

## 하이라이트 — 10주차 4모델 비교표

| 모델 | 파라미터 | train 손실 | val 손실 | val 퍼플렉시티 |
|---|---|---|---|---|
| ① 7주차 무작위 초기화 | 163,009,536 | 10.9876 | **10.9811** | 58,753.5 |
| ② 9주차 10에폭 (the-verdict) | 163,009,536 | 0.6830 | **6.3353** | 564.1 |
| ③ OpenAI GPT-2 124M | 163,037,184 | 3.7548 | **3.5596** | 35.2 |
| ④ OpenAI GPT-2 355M | 406,286,336 | 3.5024 | **3.3585** | 28.7 |

전문: [week10/compare_generation.md](week10/compare_generation.md)

**이 표가 한 학기의 서사다.** 아키텍처도 파라미터 수도 같은 급인데, 이 소설을 한 번도 본 적 없는 GPT-2 124M(val 3.56)이 이 소설로 10에폭 훈련한 우리 모델(val 6.34)을 압도한다. 다른 것은 오직 훈련 데이터의 양이다.

## 재현 방법

```bash
# 1. 골든 이미지 빌드 (저장소 루트에서 — 이 README 기준 한 단계 위)
docker build -t llm-course:v1 -f ../harness/Dockerfile.llm-course-v1 ..

# 2. 컨테이너 기동
docker run -d --name llm-lab --gpus all --ipc=host \
  -v $PWD/code:/work -v $PWD/textbook:/textbook \
  llm-course:v1 sleep infinity

# 3. 주차별 진입점 (예)
docker exec -w /work/week02 llm-lab python3 tokenizer_v1.py
docker exec -w /work/week03 llm-lab python3 dataset.py

# 4. 전 주차 테스트
for w in week0{2,3,4,5,6,7,9} week1{0,1,2,3}; do \
  docker exec -w /work/$w llm-lab python3 -m pytest -q 2>/dev/null; done
```

> 다운로드 가중치·체크포인트는 각 주차의 `.gitignore` 로 제외했다 (week10 4.02GB, week13 5.23GB).
