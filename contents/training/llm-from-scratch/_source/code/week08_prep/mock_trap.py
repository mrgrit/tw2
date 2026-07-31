"""P5-4 + P5-5 — 멀티헤드 어텐션 두 방식 (래퍼 / 분할) + 연습문제 3.2, 3.3."""
import torch
import torch.nn as nn

from causal_attention import CausalAttention
from inputs import inputs

torch.set_printoptions(precision=4, sci_mode=False)


class MultiHeadAttentionWrapper(nn.Module):
    """이해용 — 독립된 CausalAttention 여러 개를 만들어 출력을 이어붙인다."""

    def __init__(self, d_in, d_out, context_length, dropout, num_heads, qkv_bias=False):
        super().__init__()
        self.heads = nn.ModuleList([
            CausalAttention(d_in, d_out, context_length, dropout, qkv_bias)
            for _ in range(num_heads)
        ])

    def forward(self, x):
        # 각 헤드가 [b, T, d_out] 을 내고, 마지막 차원으로 concat → [b, T, d_out*num_heads]
        return torch.cat([head(x) for head in self.heads], dim=-1)


class MultiHeadAttention(nn.Module):
    """실전용(GPT-2 방식) — 큰 투영 하나를 만들고 view/transpose 로 헤드를 쪼갠다."""

    def __init__(self, d_in, d_out, context_length, dropout, num_heads, qkv_bias=False):
        super().__init__()
        assert d_out % num_heads == 0, \
            f"d_out({d_out}) 이 num_heads({num_heads}) 로 나누어떨어지지 않는다"

        self.d_out = d_out
        self.num_heads = num_heads
        self.head_dim = d_out // num_heads

        self.W_query = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_key = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_value = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.out_proj = nn.Linear(d_out, d_out)
        self.dropout = nn.Dropout(dropout)
        self.register_buffer(
            "mask",
            torch.triu(torch.ones(context_length, context_length), diagonal=1),
        )

    def forward(self, x, trace=False):
        b, num_tokens, d_in = x.shape
        rows = []

        queries = self.W_query(x)                      # [b, T, d_out]
        keys = self.W_key(x)
        values = self.W_value(x)
        rows.append(("queries (투영 직후)", tuple(queries.shape),
                     "모든 헤드의 쿼리가 한 텐서에 붙어 있다"))

        # [b, T, d_out] → [b, T, heads, head_dim]
        queries = queries.view(b, num_tokens, self.num_heads, self.head_dim)
        keys = keys.view(b, num_tokens, self.num_heads, self.head_dim)
        values = values.view(b, num_tokens, self.num_heads, self.head_dim)
        rows.append(("queries.view", tuple(queries.shape),
                     "마지막 차원을 헤드 수만큼 쪼갰다 (데이터 이동 없음)"))

        # → [b, heads, T, head_dim]
        queries = queries.transpose(1, 2)
        keys = keys.transpose(1, 2)
        values = values.transpose(1, 2)
        rows.append(("queries.transpose(1,2)", tuple(queries.shape),
                     "헤드 축을 앞으로 — 이제 헤드별로 배치처럼 병렬 연산된다"))

        attn_scores = queries @ keys.transpose(2, 3)   # [b, heads, T, T]
        rows.append(("attn_scores", tuple(attn_scores.shape),
                     "헤드마다 독립적인 TxT 점수 행렬"))

        attn_scores.masked_fill_(
            self.mask.bool()[:num_tokens, :num_tokens], 0.0
        )
        attn_weights = torch.softmax(attn_scores / self.head_dim ** 0.5, dim=-1)
        attn_weights = self.dropout(attn_weights)
        rows.append(("attn_weights", tuple(attn_weights.shape),
                     "코잘 마스킹 + √head_dim 스케일 softmax 후"))

        context = (attn_weights @ values).transpose(1, 2)   # [b, T, heads, head_dim]
        rows.append(("context.transpose(1,2)", tuple(context.shape),
                     "헤드 축을 다시 토큰 뒤로 되돌렸다"))

        # contiguous() 가 필요한 이유: transpose 후 메모리가 비연속이라 view 가 실패한다
        context = context.contiguous().view(b, num_tokens, self.d_out)
        rows.append(("context.view (헤드 병합)", tuple(context.shape),
                     "헤드 출력들을 이어붙여 d_out 으로 복원"))

        out = self.out_proj(context)
        rows.append(("out_proj 직후", tuple(out.shape),
                     "헤드별 결과를 섞는 마지막 선형 투영"))

        if trace:
            print("| 텐서 이름 | shape | 의미 |")
            print("|---|---|---|")
            for name, shape, meaning in rows:
                print(f"| `{name}` | `{shape}` | {meaning} |")
        return out


if __name__ == "__main__":
    batch = torch.stack((inputs, inputs), dim=0)

    print("=" * 66)
    print("P5-4 — MultiHeadAttentionWrapper (래퍼 방식)")
    print("=" * 66)
    torch.manual_seed(123)
    mha_w = MultiHeadAttentionWrapper(
        d_in=3, d_out=2, context_length=6, dropout=0.0, num_heads=2
    )
    out_w = mha_w(batch)
    print(f"2) d_out=2, num_heads=2 → 출력 shape {tuple(out_w.shape)}")
    print(f"   기대값 [2, 6, 4] 와 일치: {tuple(out_w.shape) == (2, 6, 4)}")

    print()
    print("3) [연습문제 3.2] 클래스 코드를 바꾸지 말고 생성 인자만 조절해")
    print("   최종 출력의 마지막 차원을 2로 만들기")
    torch.manual_seed(123)
    mha_w2 = MultiHeadAttentionWrapper(
        d_in=3, d_out=1, context_length=6, dropout=0.0, num_heads=2
    )
    out_w2 = mha_w2(batch)
    print(f"   → d_out=1, num_heads=2 로 바꿈. 출력 shape {tuple(out_w2.shape)}")
    print(f"   기대값 [2, 6, 2] 와 일치: {tuple(out_w2.shape) == (2, 6, 2)}")
    print("   이유: 래퍼는 각 헤드 출력(d_out)을 num_heads 개 이어붙이므로")
    print("         최종 차원 = d_out x num_heads. 2 = 1 x 2 이므로 d_out=1 로 낮춘다.")

    print()
    print("=" * 66)
    print("P5-5 — MultiHeadAttention (분할 방식, GPT-2 방식)")
    print("=" * 66)
    torch.manual_seed(123)
    mha = MultiHeadAttention(
        d_in=3, d_out=4, context_length=6, dropout=0.0, num_heads=2
    )
    print(f"\n2) d_in=3, d_out=4, num_heads=2 → head_dim = {mha.head_dim}")
    out = mha(batch)
    print(f"   출력 shape {tuple(out.shape)}, 기대값 [2, 6, 4] 와 일치: "
          f"{tuple(out.shape) == (2, 6, 4)}")

    print("\n3) [shape 추적표]")
    _ = mha(batch, trace=True)

    print()
    print("4) [연습문제 3.3] GPT-2 규모 (d_in=d_out=768, num_heads=12, context=1024)")
    for qkv_bias in (False, True):
        torch.manual_seed(123)
        m = MultiHeadAttention(
            d_in=768, d_out=768, context_length=1024, dropout=0.0,
            num_heads=12, qkv_bias=qkv_bias,
        )
        total = sum(p.numel() for p in m.parameters())
        # 공식으로도 계산
        if qkv_bias:
            formula = 4 * (768 * 768 + 768)
            expr = "4 x (768^2 + 768)"
        else:
            formula = 3 * 768 * 768 + 768 * 768 + 768
            expr = "3 x 768^2 + 768^2 + 768"
        print(f"   qkv_bias={qkv_bias!s:5}: head_dim={m.head_dim}, "
              f"파라미터 {total:,}  |  공식 {expr} = {formula:,}  "
              f"|  일치 {total == formula}")
        del m
