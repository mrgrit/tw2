"""P4-4 + P4-5 — 학습 가능한 가중치 SelfAttention v1/v2 와 연습문제 3.1(가중치 이식)."""
import torch
import torch.nn as nn

from inputs import inputs

torch.set_printoptions(precision=4, sci_mode=False)


class SelfAttention_v1(nn.Module):
    """날 것의 nn.Parameter 로 세 투영 행렬을 만든 버전.

    가중치 shape 가 (d_in, d_out) 이므로 forward 에서 x @ W 로 곱한다.
    """

    def __init__(self, d_in, d_out):
        super().__init__()
        self.W_query = nn.Parameter(torch.rand(d_in, d_out))
        self.W_key = nn.Parameter(torch.rand(d_in, d_out))
        self.W_value = nn.Parameter(torch.rand(d_in, d_out))

    def forward(self, x):
        queries = x @ self.W_query
        keys = x @ self.W_key
        values = x @ self.W_value

        attn_scores = queries @ keys.T
        d_k = keys.shape[-1]
        attn_weights = torch.softmax(attn_scores / d_k ** 0.5, dim=-1)
        return attn_weights @ values


class SelfAttention_v2(nn.Module):
    """세 투영을 nn.Linear(bias=False) 로 구현한 버전.

    nn.Linear 는 가중치를 (out_features, in_features) 로 저장하고 forward 에서
    x @ W.T 를 계산한다 — v1과 저장 방향이 전치 관계다.
    """

    def __init__(self, d_in, d_out, qkv_bias=False):
        super().__init__()
        self.W_query = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_key = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_value = nn.Linear(d_in, d_out, bias=qkv_bias)

    def forward(self, x):
        queries = self.W_query(x)
        keys = self.W_key(x)
        values = self.W_value(x)

        attn_scores = queries @ keys.T
        d_k = keys.shape[-1]
        attn_weights = torch.softmax(attn_scores / d_k ** 0.5, dim=-1)
        return attn_weights @ values


if __name__ == "__main__":
    print("=" * 66)
    print("P4-4 — SelfAttention_v1 (seed 123, d_in=3, d_out=2)")
    print("=" * 66)
    torch.manual_seed(123)
    sa_v1 = SelfAttention_v1(d_in=3, d_out=2)
    out_v1 = sa_v1(inputs)
    print(torch.round(out_v1, decimals=4))
    print(f"\n두 번째 행 (journey 의 문맥 벡터): "
          f"{torch.round(out_v1[1], decimals=4).tolist()}")

    print()
    print("=" * 66)
    print("P4-5 — SelfAttention_v2 (seed 789) 와 연습문제 3.1 가중치 이식")
    print("=" * 66)
    torch.manual_seed(789)
    sa_v2 = SelfAttention_v2(d_in=3, d_out=2)
    out_v2 = sa_v2(inputs)
    print("v2 출력:")
    print(torch.round(out_v2, decimals=4))

    print()
    print("--- 저장 방향 확인 ---")
    print(f"v1 W_query shape (d_in, d_out) : {tuple(sa_v1.W_query.shape)}")
    print(f"v2 W_query.weight shape        : {tuple(sa_v2.W_query.weight.shape)}")
    print("→ nn.Linear 는 (out_features, in_features) 로 저장한다.")
    print("  nn.Linear 의 forward 는 x @ W.T 이고, v1 의 forward 는 x @ W 다.")
    print("  같은 선형변환을 얻으려면 v1.W = v2.weight.T 여야 한다 → **전치가 필요**하다.")

    print()
    print("--- 이식 (전치해서 복사) ---")
    sa_v1.W_query.data = sa_v2.W_query.weight.data.T.clone()
    sa_v1.W_key.data = sa_v2.W_key.weight.data.T.clone()
    sa_v1.W_value.data = sa_v2.W_value.weight.data.T.clone()

    out_v1_after = sa_v1(inputs)
    print("이식 후 v1 출력:")
    print(torch.round(out_v1_after, decimals=4))
    same = torch.allclose(out_v1_after, out_v2, atol=1e-6)
    print(f"\ntorch.allclose(v1(inputs), v2(inputs)) = {same}")
    print(f"최대 절대 오차: {(out_v1_after - out_v2).abs().max().item():.3e}")

    print()
    print("--- 반례: 전치 없이 복사하면? ---")
    torch.manual_seed(789)
    sa_v2b = SelfAttention_v2(d_in=3, d_out=2)
    sa_v1b = SelfAttention_v1(d_in=3, d_out=2)
    try:
        sa_v1b.W_query.data = sa_v2b.W_query.weight.data.clone()
        print("  shape 이 (2,3) vs (3,2) 라 대입 자체는 되지만 이후 x@W 에서 오류가 난다")
        _ = sa_v1b(inputs)
        print("  → 오류 없음(예상과 다름)")
    except RuntimeError as e:
        print(f"  RuntimeError: {str(e)[:110]}")
        print("  → d_in=3, d_out=2 처럼 두 값이 다르면 전치 누락이 즉시 shape 오류로 드러난다.")
        print("     (d_in == d_out 인 경우엔 조용히 틀린 값이 나온다 — 더 위험하다)")
