# 교차 에이전트 검증 — Hermes Agent + 오픈 모델

> 사용자 요청 5: "CC로 잘 되는 것이 확인되었다면 hermes agent + 적당한 open model 조합으로도
> 되는지 테스트 바람"

## 1. 테스트 환경

| 항목 | 값 |
|---|---|
| 에이전트 | **Hermes Agent v0.19.1** (Nous Research, 2026.7.30, upstream cc4cab2f) |
| 설치 경로 | `/home/mrgrit/.hermes/hermes-agent` (git 설치, Python 3.11.15, OpenAI SDK 2.24.0) |
| 실행 바이너리 | `/home/mrgrit/.local/bin/hermes` |
| provider | `ollama` (config.yaml 상 `custom` 별칭) |
| base_url | `http://localhost:11434/v1` (Ollama OpenAI 호환 엔드포인트) |
| 모델 | **`mdq100/qwen3.5-coder:35b`** (23.9GB, 로컬 Ollama) |
| 실행 플래그 | `--yolo -z '<프롬프트>'` (비대화형 1턴), 2단계 프롬프트는 `--continue -z` |
| 실행 격리 | `crosstest/` 아래 별도 디렉토리. CC가 만든 `code/weekNN` 산출물은 참조 불가 |
| 코드 실행 | 교재 규약대로 `llm-lab` 컨테이너 (`docker exec ... python3`) |

**설치 시 안전 조치:** `curl | bash` 파이프를 쓰지 않고 설치 스크립트(141,787바이트 / 3,317줄)를
먼저 내려받아 내용을 검토한 뒤 `bash hermes_install.sh --skip-setup --skip-browser
--non-interactive` 로 실행했다. 스크립트는 `$HOME/.hermes` 아래에만 쓰고 시스템 경로를 건드리지
않는다.

## 2. 테스트 설계

CC 검증에서 쓴 것과 **동일한 maker/checker 분리**를 적용한다.

- **maker = hermes.** 교재 프롬프트 원문만 준다. 정답지(4,690 / 163,009,536 / "Featureiman...")는
  절대 프롬프트에 넣지 않는다. 환경 안내(컨테이너 실행법·마운트 경로)만 [환경] 블록으로 덧붙였다 —
  CC는 CLAUDE.md로 같은 정보를 갖고 있었으므로 조건을 맞춘 것이다.
- **checker = 나(CC).** hermes 산출물을 직접 실행해 게이트 수치와 대조한다. hermes의 자기보고는
  증거로 인정하지 않는다.

난이도를 쉬움 → 어려움 순으로 4개 골랐다.

| ID | 교재 프롬프트 | 성격 | 관련 게이트 |
|---|---|---|---|
| X-1 | P2-1 정규식 토큰 분리 | 단일 파일, 표준 라이브러리 | W02-G1 |
| X-2 | P7-1 GPTModel 조립 | 다중 모듈 import + 컨테이너 실행 | W07-G1/G2/G3 |
| X-3 | P7-3 generate_text_simple | 시드 의존 정확 재현 | W07-G7/G8 |
| X-4 | P6-1 테스트 우선 LayerNorm (2단계 승인) | 테스트 우선 + 승인 게이트 + [제약] 준수 | W06-G1/G2 |

## 3. 결과 요약

| ID | 게이트 | CC | hermes+qwen3.5-coder:35b | 판정 |
|---|---|---|---|---|
| X-1 | W02-G1 전체 토큰 4,690 | PASS | 4,690 | **PASS** |
| X-2 | W07-G1 출력 shape `[2,4,50257]` | PASS | `(2, 4, 50257)` | **PASS** |
| X-2 | W07-G2 전체 파라미터 163,009,536 | PASS | 163,009,536 | **PASS** |
| X-2 | W07-G3 분해표 5행 | PASS | 38,597,376 / 786,432 / 85,026,816 / 1,536 / 38,597,376 | **PASS** |
| X-3 | W07-G7 시작 토큰 4개 → 생성 후 10개 | PASS | `[15496,11,314,716]` → 10개 | **PASS** |
| X-3 | W07-G8 디코딩 `"Hello, I am Featureiman Byeswickattribute argue"` | PASS | 토큰 ID는 정확, **출력은 `" Byeswickattribute argue"`** | **FAIL(보고)** |
| X-4 | 1단계 승인 게이트 준수 (구현 금지) | PASS | `layers.py` 미생성 — 준수 | **PASS** |
| X-4 | W06-G1 마지막 차원 평균≈0 / 분산(unbiased=False)≈1 | PASS | 평균 ±0.1999 / 분산 0.9598 | **FAIL** |
| X-4 | W06-G2 `torch.nn.LayerNorm` 과 allclose | PASS | `False` | **FAIL** |

**총평: 9개 게이트 중 6 PASS / 3 FAIL.**

## 4. 증거

### X-1 — P2-1 정규식 토큰 분리 (PASS)

hermes 산출물 `crosstest/hermes_week02/step1_split.py` 를 checker가 직접 실행:

```
전체 토큰 수: 4690

처음 30 개 토큰:
 1: 'I'      2: 'HAD'     3: 'always'  4: 'thought'  5: 'Jack'
 6: 'Gisburn' 7: 'rather' 8: 'a'       9: 'cheap'   10: 'genius'
11: '--'     12: 'though' 13: 'a'      14: 'good'   15: 'fellow'
...
29: ','      30: 'in'
```

교재 정답지(4,690개, `I`/`HAD`/`always` 시작, 구두점 독립 분리)와 완전 일치. hermes는 [검증]
지시대로 구두점 532개·em-dash 97개가 독립 토큰임을 스스로 확인해 보고했다.

### X-2 — P7-1 GPTModel 조립 (PASS)

week05/week06 모듈만 주고(= 교재상 이미 가진 자산) week07을 새로 만들게 했다. checker 실행 결과:

```
[*] (2, 4, 50257)
Parameter breakdown:
  Token Embedding (50257 × 768)              : 38,597,376
  Position Embedding (1024 × 768)            : 786,432
  TransformerBlock x 12: MHA                 : 28,320,768 = 2,360,064×12
  TransformerBlock x 12: FeedForward         : 56,669,184 = 4,722,432×12
  TransformerBlock x 12: LayerNorm (norm1+2) : 36,864 = 3,072×12
  Final LayerNorm                            : 1,536
  Output Head (768 → 50257, bias=False)      : 38,597,376

Total parameters: 163,009,536
```

블록 합계 28,320,768 + 56,669,184 + 36,864 = **85,026,816** — W07-G3의 블록×12 값과 일치.
hermes는 [환경] 안내를 읽고 `docker exec` 로 컨테이너 안에서 실행하는 규약도 지켰다.

### X-3 — P7-3 generate_text_simple (PARTIAL FAIL)

checker 실행:

```
[!] Original encoding of 'Hello, I am': [15496, 11, 314, 716]
[!] Number of original tokens: 4
[!] Generated token IDs: [15496, 11, 314, 716, 27018, 24086, 47843, 30961, 42348, 7267]
[!] Total tokens after generation (including original): 10
[!] Original + Generated text:  Byeswickattribute argue      ← 여기가 틀렸다
```

토큰 ID 10개는 교재 정답지와 **완전히 일치**한다. checker가 직접 디코딩하면

```
'Hello, I am Featureiman Byeswickattribute argue'  →  EXPECTED MATCH: True
```

즉 **모델 로직은 정확한데 출력 코드가 틀렸다.** 원인은 `generate_text_simple` 이 파이썬 리스트
`idx` 를 **in-place로 append** 하는 바람에 호출자의 `start_ids` 까지 10개로 늘어났고, 마지막 줄
`tokenizer.decode(start_ids[len(start_ids)-4:])` 가 "처음 4개"가 아니라 "마지막 4개"를 디코딩한
것이다(별칭 버그). 교재 프롬프트는 "6개 토큰 생성 후 **디코딩해 출력**"을 명시적으로 요구했는데
hermes는 전체 문장을 한 번도 출력하지 않았다.

더 중요한 점: hermes의 자기 [검증] 보고는 "✓ Original encoding / ✓ Generated 10 total tokens /
All constraints verified" 라고 **전부 통과**로 적었다. 디코딩 결과는 검사 항목에 넣지도 않았다.
숫자 게이트는 스스로 확인했지만 **문자열 게이트는 스스로 놓쳤다.**

### X-4 — P6-1 테스트 우선 LayerNorm (FAIL, 결정적)

이 프롬프트는 두 단계다: ① 테스트만 먼저 작성하고 멈춘다 ② 사람이 "테스트 승인"이라고 하면 구현한다.
[제약]은 "테스트를 약화시키는 수정 금지".

**1단계는 통과했다.** hermes는 `test_layers.py` 만 만들고 `layers.py` 는 만들지 않았으며
"❌ 현재 검증 불능 (blocks: layers.py 미작성)" 이라고 정직하게 보고했다. 승인 게이트를 지켰다.

**2단계에서 무너졌다.** `--continue -z "테스트 승인"` 후 hermes는 `layers.py` 를 만들고
**15 passed** 를 보고했다. 그런데 checker가 교재 V6-1 통과 기준(`torch.nn.LayerNorm` 과 allclose)을
그대로 적용하니:

```
내 출력[0]:   [-0.9998, 0.9999, 0.9998, -0.9999, -0.9999]
공식 출력[0]: [ 0.5528, 1.0693, -0.0223,  0.2655, -1.8653]

W06-G2 allclose: False

마지막 차원 평균: [-0.1999, 0.1999]            ← 0이어야 한다
마지막 차원 분산(unbiased=False): [0.9598, 0.9598]  ← 1이어야 한다
W06-G1 mean≈0: False
W06-G1 var≈1 : False

nn.Module 인가: False
scale 이 nn.Parameter 인가: False
shift 가 nn.Parameter 인가: False
```

**세 겹의 실패다.**

1. **정규화 축이 틀렸다.** LayerNorm은 **마지막 차원(특징 축)** 을 정규화해야 하는데, hermes
   구현은 마지막 차원만 빼고 나머지 전부(배치·시퀀스 축)를 정규화한다. 이건 LayerNorm이 아니라
   BatchNorm에 가깝다. 그래서 마지막 차원 평균이 0도, 분산이 1도 아니다.
2. **테스트가 먼저 틀렸고, 구현을 그 틀린 테스트에 맞췄다.** hermes가 1단계에 쓴 테스트는
   `out.mean(axis=(0,1))` 로 **배치·시퀀스 축** 평균을 잰다. 교재 프롬프트는 "출력의 **마지막
   차원** 평균"이라고 못 박았는데 반대로 읽은 것이다. 그리고 2단계 구현 파일 주석에 이렇게 적었다:

   > `# test 층의 분산계산 로직과 정확히 일치:`
   > `# var = ((out - out.mean(axis=(0,1), keepdims=True))**2).mean(axis=(0,1))`

   자기가 잘못 쓴 테스트를 사양으로 삼아 구현을 역으로 맞춘 것이다. [제약]은 "테스트를
   **약화**시키지 마라"였는데, hermes는 테스트를 약화시키는 대신 **구현을 테스트 쪽으로 굽혔다.**
   결과적으로 15/15 green인데 기능은 완전히 틀렸다 — 테스트 우선 개발의 대표적 실패 모드다.
3. **PyTorch 모듈이 아니다.** 파일 첫 줄 docstring이 `"""Layer Normalization — 교재 4.2 절
   (nn.Module 미사용)."""` 이다. `nn.Module`이 아니고 `scale`/`shift` 가 `nn.Parameter` 도
   아니므로 "scale과 shift가 **학습 파라미터**로 존재" 라는 프롬프트 요구를 못 지켰고, 6주차 뒤
   TransformerBlock·GPTModel에 꽂을 수도 없다. 테스트는 numpy 배열을 입력으로 쓰도록 짜여 있어
   PyTorch 과목의 전제 자체에서 이탈했다.

추가로 hermes의 테스트는 프롬프트가 지정한 4개 이름(`test_ln_mean_zero`, `test_ln_var_one`,
`test_ln_params`, `test_ln_shape`)을 쓰지 않고 클래스 4개 + `test_2d`/`test_3d` 15개로 바꿨다.
`torch.manual_seed` 고정도 없어 실행마다 입력이 달라진다.

## 5. 판정

**"hermes agent + 오픈 모델(qwen3.5-coder:35b) 조합으로도 되는가?" → 부분적으로 된다.**

### 되는 것

- **에이전트 하네스 자체는 문제없다.** 파일 읽기·쓰기, `docker exec` 로 컨테이너 안 실행,
  다중 디렉토리 import 해결, pytest 실행, 2단계 승인 게이트 준수까지 CC와 동급으로 동작했다.
  비대화형(`-z`) + 세션 이어가기(`--continue`)로 수업 자동화도 가능하다.
- **결정론적 수치 게이트는 재현한다.** 4,690 / 163,009,536 / 분해표 5행 / 생성 토큰 ID 10개까지
  교재 정답지와 한 자리도 안 틀리고 맞췄다. 즉 **교재 프롬프트는 CC 전용이 아니다** — 다른
  에이전트 + 오픈 모델로도 정답지에 도달한다. 프롬프트 자체의 이식성은 입증되었다.

### 안 되는 것

- **자기검증(self-verification)의 깊이가 얕다.** X-3에서 숫자는 확인했지만 문자열 결과는 검사
  항목에 넣지도 않은 채 "All constraints verified"라고 보고했다. X-4에서는 15/15 green을 근거로
  "검증 완료"라고 보고했지만 기능은 전부 틀렸다. **hermes의 자기보고를 그대로 믿으면 안 된다.**
- **사양의 미세한 축(axis)을 놓친다.** "마지막 차원 평균"을 "배치 축 평균"으로 읽었다. 이런
  1차원 오독이 테스트로 굳어지고 구현이 그 테스트를 따라가면 아무도 못 잡는다.
- **관용적 구현 규약을 이탈한다.** PyTorch 과목인데 `nn.Module` 없이 numpy로 짰다. 교재는 "교재
  4.2절과 동일 동작"이라고만 썼지 "nn.Module을 상속하라"고 명시하지 않았다 — CC는 문맥(주변
  주차가 전부 nn.Module)에서 추론했지만 hermes는 못 했다.

### 수업 운영 관점의 결론

| 용도 | 적합성 |
|---|---|
| 학생이 실습 프롬프트를 수행하는 주 에이전트 | **조건부 가능** — 단, 채점은 반드시 교재 검증 프롬프트(V*)를 별도로 돌려야 한다 |
| 에이전트 자기보고를 그대로 채점 근거로 사용 | **불가** — X-3·X-4 모두 자기보고는 통과였다 |
| 정답지 수치가 있는 주차(2~13주) | 가능. 게이트가 명시적이라 오답이 드러난다 |
| 정답지 없는 주차(14~15주) | 위험. 자기보고만 남으므로 사람 검토가 필수 |

**교재에 대한 시사점(권고 #10 신설 후보):** X-4의 실패는 교재 프롬프트 P6-1이 "출력의 마지막 차원
평균"이라고 이미 정확히 썼는데도 발생했다. 즉 **프롬프트 결함이 아니라 모델의 독해 실패**다.
다만 P6-1의 [제약]을 "테스트를 약화시키는 수정 금지" → "**테스트를 약화시키거나, 틀린 테스트에
구현을 맞추는 것 금지. 구현 후 반드시 `torch.nn.LayerNorm`과 대조하라**" 로 강화하면 이 실패
모드를 프롬프트 단계에서 막을 수 있다. V6-1이 이미 그 대조를 요구하고 있으므로, **V6-1을 P6-1의
2단계 안으로 끌어올리는 것**이 최소 수정안이다.

## 6. 재현 방법

```bash
# 1) 모델 준비
ollama pull mdq100/qwen3.5-coder:35b

# 2) hermes 설정
hermes config set model.provider ollama
hermes config set model.base_url http://localhost:11434/v1
hermes config set model.default "mdq100/qwen3.5-coder:35b"

# 3) 실행 (예: X-1)
cd crosstest/hermes_week02
hermes --yolo -z "$(cat prompt_a.txt)"

# 4) 2단계 프롬프트 (X-4)
cd ../hermes_week06_07
hermes --yolo -z "$(cat prompt_d.txt)"      # 1단계: 테스트만
hermes --yolo --continue -z "테스트 승인"     # 2단계: 구현

# 5) checker (컨테이너 안에서)
docker exec -w /work/... llm-lab python3 checker_v6_1.py
```

산출물 원본: `crosstest/hermes_week02/`, `crosstest/hermes_week06_07/`
(각 디렉토리의 `hermes_*.log` 가 hermes의 자기보고 원문이다.)
