# 환경·교재 저장소 검증 (전 주차 선행 조건)

## 1. 골든 이미지 `llm-course:v1` 구축

교재는 골든 이미지를 `<llm-course:v1>`로만 지칭하고 "조교 배포"라고 적었다.
실물이 없으므로 교재의 요구사항(aarch64 / CUDA 13 / GPU 사용 가능 / 실습 의존성)을 만족하는
이미지를 직접 구성했다. → `harness/Dockerfile.llm-course-v1`

| 항목 | 값 |
|---|---|
| base | `nvidia/cuda:13.0.1-runtime-ubuntu24.04` |
| python | 3.12 (Ubuntu 24.04 시스템 python) |
| torch | **2.9.1+cu130** (`--index-url https://download.pytorch.org/whl/cu130`) |
| 기타 | tiktoken 0.13.0, matplotlib 3.11.1, pandas 3.0.5, pytest 9.1.1, numpy 2.5.1, jupyter/nbconvert 7.17.1, requests, tqdm |
| 이미지 크기 | 8.02GB |

### GB10(sm_121) 관련 중요 관찰

```
$ docker exec llm-lab python3 -c "import torch; print(torch.cuda.get_arch_list(), torch.cuda.get_device_capability(0))"
['sm_80','sm_90','sm_100','sm_110','sm_120','compute_120'] (12, 1)
```

- GB10의 compute capability는 **12.1(sm_121)** 인데, torch 2.9.1+cu130 의 바이너리는 sm_120까지다.
  → `compute_120` PTX JIT로 실행된다. 다음 경고가 출력된다(무해하지만 학생이 놀란다):
  ```
  Minimum and Maximum cuda capability supported by this version of PyTorch is (8.0) - (12.0)
  ```
- torch **2.13.0+cu130** 도 확인했으나 arch_list는 `sm_120`까지로 동일 (native sm_121 없음).
  → 보수적으로 검증이 끝난 2.9.1 유지.

### 교재가 요구하는 연산 전수 스모크 테스트 (12/12 OK)

| 연산 | 결과 | 사용 주차 |
|---|---|---|
| matmul | OK | 3·4주 |
| embedding | OK | 3주 |
| layernorm | OK | 6주 |
| softmax | OK | 4주 |
| gelu(tanh) | OK | 6주 |
| dropout | OK | 5주 |
| cross_entropy | OK | 9주 |
| backward | OK | 6·9주 |
| adamw | OK | 9주 |
| bf16 autocast | OK | 9·11주 |
| multinomial | OK | 10주 |
| topk | OK | 10주 |

### 컨테이너 기동/재진입 (교재 P1-4 대응)

```bash
docker run -d --name llm-lab --gpus all --ipc=host \
  -v /home/mrgrit/llm_from_scratch/code:/work \
  -v /home/mrgrit/llm_from_scratch/textbook:/textbook \
  llm-course:v1 sleep infinity
docker exec -it llm-lab bash          # 재진입
```

`nvidia-smi` in container → `NVIDIA GB10` 표시 ✓
`torch.cuda.is_available()` → `True`, `get_device_name(0)` → `NVIDIA GB10` ✓
→ **W01-G8 PASS**

## 2. 교재 저장소 `rickiepark/llm-from-scratch` 경로 실재 확인

| 교재 참조 | 실제 경로 | 판정 |
|---|---|---|
| ch02 메인 노트북 (P1-7, V2-1) | `ch02/01_main-chapter-code/ch02.ipynb` | ✓ |
| the-verdict.txt (P2-0) | `ch02/01_main-chapter-code/the-verdict.txt` | ✓ |
| ch03 노트북 (P4-0, V3-1) | `ch03/01_main-chapter-code/ch03.ipynb` | ✓ |
| ch05 가중치 다운로드 유틸 (P10-5) | `ch05/01_main-chapter-code/gpt_download.py` | ✓ |
| ch05 보너스 대안 로더 (10.12 트러블슈팅) | `ch05/02_alternative_weight_loading/` (3종) | ✓ |
| ch05 구텐베르크 (10.8) | `ch05/03_bonus_pretraining_on_gutenberg/` | ✓ |
| ch06 스팸 분류 (11주) | `ch06/01_main-chapter-code/ch06.ipynb` | ✓ |
| ch07 instruction-data.json (P12-0) | `ch07/01_main-chapter-code/instruction-data.json` — **1,100개** | ✓ **W12-G1 PASS** |
| ch07 저지 (P13-3) | `ch07/03_model-evaluation/`, `ollama_evaluate.py` | ✓ |
| 부록 E LoRA (P13-4) | `appendix-E/01_main-chapter-code/appendix-E.ipynb` | ✓ |
| 부록 A DDP (트랙 D) | `appendix-A/01_main-chapter-code/DDP-script.py`, `DDP-script-torchrun.py` | ✓ |

### Week 14 트랙 카드 출발 자료 (W14-G2)

| 트랙 | 교재 저장소 경로 | 판정 |
|---|---|---|
| A — KV 캐시 | `ch04/03_kv-cache/` (+ `04_gqa`, `05_mla`, `06_swa`) | ✓ |
| B — Llama 3.2 / Qwen3 / Gemma 3 | `ch05/07_gpt_to_llama/`, `ch05/11_qwen3/`, `ch05/12_gemma3/` | ✓ |
| C — DPO | `ch07/04_preference-tuning-with-dpo/dpo-from-scratch.ipynb` | ✓ |
| D — 분산 훈련 | `appendix-A/01_main-chapter-code/DDP-script*.py`, `ch05/10_llm-training-speed/02_opt_multi_gpu_ddp.py` | ✓ |
| E — 서빙 | `ch05/06_user_interface/`, `ch06/04_user_interface/`, `ch07/06_user_interface/` | ✓ |
| F — 자율 | (해당 없음, 학생 자체 구성) | — |

→ **W14-G2 PASS** — 트랙 A~E 출발 자료가 전부 실재한다.
