# 골든 이미지 `llm-course:v1` 제작 가이드 (조교·강사용)

`llm-from-scratch` 트랙 15주차 실습은 **전원이 같은 컨테이너 이미지** 안에서 돈다.
이 문서는 그 이미지를 **처음부터 만드는 절차**다. 학생용 요약은 강의 `lecture_week01.md` **부록 A**.

| 파일 | 역할 |
|---|---|
| `_golden-image/Dockerfile.llm-course-v1` | **정본** Dockerfile |
| `_golden-image/build.sh` | 사전조건 검사 → 빌드 → 수락 시험 한 방 스크립트 |
| `_golden-image/smoke_test.py` | 수락 시험 — GPU 12연산 + 한글 폰트 + 패키지 + 의도적 부재 |
| `_source/harness/Dockerfile.llm-course-v1` | 15주 전수 검증 당시의 사본(기록물). 수정은 `_golden-image/` 쪽에만 한다 |

---

## 1. 왜 골든 이미지인가

"제 환경에선 되는데요"를 원천 차단하는 장치다. 이 수업은 15주 내내 **숫자가 판정 기준**이다
(2주차 토큰 4,690 / 9주차 파라미터 163,009,536 / 11주차 훈련 가능 7,090,946 …). 학생마다 torch
버전이 다르면 같은 코드가 다른 숫자를 뱉고, 채점도 트러블슈팅도 성립하지 않는다.

그리고 이 장비는 함정이 둘이다.

1. **aarch64(ARM64)** — 인터넷 설치 가이드 대부분이 x86_64 기준이다. 그대로 따라 하면 휠이 안 맞는다.
2. **GB10 = Blackwell 세대(CUDA 13)** — PyPI 기본 `pip install torch` 휠에는 이 GPU 커널이 없다.
   반드시 `download.pytorch.org/whl/cu130` 인덱스에서 받아야 CUDA 가 켜진다.

호스트에 직접 설치하면 학생이 이 둘을 각자 밟는다. 그래서 **호스트에는 아무것도 설치하지 않고**
검증된 이미지 하나를 전원에게 배포한다.

---

## 2. 사전 조건 (호스트)

| 항목 | 기대값 | 확인 명령 |
|---|---|---|
| 아키텍처 | `aarch64` | `LC_ALL=C uname -m` |
| OS | Ubuntu 24.04 LTS | `LC_ALL=C lsb_release -ds` |
| GPU / 드라이버 | `NVIDIA GB10` / `580.x` | `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` |
| Docker | 있으면 됨 (검증판 29.1.3) | `docker version --format '{{.Server.Version}}'` |
| **컨테이너 GPU 패스스루** | 컨테이너 안에서 GPU 가 보일 것 | `docker run --rm --gpus all nvidia/cuda:13.0.1-runtime-ubuntu24.04 nvidia-smi -L` |
| 디스크 | 최소 20GB 여유 (이미지 8.06GB + 빌드 중간층) | `LC_ALL=C df -h /` |

마지막 줄이 실패하면 `nvidia-container-toolkit` 이 없거나 Docker 런타임 등록이 안 된 것이다.
**이걸 고치기 전에 이미지를 만들어 봐야 소용없다.** 빌드는 성공하고 실행만 실패한다.

---

## 3. 빌드

빌드는 **DGX Spark 호스트에서** 한다(aarch64 이미지라 x86 장비에서 구우면 안 된다). 그 호스트에는
이 저장소가 이미 clone 돼 있다 — `~/llm_from_scratch/tw2`.

```bash
cd ~/llm_from_scratch/tw2/contents/training/llm-from-scratch/_golden-image
bash build.sh                # 사전조건 검사 → 빌드 → 수락 시험까지 한 번에
bash build.sh --no-cache     # 캐시 없이 처음부터 (재현성 확인용)
TAG=llm-course:v1-test bash build.sh   # 기존 v1 을 건드리지 않고 시험 빌드
```

스크립트를 안 쓰고 직접 할 때:

```bash
docker build -t llm-course:v1 -f Dockerfile.llm-course-v1 .
docker run --rm --gpus all --ipc=host \
  -v "$PWD/smoke_test.py:/work/smoke_test.py:ro" \
  llm-course:v1 python3 /work/smoke_test.py
```

**실측 소요(DGX Spark, 캐시 없음)** — apt 50s + torch 89s + 나머지 pip 22s + export 9s ≈ **약 3분**,
결과 이미지 **8.06GB**. 네트워크가 느리면 torch 층(cu130 휠 + CUDA 라이브러리 약 3GB)이 지배한다.

---

## 4. Dockerfile 을 이렇게 쓴 이유

정본은 `_golden-image/Dockerfile.llm-course-v1`. 각 층의 근거만 정리한다.

| 층 | 내용 | 왜 이것이어야 하는가 |
|---|---|---|
| 베이스 | `nvidia/cuda:13.0.1-runtime-ubuntu24.04` | 호스트 드라이버 580.x / CUDA 13.0 과 정합. `devel` 이 아닌 `runtime` 으로 충분하다(교재는 커스텀 CUDA 커널을 컴파일하지 않는다) — `devel` 을 쓰면 이미지가 배 이상 커진다 |
| python | 3.12 (Ubuntu 24.04 시스템 python) | torch cu130 의 **cp312 aarch64** 휠과 정확히 일치. conda/pyenv 로 다른 버전을 깔면 맞는 휠이 없다 |
| torch | `torch==2.9.1+cu130`, `--index-url .../whl/cu130` | 인덱스를 안 바꾸면 CUDA 없는 휠이 설치되고 `torch.cuda.is_available()` 가 `False` 가 된다. **이 한 줄이 이 이미지의 존재 이유다** |
| 실습 패키지 | tiktoken(2주) · matplotlib(4·6·9·10·11·13주) · pandas(11주) · pytest(전주차) · numpy · requests/tqdm(10·11·12주) · jupyter/nbconvert(1주 스모크) | 주차별 필요에서 역산한 최소 집합 |
| 한글 폰트 | `fonts-nanum` + `fonts-nanum-coding` + `fc-cache -fv` | 없으면 그래프 한글 라벨이 전부 `□` |
| `MATPLOTLIBRC` | `/opt/mplconfig/matplotlibrc` (backend Agg, font.family NanumGothic, axes.unicode_minus False) | 폰트만 깔면 matplotlib 이 자동으로 쓰지 않는다. **패키지 기본 matplotlibrc 를 직접 고치면 `Duplicate key` 경고가 나므로** 별도 파일 + 환경변수로 지정한다. `axes.unicode_minus: False` 는 나눔폰트에 유니코드 마이너스 글리프가 없어 음수 축이 깨지는 것을 막는다 |
| `MPLCONFIGDIR=/tmp/mplcache` | 캐시 경로 | 홈이 없는 컨테이너 사용자에서 나는 캐시 경고 제거 |
| `WORKDIR /work` | 마운트 지점과 일치 | 학생이 `docker exec` 로 들어오면 바로 작업 디렉토리 |

> **버전을 임의로 올리지 말 것.** 교재 전 주차의 기대 숫자가 이 조합에서 나왔다. 올려야 한다면
> §7 의 절차를 밟는다.

---

## 5. 수락 시험 — 무엇을 통과해야 배포하는가

`smoke_test.py` 가 5개 구획을 검사한다. 하나라도 `FAIL` 이면 배포하지 않는다.

| 구획 | 내용 |
|---|---|
| ① 런타임 신원 | `aarch64` / torch `2.9.1+cu130` / `cuda.is_available() == True` / `NVIDIA GB10` |
| ② GPU 12연산 | matmul · embedding · layernorm · softmax · gelu(tanh) · dropout · cross_entropy · backward · adamw · bf16 autocast · multinomial · topk — 교재 15주가 실제로 쓰는 연산 전수 |
| ③ 한글 렌더 | `font.family` 가 NanumGothic 으로 **해석되는지**(폰트 설치만이 아니라) + 한글 라벨 `savefig` 실행 |
| ④ 실습 패키지 | tiktoken/pandas/numpy/pytest/requests/tqdm/nbconvert 임포트 |
| ⑤ **의도적 부재** | `tensorflow` 가 **없어야** 통과 (§6) |

마지막 줄에 `SMOKE_OK` 가 나오면 합격이다.

### 🔶 반드시 알고 있어야 할 경고 — sm_121 PTX JIT

컨테이너 안에서 torch 를 처음 쓰면 이 경고가 뜬다. **정상이다.**

```
UserWarning: Found GPU0 NVIDIA GB10 which is of cuda capability 12.1.
    Minimum and Maximum cuda capability supported by this version of PyTorch is (8.0) - (12.0)
```

GB10 의 compute capability 는 **12.1(sm_121)** 인데 torch 2.9.1+cu130 바이너리의 arch 목록은
`['sm_80','sm_90','sm_100','sm_110','sm_120','compute_120']` 로 sm_120 까지다. 마지막의
`compute_120` 은 **PTX 중간표현**이라, 실행 시 드라이버가 sm_121 용으로 JIT 컴파일해 돌린다.
그래서 결과는 정확하고 성능도 정상이다. 첫 커널 실행이 조금 느린 것이 유일한 대가다.

> torch 2.13.0+cu130 도 확인했으나 arch 목록은 동일했다(네이티브 sm_121 없음). 그래서 15주
> 전수 검증이 끝난 **2.9.1 을 유지**한다.

학생이 이 경고를 보고 "환경이 잘못됐다"고 판단해 버전을 올리기 시작하는 것이 1주차의 대표적
사고다. 강의 부록 A 와 W01 트러블슈팅에 같은 설명을 넣어 뒀다.

---

## 6. 일부러 넣지 않은 것 — `tensorflow`

넣으면 **10주차 미션이 무력화된다.**

10주차 P10-5 는 OpenAI GPT-2 가중치를 학생이 만든 `GPTModel` 에 이식하는 미션이고, 배워야 할
것은 (a) 한 텐서에 붙어 있는 QKV 를 `torch.chunk` 로 3분할, (b) TF 규약 `(입력,출력)` → PyTorch
`nn.Linear` `(출력,입력)` 전치다. 교재 저장소의 1차 경로
(`ch05/01_main-chapter-code/gpt_download.py`)는 `import tensorflow` 로 시작하는데, 이 환경에
TF 가 없어 실패한다. **그 실패를 겪고 safetensors 경로로 갈아타는 것이 미션의 일부다.**
편의로 TF 를 넣어 버리면 그 학습이 사라진다. `smoke_test.py` 구획 ⑤ 가 이걸 지킨다.

### ⚠️ `safetensors` — 알려진 공백

10주차의 정답 경로(safetensors)에 필요한 `safetensors` 패키지가 **이미지에 없다.** 15주 검증
당시 컨테이너 안에서 수동 설치해 진행했다. 조교는 둘 중 하나를 택한다.

| 선택 | 방법 | 영향 |
|---|---|---|
| **A. 그때 설치** (검증된 상태 유지) | 10주차 실습 안내에 `docker exec llm-lab pip install safetensors` 한 줄 추가 | 이미지 불변 → v1 재검증 불필요. **권장** |
| B. 이미지에 포함 | Dockerfile 2번 pip 층에 `safetensors` 추가 후 `v1.1` 로 태그 | §7 절차(전 주차 재검증) 필요 |

어느 쪽이든 **`tensorflow` 는 넣지 않는다.**

---

## 7. 버전을 올려야 할 때 (v1 → v2)

1. `_golden-image/Dockerfile.llm-course-v1` 를 복사해 `Dockerfile.llm-course-v2` 로 만들고 변경.
2. `TAG=llm-course:v2 bash build.sh --no-cache` → `SMOKE_OK` 확인.
3. **숫자가 바뀌는지 확인** — 최소 다음 게이트를 v2 컨테이너에서 재실행한다.
   `_source/harness/ANSWERKEY.md` 의 W02(토큰 4,690) · W09(파라미터 163,009,536) ·
   W11(훈련 가능 7,090,946) · W13(저지 점수 평균). 하나라도 달라지면 해당 주차 교재 수치를
   함께 고쳐야 한다.
4. 강의/실습의 버전 표기 동시 수정 — `lecture_week01.md`(§4.1, 부록 A), `lab_week01.yaml`
   (prerequisites, order 4), 이 문서.
5. 학기 중에는 올리지 않는다. 학생마다 이미지가 달라지는 순간 채점 기준이 무너진다.

---

## 8. 배포

### 학생 계정이 같은 호스트를 쓰는 경우 (DGX 공용)
이미지는 Docker 데몬 전역에 있으므로 **빌드 한 번이면 끝이다.** 학생은 `docker images` 로 확인만
한다(W01 order 4). 학생을 `docker` 그룹에 넣어 주면 된다.

### 장비가 여러 대인 경우
```bash
# 만든 호스트에서
docker save llm-course:v1 | gzip -1 > llm-course-v1.tar.gz

# 받는 호스트에서
gunzip -c llm-course-v1.tar.gz | docker load
docker images llm-course:v1     # 확인
```
`gzip -1` 이면 8.06GB 이미지가 **5.08GB**(실측) 로 줄고, 압축이 전송보다 빨라 파이프가 안 막힌다.
장비가 여럿이면 사내 레지스트리(`docker tag … && docker push`)가 편하지만, 검증한 경로는 위의
`save/load` 다.

---

## 9. 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| `torch.cuda.is_available()` 가 `False` | ①~④ 중 어디서 끊겼는지 먼저 특정 | 계층별 진단: ① 호스트 `nvidia-smi` ② `docker run` 에 `--gpus all` ③ 컨테이너 안 `nvidia-smi` ④ `torch.version.cuda` 가 `None` 이면 CPU 휠 |
| `torch.version.cuda` 가 `None` | cu130 인덱스를 안 썼다 | `pip install --index-url https://download.pytorch.org/whl/cu130 torch==2.9.1+cu130` — 캐시 남았으면 `--no-cache` 로 재빌드 |
| 빌드 중 torch 휠 `No matching distribution` | python 이 3.12 가 아니다 | 베이스를 `ubuntu24.04` 태그로 되돌린다. 22.04(py3.10)에는 맞는 휠이 없다 |
| 컨테이너 안 `nvidia-smi` 실패 | `nvidia-container-toolkit` 미설치/미등록 | 호스트에 설치 후 `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| 그래프 한글이 `□` | 폰트 없음 또는 `MATPLOTLIBRC` 미적용 | 컨테이너에서 `python3 -c "import matplotlib;print(matplotlib.rcParams['font.family'])"` → `['NanumGothic']` 이어야 |
| `Duplicate key in file … matplotlibrc` | 패키지 기본 matplotlibrc 를 직접 수정 | 별도 파일 + `MATPLOTLIBRC` 방식으로 되돌린다(정본 Dockerfile 3번 층) |
| 3주차 이후 DataLoader `Bus error` | `--ipc=host` 누락 → 공유메모리 부족 | `docker rm -f llm-lab` 후 `--ipc=host` 를 붙여 재기동 |
| `cuda capability 12.1 … (8.0)-(12.0)` 경고 | GB10 sm_121, torch 는 sm_120 까지 | **정상.** PTX JIT 로 실행된다(§5). 버전 올리지 말 것 |
| `ModuleNotFoundError: tensorflow` (10주차) | **의도된 상태** | safetensors 경로로 전환 — 미션의 일부다(§6) |
| `ModuleNotFoundError: safetensors` (10주차) | 이미지 미포함 | `docker exec llm-lab pip install safetensors` (§6) |
| 컨테이너 지웠더니 코드가 사라짐 | 볼륨 마운트 누락 | `-v ~/work:/work` 필수. 컨테이너는 언제든 버릴 수 있어야 한다 |

---

## 10. 검증 기록

| 일자 | 장비 | 내용 | 결과 |
|---|---|---|---|
| 2026-08-07 | DGX Spark `spark-1397` (GB10, aarch64, 드라이버 580.126.09, Docker 29.1.3) | 이 문서의 절차대로 `--no-cache` 전체 재빌드 → `build.sh` 수락 시험 | **SMOKE_OK** — 8.06GB, 최초 v1 과 패키지 버전 전부 일치(torch 2.9.1+cu130 / tiktoken 0.13.0 / matplotlib 3.11.1 / pandas 3.0.5 / numpy 2.5.1 / pytest 9.1.1 / nbconvert 7.17.1) |
| (최초) | 동일 장비 | 15주 전수 검증 — 게이트 157개 | PASS 142 / FAIL 13 / GATED 2, `_source/harness/FINAL_REPORT.md` |
