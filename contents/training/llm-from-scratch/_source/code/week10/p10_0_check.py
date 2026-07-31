"""P10-0 — week09/model_10ep.pth 로드 후 greedy 20토큰 생성이 9주차와 같은지 확인."""
import tiktoken
import torch

from common import MODEL_10EP, VERDICT, device, text_to_token_ids, token_ids_to_text
from generate import generate_text_simple
from gpt_model import GPT_CONFIG_124M, GPTModel

CFG = dict(GPT_CONFIG_124M, context_length=256)

print("=== P10-0 준비 확인 ===")
print(f"device        : {device}")
print(f"체크포인트    : {MODEL_10EP}  존재={MODEL_10EP.exists()}")
print(f"원문 텍스트   : {VERDICT}  존재={VERDICT.exists()}")
print(f"config        : context_length={CFG['context_length']}, qkv_bias={CFG['qkv_bias']}")

tokenizer = tiktoken.get_encoding("gpt2")

model = GPTModel(CFG)
state = torch.load(MODEL_10EP, map_location="cpu")
missing, unexpected = model.load_state_dict(state, strict=True), None
model.to(device)
model.eval()
print(f"load_state_dict: strict=True 로 성공 (missing/unexpected 없음)")

start = "Every effort moves you"
ids = text_to_token_ids(start, tokenizer).to(device)
with torch.no_grad():
    out = generate_text_simple(model, ids, max_new_tokens=20,
                               context_size=CFG["context_length"])
text = token_ids_to_text(out, tokenizer)

print()
print("=== greedy 20토큰 생성 ===")
print(repr(text))
print()
print("--- 9주차 10에폭 기록(에폭 10 생성문) 앞부분과 대조 ---")
week09_epoch10 = ('Every effort moves you?"\n\n"Yes--quite insensible to the irony. '
                  'She wanted him vindicated--and by me!"')
print(f"9주차 기록 : {week09_epoch10!r}")
print(f"이번 생성  : {text!r}")
print(f"9주차 기록이 이번 생성의 접두사인가: {text.startswith(week09_epoch10)}")

# 결정성도 함께 확인 (greedy 는 두 번 돌려도 같아야 한다)
with torch.no_grad():
    out2 = generate_text_simple(model, ids, max_new_tokens=20,
                                context_size=CFG["context_length"])
print(f"greedy 재실행 동일: {torch.equal(out, out2)}")
