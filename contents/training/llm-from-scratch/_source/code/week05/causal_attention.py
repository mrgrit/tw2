"""P5-0 + P5-1 + P5-2 + P5-3 — 코잘 마스크 두 방식의 동치, 드롭아웃, CausalAttention."""
import torch
import torch.nn as nn

from inputs import inputs

torch.set_printoptions(precision=4, sci_mode=False)

# ==========================================================================
# P5-0 — 배치 준비
# ==========================================================================
batch = torch.stack((inputs, inputs), dim=0)


class SelfAttention_v2(nn.Module):
    """4주차 v2 재사용 (가중치 계산 부분을 코잘 실험에 쓴다)."""

    def __init__(self, d_in, d_out, qkv_bias=False):
        super().__init__()
        self.W_query = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_key = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_value = nn.Linear(d_in, d_out, bias=qkv_bias)

    def forward(self, x):
        q, k, v = self.W_query(x), self.W_key(x), self.W_value(x)
        scores = q @ k.T
        w = torch.softmax(scores / k.shape[-1] ** 0.5, dim=-1)
        return w @ v


class CausalAttention(nn.Module):
    """P5-3 — 마스크·드롭아웃·배치를 지원하는 코잘 어텐션 (교재 3.5절)."""

    def __init__(self, d_in, d_out, context_length, dropout, qkv_bias=False):
        super().__init__()
        self.d_out = d_out
        self.W_query = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_key = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.W_value = nn.Linear(d_in, d_out, bias=qkv_bias)
        self.dropout = nn.Dropout(dropout)
        # 상삼각(대각선 위) 1 행렬을 버퍼로 등록.
        # register_buffer 를 쓰는 이유:
        #  ① 학습 대상이 아니다 — nn.Parameter 로 두면 옵티마이저가 마스크를 학습해버린다
        #  ② .to(device) 로 모델을 옮길 때 버퍼는 함께 따라간다 (일반 텐서 속성은 안 따라간다)
        self.register_buffer(
            "mask",
            torch.triu(torch.ones(context_length, context_length), diagonal=1),
        )

    def forward(self, x):
        b, num_tokens, d_in = x.shape
        queries = self.W_query(x)
        keys = self.W_key(x)
        values = self.W_value(x)

        attn_scores = queries @ keys.transpose(1, 2)
        # 미래 위치를 -inf 로 (softmax 이전에)
        attn_scores.masked_fill_(
            self.mask.bool()[:num_tokens, :num_tokens], -torch.inf
        )
        attn_weights = torch.softmax(
            attn_scores / keys.shape[-1] ** 0.5, dim=-1
        )
        attn_weights = self.dropout(attn_weights)
        return attn_weights @ values


if __name__ == "__main__":
    print("=" * 66)
    print("P5-0 — 배치 준비")
    print("=" * 66)
    print(f"batch shape: {tuple(batch.shape)}")
    print(f"기대값 [2, 6, 3] 과 일치: {tuple(batch.shape) == (2, 6, 3)}")

    # ======================================================================
    # P5-1 — 코잘 마스킹 두 방식의 동치 증명
    # ======================================================================
    print()
    print("=" * 66)
    print("P5-1 — 코잘 마스킹: 방식 A(순진) vs 방식 B(-inf)")
    print("=" * 66)

    torch.manual_seed(789)
    sa = SelfAttention_v2(d_in=3, d_out=2)
    queries = sa.W_query(inputs)
    keys = sa.W_key(inputs)
    d_k = keys.shape[-1]
    attn_scores = queries @ keys.T

    # --- 방식 A: 순진한 방법 ---
    w_full = torch.softmax(attn_scores / d_k ** 0.5, dim=-1)
    context_length = attn_scores.shape[0]
    mask_lower = torch.tril(torch.ones(context_length, context_length))
    w_masked = w_full * mask_lower                       # 미래 위치를 0으로
    row_sums = w_masked.sum(dim=-1, keepdim=True)
    w_a = w_masked / row_sums                            # 행 합으로 재정규화

    print("\n[방식 A] 일반 softmax → tril 원소곱 → 행 합으로 재정규화")
    print(torch.round(w_a, decimals=4))

    # --- 방식 B: -inf 트릭 ---
    mask_upper = torch.triu(torch.ones(context_length, context_length), diagonal=1)
    scores_masked = attn_scores.masked_fill(mask_upper.bool(), -torch.inf)
    w_b = torch.softmax(scores_masked / d_k ** 0.5, dim=-1)

    print("\n[방식 B] softmax 이전 점수에 -inf masked_fill → softmax 한 번")
    print(torch.round(w_b, decimals=4))

    print("\n=== 검증 3항목 ===")
    v1 = torch.allclose(w_a, w_b, atol=1e-6)
    upper_a = (w_a * mask_upper).abs().max().item()
    upper_b = (w_b * mask_upper).abs().max().item()
    v2 = upper_a == 0.0 and upper_b == 0.0
    s_a = w_a.sum(dim=-1)
    s_b = w_b.sum(dim=-1)
    v3 = torch.allclose(s_a, torch.ones(context_length), atol=1e-6) and \
         torch.allclose(s_b, torch.ones(context_length), atol=1e-6)

    print("| 검증 항목 | 결과 |")
    print("|---|---|")
    print(f"| 방식 A == 방식 B (allclose) | {v1} |")
    print(f"| 상삼각 원소가 전부 0 (A 최대 {upper_a}, B 최대 {upper_b}) | {v2} |")
    print(f"| 각 행 합이 1 (A {[round(float(x),6) for x in s_a]}) | {v3} |")

    print(f"\n첫 행 가중치: {torch.round(w_b[0], decimals=4).tolist()}")
    print("→ 첫 토큰은 자기 자신만 볼 수 있으므로 [1, 0, 0, 0, 0, 0] 이어야 한다")

    # ======================================================================
    # P5-2 — 드롭아웃 스케일링
    # ======================================================================
    print()
    print("=" * 66)
    print("P5-2 — 드롭아웃의 스케일링")
    print("=" * 66)
    torch.manual_seed(123)
    dropout = nn.Dropout(p=0.5)
    ones = torch.ones(6, 6)

    dropout.train()
    out_train = dropout(ones)
    print("\ntrain 모드 (p=0.5):")
    print(out_train)
    survivors = out_train[out_train != 0]
    print(f"살아남은 원소의 값: {sorted(set(round(float(v), 4) for v in survivors))}")
    print(f"살아남은 개수: {len(survivors)} / 36")

    dropout.eval()
    out_eval = dropout(ones)
    print("\neval 모드:")
    print(f"모두 1.0 인가: {torch.equal(out_eval, ones)}")
    print(f"고유값: {sorted(set(round(float(v), 4) for v in out_eval.flatten()))}")

    print("\n→ 살아남은 값이 2.0 인 이유: 기댓값 보존.")
    print("   p=0.5 로 절반을 0으로 만들면 합의 기댓값이 절반으로 준다.")
    print("   살아남은 값을 1/(1-p) = 1/0.5 = 2 배로 키워 기댓값을 원래대로 맞춘다.")
    print("   E[출력] = (1-p) x (1/(1-p)) x 입력 = 입력")
    print("   eval 모드에서는 드롭아웃을 끄므로 스케일링도 필요 없다(그대로 1.0).")

    # ======================================================================
    # P5-3 — CausalAttention
    # ======================================================================
    print()
    print("=" * 66)
    print("P5-3 — CausalAttention (배치 지원)")
    print("=" * 66)
    torch.manual_seed(123)
    ca = CausalAttention(d_in=3, d_out=2, context_length=6, dropout=0.0)
    out = ca(batch)
    print(f"입력 shape : {tuple(batch.shape)}")
    print(f"출력 shape : {tuple(out.shape)}")
    print(f"기대값 [2, 6, 2] 와 일치: {tuple(out.shape) == (2, 6, 2)}")

    print("\n--- register_buffer 를 쓰는 이유 (두 관점) ---")
    print("① 학습 대상 여부:")
    print(f"   mask 가 parameters() 에 포함되는가: "
          f"{any(p is ca.mask for p in ca.parameters())}")
    print(f"   mask.requires_grad = {ca.mask.requires_grad}")
    print("   코잘 마스크는 '구조'다 — 학습되면 모델이 미래를 보도록 마스크를 풀어버릴 수 있다.")
    print("② 장치 이동:")
    if torch.cuda.is_available():
        ca_gpu = CausalAttention(3, 2, 6, 0.0).to("cuda")
        print(f"   .to('cuda') 후 mask.device = {ca_gpu.mask.device}  (버퍼는 함께 이동)")
        print("   일반 텐서 속성(self.mask = torch.triu(...))으로 두면 CPU에 남아")
        print("   'Expected all tensors to be on the same device' 오류가 난다.")
        del ca_gpu
    print(f"   state_dict 에 포함되는가: {'mask' in ca.state_dict()}")
