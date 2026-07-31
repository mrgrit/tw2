"""P6-4 — shortcut 유무에 따른 기울기 크기 비교 (교재 4.4절 실험 재현)."""
import torch
import torch.nn as nn

from layers import GELU


class ExampleDeepNeuralNetwork(nn.Module):
    """5층 장난감 네트워크. use_shortcut 으로 x + layer(x) 적용 여부를 결정한다."""

    def __init__(self, layer_sizes, use_shortcut):
        super().__init__()
        self.use_shortcut = use_shortcut
        self.layers = nn.ModuleList([
            nn.Sequential(nn.Linear(layer_sizes[i], layer_sizes[i + 1]), GELU())
            for i in range(len(layer_sizes) - 1)
        ])

    def forward(self, x):
        for layer in self.layers:
            layer_output = layer(x)
            # 입력과 출력의 shape 가 같을 때만 잔차 덧셈이 가능하다
            if self.use_shortcut and x.shape == layer_output.shape:
                x = x + layer_output
            else:
                x = layer_output
        return x


def print_gradients(model, x, target):
    """역전파 후 각 층 가중치 기울기의 절대 평균을 반환한다."""
    output = model(x)
    loss = nn.MSELoss()(output, target)
    loss.backward()

    grads = {}
    for name, param in model.named_parameters():
        if "weight" in name:
            grads[name] = param.grad.abs().mean().item()
    return grads


LAYER_SIZES = [3, 3, 3, 3, 3, 1]
X = torch.tensor([[1.0, 0.0, -1.0]])
TARGET = torch.tensor([[0.0]])

# shortcut 없음
torch.manual_seed(123)
model_without = ExampleDeepNeuralNetwork(LAYER_SIZES, use_shortcut=False)
grads_without = print_gradients(model_without, X, TARGET)

# 시드를 재설정해 동일한 초기 가중치로 비교
torch.manual_seed(123)
model_with = ExampleDeepNeuralNetwork(LAYER_SIZES, use_shortcut=True)
grads_with = print_gradients(model_with, X, TARGET)

print("=== shortcut 없음 ===")
for k, v in grads_without.items():
    print(f"  {k}: {v}")
print("\n=== shortcut 있음 ===")
for k, v in grads_with.items():
    print(f"  {k}: {v}")

lines = []
lines.append("# shortcut_experiment.md — 잔차 연결과 기울기 소실 (P6-4 산출물)")
lines.append("")
lines.append(f"네트워크: `layer_sizes={LAYER_SIZES}`, 각 층 Linear+GELU")
lines.append(f"입력 `{X.tolist()}`, 타깃 `{TARGET.tolist()}`, 손실 MSE, seed 123")
lines.append("")
lines.append("| 층 | shortcut 없음 | shortcut 있음 | 배율 |")
lines.append("|---|---|---|---|")
for k in grads_without:
    a, b = grads_without[k], grads_with[k]
    lines.append(f"| `{k}` | {a:.10f} | {b:.10f} | **{b / a:.1f}배** |")
lines.append("")

first = list(grads_without)[0]
ratio = grads_with[first] / grads_without[first]
lines.append("## 검증 — 첫 번째 층(layers.0)의 배율")
lines.append("")
lines.append(f"- shortcut 없음: **{grads_without[first]:.10f}**")
lines.append(f"- shortcut 있음: **{grads_with[first]:.10f}**")
lines.append(f"- **배율: {ratio:.1f}배**")
lines.append("")
lines.append("## 관찰 — 출력에서 멀수록 기울기가 급감한다 (shortcut 없음)")
lines.append("")
vals = list(grads_without.values())
lines.append("| 층 | 기울기 절대 평균 | 마지막 층 대비 |")
lines.append("|---|---|---|")
for k, v in grads_without.items():
    lines.append(f"| `{k}` | {v:.10f} | {v / vals[-1]:.6f} |")
lines.append("")
lines.append(f"마지막 층({list(grads_without)[-1]}) 대비 첫 층의 기울기는 "
             f"**{vals[0] / vals[-1]:.6f}배** — 사실상 신호가 사라졌다.")
lines.append("")
lines.append("shortcut 이 있으면:")
vals_w = list(grads_with.values())
lines.append("")
lines.append("| 층 | 기울기 절대 평균 | 마지막 층 대비 |")
lines.append("|---|---|---|")
for k, v in grads_with.items():
    lines.append(f"| `{k}` | {v:.10f} | {v / vals_w[-1]:.6f} |")

with open("shortcut_experiment.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print()
print("\n".join(lines))
