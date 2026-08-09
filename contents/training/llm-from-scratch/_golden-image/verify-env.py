#!/usr/bin/env python3
"""골든 이미지 자체 검증 — 새 장비에 배포한 직후 이 한 줄이면 된다.

    docker run --rm --gpus all llm-course:v2 verify-env

"자기보고를 믿지 마라"(교재 W01 0.3절)를 도구에도 적용한다.
`import torch` 가 되고 `cuda.is_available()` 이 True 라는 것은 아무것도 증명하지 않는다.
그래서 여기서는 전부 **실제로 계산시켜 보고** CPU 결과와 대조한다.

  --no-gpu   GPU 검사를 건너뛴다 (docker build 중에는 GPU 가 없다)
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
import time

ROWS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    """검사 하나를 실행하고 결과를 기록한다. 예외는 곧 FAIL 이다."""
    try:
        detail = fn()
        ROWS.append((name, True, "" if detail is None else str(detail)))
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 FAIL 로 잡는다
        ROWS.append((name, False, f"{type(e).__name__}: {e}"))


# ── A. 플랫폼 ────────────────────────────────────────────────────────────
def a_platform() -> str:
    return f"{platform.machine()} / python {platform.python_version()}"


# ── B. 패키지 — requirements 고정 버전과 실제 설치본이 일치하는가 ────────
REQ = "/opt/llm-course/requirements.txt"


def b_packages() -> str:
    import importlib.metadata as md
    import re

    if not os.path.exists(REQ):
        raise FileNotFoundError(f"{REQ} 없음 — 이미지가 v2 가 아니다")
    want = {}
    for line in open(REQ, encoding="utf-8"):
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", line.strip())
        if m:
            want[m.group(1)] = m.group(2)
    bad = []
    for pkg, ver in want.items():
        try:
            got = md.version(pkg)
        except md.PackageNotFoundError:
            bad.append(f"{pkg} 미설치")
            continue
        if got != ver:
            bad.append(f"{pkg} {got}≠{ver}")
    if bad:
        raise RuntimeError("; ".join(bad))
    return f"{len(want)}개 전부 고정 버전과 일치"


# ── C. torch CPU — 라이브러리가 진짜 계산하는가 ──────────────────────────
def c_torch_cpu() -> str:
    import torch

    torch.manual_seed(123)
    a, b = torch.randn(256, 256), torch.randn(256, 256)
    ref = sum(a[0, k] * b[k, 0] for k in range(256))
    if abs((a @ b)[0, 0].item() - ref.item()) > 1e-2:
        raise RuntimeError("CPU matmul 이 손계산과 불일치")
    return f"torch {torch.__version__}"


# ── D. GPU — 인식이 아니라 연산을 검사한다 ───────────────────────────────
def d_gpu_visible() -> str:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("cuda.is_available() False — --gpus all 누락 또는 드라이버 문제")
    cap = torch.cuda.get_device_capability(0)
    return f"{torch.cuda.get_device_name(0)} sm_{cap[0]}{cap[1]} / cuda {torch.version.cuda}"


def d_gpu_matmul() -> str:
    import torch

    torch.manual_seed(123)
    a, b = torch.randn(512, 512), torch.randn(512, 512)
    ref = a @ b
    got = (a.cuda() @ b.cuda()).cpu()
    torch.cuda.synchronize()
    diff = (ref - got).abs().max().item()
    if not torch.allclose(ref, got, atol=1e-3):
        raise RuntimeError(f"GPU 결과가 CPU 와 불일치 maxdiff={diff:.3e}")
    return f"CPU 대조 allclose, maxdiff {diff:.2e}"


def d_gpu_bf16() -> str:
    import torch

    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("bf16 미지원 — W09 정밀도 비교 실험이 성립하지 않는다")
    a, b = torch.randn(512, 512).cuda().bfloat16(), torch.randn(512, 512).cuda().bfloat16()
    out = a @ b
    torch.cuda.synchronize()
    if not torch.isfinite(out).all().item():
        raise RuntimeError("bf16 matmul 결과에 inf/nan")
    return "bf16 matmul 정상"


def d_gpu_train() -> str:
    """실제 역전파 + AdamW. 커널이 없으면 여기서 죽는다."""
    import torch
    import torch.nn.functional as F

    torch.manual_seed(123)
    torch.cuda.reset_peak_memory_stats()
    m = torch.nn.Sequential(
        torch.nn.Linear(256, 256), torch.nn.GELU(), torch.nn.Linear(256, 10)
    ).cuda()
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
    x, y = torch.randn(64, 256).cuda(), torch.randint(0, 10, (64,)).cuda()
    first = F.cross_entropy(m(x), y).item()
    for _ in range(50):
        opt.zero_grad()
        loss = F.cross_entropy(m(x), y)
        loss.backward()
        opt.step()
    torch.cuda.synchronize()
    last = loss.item()
    if not last < first:
        raise RuntimeError(f"손실이 줄지 않음 {first:.4f} -> {last:.4f}")
    peak = torch.cuda.max_memory_allocated() / 1024**2
    del m, opt, x, y
    torch.cuda.empty_cache()
    return f"loss {first:.4f} -> {last:.4f}, peak {peak:.1f}MB"


# ── E. tiktoken — 네트워크 없이 되는가 (폐쇄망 실습실 대비) ──────────────
def e_tiktoken_offline() -> str:
    import tiktoken
    import tiktoken.load as tl

    # 캐시가 비어 있으면 여기서 네트워크를 타는데, 그것을 실패로 잡는다.
    def _blocked(*a, **k):
        raise RuntimeError("캐시 미스 — 네트워크를 타려고 했다(폐쇄망에서 실패한다)")

    orig, tl.read_file = tl.read_file, _blocked
    try:
        t0 = time.time()
        enc = tiktoken.get_encoding("gpt2")
        dt = time.time() - t0
    finally:
        tl.read_file = orig
    if enc.n_vocab != 50257:
        raise RuntimeError(f"n_vocab {enc.n_vocab} ≠ 50257")
    s = "Hello, world! 방화벽이 비정상 트래픽을 차단했다."
    if enc.decode(enc.encode(s)) != s:
        raise RuntimeError("encode/decode 왕복 불일치")
    return f"오프라인 로드 {dt:.2f}s, n_vocab 50257, 왕복 일치"


# ── F. matplotlib — 한글 라벨이 □ 로 깨지지 않는가 ──────────────────────
def f_matplotlib_korean() -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    path = font_manager.findfont("NanumGothic", fallback_to_default=False)
    if "Nanum" not in os.path.basename(path):
        raise RuntimeError(f"NanumGothic 해석 실패 → {path}")
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    ax.set_title("훈련 손실")
    ax.set_xlabel("에폭")
    out = "/tmp/_verify_plot.png"
    fig.savefig(out)
    plt.close(fig)
    size = os.path.getsize(out)
    os.remove(out)
    if size < 1000:
        raise RuntimeError("savefig 결과가 비었다")
    return f"NanumGothic, savefig {size}B"


# ── G. safetensors — W10 이 이것 없이는 성립하지 않는다 ─────────────────
def g_safetensors() -> str:
    import torch
    from safetensors.torch import load_file, save_file

    t = {"w": torch.randn(4, 4)}
    p = "/tmp/_verify.safetensors"
    save_file(t, p)
    back = load_file(p)
    os.remove(p)
    if not torch.equal(t["w"], back["w"]):
        raise RuntimeError("safetensors 왕복 불일치")
    import huggingface_hub

    return f"왕복 일치, huggingface_hub {huggingface_hub.__version__}"


# ── H. 작업 디렉토리 — /work 에 쓸 수 있는가 ────────────────────────────
def h_workdir() -> str:
    p = "/work/.verify_write_test"
    try:
        with open(p, "w") as f:
            f.write("ok")
        os.remove(p)
    except OSError as e:
        raise RuntimeError(f"/work 쓰기 불가 — 마운트 확인 필요: {e}") from None
    hf = os.environ.get("HF_HOME", "(미설정)")
    return f"쓰기 가능, HF_HOME={hf}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-gpu", action="store_true", help="GPU 검사 생략 (빌드 중)")
    args = ap.parse_args()

    check("A. 플랫폼", a_platform)
    check("B. 패키지 고정 버전", b_packages)
    check("C. torch CPU 연산", c_torch_cpu)
    if args.no_gpu:
        ROWS.append(("D. GPU", True, "SKIP (--no-gpu)"))
    else:
        check("D1. GPU 인식", d_gpu_visible)
        check("D2. GPU fp32 matmul", d_gpu_matmul)
        check("D3. GPU bf16", d_gpu_bf16)
        check("D4. GPU 학습 스텝", d_gpu_train)
    check("E. tiktoken 오프라인", e_tiktoken_offline)
    check("F. matplotlib 한글", f_matplotlib_korean)
    check("G. safetensors", g_safetensors)
    check("H. /work 쓰기", h_workdir)

    width = max(len(n) for n, _, _ in ROWS)
    print("=" * (width + 60))
    print("골든 이미지 검증 — llm-course")
    print("=" * (width + 60))
    for name, ok, detail in ROWS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _ in ROWS if not ok]
    print("-" * (width + 60))
    if failed:
        print(f"  ❌ {len(failed)}건 실패: {', '.join(failed)}")
        return 1
    print(f"  ✅ 전 {len(ROWS)}항목 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
