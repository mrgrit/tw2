"""P4-3 — 6x6 어텐션 가중치 히트맵."""
import matplotlib
matplotlib.use("Agg")  # 헤드리스 컨테이너이므로 파일 저장 백엔드
import matplotlib.pyplot as plt
import torch

from inputs import inputs, tokens

attn_weights = torch.softmax(inputs @ inputs.T, dim=-1)
w = attn_weights.detach().numpy()

fig, ax = plt.subplots(figsize=(7.5, 6.5))
im = ax.imshow(w, cmap="viridis")

ax.set_xticks(range(len(tokens)), labels=tokens)
ax.set_yticks(range(len(tokens)), labels=tokens)
ax.set_xlabel("Key (참고 대상 토큰)")
ax.set_ylabel("Query (주목하는 토큰)")
ax.set_title("Simple Self-Attention Weights")
plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")

# 각 셀에 수치 (소수 2자리)
for i in range(len(tokens)):
    for j in range(len(tokens)):
        ax.text(j, i, f"{w[i, j]:.2f}", ha="center", va="center",
                color="white" if w[i, j] < w.max() * 0.6 else "black", fontsize=10)

fig.colorbar(im, ax=ax, label="attention weight")
fig.tight_layout()
fig.savefig("attention_heatmap.png", dpi=130)
print("attention_heatmap.png 저장")

# ---- 관찰 3가지 (수치 근거와 함께) ----
print()
print("=== 히트맵에서 관찰되는 사실 3가지 ===")

# 1) 가장 큰 가중치 (대각선 제외/포함)
flat = [(w[i][j], tokens[i], tokens[j], i, j)
        for i in range(6) for j in range(6)]
mx = max(flat)
print(f"1) 가장 큰 가중치: {mx[0]:.4f} — query '{mx[1]}' → key '{mx[2]}'")
offdiag = max(v for v in flat if v[3] != v[4])
print(f"   대각선 제외 최대: {offdiag[0]:.4f} — '{offdiag[1]}' → '{offdiag[2]}'")

# 2) 대각선의 의미
diag = [w[i][i] for i in range(6)]
print(f"2) 대각선(자기 자신에 대한 가중치): "
      f"{[round(float(d), 4) for d in diag]}")
argmax_rows = [tokens[int(w[i].argmax())] for i in range(6)]
self_max = sum(1 for i in range(6) if int(w[i].argmax()) == i)
print(f"   각 행의 최대 가중치 대상: {argmax_rows}")
print(f"   → 6개 행 중 자기 자신이 1등인 행은 {self_max}개뿐이다.")
print("   대각선은 '자기 자신을 얼마나 참고하나'다. 학습 전이므로 자기 자신이 항상")
print("   1등은 아니다 — 단순 어텐션은 벡터 유사도만 보기 때문이다.")

# 3) journey <-> starts 상호 가중치
j, s = tokens.index("journey"), tokens.index("starts")
cos = torch.nn.functional.cosine_similarity(inputs[j], inputs[s], dim=0).item()
print(f"3) 'journey'↔'starts' 상호 가중치: "
      f"{w[j][s]:.4f} / {w[s][j]:.4f} (둘 다 최상위권)")
print(f"   두 입력 벡터의 코사인 유사도 = {cos:.6f} (거의 1)")
print(f"   inputs[journey] = {inputs[j].tolist()}")
print(f"   inputs[starts]  = {inputs[s].tolist()}")
print("   → 이 단계의 '주목'은 의미가 아니라 벡터 유사도다. 의미는 훈련 후에 생긴다.")
