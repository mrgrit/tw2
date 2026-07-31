"""P7-1 — GPTModel 조립 (교재 4.6절)."""
import sys
from pathlib import Path

import torch
import torch.nn as nn

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "week05"))
sys.path.insert(0, str(_HERE.parent / "week06"))

from layers import LayerNorm  # noqa: E402
from transformer_block import TransformerBlock  # noqa: E402

GPT_CONFIG_124M = {
    "vocab_size": 50257,
    "context_length": 1024,
    "emb_dim": 768,
    "n_heads": 12,
    "n_layers": 12,
    "drop_rate": 0.1,
    "qkv_bias": False,
}


class GPTModel(nn.Module):
    """전체 조립도: 토큰+위치 임베딩 → 드롭아웃 → 블록 x12 → 최종 LayerNorm → 출력 헤드."""

    def __init__(self, cfg):
        super().__init__()
        self.tok_emb = nn.Embedding(cfg["vocab_size"], cfg["emb_dim"])
        self.pos_emb = nn.Embedding(cfg["context_length"], cfg["emb_dim"])
        self.drop_emb = nn.Dropout(cfg["drop_rate"])

        self.trf_blocks = nn.Sequential(
            *[TransformerBlock(cfg) for _ in range(cfg["n_layers"])]
        )

        self.final_norm = LayerNorm(cfg["emb_dim"])
        # 768차원 벡터를 어휘 크기 로짓으로. bias=False 는 GPT-2 원본과 동일
        self.out_head = nn.Linear(cfg["emb_dim"], cfg["vocab_size"], bias=False)

    def forward(self, in_idx):
        batch_size, seq_len = in_idx.shape
        tok_embeds = self.tok_emb(in_idx)
        pos_embeds = self.pos_emb(torch.arange(seq_len, device=in_idx.device))
        x = tok_embeds + pos_embeds
        x = self.drop_emb(x)
        x = self.trf_blocks(x)
        x = self.final_norm(x)
        return self.out_head(x)


if __name__ == "__main__":
    import tiktoken

    tokenizer = tiktoken.get_encoding("gpt2")

    torch.manual_seed(123)
    model = GPTModel(GPT_CONFIG_124M)

    txt1 = "Every effort moves you"
    txt2 = "Every day holds a"
    batch = torch.stack([
        torch.tensor(tokenizer.encode(txt1)),
        torch.tensor(tokenizer.encode(txt2)),
    ], dim=0)

    print("=== 입력 ===")
    print(f"txt1 {txt1!r} → {tokenizer.encode(txt1)}")
    print(f"txt2 {txt2!r} → {tokenizer.encode(txt2)}")
    print(f"배치 shape: {tuple(batch.shape)}")

    out = model(batch)
    print()
    print("=== 출력 ===")
    print(f"출력 shape: {tuple(out.shape)}")
    print("  차원 1 (2)     : 배치 크기 — 동시에 처리한 시퀀스 개수")
    print("  차원 2 (4)     : 토큰 수 — 각 시퀀스의 길이(위치별로 예측을 낸다)")
    print("  차원 3 (50257) : 어휘 로짓 — 각 위치에서 '다음 토큰'이 될 5만여 후보의 점수")

    total = sum(p.numel() for p in model.parameters())
    print()
    print(f"=== 전체 파라미터: {total:,} ===")
    print(f"정답지 163,009,536 과 일치: {total == 163_009_536}")
