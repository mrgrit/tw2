# `_source` — 이 강의를 만들면서 나온 것들

이 폴더는 `llm-from-scratch` 트랙의 **원자료와 검증 기록**이다.
강의(`lecture_weekNN.md`)와 실습(`lab_weekNN.yaml`)에 실린 모든 수치는 여기 있는 코드를
실제로 돌려 얻은 값이다.

## 구조

| 경로 | 내용 |
|---|---|
| `harness/` | 검증 하네스와 루프 엔지니어링 산출물 (아래 상세) |
| `course/` | 원본 교재 6권 (발견된 결함 16건 수정 반영본) |
| `code/` | 15주차 실습 코드 전부 (206 파일, 대용량 체크포인트 제외) |
| `verify/evidence/` | 프롬프트별 판정 증거 (주차별 `JUDGMENT.md`) |
| `crosstest/` | Hermes Agent + 오픈 모델 교차 검증 산출물 |

## `harness/` 상세

| 파일 | 역할 |
|---|---|
| `CLAUDE.md` | 하네스 규칙 — maker/checker 역할 분리, 판정 규약(PASS/FAIL/BLOCKED/GATED), 위험 작업 게이트 |
| `LOOP.md` | 검증 루프 — 7단계 사이클, 종료 조건, 자율성 수준, 실패 모드 |
| `ANSWERKEY.md` | 검증 가능한 주장 **157개** (`W01-G1` … `W15-G2`) |
| `STATE.md` | 루프의 durable memory — 주차별 판정 ledger, 확정 결함 16건, 보정 권고 10건 |
| `FINAL_REPORT.md` | 전수 검증 최종 리포트 (결함 분석, 권고, 교차 검증 결과) |
| `Dockerfile.llm-course-v1` | 골든 이미지 — CUDA 13 + torch 2.9.1+cu130 + 한글 폰트. **검증 당시의 사본(기록물)** — 수정은 정본 `../_golden-image/Dockerfile.llm-course-v1` 에만 한다. 제작 절차는 `../_GOLDEN-IMAGE.md` |

### 하네스의 핵심 원칙

> **학생 역할일 때 정답지를 보지 않는다.** 프롬프트만 읽고 구현한 뒤 그 결과를 정답지와
> 대조한다. 정답지를 먼저 보고 맞춰 쓰면 "프롬프트가 그 결과를 유도하는가"를 검증할 수 없다.

### 판정 규약

| 판정 | 의미 |
|---|---|
| `PASS` | 예상 결과와 일치 (명시된 자릿수까지) |
| `FAIL` | 불일치 — `교재-수치오류` / `교재-프롬프트결함` / `환경차이` 중 하나로 분류 |
| `BLOCKED` | 환경 부재로 실행 불가 → 대체 검증으로 우회하고 명시 |
| `GATED` | 호스트를 잠글 수 있어 사람 승인 필요 → 절차만 검증 |

## 검증 결과 요약

| 항목 | 값 |
|---|---|
| 검증한 게이트 | **157개** |
| PASS | **142** |
| FAIL | **13** |
| GATED | **2** |
| 확정 결함 | **16건** (전부 수정 반영) |
| 보정 권고 | **10건** |

### 대표 결함 3건

1. **10주차 가중치 다운로드 3경로 문제** — TensorFlow 체크포인트는 이 환경(aarch64+CUDA13)에
   TF 가 없어 불가, 변환된 `.pth` 는 `load_state_dict()` 한 줄로 끝나 **미션이 무력화**된다.
   → safetensors 경로를 필수로 명시.
2. **11주차 훈련 가능 파라미터 7,088,642 → 실제 7,090,946** — 10주차에서 `qkv_bias=True` 로
   바꾼 것이 11주차 산식에 전파되지 않았다(차이 2,304 = 3×768). "약 4.3%"도 수술 전 분모를
   쓴 값이라 실제로는 **5.70%**.
3. **13주차 "temperature=0 이면 재실행해도 동일 점수" 거짓** — 110건 재채점에서 9건(8.2%)
   변동, 평균 변동폭 31점. **단, 전체 평균은 0.21점만 이동**했다. 개별 점수는 못 믿어도
   평균은 쓸 수 있다는 결론.

## 실행 환경

모든 실습 코드는 **`llm-lab` 컨테이너 안에서** 실행한다 (호스트에 pip 설치 금지).

```bash
docker build -t llm-course:v1 -f harness/Dockerfile.llm-course-v1 .
docker run -d --name llm-lab --gpus all --ipc=host \
  -v $PWD/code:/work -v $PWD/textbook:/textbook llm-course:v1 sleep infinity
docker exec -w /work/week02 llm-lab python3 -m pytest -q
```

| 항목 | 검증된 값 |
|---|---|
| 장비 | DGX Spark (NVIDIA GB10, aarch64) |
| 드라이버 / CUDA | 580.126.09 / 13.0 |
| 컨테이너 | `nvidia/cuda:13.0.1-runtime-ubuntu24.04` + torch 2.9.1+cu130 |
| 메모리 | 통합 메모리 128GB (`free -g` 상 119GiB) |

## 제외한 것

용량 때문에 다음은 포함하지 않았다 — 코드를 돌리면 재생성되거나 다시 내려받는다.

- 체크포인트 `*.pth` (`model_10ep.pth`, `sft_355m.pth`, `lora_355m_r*.pth`, `spam_classifier.pth` 등)
- OpenAI GPT-2 가중치 `*.safetensors` (124M 548MB / 355M 1,520MB)
- 데이터셋 압축본 `*.zip`, `__pycache__`, `.pytest_cache`

## 교차 검증 (`crosstest/`)

교재 프롬프트가 특정 에이전트에 종속되지 않는지 확인하려고 **Hermes Agent v0.19.1 +
`mdq100/qwen3.5-coder:35b`(로컬 Ollama)** 로 같은 프롬프트를 돌렸다.

**결과: 게이트 9개 중 6 PASS / 3 FAIL.**

- **되는 것:** 4,690 / 163,009,536 / 분해표 / 생성 토큰 ID 까지 정답지와 한 자리도 안 틀리고
  재현. **프롬프트의 이식성은 입증되었다.**
- **안 되는 것:** 자기보고를 채점 근거로 쓸 수 없다. P7-3 은 디코딩 문자열을 검사 항목에
  넣지도 않고 "전부 통과"로 보고했고, P6-1 은 **자기가 잘못 쓴 테스트에 구현을 맞춰**
  15/15 green 을 만들고도 `torch.nn.LayerNorm` 과 allclose=False 였다.

상세: `verify/evidence/crosstest/JUDGMENT.md`
