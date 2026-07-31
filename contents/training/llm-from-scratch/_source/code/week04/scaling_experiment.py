"""P4-6 — 차원 증가가 내적과 softmax 에 미치는 영향 측정."""
import torch

torch.manual_seed(123)

# ---- 표 1: d 별 내적 분산 ----
DIMS = [8, 64, 512]
NPAIRS = 1000

table1 = []
for d in DIMS:
    a = torch.randn(NPAIRS, d)
    b = torch.randn(NPAIRS, d)
    dots = (a * b).sum(dim=-1)
    var = dots.var(unbiased=True).item()
    mean = dots.mean().item()
    table1.append((d, mean, var, var / d))

# ---- 표 2: d=512 에서 스케일링 유무 ----
d = 512
scores = torch.randn(6) * (d ** 0.5)   # 차원 d 내적의 전형적 크기(표준편차 √d)

p_unscaled = torch.softmax(scores, dim=-1)
p_scaled = torch.softmax(scores / d ** 0.5, dim=-1)


def entropy(p):
    return float(-(p * torch.log(p + 1e-12)).sum())


lines = []
lines.append("# scaling_experiment.md — √d 스케일링 측정 실험 (P4-6 산출물)")
lines.append("")
lines.append("## 표 1 — 차원 d 별 내적의 분산")
lines.append("")
lines.append(f"표준정규 무작위 벡터 쌍 {NPAIRS}개의 내적을 계산해 분산을 측정했다.")
lines.append("")
lines.append("| d | 내적 평균 | 내적 분산(측정) | 이론값 (= d) | 측정/이론 | 판정 |")
lines.append("|---|---|---|---|---|---|")
for dd, mean, var, ratio in table1:
    verdict = "근접 O" if 0.85 <= ratio <= 1.15 else f"이탈 X ({ratio:.2f})"
    lines.append(f"| {dd} | {mean:+.4f} | **{var:.2f}** | {dd} | {ratio:.3f} | {verdict} |")
lines.append("")
lines.append("이론: 서로 독립인 표준정규 성분 d개의 곱을 더하므로")
lines.append("`Var(q·k) = Σ Var(q_i k_i) = d × 1 = d`. 측정값이 d 에 근접한다.")
lines.append("")
lines.append("## 표 2 — d=512 에서 스케일링 유무에 따른 softmax 분포")
lines.append("")
lines.append(f"무작위 점수 벡터(길이 6, 표준편차 √512 규모): "
             f"`{[round(float(s), 2) for s in scores]}`")
lines.append("")
lines.append("| 스케일링 | 분포 | 최댓값 | 엔트로피 |")
lines.append("|---|---|---|---|")
lines.append(f"| **없음** (softmax(scores)) | `{[round(float(p), 6) for p in p_unscaled]}` | "
             f"**{p_unscaled.max().item():.6f}** | {entropy(p_unscaled):.4f} |")
lines.append(f"| **있음** (softmax(scores/√d)) | `{[round(float(p), 4) for p in p_scaled]}` | "
             f"**{p_scaled.max().item():.4f}** | {entropy(p_scaled):.4f} |")
lines.append("")
lines.append(f"스케일링 없음: 최댓값 {p_unscaled.max().item():.6f} → 거의 1. "
             f"사실상 원-핫이다(엔트로피 {entropy(p_unscaled):.4f} ≈ 0).")
lines.append(f"스케일링 있음: 최댓값 {p_scaled.max().item():.4f}. "
             f"분포가 완만해졌다(엔트로피 {entropy(p_scaled):.4f}).")
lines.append("")
lines.append("균등분포(6개)의 엔트로피 = ln 6 = "
             f"{float(torch.log(torch.tensor(6.0))):.4f} 이 상한이다.")

with open("scaling_experiment.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines))
