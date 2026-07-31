"""P13-0 — 튜닝 전 355M 의 상태를 기록한다."""
import json

import torch

import common  # noqa: F401
from common import (WEEK10_WEIGHTS, build_instruction_loaders, device,
                    text_to_token_ids, token_ids_to_text)

import openai_load
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

from decoding import generate            # noqa: E402
from instr_data import format_input      # noqa: E402
from pretrain import calc_loss_loader    # noqa: E402

print("=" * 74)
print("P13-0 — 튜닝 전 상태 기록 (GPT-2 355M)")
print("=" * 74)

gpt, cfg, _ = openai_load.build("gpt2-medium (355M)")
n = sum(p.numel() for p in gpt.parameters())
print(f"로드 완료: emb {cfg['emb_dim']}, layers {cfg['n_layers']}, "
      f"heads {cfg['n_heads']}, ctx {cfg['context_length']}, "
      f"qkv_bias {cfg['qkv_bias']}, 파라미터 {n:,}")

train_loader, val_loader, test_loader, train_data, val_data, test_data, tokenizer = \
    build_instruction_loaders(batch_size=8)
print(f"12주차 로더: train {len(train_loader)}배치 / val {len(val_loader)}배치 / "
      f"test {len(test_loader)}배치")

print()
print("--- 튜닝 전 손실 (지시 데이터 기준) ---")
gpt.eval()
with torch.no_grad():
    tr = calc_loss_loader(train_loader, gpt, device)
    va = calc_loss_loader(val_loader, gpt, device)
print(f"  train **{tr:.4f}** / val **{va:.4f}**")
print(f"  3점대(3.8 안팎)인가: train {3.0 <= tr < 4.0} / val {3.0 <= va < 4.0}")
print(f"  참고 — 10주차에서 잰 355M 의 the-verdict val 손실: 3.3585")
print(f"         자연어 텍스트든 지시 데이터든 같은 동네다. "
      f"영어는 이미 잘하는 모델이라는 뜻.")

print()
print("--- val 첫 항목에 greedy 35토큰 ---")
entry = val_data[0]
prompt = format_input(entry)
print("[입력 프롬프트]")
print(prompt)
print()
print(f"[정답] {entry['output']}")
print()
ids = text_to_token_ids(prompt, tokenizer).to(device)
out = generate(gpt, ids, max_new_tokens=35,
               context_size=cfg["context_length"], temperature=0.0)
full = token_ids_to_text(out, tokenizer)
cont = full[len(prompt):]
print(f"[튜닝 전 모델이 이어 쓴 35토큰 — 원문 그대로]")
print(repr(cont))

print()
print("=" * 74)
print("[검증] 판정")
print("=" * 74)
has_marker = "### Response:" in cont
print(f"  ① 손실이 3점대인가            : train {tr:.4f} / val {va:.4f} → "
      f"{'PASS' if 3.0 <= va < 4.0 else 'FAIL'}")
print(f"  ② 생성이 지시를 따르는가       : ", end="")
print("아니다 — ", end="")
if has_marker:
    print("'### Response:' 를 스스로 찍고 이어 쓴다(템플릿 흉내).")
else:
    print("지시문을 이어 쓰거나 새 지시를 만들어 낸다.")
print()
print("  → 언어 능력과 지시 수행 능력은 별개다. 11주차 P11-3 의 재확인.")

json.dump({"train_loss": tr, "val_loss": va, "val0_prompt": prompt,
           "val0_answer": entry["output"], "val0_before": cont},
          open("before_tuning.json", "w"), ensure_ascii=False, indent=2)
print("\n[저장] before_tuning.json")
