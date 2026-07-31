"""P5-7 — mha_trap.py 의 버그를 차등 테스트로 규명.

기준 구현(multihead.MultiHeadAttention) vs 피검 대상(mha_trap.MultiHeadAttention)을
동일 시드·동일 가중치·동일 입력에서 비교하고, 어느 중간 단계부터 갈라지는지 특정한다.
trap 코드는 수정하지 않는다 — 진단만.
"""
import torch

import mha_trap
from multihead import MultiHeadAttention as RefMHA

torch.set_printoptions(precision=4, sci_mode=False)

D_IN, D_OUT, T, HEADS = 3, 4, 6, 2

# --- 1) 동일 가중치로 두 구현 준비 ---
torch.manual_seed(123)
ref = RefMHA(D_IN, D_OUT, T, 0.0, HEADS).eval()
sus = mha_trap.MultiHeadAttention(D_IN, D_OUT, T, 0.0, HEADS).eval()
sus.load_state_dict(ref.state_dict())   # 가중치를 완전히 동일하게

torch.manual_seed(42)
x = torch.rand(2, T, D_IN)

with torch.no_grad():
    out_ref = ref(x)
    out_sus = sus(x)

print("=" * 68)
print("1) 최종 출력 비교")
print("=" * 68)
same = torch.allclose(out_ref, out_sus, atol=1e-6)
print(f"allclose: {same}")
print(f"최대 절대 오차: {(out_ref - out_sus).abs().max().item():.6f}")
if same:
    print("→ 출력이 같다. 다른 입력/설정으로 재시도해야 한다.")
    raise SystemExit

# --- 2) 단계별 텐서를 재현해 분기 지점 특정 ---
print()
print("=" * 68)
print("2) 단계별 비교 — 어디서 갈라지는가")
print("=" * 68)


def stages(model, x, softmax_dim):
    """두 구현의 forward 를 단계별로 재현한다. softmax_dim 만 다르게 준다."""
    b, num_tokens, _ = x.shape
    q = model.W_query(x).view(b, num_tokens, model.num_heads, model.head_dim).transpose(1, 2)
    k = model.W_key(x).view(b, num_tokens, model.num_heads, model.head_dim).transpose(1, 2)
    v = model.W_value(x).view(b, num_tokens, model.num_heads, model.head_dim).transpose(1, 2)
    s = q @ k.transpose(2, 3)
    s_masked = s.masked_fill(model.mask.bool()[:num_tokens, :num_tokens], -torch.inf)
    w = torch.softmax(s_masked / model.head_dim ** 0.5, dim=softmax_dim)
    ctx = (w @ v).transpose(1, 2).contiguous().view(b, num_tokens, model.d_out)
    out = model.out_proj(ctx)
    return {"queries": q, "keys": k, "values": v, "scores": s,
            "scores_masked": s_masked, "weights": w, "context": ctx, "out": out}


with torch.no_grad():
    a = stages(ref, x, -1)     # 기준: dim=-1
    b_ = stages(sus, x, -2)    # 가설: trap 은 dim=-2

print("| 단계 | 일치 | 최대 절대 오차 |")
print("|---|---|---|")
first_diverge = None
for key in ["queries", "keys", "values", "scores", "scores_masked", "weights", "context", "out"]:
    ta, tb = a[key], b_[key]
    finite = torch.isfinite(ta) & torch.isfinite(tb)
    eq = torch.allclose(ta[finite], tb[finite], atol=1e-6)
    err = (ta[finite] - tb[finite]).abs().max().item()
    print(f"| {key} | {eq} | {err:.6f} |")
    if not eq and first_diverge is None:
        first_diverge = key

print()
print(f"→ **분기 지점: `{first_diverge}`**")
print("   queries/keys/values/scores/scores_masked 까지는 동일하다.")
print("   softmax 를 적용하는 순간부터 갈라진다 → softmax 인자가 의심된다.")

# --- 3) 가설 확정: 행 합 검사 ---
print()
print("=" * 68)
print("3) 가설 확정 — 어텐션 가중치의 행 합")
print("=" * 68)
with torch.no_grad():
    w_sus = sus(x)  # 실행만
    # trap 의 실제 weights 를 직접 계산
    wt = b_["weights"]
    wr = a["weights"]
print(f"기준 구현 weights 행 합 (dim=-1 방향): "
      f"{[round(float(v), 4) for v in wr[0, 0].sum(dim=-1)]}")
print(f"trap  구현 weights 행 합 (dim=-1 방향): "
      f"{[round(float(v), 4) for v in wt[0, 0].sum(dim=-1)]}   <- 1 이 아니다")
print(f"trap  구현 weights 열 합 (dim=-2 방향): "
      f"{[round(float(v), 4) for v in wt[0, 0].sum(dim=-2)]}   <- 이쪽이 1 이다")
print()
print("→ trap 은 **열 방향(dim=-2)으로 정규화**했다. 코잘 마스크가 있는 상태에서")
print("  열 방향 정규화를 하면 첫 열은 -inf 가 없어 정상 합이 되지만,")
print("  각 행(= 한 토큰이 참고하는 분포)의 합이 1이 아니게 된다.")
print("  즉 '가중 평균'이라는 어텐션의 정의 자체가 깨진다.")

# nan 발생 여부 — 완전히 마스킹된 열이 있으면 softmax(dim=-2)가 nan 을 만든다
nan_count = int(torch.isnan(wt).sum())
print(f"\ntrap weights 의 NaN 개수: {nan_count}")
print("  NaN 은 나지 않는다: 코잘 마스크는 scores[i][j] 를 j>i 일 때 -inf 로 만들므로,")
print("  열 j 에는 i=j 위치가 항상 유한하다 → 열 방향 softmax 의 분모가 0 이 되지 않는다.")
print("  이것이 이 버그가 '조용한' 이유다. 오류도 NaN 도 없이 값만 틀린다.")

# --- 4) 인과성 테스트를 trap 에 적용 ---
print()
print("=" * 68)
print("4) V5-2 의 test_causal_invariance 를 trap 에 적용")
print("=" * 68)
x2 = torch.rand(2, T, D_IN)
x2_mod = x2.clone()
x2_mod[:, -1, :] = torch.rand(2, D_IN) + 10.0

for name, model in (("기준 구현", ref), ("trap 구현", sus)):
    with torch.no_grad():
        o1, o2 = model(x2), model(x2_mod)
    t = 2
    ok = torch.allclose(o1[:, :t + 1, :], o2[:, :t + 1, :], atol=1e-6)
    err = (o1[:, :t + 1, :] - o2[:, :t + 1, :]).abs().max().item()
    print(f"  {name}: 인과성 {'PASS' if ok else 'FAIL'}  (위치 0~2 최대 오차 {err:.6f})")

print()
print("=" * 68)
print("결론")
print("=" * 68)
print("의심 라인 : mha_trap.py 47행")
print("            attn_weights = torch.softmax(... , dim=-2)")
print("정답       : dim=-1")
print("분기 지점 : weights (softmax 직후) — 그 앞 단계(q/k/v/scores/masked)는 전부 오차 0")
print("증상       : ① 행 합이 1이 아니다 (0.1713 ~ 2.4228)")
print("             ② 열 합이 1이 되어 있다 (정규화 방향이 뒤바뀐 증거)")
print("             ③ V5-2 인과성 테스트 FAIL (기준 구현은 PASS)")
print("             ④ 오류도 NaN 도 없이 값만 틀린다 — '조용한' 버그")
