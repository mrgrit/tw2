"""V5-2 — 멀티헤드 어텐션 pytest 3개. 1번이 이번 주 핵심(인과성 = 성질 테스트)."""
import pytest
import torch

from multihead import MultiHeadAttention


def test_causal_invariance():
    """위치 t 이후의 토큰 값을 바꿔도 위치 t 까지의 출력이 변하지 않는다.

    이것이 코잘 어텐션의 '정의 그 자체'다. 구현 세부가 아니라 성질을 검사한다.
    """
    torch.manual_seed(123)
    d_in, d_out, T = 3, 4, 6
    mha = MultiHeadAttention(d_in, d_out, context_length=T, dropout=0.0, num_heads=2)
    mha.eval()  # 드롭아웃 확실히 끔

    x = torch.rand(2, T, d_in)
    x_mod = x.clone()
    # 마지막 토큰을 완전히 다른 값으로 교체
    x_mod[:, -1, :] = torch.rand(2, d_in) + 10.0

    with torch.no_grad():
        out = mha(x)
        out_mod = mha(x_mod)

    t = 2
    assert torch.allclose(out[:, :t + 1, :], out_mod[:, :t + 1, :], atol=1e-6), \
        "미래 토큰을 바꿨는데 과거 위치의 출력이 변했다 → 인과성 위반"

    # 반대로 마지막 위치는 실제로 변해야 한다 (테스트가 무의미하지 않음을 보증)
    assert not torch.allclose(out[:, -1, :], out_mod[:, -1, :], atol=1e-6), \
        "마지막 위치 출력도 안 변했다면 입력 교체가 반영되지 않은 것이다"


def test_output_shape():
    """[2,6,3] 입력에 대해 출력 [2,6,4]."""
    torch.manual_seed(123)
    mha = MultiHeadAttention(3, 4, context_length=6, dropout=0.0, num_heads=2)
    out = mha(torch.rand(2, 6, 3))
    assert tuple(out.shape) == (2, 6, 4)


def test_head_divisibility():
    """d_out=5, num_heads=2 생성 시 오류가 발생한다."""
    with pytest.raises(AssertionError):
        MultiHeadAttention(3, 5, context_length=6, dropout=0.0, num_heads=2)
