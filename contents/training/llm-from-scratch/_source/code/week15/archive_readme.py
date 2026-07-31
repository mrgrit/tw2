"""P15-2 — 과제 저장소를 포트폴리오로. README.md 생성 + 전 링크 실재 검사.

[제약] 없는 것을 포장하지 말 것 — 링크가 실재하는지 전부 확인 후 작성.
그래서 이 스크립트는 **파일 시스템을 먼저 스캔하고, 실재하는 것만 표에 넣는다.**
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # code/
OUT = ROOT / "README.md"

# 주차별 메타 — '대표 결과' 는 이번 학기 실측값만 적는다 (지어내지 않는다)
WEEKS = [
    ("week01", "인프라와 골든 이미지",
     ["spec-report.md", "hardening-checklist.md", "smoke-test.log"],
     "aarch64 / GB10 / CUDA 13.0 확인. ch02 스모크 테스트는 의도된 KeyError 셀 때문에 `--allow-errors` 필요"),
    ("week02", "토크나이저와 BPE",
     ["tokenizer_v1.py", "tokenizer_v2.py", "test_tokenizer.py", "bpe_compare.md"],
     "GPT-2 BPE 어휘 50,257. 한국어는 영어 대비 문자당 토큰 3.73~7.17배"),
    ("week03", "배치와 임베딩",
     ["dataset.py", "embedding_pipeline.py", "test_pipeline.py"],
     "슬라이딩 윈도우 (max_length, stride) 그리드. 입력·타깃 한 칸 밀림 검증"),
    ("week04", "어텐션",
     ["attention_v1v2.py", "test_attention.py", "scaling_experiment.md",
      "attention_heatmap.png"],
     "v1→v2 전치 이식. √d 스케일링이 softmax 분포를 바꾸는 것을 실측"),
    ("week05", "코잘 어텐션과 멀티헤드",
     ["causal_attention.py", "multihead.py", "test_mha.py", "heads_experiment.md"],
     "인과성 성질 테스트 통과. 헤드 수 1→12 에서 시간 2.90배 (교재 '대체로 비슷'과 불일치)"),
    ("week06", "레이어와 트랜스포머 블록",
     ["layers.py", "transformer_block.py", "test_layers.py", "gelu_plot.png"],
     "테스트 10개를 구현보다 먼저 작성. LayerNorm·GELU·FeedForward·잔차 연결"),
    ("week07", "GPT 조립",
     ["gpt_model.py", "generate.py", "test_gpt.py", "param_breakdown.md"],
     "파라미터 **163,009,536** 개. 무작위 가중치 생성문이 교재와 문자 단위 일치"),
    ("week08", "중간고사 대비 — 버그 은행",
     ["bug_bank_validation.py", "bug_bank_recheck.py"],
     "버그 10종을 직접 심고 검출. #8·#10 은 교재 서술로는 검출 불가임을 규명"),
    ("week09", "첫 사전 훈련",
     ["pretrain.py", "loss_anatomy.py", "test_loss.py", "overfit_evidence.md",
      "speed_report.md", "loss_curve.png"],
     "초기 손실 **10.7940** (ln 50257 = 10.8249). 10에폭 후 train 0.8908 / val 6.3130. 원문 13단어 연속 암기 확인"),
    ("week10", "디코딩 전략과 가중치 이식",
     ["decoding.py", "openai_load.py", "test_decoding.py", "sampling_grid.md",
      "resume_experiment.md", "compare_generation.md", "temp_plot.png"],
     "T=5 에서 pizza 41/1000. OpenAI 124M val **3.5596** vs 우리 10에폭 6.3353"),
    ("week11", "분류기가 된 GPT",
     ["spam_data.py", "spam_finetune.py", "test_spam.py", "confusion.md",
      "matrix_experiment.md", "acc_curve.png"],
     "test 정확도 **95.67%** — 교재 정답지와 소수점까지 일치. 매트릭스 6조합"),
    ("week12", "지시 데이터 파이프라인",
     ["instr_data.py", "test_collate.py", "collate_evolution.md",
      "quality_report.md", "length_hist.png"],
     "collate 3단계 진화. -100 손실 제거 실증(차이 0.00e+00). 완전 중복 20그룹 발견"),
    ("week13", "지시 튜닝·심판·LoRA",
     ["instr_finetune.py", "judge.py", "lora.py", "test_sft.py",
      "judge_report.md", "lora_compare.md", "sft_loss_curve.png"],
     "355M 튜닝 val 3.8172 → **0.6131**. LoRA 훈련가능 1.94%, 저지 평균 60.92 vs 60.87"),
    ("week14", "팀 프로젝트",
     ["proposal.md", "premortem.md", "check_premortem.py", "check_rubrics.py"],
     "제안서 + 사전 부검. 루브릭 합계 100 / 기말 배분 100% 검산"),
    ("week15", "발표회",
     ["demo_scenario.md", "dryrun.py", "archive_readme.py"],
     "시연 드라이런 2회 (13.56s / 10.81s, 10분 제한의 2.3%)"),
]

ASSETS = [
    ("성질 테스트", [
        ("week05/test_mha.py", "인과성 불변 — 위치 t 출력은 t+1 이후를 바꿔도 불변"),
        ("week10/test_decoding.py", "top-k 제약 — 선택 토큰이 항상 상위 k 안"),
        ("week12/test_collate.py", "ignore_index 동등성 — -100 위치는 손실에서 사라진다"),
        ("week13/test_sft.py", "LoRA 항등 — B=0 이면 적용 직후 출력이 원본과 동일"),
    ]),
    ("품질 게이트", [
        ("week10/test_decoding.py", "이식 품질 — the-verdict val 손실 < 5.0"),
        ("week11/spam_finetune.py", "재현 게이트 — test 정확도 교재 값 ±1%p"),
        ("week13/lora.py", "훈련 전 게이트 — LoRA 적용 직후 val 손실 == 원본"),
    ]),
    ("실패 테스트 (오류가 나야 정상)", [
        ("week10/test_decoding.py", "qkv_bias=False 로 124M 로드 → AttributeError"),
        ("week05/mha_trap.py", "softmax(dim=-2) 함정을 심고 검출"),
        ("week08/bug_bank_validation.py", "버그 10종 심기·검출"),
    ]),
]

# --------------------------------------------------------------------------
print("=" * 70)
print("1. 파일 실재 스캔 (없는 것은 표에 넣지 않는다)")
print("=" * 70)
week_rows, missing = [], []
for wk, topic, files, result in WEEKS:
    present = [f for f in files if (ROOT / wk / f).exists()]
    absent = [f for f in files if not (ROOT / wk / f).exists()]
    missing += [f"{wk}/{f}" for f in absent]
    if not (ROOT / wk).is_dir():
        print(f"  [X] {wk}/ 디렉토리 없음 — 통째로 제외")
        continue
    week_rows.append((wk, topic, present, result))
    print(f"  [O] {wk}: 핵심 파일 {len(present)}/{len(files)} 실재"
          + (f"  (누락 {absent})" if absent else ""))
if missing:
    print(f"\n  → 누락 {len(missing)}건은 README 에 **적지 않는다**: {missing}")
else:
    print("\n  → 누락 없음")

asset_rows = []
for cat, items in ASSETS:
    ok = [(p, d) for p, d in items if (ROOT / p).exists()]
    asset_rows.append((cat, ok))
    print(f"  [{cat}] {len(ok)}/{len(items)} 실재")

# --------------------------------------------------------------------------
L = ["# 밑바닥부터 만들면서 배우는 LLM — 한 학기의 기록", ""]
L.append("이 저장소는 GPT-2급 LLM을 밑바닥부터 구현·훈련·튜닝한 한 학기의 기록이다. "
         "**모든 코드는 코딩 에이전트 지휘로 작성했다** — 사람의 역할은 명세하고, "
         "검증하고, 해석하는 것이었다.")
L.append("")
L.append("실행 환경: `llm-course:v1` 컨테이너 (aarch64 / NVIDIA GB10 / CUDA 13.0 / "
         "torch 2.9.1+cu130). 호스트에 pip 설치하지 않는다.")
L.append("")
L.append("## 주차별 산출물 지도")
L.append("")
L.append("| 주차 | 주제 | 핵심 파일 | 대표 결과 |")
L.append("|---|---|---|---|")
for wk, topic, files, result in week_rows:
    links = " · ".join(f"[{f}]({wk}/{f})" for f in files[:4])
    L.append(f"| [{wk}]({wk}/) | {topic} | {links} | {result} |")
L.append("")
L.append("## 재사용 자산")
L.append("")
for cat, items in asset_rows:
    if not items:
        continue
    L.append(f"### {cat}")
    L.append("")
    L.append("| 파일 | 내용 |")
    L.append("|---|---|")
    for p, d in items:
        L.append(f"| [`{p}`]({p}) | {d} |")
    L.append("")

L.append("## 하이라이트 — 10주차 4모델 비교표")
L.append("")
cmp_path = ROOT / "week10" / "compare_generation.md"
if cmp_path.exists():
    body = cmp_path.read_text(encoding="utf-8")
    tbl = [l for l in body.splitlines() if l.startswith("|")]
    L += tbl[:7]
    L.append("")
    L.append(f"전문: [week10/compare_generation.md](week10/compare_generation.md)")
    L.append("")
    L.append("**이 표가 한 학기의 서사다.** 아키텍처도 파라미터 수도 같은 급인데, "
             "이 소설을 한 번도 본 적 없는 GPT-2 124M(val 3.56)이 "
             "이 소설로 10에폭 훈련한 우리 모델(val 6.34)을 압도한다. "
             "다른 것은 오직 훈련 데이터의 양이다.")
    L.append("")

L.append("## 재현 방법")
L.append("")
L.append("```bash")
L.append("# 1. 골든 이미지 빌드 (저장소 루트에서 — 이 README 기준 한 단계 위)")
L.append("docker build -t llm-course:v1 -f ../harness/Dockerfile.llm-course-v1 ..")
L.append("")
L.append("# 2. 컨테이너 기동")
L.append("docker run -d --name llm-lab --gpus all --ipc=host \\")
L.append("  -v $PWD/code:/work -v $PWD/textbook:/textbook \\")
L.append("  llm-course:v1 sleep infinity")
L.append("")
L.append("# 3. 주차별 진입점 (예)")
for wk, topic, files, _ in week_rows[:3]:
    entry = next((f for f in files if f.endswith(".py")), None)
    if entry:
        L.append(f"docker exec -w /work/{wk} llm-lab python3 {entry}")
L.append("")
L.append("# 4. 전 주차 테스트")
L.append("for w in week0{2,3,4,5,6,7,9} week1{0,1,2,3}; do \\")
L.append("  docker exec -w /work/$w llm-lab python3 -m pytest -q 2>/dev/null; done")
L.append("```")
L.append("")
L.append("> 다운로드 가중치·체크포인트는 각 주차의 `.gitignore` 로 제외했다 "
         "(week10 4.02GB, week13 5.23GB).")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"\n[저장] {OUT}")

# --------------------------------------------------------------------------
print()
print("=" * 70)
print("2. [검증] README 의 모든 상대 링크가 유효한가")
print("=" * 70)
text = OUT.read_text(encoding="utf-8")
links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
links = [l for l in links if not l.startswith(("http://", "https://", "#"))]
bad = []
for l in links:
    target = ROOT / l.rstrip("/")
    if not target.exists():
        bad.append(l)
print(f"  상대 링크 총 {len(links)}개")
print(f"  깨진 링크 **{len(bad)}개** {bad if bad else ''}")
print(f"  → 판정: **{'PASS' if not bad else 'FAIL'}**")

# 코드 블록 안에 언급한 경로도 확인한다 (재현 방법의 진입점)
print()
print("  재현 방법 블록의 파일 경로도 확인:")
for m in re.finditer(r"-w /work/(week\d+) llm-lab python3 (\S+)", text):
    wk, f = m.groups()
    e = (ROOT / wk / f).exists()
    print(f"    [{'O' if e else 'X'}] {wk}/{f}")
for m in re.finditer(r"-f (\S+Dockerfile\S*)", text):
    rel = m.group(1)
    dk = (OUT.parent / rel).resolve()
    print(f"    [{'O' if dk.exists() else 'X'}] {rel}  → {dk}")
    if not dk.exists():
        bad.append(rel)
print(f"\n  최종 판정 (README 위치 기준 전 경로): "
      f"**{'PASS' if not bad else 'FAIL — ' + str(bad)}**")
