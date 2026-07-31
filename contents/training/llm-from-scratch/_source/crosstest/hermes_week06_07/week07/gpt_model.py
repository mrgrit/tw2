"""P7-1 — GPTModel 완성 (교재 4.6 절).

GPTModel(cfg): 토큰 임베딩 + 위치 임베딩 → 드롭아웃 → TransformerBlock 12 개 → LayerNorm → 출력 헤드
torch.manual_seed(123) 으로 GPT_CONFIG_124M 인스턴스 생성
"Every effort moves you" 와 "Every day holds a" 를 tiktoken 으로 인코-Encoding 해 배치 만들기, 통과, shape 확인
전체 파라미터 수 출력
"""

import torch
import torch.nn as nn

# 가변 길이 import: 현재 디렉터리의 상위 week06 에서 TransformerBlock, GPT_CONFIG_124M 가져옴
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "week06"))

from transformer_block import TransformerBlock, GPT_CONFIG_124M  # noqa: E402


class GPTModel(nn.Module):
    """토큰을 벡터로 임베딩하고 위치 정보를 더해 50257 차원 단어 분포를 예측하는 GPT-2 모델."""

    def __init__(self, cfg):
        super().__init__()
        self.emb_layer = nn.Embedding(cfg["vocab_size"], cfg["emb_dim"])
        self.pos_emb = nn.Embedding(cfg["context_length"], cfg["emb_dim"])
        self.drop = nn.Dropout(cfg["drop_rate"])

        self.transformer_blocks = nn.Sequential(
            *[TransformerBlock(cfg) for _ in range(cfg["n_layers"])]
        )

        self.end_norm = nn.LayerNorm(cfg["emb_dim"])
        self.out_head = nn.Linear(cfg["emb_dim"], cfg["vocab_size"], bias=False)

    def forward(self, x):
        # x: (batch, seq_len) 의 토큰 IDs
        tok_embd = self.emb_layer(x)           # (B, L, 768)
        pos_idx = torch.arange(x.size(1), device=x.device)          # (L,)
        pos_embd = self.pos_emb(pos_idx)       # (L, 768)

        x = tok_embd + pos_embd                # (B, L, 768) broadcast
        x = self.drop(x)

        x = self.transformer_blocks(x)         # (B, L, 768)
        x = self.end_norm(x)                   # (B, L, 768)
        logits = self.out_head(x)              # (B, L, vocab_size)
        return logits


def encode_texts(texts, tokenizer):
    """list of str 를 token IDs 의 list[List[int]] 로 변환."""
    encodings = [tokenizer.encode(t) for t in texts]
    # 패딩으로 동일 길이 맞추기 (최대 길이까지)
    max_len = max(len(e) for e in encodings)
    padded = []
    for e in encodings:
        if len(e) < max_len:
            e = e + [50256] * (max_len - len(e))  # 50256 은 EOS 패딩
        padded.append(e[:max_len])
    return torch.tensor(padded, dtype=torch.long)


if __name__ == "__main__":
    import tiktoken

    tokenizer = tiktoken.get_encoding("gpt2")
    texts = [
        "Every effort moves you",
        "Every day holds a"
    ]

    tokenized_ids = encode_texts(texts, tokenizer)

    torch.manual_seed(123)
    gpt_model = GPTModel(GPT_CONFIG_124M)
    outputs = gpt_model(tokenized_ids)

    param_count = sum(p.numel() for p in gpt_model.parameters())
    mha_p = sum(p.numel() for p in gpt_model.transformer_blocks[0].att.parameters())
    ff_p = sum(p.numel() for p in gpt_model.transformer_blocks[0].ff.parameters())
    ln_p = sum(p.numel() for p in gpt_model.transformer_blocks[0].norm1.parameters()) + \
           sum(p.numel() for p in gpt_model.transformer_blocks[0].norm2.parameters())
    
    emb_p = gpt_model.emb_layer.weight.numel()
    pos_emb_p = gpt_model.pos_emb.weight.numel()
    out_head_p = gpt_model.out_head.in_features * gpt_model.out_head.out_features
    end_norm_p = sum(p.numel() for p in gpt_model.end_norm.parameters())

    print("[*]", tuple(outputs.shape))  # (2, 4, 50257)
    # Expected shape: [batch_size, sequence_length, vocab_size]

    print(f"Output dimensions explanation:")
    print(f"  1st dim ({outputs.shape[0]}): Batch size — 두 문장을 동시에 처리")
    print(f"  2nd dim ({outputs.shape[1]}): Sequence length — 인코딩된 토큰 수 (4)")
    print(f"  3rd dim ({outputs.shape[2]}): Vocabulary size — 각 토큰에 대한 확률 분포 차원")
    
    print()
    print("Parameter breakdown:")
    print(f"  Token Embedding (50257 × 768)                : {emb_p:,}")
    print(f"  Position Embedding (1024 × 768)             : {pos_emb_p:,}")
    print(f"  TransformerBlock x 12: MHA                   : {mha_p * 12:,} = {mha_p:,}×12")
    print(f"  TransformerBlock x 12: FeedForward           : {ff_p * 12:,} = {ff_p:,}×12")
    print(f"  TransformerBlock x 12: LayerNorm (norm1+2)   : {ln_p * 12:,} = {ln_p:,}×12")
    print(f"  Final LayerNorm                               : {end_norm_p:,}")
    print(f"  Output Head (768 → 50257, bias=False)        : {out_head_p:,}")
    print()
    print(f"Total parameters: {param_count:,}")
