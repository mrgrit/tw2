"""P15-1 — 시연 드라이런. 시나리오를 실제로 실행하며 단계별 소요 시간을 잰다."""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "week13"))

import common  # noqa: F401,E402
from common import WEEK10_WEIGHTS, device  # noqa: E402

import openai_load  # noqa: E402
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

import torch  # noqa: E402
import tiktoken  # noqa: E402

from common import text_to_token_ids, token_ids_to_text  # noqa: E402
from decoding import generate  # noqa: E402
from instr_data import format_input  # noqa: E402

W13 = Path(__file__).resolve().parent.parent / "week13"
DEMO = [
    {"instruction": "Convert the active sentence to passive: "
                    "'The chef cooks the meal every day.'", "input": ""},
    {"instruction": "What is the capital of France?", "input": ""},
    {"instruction": "Rewrite the sentence using a simile.",
     "input": "The runner is very fast."},
]
tokenizer = tiktoken.get_encoding("gpt2")
steps = []


def step(name):
    def deco(fn):
        steps.append((name, fn))
        return fn
    return deco


state = {}


@step("1. 환경 확인 (nvidia-smi)")
def s1():
    r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used",
                        "--format=csv,noheader"], capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()[:60]


@step("2. 튜닝 전 355M 로드")
def s2():
    m, cfg, _ = openai_load.build("gpt2-medium (355M)")
    state["model"], state["cfg"] = m, cfg
    return f"파라미터 {sum(p.numel() for p in m.parameters()):,}"


@step("3. 튜닝 전 응답 3개")
def s3():
    outs = []
    for e in DEMO:
        p = format_input(e)
        ids = text_to_token_ids(p, tokenizer).to(device)
        o = generate(state["model"], ids, 30, state["cfg"]["context_length"],
                     temperature=0.0, eos_id=50256)
        outs.append(token_ids_to_text(o, tokenizer)[len(p):].strip()[:60])
    state["before"] = outs
    return " / ".join(o[:34] for o in outs)


@step("4. 튜닝 후 모델 로드 (sft_355m.pth)")
def s4():
    state["model"].load_state_dict(
        torch.load(W13 / "sft_355m.pth", map_location=device))
    state["model"].to(device).eval()
    return "로드 완료"


@step("5. 튜닝 후 응답 3개")
def s5():
    outs = []
    for e in DEMO:
        p = format_input(e)
        ids = text_to_token_ids(p, tokenizer).to(device)
        o = generate(state["model"], ids, 30, state["cfg"]["context_length"],
                     temperature=0.0, eos_id=50256)
        outs.append(token_ids_to_text(o, tokenizer)[len(p):].strip()[:70])
    state["after"] = outs
    return " / ".join(o[:34] for o in outs)


@step("6. 검증의 순간 ① — LoRA 항등 게이트")
def s6():
    r = subprocess.run(["python3", "-m", "pytest",
                        "test_sft.py::test_lora_identity_at_init", "-q"],
                       cwd=W13, capture_output=True, text=True)
    return [l for l in r.stdout.strip().split("\n") if "passed" in l or "failed" in l][-1]


@step("7. 검증의 순간 ② — 저지 상한/하한")
def s7():
    r = subprocess.run(["python3", "-m", "pytest",
                        "test_sft.py::test_judge_upper_beats_lower", "-q"],
                       cwd=W13, capture_output=True, text=True)
    return [l for l in r.stdout.strip().split("\n") if "passed" in l or "failed" in l][-1]


@step("8. 3축 비교표 출력")
def s8():
    rows = [l for l in open(W13 / "lora_compare.md", encoding="utf-8")
            if l.startswith("| **")]
    return f"{len(rows)}행 출력"


def dryrun(label):
    print("=" * 74)
    print(f"드라이런 {label}")
    print("=" * 74)
    times = []
    t_all = time.perf_counter()
    for name, fn in steps:
        t0 = time.perf_counter()
        try:
            out = fn()
        except Exception as e:
            out = f"[오류] {type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        times.append((name, dt))
        print(f"  {name:<38} {dt:6.2f}s   {str(out)[:74]}")
    total = time.perf_counter() - t_all
    print(f"  {'합계':<38} {total:6.2f}s")
    state.pop("model", None)
    torch.cuda.empty_cache()
    return times, total


t1, tot1 = dryrun("1회차")
print()
t2, tot2 = dryrun("2회차")

print()
print("=" * 74)
print("[검증] 두 실행의 소요 시간 차이")
print("=" * 74)
print(f"{'단계':<38}{'1회차':>9}{'2회차':>9}{'차이':>9}")
print("-" * 66)
for (n, a), (_, b) in zip(t1, t2):
    print(f"{n:<38}{a:>8.2f}s{b:>8.2f}s{b-a:>+8.2f}s")
print(f"{'합계':<38}{tot1:>8.2f}s{tot2:>8.2f}s{tot2-tot1:>+8.2f}s")
print(f"\n  10분(600초) 제한 대비: 1회차 {tot1/600*100:.1f}% / 2회차 {tot2/600*100:.1f}%")
print(f"  → {'여유 있음' if max(tot1, tot2) < 600 else '초과 — 축소 필요'}")

print()
print("=" * 74)
print("리스크 점검과 완화책")
print("=" * 74)
load1 = dict(t1)["2. 튜닝 전 355M 로드"]
load2 = dict(t2)["2. 튜닝 전 355M 로드"]
print(f"  · 모델 로딩: {load1:.2f}s → {load2:.2f}s "
      f"(2회차가 {'빠름 — 파일 캐시 효과' if load2 < load1 else '느림'})")
print(f"    완화: 발표 전 한 번 로드해 OS 파일 캐시를 데워 둔다. "
      f"다만 15.1 규칙대로 '미리 띄워둔 것'에 선언할 것")
print(f"  · 첫 토큰 지연: 3번 단계에 CUDA 커널 JIT 워밍업이 포함된다 "
      f"({dict(t1)['3. 튜닝 전 응답 3개']:.2f}s → "
      f"{dict(t2)['3. 튜닝 전 응답 3개']:.2f}s)")
print(f"    완화: 시연 직전 더미 생성 1회로 워밍업")
print(f"  · 네트워크 의존: 7번 저지 테스트가 유일하다 (Ollama HTTP)")
print(f"    완화: Ollama 미기동 시 pytest 가 skip 되도록 이미 설계됨. "
      f"발표 5분 전 `curl` 로 확인")
print(f"  · 잔여 상태: GPU 메모리. 조합 사이 `del` + `empty_cache()` 를 넣었다")
print(f"    완화: 1번 단계의 nvidia-smi 로 사용 메모리 0 근처인지 눈으로 확인")

print()
print("=" * 74)
print("발표 5분 전 체크리스트 (명령어 수준)")
print("=" * 74)
CHECK = [
    ("컨테이너 살아 있나", "docker ps --filter name=llm-lab --format '{{.Status}}'"),
    ("GPU 비어 있나", "nvidia-smi --query-gpu=memory.used --format=csv,noheader"),
    ("체크포인트 있나", "ls -la code/week13/sft_355m.pth code/week13/lora_355m_r16.pth"),
    ("가중치 캐시 있나", "ls -la code/week10/gpt2_weights/"),
    ("Ollama 응답하나", "docker exec llm-lab curl -s --max-time 5 "
                       "http://172.17.0.1:11434/api/tags | head -c 40"),
    ("파일 캐시 데우기", "docker exec llm-lab python3 -c \"open("
                       "'/work/week13/sft_355m.pth','rb').read(1)\""),
    ("테스트 한 번 돌려보기", "docker exec -w /work/week13 llm-lab "
                          "python3 -m pytest test_sft.py -q"),
]
for i, (what, cmd) in enumerate(CHECK, 1):
    print(f"  {i}. {what}")
    print(f"     $ {cmd}")

json.dump({"run1": t1, "run2": t2, "total1": tot1, "total2": tot2,
           "before": state.get("before"), "after": state.get("after")},
          open("dryrun.json", "w"), ensure_ascii=False, indent=2)
print("\n[저장] dryrun.json")
