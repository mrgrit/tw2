"""V3-2, V3-3 — 임베딩 동치성 + 파이프라인 shape·파라미터 회귀 테스트."""
import random

import torch
import torch.nn as nn

from dataset import create_dataloader_v1

VOCAB_SIZE = 50257
OUTPUT_DIM = 256
MAX_LENGTH = 4
BATCH_SIZE = 8


def test_embedding_equals_onehot_matmul():
    """V3-2 — 무작위 vocab_size(10~100), 차원(4~64), 임의 ID 시퀀스에 대해
    임베딩 조회와 원-핫 행렬곱이 allclose 인지 확인 (20회 반복)."""
    rng = random.Random(123)
    for trial in range(20):
        vocab_size = rng.randint(10, 100)
        dim = rng.randint(4, 64)
        seq_len = rng.randint(1, 20)

        torch.manual_seed(trial)
        emb = nn.Embedding(vocab_size, dim)
        ids = torch.tensor([rng.randrange(vocab_size) for _ in range(seq_len)])

        looked_up = emb(ids)
        onehot = torch.nn.functional.one_hot(ids, num_classes=vocab_size).float()
        matmul = onehot @ emb.weight

        assert torch.allclose(matmul, looked_up), \
            f"trial {trial}: vocab={vocab_size}, dim={dim}, seq={seq_len} 에서 불일치"


def _build_pipeline():
    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()
    loader = create_dataloader_v1(
        raw_text, batch_size=BATCH_SIZE, max_length=MAX_LENGTH,
        stride=MAX_LENGTH, shuffle=False, drop_last=True,
    )
    inputs, _ = next(iter(loader))
    torch.manual_seed(123)
    tok = nn.Embedding(VOCAB_SIZE, OUTPUT_DIM)
    pos = nn.Embedding(MAX_LENGTH, OUTPUT_DIM)
    tok_emb = tok(inputs)
    pos_emb = pos(torch.arange(MAX_LENGTH))
    return inputs, tok_emb, pos_emb, tok_emb + pos_emb, tok, pos


def test_pipeline_shapes():
    """V3-3 1번 — 파이프라인 각 단계의 shape 가 정답과 일치."""
    inputs, tok_emb, pos_emb, final, _, _ = _build_pipeline()
    assert tuple(inputs.shape) == (8, 4)
    assert tuple(tok_emb.shape) == (8, 4, 256)
    assert tuple(pos_emb.shape) == (4, 256)
    assert tuple(final.shape) == (8, 4, 256)


def test_param_counts():
    """V3-3 2번 — 두 임베딩 층의 파라미터 수가 (50257*256, 4*256) 과 일치."""
    _, _, _, _, tok, pos = _build_pipeline()
    assert sum(p.numel() for p in tok.parameters()) == 50257 * 256 == 12865792
    assert sum(p.numel() for p in pos.parameters()) == 4 * 256 == 1024
