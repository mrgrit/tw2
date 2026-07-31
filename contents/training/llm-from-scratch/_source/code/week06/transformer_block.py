"""P6-5 — TransformerBlock 완성 (교재 4.5절).

P6-0 에서 정한 재사용 방식: sys.path 에 week05 를 추가해 MultiHeadAttention 을 import.
  · 장점: 파일 중복이 없어 한 곳만 고치면 된다
  · 단점: 실행 위치에 의존한다 (절대경로로 계산해 완화)
  · 대안 비교 — 파일 복사: 단순하지만 버그 수정이 주차별로 갈라진다 /
                패키지화: 가장 견고하지만 __init__.py·상대 import 규칙을 추가로 배워야 한다
"""
import sys
from pathlib import Path

import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "week05"))

from multihead import MultiHeadAttention  # noqa: E402

from layers import FeedForward, LayerNorm  # noqa: E402

GPT_CONFIG_124M = {
    "vocab_size": 50257,
    "context_length": 1024,
    "emb_dim": 768,
    "n_heads": 12,
    "n_layers": 12,
    "drop_rate": 0.1,
    "qkv_bias": False,
}


class TransformerBlock(nn.Module):
    """GPT-2 블록 — pre-norm 배치.

    x = x + Dropout(MHA(LN1(x)))
    x = x + Dropout(FF(LN2(x)))

    정규화를 부품 '앞'에 두는 pre-norm 이 훈련 안정성에 유리하다.
    드롭아웃이 잔차 덧셈 '앞'에 있으므로, 지워지는 것은 부품의 출력뿐이고
    원본 신호 x 는 항상 온전히 통과한다.
    """

    def __init__(self, cfg):
        super().__init__()
        self.att = MultiHeadAttention(
            d_in=cfg["emb_dim"],
            d_out=cfg["emb_dim"],
            context_length=cfg["context_length"],
            dropout=cfg["drop_rate"],
            num_heads=cfg["n_heads"],
            qkv_bias=cfg["qkv_bias"],
        )
        self.ff = FeedForward(cfg)
        self.norm1 = LayerNorm(cfg["emb_dim"])
        self.norm2 = LayerNorm(cfg["emb_dim"])
        self.drop_shortcut = nn.Dropout(cfg["drop_rate"])

    def forward(self, x):
        shortcut = x
        x = self.norm1(x)
        x = self.att(x)
        x = self.drop_shortcut(x)
        x = x + shortcut

        shortcut = x
        x = self.norm2(x)
        x = self.ff(x)
        x = self.drop_shortcut(x)
        x = x + shortcut
        return x


if __name__ == "__main__":
    torch.manual_seed(123)
    block = TransformerBlock(GPT_CONFIG_124M)

    x = torch.rand(2, 4, 768)
    out = block(x)
    print("=== shape 보존 확인 ===")
    print(f"입력 {tuple(x.shape)} → 출력 {tuple(out.shape)}  "
          f"보존 {tuple(x.shape) == tuple(out.shape)}")

    print()
    print("=== 파라미터 분해 ===")
    mha_p = sum(p.numel() for p in block.att.parameters())
    ff_p = sum(p.numel() for p in block.ff.parameters())
    ln_p = sum(p.numel() for p in block.norm1.parameters()) + \
        sum(p.numel() for p in block.norm2.parameters())
    total = sum(p.numel() for p in block.parameters())

    print("| 구성 요소 | 산식 | 파라미터 수 |")
    print("|---|---|---|")
    print(f"| MultiHeadAttention | 3x768² + 768² + 768 | {mha_p:,} |")
    print(f"| FeedForward | (768x3072+3072) + (3072x768+768) | {ff_p:,} |")
    print(f"| LayerNorm x 2 | 2 x 2 x 768 | {ln_p:,} |")
    print(f"| **합계** | | **{total:,}** |")

    expected = 2_360_064 + 4_722_432 + 3_072
    print()
    print(f"손계산: 2,360,064 + 4,722,432 + 3,072 = {expected:,}")
    print(f"실측  : {total:,}")
    print(f"일치  : {total == expected}")
    print()
    print(f"FFN / MHA 비율: {ff_p / mha_p:.4f}배  "
          f"→ 파라미터의 무게중심은 어텐션이 아니라 FFN 에 있다 (연습문제 4.1의 답)")
