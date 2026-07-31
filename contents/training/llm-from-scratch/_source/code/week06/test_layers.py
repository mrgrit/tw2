"""P6-1 1단계 — 구현 전에 먼저 쓰는 테스트 (테스트 = 명세서).

이 파일이 존재하는 시점에 layers.py 는 아직 없다. 테스트가 요구를 확정한 뒤 구현한다.
V6-1, P6-2, P6-3, P6-5 의 테스트도 여기에 누적된다.
"""
import sys
from pathlib import Path

import pytest
import torch
import torch.nn as nn

# P6-0 에서 정한 방식: sys.path 에 week05 를 추가해 MultiHeadAttention 을 재사용
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "week05"))

from layers import GELU, FeedForward, LayerNorm  # noqa: E402


# ==========================================================================
# P6-1 — LayerNorm 테스트 4개
# ==========================================================================
@pytest.fixture
def batch_example():
    torch.manual_seed(123)
    return torch.randn(2, 5)


def test_ln_mean_zero(batch_example):
    """출력의 마지막 차원 평균이 0에 근접."""
    ln = LayerNorm(emb_dim=5)
    out = ln(batch_example)
    mean = out.mean(dim=-1)
    assert torch.allclose(mean, torch.zeros_like(mean), atol=1e-5), \
        f"평균이 0이 아니다: {mean.tolist()}"


def test_ln_var_one(batch_example):
    """출력의 마지막 차원 분산(unbiased=False)이 1에 근접."""
    ln = LayerNorm(emb_dim=5)
    out = ln(batch_example)
    var = out.var(dim=-1, unbiased=False)
    assert torch.allclose(var, torch.ones_like(var), atol=1e-4), \
        f"분산이 1이 아니다: {var.tolist()}"


def test_ln_params():
    """scale 과 shift 가 학습 파라미터로 존재하고 초기값이 각각 1, 0."""
    ln = LayerNorm(emb_dim=5)
    names = dict(ln.named_parameters())
    assert "scale" in names, f"scale 파라미터가 없다: {list(names)}"
    assert "shift" in names, f"shift 파라미터가 없다: {list(names)}"
    assert names["scale"].requires_grad and names["shift"].requires_grad
    assert torch.equal(names["scale"].data, torch.ones(5))
    assert torch.equal(names["shift"].data, torch.zeros(5))


def test_ln_shape():
    """입출력 shape 동일."""
    ln = LayerNorm(emb_dim=768)
    x = torch.rand(2, 4, 768)
    assert tuple(ln(x).shape) == tuple(x.shape)


# ==========================================================================
# V6-1 — 공식 구현과 교차 검증
# ==========================================================================
def test_ln_matches_torch():
    """내 LayerNorm == torch.nn.LayerNorm(emb_dim, eps=1e-5)."""
    torch.manual_seed(123)
    x = torch.randn(4, 16, 768)
    mine = LayerNorm(768)
    official = nn.LayerNorm(768, eps=1e-5)
    # 공식 구현의 초기 가중치는 weight=1, bias=0 — 내 초기값과 같다
    assert torch.equal(official.weight.data, torch.ones(768))
    assert torch.equal(official.bias.data, torch.zeros(768))
    assert torch.allclose(mine(x), official(x), atol=1e-5), \
        "불일치 — 분산 계산의 unbiased 설정을 먼저 의심하라"


# ==========================================================================
# P6-2 — GELU
# ==========================================================================
def test_gelu_matches_torch():
    """내 GELU == F.gelu(x, approximate="tanh")."""
    x = torch.linspace(-5, 5, 1000)
    mine = GELU()(x)
    official = torch.nn.functional.gelu(x, approximate="tanh")
    assert torch.allclose(mine, official, atol=1e-6), \
        f"최대 오차 {(mine - official).abs().max().item():.3e}"


# ==========================================================================
# P6-3 — FeedForward
# ==========================================================================
GPT_CONFIG_124M = {
    "vocab_size": 50257,
    "context_length": 1024,
    "emb_dim": 768,
    "n_heads": 12,
    "n_layers": 12,
    "drop_rate": 0.1,
    "qkv_bias": False,
}


def test_ff_shape():
    """FeedForward 는 shape 를 보존한다."""
    ff = FeedForward(GPT_CONFIG_124M)
    x = torch.rand(2, 3, 768)
    assert tuple(ff(x).shape) == (2, 3, 768)


def test_ff_params():
    """FeedForward 파라미터 수 = (768x3072 + 3072) + (3072x768 + 768) = 4,722,432."""
    ff = FeedForward(GPT_CONFIG_124M)
    total = sum(p.numel() for p in ff.parameters())
    expected = (768 * 3072 + 3072) + (3072 * 768 + 768)
    assert expected == 4_722_432, f"산식 자체가 틀렸다: {expected}"
    assert total == expected, f"실측 {total:,} != 산식 {expected:,}"


# ==========================================================================
# P6-5 — TransformerBlock
# ==========================================================================
def test_block_shape():
    """블록은 [2,4,768] 을 보존한다."""
    from transformer_block import TransformerBlock
    torch.manual_seed(123)
    block = TransformerBlock(GPT_CONFIG_124M)
    x = torch.rand(2, 4, 768)
    assert tuple(block(x).shape) == (2, 4, 768)


def test_block_causal():
    """블록 수준에서도 인과성 유지 — 마지막 토큰을 바꿔도 앞 위치 출력 불변."""
    from transformer_block import TransformerBlock
    cfg = dict(GPT_CONFIG_124M)
    cfg["drop_rate"] = 0.0
    torch.manual_seed(123)
    block = TransformerBlock(cfg).eval()

    x = torch.rand(2, 6, 768)
    x_mod = x.clone()
    x_mod[:, -1, :] = torch.rand(2, 768) + 5.0

    with torch.no_grad():
        out, out_mod = block(x), block(x_mod)

    t = 3
    assert torch.allclose(out[:, :t + 1, :], out_mod[:, :t + 1, :], atol=1e-5), \
        "블록 조립이 인과성을 깨뜨렸다"
    assert not torch.allclose(out[:, -1, :], out_mod[:, -1, :], atol=1e-5), \
        "마지막 위치도 안 변했다면 입력 교체가 반영되지 않은 것이다"
