"""P9-1 — 크로스 엔트로피를 확률 단계부터 수동 재구성 (교재 5.1.2절)."""
import math

import torch
import torch.nn.functional as F

from common import device  # noqa: F401  (import 확인용)
from gpt_model import GPT_CONFIG_124M, GPTModel

torch.set_printoptions(precision=4, sci_mode=False)

# 1) 훈련용 config: context_length 를 1024 → 256 으로 줄인다
cfg = dict(GPT_CONFIG_124M, context_length=256)
torch.manual_seed(123)
model = GPTModel(cfg)
model.eval()

# 2) 예제 배치
inputs = torch.tensor([[16833, 3626, 6100], [40, 1107, 588]])
targets = torch.tensor([[3626, 6100, 345], [1107, 588, 11311]])

print("=== 예제 배치 ===")
print(f"inputs  {inputs.tolist()}   (\"every effort moves\" / \"I really like\")")
print(f"targets {targets.tolist()}")

# 3a) 로짓 → softmax → 확률
with torch.no_grad():
    logits = model(inputs)
probas = torch.softmax(logits, dim=-1)
print()
print("=== a) 확률 텐서 ===")
print(f"logits shape : {tuple(logits.shape)}")
print(f"probas shape : {tuple(probas.shape)}")
print(f"각 위치 확률 합 == 1: "
      f"{torch.allclose(probas.sum(dim=-1), torch.ones(2, 3), atol=1e-5)}")

# 3b) 정답 토큰이 받은 확률 6개
print()
print("=== b) 정답 토큰이 받은 확률 6개 ===")
target_probas = []
for b in range(inputs.shape[0]):
    tp = probas[b, torch.arange(targets.shape[1]), targets[b]]
    target_probas.append(tp)
    print(f"  배치 {b}: {[f'{v:.8f}' for v in tp.tolist()]}")
all_target_probas = torch.cat(target_probas)
uniform = 1 / 50257
print(f"  균등분포 확률 1/50257 = {uniform:.8f}")
print(f"  6개 모두 균등분포와 같은 자릿수인가: "
      f"{all((uniform/10) < float(p) < (uniform*10) for p in all_target_probas)}")

# 3c) log → 평균 → 부호 반전 = 수동 손실
print()
print("=== c) 수동 손실 ===")
log_probas = torch.log(all_target_probas)
print(f"  log 적용   : {[f'{v:.4f}' for v in log_probas.tolist()]}")
avg_log = torch.mean(log_probas)
print(f"  평균        : {avg_log.item():.4f}")
manual_loss = -avg_log
print(f"  부호 반전   : {manual_loss.item():.4f}   ← 수동 손실")

# 3d) F.cross_entropy = 자동 손실
print()
print("=== d) 자동 손실 (F.cross_entropy) ===")
auto_loss = F.cross_entropy(logits.flatten(0, 1), targets.flatten())
print(f"  F.cross_entropy(logits.flatten(0,1), targets.flatten()) = {auto_loss.item():.4f}")

print()
print("=== c 와 d 의 일치 (소수 4자리) ===")
print(f"  수동 {manual_loss.item():.4f}  |  자동 {auto_loss.item():.4f}")
print(f"  소수 4자리까지 일치: {round(manual_loss.item(), 4) == round(auto_loss.item(), 4)}")
print(f"  allclose: {torch.allclose(manual_loss, auto_loss, atol=1e-5)}")

# 4) 퍼플렉시티
print()
print("=== 4) 퍼플렉시티 ===")
ppl = torch.exp(auto_loss)
print(f"  exp({auto_loss.item():.4f}) = {ppl.item():.2f}")

# 이론 대조
print()
print("=== 이론 예언과의 대조 ===")
ln_v = math.log(50257)
print(f"  ln(50257)        = {ln_v:.4f}   ← 균등분포 가정의 이론값")
print(f"  측정 손실        = {auto_loss.item():.4f}")
print(f"  차이             = {abs(auto_loss.item() - ln_v):.4f}")
print(f"  exp(ln 50257)    = {math.exp(ln_v):.0f}  (= 어휘 크기 자체)")
print(f"  측정 퍼플렉시티  = {ppl.item():.2f}")

print()
print("=== 정답지 대조 ===")
print(f"  교재 손실 10.7940 vs 실측 {auto_loss.item():.4f}  "
       f"→ 일치 {abs(auto_loss.item() - 10.7940) < 0.05}")
print(f"  교재 퍼플렉시티 48,726 vs 실측 {ppl.item():.0f}  "
       f"→ 상대 오차 {abs(ppl.item() - 48726)/48726*100:.2f}%")
