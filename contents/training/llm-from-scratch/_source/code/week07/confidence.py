"""P7-4 — 훈련 전 로짓 분포 관찰."""
import tiktoken
import torch

from gpt_model import GPT_CONFIG_124M, GPTModel

tokenizer = tiktoken.get_encoding("gpt2")

torch.manual_seed(123)
model = GPTModel(GPT_CONFIG_124M)
model.eval()

idx = torch.tensor([tokenizer.encode("Hello, I am")])
with torch.no_grad():
    logits = model(idx)

last = logits[0, -1, :]
probs = torch.softmax(last, dim=-1)

top_p, top_i = torch.topk(probs, 5)

print("=== 1) 확률 상위 5개 토큰 ===")
print("| 순위 | 토큰 ID | 토큰 문자열 | 확률 | 확률(%) |")
print("|---|---|---|---|---|")
for rank, (p, i) in enumerate(zip(top_p.tolist(), top_i.tolist()), start=1):
    print(f"| {rank} | {i} | {tokenizer.decode([i])!r} | {p:.8f} | {p*100:.6f}% |")

uniform = 1 / 50257
print()
print("=== 2) 최고 확률 vs 균등분포 ===")
print(f"최고 확률        : {top_p[0].item():.8f}  ({top_p[0].item()*100:.6f}%)")
print(f"균등분포 확률    : {uniform:.8f}  ({uniform*100:.6f}%)   (= 1/50257)")
print(f"최고 / 균등      : {top_p[0].item()/uniform:.2f}배")
print(f"최고 확률이 1% 미만인가: {top_p[0].item() < 0.01}")

ent = float(-(probs * torch.log(probs + 1e-12)).sum())
max_ent = float(torch.log(torch.tensor(50257.0)))
print()
print("=== 3) 분포의 상태 ===")
print(f"엔트로피         : {ent:.4f}")
print(f"균등분포 엔트로피: {max_ent:.4f}  (= ln 50257)")
print(f"엔트로피 비율    : {ent/max_ent*100:.2f}%  (100% 면 완전 균등)")
print()
print("한 문장 요약: 훈련 전 모델의 확률분포는 **거의 균등분포**다 — 최고 확률조차")
print(f"{top_p[0].item()*100:.4f}% 로 1% 에 한참 못 미치고, 엔트로피가 균등분포의")
print(f"{ent/max_ent*100:.2f}% 에 달한다. 5만 개 후보 사이에서 아무 확신이 없다.")
