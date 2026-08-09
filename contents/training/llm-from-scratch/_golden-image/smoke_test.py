"""골든 이미지 llm-course:v2 수락 시험 — 컨테이너 안에서 돌린다.

  docker exec llm-lab python3 /work/smoke_test.py

교재 15주차가 실제로 쓰는 연산만 검사한다. 하나라도 FAIL 이면 그 이미지는 배포하지 않는다.
검사 항목: ① 런타임 신원 ② GPU 12연산 ③ matplotlib 한글 렌더 ④ 실습 패키지 임포트
        ⑤ 의도적 부재 ⑥ 오프라인 동작(폐쇄망 실습실 대비)

이미지 안에는 더 가벼운 `verify-env` 도 들어 있다. 역할이 다르다.
  verify-env   : 배포 직후 "이 장비에서 도는가" — 버전 고정 대조 + GPU 실연산
  smoke_test.py: 배포 전 "이 이미지를 받아도 되는가" — 15주 연산 전수 + 의도적 부재
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

# 기준 환경은 aarch64(DGX Spark)다. x86_64 에서도 이미지는 돌지만, 교재의 실측치
# (tokens/sec, peak 메모리, 훈련 시간)는 GB10 기준이므로 그대로 비교하면 안 된다.
if platform.machine() not in ("aarch64", "x86_64"):
    FAILED.append(f"arch({platform.machine()}) — 지원 대상이 아니다")
elif platform.machine() != "aarch64":
    print("  주의          x86_64 — 기준 환경(aarch64/GB10)이 아니다. 교재 실측치와 직접 비교 금지")
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
for _mod in ("tiktoken", "pandas", "numpy", "pytest", "requests", "tqdm", "nbconvert",
             "safetensors", "huggingface_hub", "tokenizers", "sentencepiece"):
    check(_mod, lambda m=_mod: __import__(m).__version__ if hasattr(__import__(m), "__version__") else "")


def _safetensors_roundtrip():
    """W10 은 이것 없이는 성립하지 않는다. import 만으로는 부족해서 실제로 왕복시킨다."""
    import os

    from safetensors.torch import load_file, save_file

    t = {"h.0.attn.c_attn.weight": torch.randn(768, 2304)}  # W10 이 chunk 3분할 하는 그 텐서
    p = "/tmp/_smoke.safetensors"
    save_file(t, p)
    back = load_file(p)
    os.remove(p)
    assert torch.equal(t["h.0.attn.c_attn.weight"], back["h.0.attn.c_attn.weight"])
    return "10주 — QKV 텐서 왕복 일치"


check("safetensors 왕복", _safetensors_roundtrip)

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

# ── ⑥ 오프라인 동작 (폐쇄망 실습실 대비) ────────────────────────────────────
print("\n[6] 오프라인 동작")


def _tiktoken_offline():
    """tiktoken 은 gpt2 사전을 첫 호출에 인터넷에서 받아온다.
    이미지에 미리 구워 두지 않으면 폐쇄망에서 2주차 미션 1이 첫 줄에서 죽는다.
    캐시 미스 시 타는 경로를 막아 두고 호출해서, 네트워크 없이도 되는지 증명한다."""
    import tiktoken
    import tiktoken.load as tl

    def _blocked(*_a, **_k):
        raise AssertionError("캐시 미스 — 네트워크를 타려 했다(폐쇄망에서 실패한다)")

    _orig, tl.read_file = tl.read_file, _blocked
    try:
        enc = tiktoken.get_encoding("gpt2")
    finally:
        tl.read_file = _orig
    assert enc.n_vocab == 50257, f"n_vocab {enc.n_vocab}"
    s = "방화벽이 비정상 트래픽을 차단했다."
    assert enc.decode(enc.encode(s)) == s
    return "2주 — 네트워크 없이 gpt2 사전 로드 + 왕복 일치"


check("tiktoken 캐시", _tiktoken_offline)

print("\n" + "=" * 60)
if FAILED:
    print(f"SMOKE_FAIL — {len(FAILED)}건: {', '.join(FAILED)}")
    sys.exit(1)
print("SMOKE_OK — 골든 이미지 수락 시험 전 항목 통과")
