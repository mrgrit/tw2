"""P10-4 (1) — 9주차 설정으로 5 에폭만 훈련하고 모델+옵티마이저를 함께 저장한다.

옵티마이저 state_dict 를 같이 저장하는 이유: AdamW 는 파라미터마다 1차·2차 모멘트
2개를 들고 있다. 이 관성을 버리고 새 옵티마이저로 이어 훈련하면 초반 몇 스텝 동안
학습률 워밍업을 다시 하는 셈이 되어 손실이 튄다 (연습문제 5.4 / 10.11 문제 5).
"""
import json

import tiktoken
import torch

import common  # noqa: F401
from common import VERDICT, device
from gpt_model import GPT_CONFIG_124M, GPTModel
from pretrain import build_loaders, evaluate_model, train_model_simple

CFG = dict(GPT_CONFIG_124M, context_length=256)

tokenizer = tiktoken.get_encoding("gpt2")
with open(VERDICT, "r", encoding="utf-8") as f:
    text_data = f.read()

train_loader, val_loader, _, _ = build_loaders(text_data)

torch.manual_seed(123)
model = GPTModel(CFG).to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=4e-4, weight_decay=0.1)

print("=" * 70)
print("P10-4 (1) — 5 에폭 훈련 후 체크포인트 저장")
print("=" * 70)
train_losses, val_losses, tokens_seen, samples = train_model_simple(
    model, train_loader, val_loader, optimizer, device,
    num_epochs=5, eval_freq=5, eval_iter=5,
    start_context="Every effort moves you", tokenizer=tokenizer,
)

# 저장 직전 손실을 '전체 로더' 기준으로 한 번 더 정확히 잰다 (eval_iter 제한 없이)
tr_full, va_full = evaluate_model(model, train_loader, val_loader, device,
                                  eval_iter=len(train_loader))
print()
print(f"저장 직전 손실 (eval_iter=5 추적값)  : train {train_losses[-1]:.4f} / "
      f"val {val_losses[-1]:.4f}")
print(f"저장 직전 손실 (전체 로더 기준)      : train {tr_full:.4f} / val {va_full:.4f}")

torch.save({
    "model_state_dict": model.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
}, "checkpoint_5ep.pth")
print("\n[저장] checkpoint_5ep.pth (model + optimizer state_dict)")

meta = {
    "epochs_done": 5,
    "train_loss_tracked": train_losses[-1],
    "val_loss_tracked": val_losses[-1],
    "train_loss_full": tr_full,
    "val_loss_full": va_full,
    "tokens_seen": tokens_seen[-1],
    "train_curve": train_losses,
    "val_curve": val_losses,
}
with open("checkpoint_5ep_meta.json", "w") as f:
    json.dump(meta, f, indent=2)
print("[저장] checkpoint_5ep_meta.json (저장 직전 손실 기록)")

import os
print(f"\n체크포인트 크기: {os.path.getsize('checkpoint_5ep.pth')/1e6:.1f} MB "
      f"(모델만이면 절반 수준 — 옵티마이저 모멘트 2개가 파라미터와 같은 크기)")
