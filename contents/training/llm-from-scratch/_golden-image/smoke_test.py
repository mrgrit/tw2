"""골든 이미지 llm-course:v1 수락 시험 — 컨테이너 안에서 돌린다.

  docker exec llm-lab python3 /work/smoke_test.py

교재 15주차가 실제로 쓰는 연산만 검사한다. 하나라도 FAIL 이면 그 이미지는 배포하지 않는다.
검사 항목: ① 런타임 신원 ② GPU 12연산 ③ matplotlib 한글 렌더 ④ 실습 패키지 임포트
"""
from __future__ import annotations

import sys

FAILED: list[str] = []


def check(name: str, fn):
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 리포트에 담는 것이 목적
        FAILED.append(name)
        print(f"  FAIL  {name:<22} {type(exc).__name__}: {exc}")
    else:
        print(f"  ok    {name:<22} {detail if detail else ''}")


# ── ① 런타임 신원 ────────────────────────────────────────────────────────────
import platform  # noqa: E402

import torch  # noqa: E402

print("[1] 런타임 신원")
print(f"  python        {platform.python_version()}  ({platform.machine()})")
print(f"  torch         {torch.__version__}")
print(f"  cuda(torch)   {torch.version.cuda}")
print(f"  is_available  {torch.cuda.is_available()}")

if platform.machine() != "aarch64":
    FAILED.append("arch(aarch64)")
if not torch.__version__.endswith("+cu130"):
    FAILED.append("torch(cu130 빌드)")
if not torch.cuda.is_available():
    FAILED.append("cuda.is_available")
    print("\n  CUDA 를 못 쓰면 이하 검사는 의미가 없다. --gpus all 을 확인하라.")
    sys.exit(1)

dev = torch.device("cuda")
print(f"  device        {torch.cuda.get_device_name(0)}")
print(f"  capability    sm_{''.join(map(str, torch.cuda.get_device_capability(0)))}")
print(f"  arch_list     {torch.cuda.get_arch_list()}")
# GB10 은 sm_121 인데 torch 2.9.1 바이너리는 sm_120 까지다 → compute_120 PTX JIT 로 돈다.
# 경고가 떠도 정상이다. 자세한 설명은 _GOLDEN-IMAGE.md §5.

# ── ② GPU 12연산 (주차별 필수 연산 전수) ────────────────────────────────────
print("\n[2] GPU 연산 12종")


def _matmul():
    a, b = torch.randn(512, 512, device=dev), torch.randn(512, 512, device=dev)
    assert (a @ b).shape == (512, 512)
    return "3·4주"


def _embedding():
    emb = torch.nn.Embedding(50257, 768).to(dev)
    assert emb(torch.randint(0, 50257, (4, 16), device=dev)).shape == (4, 16, 768)
    return "3주"


def _layernorm():
    x = torch.randn(4, 16, 768, device=dev)
    assert torch.nn.LayerNorm(768).to(dev)(x).shape == x.shape
    return "6주"


def _softmax():
    x = torch.randn(4, 12, 16, 16, device=dev)
    assert torch.allclose(torch.softmax(x, -1).sum(-1), torch.ones(4, 12, 16, device=dev))
    return "4주"


def _gelu():
    x = torch.randn(1024, device=dev)
    assert torch.nn.functional.gelu(x, approximate="tanh").shape == x.shape
    return "6주"


def _dropout():
    torch.nn.Dropout(0.5).to(dev).train()(torch.ones(1000, device=dev))
    return "5주"


def _cross_entropy():
    logits, tgt = torch.randn(32, 50257, device=dev), torch.randint(0, 50257, (32,), device=dev)
    return f"6주 loss={torch.nn.functional.cross_entropy(logits, tgt).item():.3f}"


def _backward():
    w = torch.randn(256, 256, device=dev, requires_grad=True)
    (w @ w.T).sum().backward()
    assert w.grad is not None
    return "6·9주"


def _adamw():
    p = torch.nn.Linear(64, 64).to(dev)
    opt = torch.optim.AdamW(p.parameters(), lr=1e-4)
    p(torch.randn(8, 64, device=dev)).sum().backward()
    opt.step()
    opt.zero_grad()
    return "9주"


def _bf16_autocast():
    with torch.autocast("cuda", dtype=torch.bfloat16):
        out = torch.randn(128, 128, device=dev) @ torch.randn(128, 128, device=dev)
    assert out.dtype == torch.bfloat16
    return "9·11주"


def _multinomial():
    probs = torch.softmax(torch.randn(50257, device=dev), -1)
    assert torch.multinomial(probs, 1).shape == (1,)
    return "10주"


def _topk():
    assert torch.topk(torch.randn(50257, device=dev), 50).values.shape == (50,)
    return "10주"


for _name, _fn in [
    ("matmul", _matmul), ("embedding", _embedding), ("layernorm", _layernorm),
    ("softmax", _softmax), ("gelu(tanh)", _gelu), ("dropout", _dropout),
    ("cross_entropy", _cross_entropy), ("backward", _backward), ("adamw", _adamw),
    ("bf16 autocast", _bf16_autocast), ("multinomial", _multinomial), ("topk", _topk),
]:
    check(_name, _fn)

# ── ③ matplotlib 한글 렌더 (4·6·9·10·11·13주차 그래프) ──────────────────────
print("\n[3] matplotlib 한글 라벨")


def _hangul_font():
    import matplotlib
    from matplotlib.font_manager import findfont, FontProperties

    fam = matplotlib.rcParams["font.family"]
    path = findfont(FontProperties(family=fam), fallback_to_default=False)
    if "Nanum" not in path:
        raise AssertionError(f"NanumGothic 이 아니라 {path} 로 해석됨")
    return f"{fam} → {path.rsplit('/', 1)[-1]}"


def _hangul_savefig():
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3, 1, 2])
    ax.set_title("손실 곡선")
    ax.set_xlabel("에폭")
    ax.set_ylabel("손실")
    fig.savefig("/tmp/_smoke_hangul.png")
    plt.close(fig)
    return "/tmp/_smoke_hangul.png 저장"


check("font.family", _hangul_font)
check("한글 라벨 savefig", _hangul_savefig)

# ── ④ 실습 패키지 임포트 ────────────────────────────────────────────────────
print("\n[4] 실습 패키지")
for _mod in ("tiktoken", "pandas", "numpy", "pytest", "requests", "tqdm", "nbconvert"):
    check(_mod, lambda m=_mod: __import__(m).__version__ if hasattr(__import__(m), "__version__") else "")

# 일부러 없어야 하는 것 — 있으면 10주차 미션이 무력화된다 (_GOLDEN-IMAGE.md §6)
print("\n[5] 의도적 부재 (있으면 안 된다)")
for _mod in ("tensorflow",):
    try:
        __import__(_mod)
    except ModuleNotFoundError:
        print(f"  ok    {_mod:<22} 없음 (의도된 상태)")
    else:
        FAILED.append(f"{_mod} 가 설치돼 있음")
        print(f"  FAIL  {_mod:<22} 설치돼 있다 — 10주차 미션이 무력화된다")

print("\n" + "=" * 60)
if FAILED:
    print(f"SMOKE_FAIL — {len(FAILED)}건: {', '.join(FAILED)}")
    sys.exit(1)
print("SMOKE_OK — 골든 이미지 수락 시험 전 항목 통과")
