"""W08-G3 재검증 — 1차에서 '검출 X' 로 나온 #8, #10 을 정확히 다시 본다.

1차 결과의 원인 분리가 목적이다:
  #10 → 내가 심은 코드가 애초에 버그가 아니었을 가능성 (수학적 동일)
  #8  → 검출 임계값이 너무 엄했거나, 1개 블록에서는 원리적으로 약하게 드러나는 것
"""
import math
import sys
from pathlib import Path

import torch
import torch.nn as nn

_HERE = Path(__file__).resolve().parent
for w in ("week05", "week06", "week07"):
    sys.path.insert(0, str(_HERE.parent / w))

from generate import generate_text_simple  # noqa: E402
from gpt_model import GPTModel  # noqa: E402
from layers import FeedForward, LayerNorm  # noqa: E402
from multihead import MultiHeadAttention  # noqa: E402
from transformer_block import GPT_CONFIG_124M, TransformerBlock  # noqa: E402

print("=" * 78)
print("#10 재검증 — '전체에 argmax' 의 올바른 구현이 무엇인가")
print("=" * 78)

cfg = dict(GPT_CONFIG_124M, n_layers=1, context_length=32, drop_rate=0.0)
torch.manual_seed(123)
model = GPTModel(cfg).eval()
start = torch.tensor([[15496, 11, 314, 716]])

with torch.no_grad():
    logits = model(start)
print(f"logits shape: {tuple(logits.shape)}  "
      f"(b={logits.shape[0]}, T={logits.shape[1]}, V={logits.shape[2]})")

correct = torch.argmax(logits[:, -1, :], dim=-1, keepdim=True)
attempt1 = torch.argmax(logits, dim=-1)[:, -1:]
print()
print("(a) 정답  : argmax(logits[:, -1, :], dim=-1)  →", correct.tolist())
print("(b) 1차試 : argmax(logits, dim=-1)[:, -1:]    →", attempt1.tolist())
print(f"    동일한가: {torch.equal(correct, attempt1)}")
print("    → argmax(dim=-1) 는 '위치별' argmax 를 내고, 그중 마지막을 취하면")
print("      결국 마지막 위치의 argmax 와 같다. **이것은 버그가 아니다.**")
print("      1차 검증의 '검출 X' 는 내가 심은 코드가 버그가 아니었기 때문이다.")

flat = torch.argmax(logits.flatten(1), dim=-1, keepdim=True)
print()
print("(c) 진짜 버그 A: argmax(logits.flatten(1), dim=-1)  →", flat.tolist())
print(f"    어휘 크기 {cfg['vocab_size']} 를 넘는가: "
      f"{bool((flat >= cfg['vocab_size']).any())}")
print("    → T*V 평탄화 인덱스라 토큰 ID 로 쓸 수 없다.")

pos_argmax = torch.argmax(logits, dim=1)
print()
print("(d) 진짜 버그 B: argmax(logits, dim=1)  → shape", tuple(pos_argmax.shape))
print("    → [b, V] 가 나온다. 토큰 하나가 아니라 어휘 크기만큼의 '위치 인덱스' 벡터다.")


def generate_bug_flat(model, idx, max_new_tokens, context_size, vocab_size):
    """진짜 버그 A 를 쓴 생성 루프."""
    for _ in range(max_new_tokens):
        idx_cond = idx[:, -context_size:]
        with torch.no_grad():
            lg = model(idx_cond)
        nxt = torch.argmax(lg.flatten(1), dim=-1, keepdim=True)
        if bool((nxt >= vocab_size).any()):
            raise IndexError(
                f"토큰 ID {int(nxt.max())} 가 어휘 크기 {vocab_size} 초과 — "
                f"평탄화 argmax 결과는 토큰 ID 가 아니다"
            )
        idx = torch.cat((idx, nxt), dim=1)
    return idx


print()
print("--- 진짜 버그 A 로 생성 시도 ---")
detected10 = False
try:
    out = generate_bug_flat(model, start, 5, 32, cfg["vocab_size"])
    ref_out = generate_text_simple(model, start, 5, 32)
    print("   버그 구현:", out[0].tolist())
    print("   기준 구현:", ref_out[0].tolist())
    detected10 = not torch.equal(out, ref_out)
    print(f"   결과 동일: {torch.equal(out, ref_out)}")
except IndexError as e:
    print(f"   IndexError: {e}")
    detected10 = True
print(f"\n#10 검출 판정: {'O — 즉시 드러난다' if detected10 else 'X'}")

print()
print("=" * 78)
print("#8 재검증 — 잔차 덧셈 누락은 몇 개 블록을 쌓으면 드러나는가")
print("=" * 78)


class BlockNoResidual(nn.Module):
    """FF 쪽 잔차 덧셈만 누락한 블록."""

    def __init__(self, cfg):
        super().__init__()
        self.att = MultiHeadAttention(cfg["emb_dim"], cfg["emb_dim"],
                                      cfg["context_length"], cfg["drop_rate"],
                                      cfg["n_heads"], cfg["qkv_bias"])
        self.ff = FeedForward(cfg)
        self.norm1 = LayerNorm(cfg["emb_dim"])
        self.norm2 = LayerNorm(cfg["emb_dim"])
        self.drop = nn.Dropout(cfg["drop_rate"])

    def forward(self, x):
        x = x + self.drop(self.att(self.norm1(x)))
        x = self.drop(self.ff(self.norm2(x)))      # BUG: + shortcut 누락
        return x


cfg8 = dict(GPT_CONFIG_124M, context_length=16, drop_rate=0.0)


def input_grad(block_cls, n_blocks, seed=123):
    torch.manual_seed(seed)
    blocks = nn.Sequential(*[block_cls(cfg8) for _ in range(n_blocks)])
    x = torch.rand(1, 8, 768, requires_grad=True)
    blocks(x).sum().backward()
    return x.grad.abs().mean().item()


print("| 블록 수 | 정상 (입력 기울기) | 잔차 누락 | 비율 |")
print("|---|---|---|---|")
for n in (1, 2, 4, 8, 12):
    g_ok = input_grad(TransformerBlock, n)
    g_bug = input_grad(BlockNoResidual, n)
    print(f"| {n} | {g_ok:.6f} | {g_bug:.6f} | **{g_bug/g_ok:.4f}배** |")

print()
print("--- #8 을 확실히 잡는 다른 자산: 9주차 초기 손실 게이트 ---")
cfg9 = dict(GPT_CONFIG_124M, n_layers=12, context_length=32, drop_rate=0.0)


class GPTNoResidual(GPTModel):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.trf_blocks = nn.Sequential(
            *[BlockNoResidual(cfg) for _ in range(cfg["n_layers"])]
        )


torch.manual_seed(123)
m_ok = GPTModel(cfg9).eval()
torch.manual_seed(123)
m_bug = GPTNoResidual(cfg9).eval()

ids = torch.tensor([[16833, 3626, 6100], [40, 1107, 588]])
tgts = torch.tensor([[3626, 6100, 345], [1107, 588, 11311]])
with torch.no_grad():
    l_ok = torch.nn.functional.cross_entropy(
        m_ok(ids).flatten(0, 1), tgts.flatten()).item()
    l_bug = torch.nn.functional.cross_entropy(
        m_bug(ids).flatten(0, 1), tgts.flatten()).item()

ln_v = math.log(50257)
print(f"9주차 초기 손실 게이트 ln(50257) = {ln_v:.4f} ± 0.5 "
      f"→ 허용 [{ln_v-0.5:.4f}, {ln_v+0.5:.4f}]")
print(f"  정상 모델 초기 손실 : {l_ok:.4f}  → "
      f"{'통과' if abs(l_ok-ln_v) < 0.5 else 'FAIL (검출됨)'}")
print(f"  잔차 누락 모델 손실 : {l_bug:.4f}  → "
      f"{'통과' if abs(l_bug-ln_v) < 0.5 else 'FAIL (검출됨)'}")
print()
print(f"#8 검출 판정: "
      f"{'O — 12층 + 9주차 초기 손실 게이트로 잡힌다' if abs(l_bug-ln_v) >= 0.5 else 'X — 손실 게이트로도 안 잡힌다'}")
