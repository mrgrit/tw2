# STATE — 검증 루프의 durable memory

> 이 파일이 루프의 스파인이다. 대화가 끊기거나 컨텍스트가 소진되어도 이 파일을 읽고 이어서 진행한다.
> 갱신 규칙: 프롬프트 1개를 판정할 때마다 ledger에 한 줄 추가.

## 현재 위치

- **단계**: **Week01~15 전 주차 검증 완료 + hermes 교차 검증 완료**
- **다음 액션**: tw2 강의 제작(`contents/training/llm-from-scratch/`) → push
- **누적 결함**: 16건 확정 (#2는 오판으로 철회) + 보정 권고 10건 (#10은 교차 검증에서 추가)

## 환경 사실 (검증된 값 — 지어내지 말 것)

| 항목 | 값 | 확인 명령 |
|---|---|---|
| 아키텍처 | `aarch64` | `uname -m` |
| 커널 | `6.17.0-1008-nvidia` | `uname -r` |
| OS | Ubuntu 24.04.4 LTS | `lsb_release -d` |
| 메모리 | 119GiB 총계 (통합 메모리 128GB) | `free -g` |
| GPU | `NVIDIA GB10`, 드라이버 580.126.09 | `nvidia-smi` |
| CUDA | release 13.0, V13.0.88 | `nvcc --version` |
| Docker | 29.1.3, `nvidia` 런타임 사용 가능 | `docker info` |
| 호스트 Python | 3.12.3 (torch **미설치** — 컨테이너에서만 사용) | `python3 -V` |
| Ollama | 0.30.0, 37개 모델 (qwen3:8b, llama3.1:8b, ministral-3:8b 등 8B급 보유) | `ollama list` |
| 디스크 | 2.3TB 여유 | `df -h /` |

## 디렉토리 규약

```
/home/mrgrit/llm_from_scratch/
├── CLAUDE.md ANSWERKEY.md LOOP.md STATE.md   하네스
├── course/          Drive에서 받은 원본 교재 6권
├── code/weekNN/     실습 산출물 (컨테이너 /work/weekNN 로 마운트)
├── verify/evidence/weekNN/   프롬프트별 증거
├── verify/findings/          결함 리포트
├── harness/         골든 이미지 Dockerfile 등
└── textbook/        rickiepark/llm-from-scratch 클론
```

## Ledger — 주차별 판정 요약

| 주차 | 게이트 | PASS | FAIL | GATED/BLOCKED | 증거 |
|---|---|---|---|---|---|
| 사전 | 환경·교재 저장소 | 2 (W12-G1, W14-G2) | 0 | 0 | `verify/evidence/week00-setup.md` |
| W01 | 10개 | 7 | 1 (G10) | 2 (G5, G7) | `verify/evidence/week01/JUDGMENT.md` |
| W02 | 16개 | 15 | 1 (G5) | 0 | `verify/evidence/week02/JUDGMENT.md` |
| W03 | 10개 | 10 | 0 | 0 | `verify/evidence/week03/JUDGMENT.md` |
| W04 | 13개 | 13 | 0 | 0 | `verify/evidence/week04/JUDGMENT.md` |
| W05 | 14개 | 13 | 1 (G12b 시간) | 0 | `verify/evidence/week05/JUDGMENT.md` |
| W06 | 9개 | 9 | 0 | 0 | `verify/evidence/week06/JUDGMENT.md` |
| W07 | 11개 | 11 | 0 | 0 | `verify/evidence/week07/JUDGMENT.md` |
| W08 | 3개 | 3 | 0 | 0 | `verify/evidence/week08/JUDGMENT.md` |
| W09 | 14개 | 14 (G13은 정정 후) | 0 | 0 | `verify/evidence/week09/JUDGMENT.md` |
| W10 | 16개 | 16 | 0 | 0 | `verify/evidence/week10/JUDGMENT.md` |
| W11 | 12개 | 10 | 2 (G8, G12) | 0 | `verify/evidence/week11/JUDGMENT.md` |
| W12 | 10개 | 10 | 0 | 0 | `verify/evidence/week12/JUDGMENT.md` |
| W13 | 12개 | 9 | 3 (G6a, G6b, G9) | 0 | `verify/evidence/week13/JUDGMENT.md` |
| W14-15 | 5개 | 5 | 0 | 0 | `verify/evidence/week14-15/JUDGMENT.md` |
| **합계** | **157개** | **142** | **13** | **2** | |

## 확정 결함

| # | 위치 | 분류 | 요약 |
|---|---|---|---|
| 1 | W1-2 §1.3 P1-1 | 환경차이 | 한국어 로케일에서 `lscpu \| grep Architecture` 무출력 → `LC_ALL=C` 필요 |
| 3 | W1-2 §1.4.2 P1-3 | 교재-프롬프트결함 | `ufw enable` 대화형 확인 → 비대화형 실행 시 멈춤. + docker가 ufw 우회 경고 누락 |
| 4 | W1-2 §1.7 P1-7 | **교재-수치오류** | ch02.ipynb에 의도된 KeyError 셀 → `--allow-errors` 없이는 100% 실패. "무결 실행" 불가능 |
| 5 | W1-2 §2.4 P2-3 | **교재-수치오류** | V1 decode가 원문 복원 못 함(`" It' s`). 교재 저장소 출력도 동일 |
| 6 | W3-5 §3.7 P3-5 | **교재-프롬프트결함** | `"the cat and the dog"` 에 중복 토큰 0개 (BPE 선행공백). 실험 성립 불가 |
| 7 | 골든 이미지 (전 주차 그래프) | 환경차이 | 한글 폰트 부재로 matplotlib 라벨이 □. **수정 완료** (fonts-nanum + MATPLOTLIBRC) |
| 8 | W3-5 §5.8 P5-6 | **교재-수치오류** | "시간은 대체로 비슷" → 실측 3.48/5.11/10.10ms = **2.90배**. 원인: attn_weights 가 heads 에 비례 |
| 9 | W6-8 §8.7 버그은행 | 교재-프롬프트결함 | #8은 12층에 심어야 검출력 확보 / #10은 `argmax(dim=-1)[:,-1:]` 이 정답과 동일해 버그가 안 됨 |
| 10 | W9-10 §9.6 P9-4 | **교재-수치오류** | 실험 B `batch=32` 가 배치 0개로 **실행 불가**. stride=128 정정안 실측 완료 |
| 11 | W9-10 §10.7 P10-5 | **교재-프롬프트결함** | 가중치 다운로드 3경로 모두 문제: ①TF 없음 ②safetensors 미설치 ③pytorch .pth 는 **미션 무력화**(분할·전치 불필요) |
| 12 | W11-13 §11.5 P11-3 | **교재-수치오류** | 훈련가능 파라미터 7,088,642 → 실제 **7,090,946** (qkv_bias=True 의 3×768 누락). "약 4.3%" 도 수술 전 분모 → **5.70%** |
| 13 | W11-13 §11.8 P11-6 | **교재-수치오류** | "355M ≥ 124M" 이 3전략 중 1개에서만 성립. (b) 는 124M 96.33% vs 355M 85.00%. 20에폭 재측정에서도 94.33% |
| 14 | W11-13 §13.5 P13-3 | **교재-수치오류** | "temperature=0 이면 재실행해도 동일 점수" 거짓. 110개 재채점 9건(8.2%) 변동, 평균 변동폭 31점. 단 **평균은 0.21점만 이동** |
| 15 | W11-13 §13.5 P13-3 | **교재-프롬프트결함** | 저지 모델명은 플레이스홀더인데 평균 "50점 안팎"을 정답지로 제시. llama3.1:8b 실측 **60.92** |
| 16 | W11-13 §13.5 P13-3 | **교재-프롬프트결함** | `http://localhost:11434` 하드코딩 — 컨테이너에서 연결 거부(exit=7). `172.17.0.1` 필요 |

## 보정 권고

| # | 위치 | 요약 |
|---|---|---|
| R1 | W1-2 §2.7 | 한국어 토큰 비율 "2~5배" → 실측 3.73~7.17, 평균 4.94 → "4~7배" 권고 |
| R2 | W9-10 §9.5 V9-2 | "상당수 조각" 정량화 권고 → "조각 1/3 이상 + 최장 연속 10단어 이상" |
| R3 | W9-10 §10.5 P10-3 | T=0.5 행은 top_k 를 바꿔도 출력이 동일하다(정상). 버그 오인 방지 문구 필요 |
| R4 | W9-10 §10.3 P10-1 | 장난감 어휘를 "알파벳순"이라 했으나 아니다(every < effort). 표기 삭제 권고 |
| R5 | W11-13 §12.3 P12-1 | 고정 서두를 "..." 로 생략 → 프롬프트만으로 복원 불가. 모델의 사전지식이 채움. 전문 게재 권고 |
| R6 | W11-13 §12.7 P12-5 | "심각한 문제는 적을 것" 이 탐색을 조기 종료시킴. 실측 완전중복 20그룹 45건 전부 output 상이 |
| R7 | W11-13 §13.1 vs §13.6 | LoRA 스케일이 배경이론 (α/r) vs P13-4 α 로 충돌 (r=α=16 이면 16배 차이). 실행 기준(α)으로 통일 권고 |
| R8 | W14-15 §15.2 P15-1 | "총 시간 10분" 기준이 명령 실행 시간만 잼 (실측 11~14초). 설명 시간 산정 추가 권고 |
| R9 | W14-15 §15.4 | 동료 평가 4항목×5점(20점)을 5% 로 환산하는 규칙 부재 |
| R10 | W6-8 §6.3 P6-1 | 교차 검증에서 "green인데 틀린 구현" 관측 → 2단계에 `nn.Module`/`nn.Parameter` 명시 + `torch.nn.LayerNorm` allclose 대조를 끌어올림. **수정 완료** |

## 교차 에이전트 검증 (Hermes + 오픈 모델)

| 항목 | 값 |
|---|---|
| 에이전트 | Hermes Agent v0.19.1 (Nous Research) |
| 모델 | `mdq100/qwen3.5-coder:35b` (로컬 Ollama, OpenAI 호환 `/v1`) |
| 테스트 | P2-1 / P7-1 / P7-3 / P6-1(2단계) — 쉬움→어려움 4개 |
| 결과 | 게이트 9개 중 **6 PASS / 3 FAIL** |
| 증거 | `verify/evidence/crosstest/JUDGMENT.md`, `crosstest/` |

**결론:** 교재 프롬프트는 CC 전용이 아니다 — 4,690 / 163,009,536 / 분해표 / 생성 토큰 ID까지
오픈 모델로도 정확히 재현된다. 그러나 **자기보고를 채점 근거로 쓰면 안 된다**: P7-3은 디코딩
문자열을 검사 항목에 넣지도 않고 "전부 통과"로 보고했고, P6-1은 자기가 잘못 쓴 테스트에 구현을
맞춰 15/15 green을 만들고도 `torch.nn.LayerNorm`과 allclose=False 였다.

## 사용자 지시 메모

- 순차 진행, 자동화 러너 금지, 전수 검사
- 테스트 코드는 `./code` 에 저장
- 최종 산출: `mrgrit/tw2` 의 `contents/training/llm-from-scratch/` 에
  lecture_weekNN.md × 15 + lab_weekNN.yaml × 15 (기존 `_LECTURE_RUBRIC.md` 형식 준수)
- 하네스·루프 구축 산출물도 함께 저장
- PAT는 커밋 금지 (평문 노출됨 → 작업 후 폐기 권고)
