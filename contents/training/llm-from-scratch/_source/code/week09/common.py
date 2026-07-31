"""P9-0 — 공통 유틸. device 결정과 텍스트↔토큰ID 왕복 변환."""
import sys
from pathlib import Path

import tiktoken
import torch

_HERE = Path(__file__).resolve().parent
for _w in ("week03", "week05", "week06", "week07"):
    sys.path.insert(0, str(_HERE.parent / _w))

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def text_to_token_ids(text, tokenizer):
    """문자열 → [1, T] 텐서."""
    encoded = tokenizer.encode(text, allowed_special={"<|endoftext|>"})
    return torch.tensor(encoded).unsqueeze(0)


def token_ids_to_text(token_ids, tokenizer):
    """[1, T] 텐서 → 문자열."""
    flat = token_ids.squeeze(0)
    return tokenizer.decode(flat.tolist())


if __name__ == "__main__":
    print("=== P9-0 검증 ===")
    print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
    print(f"device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    print()
    print("--- week07 모듈 import 스모크 테스트 ---")
    from generate import generate_text_simple
    from gpt_model import GPT_CONFIG_124M, GPTModel
    print(f"  GPTModel              : {GPTModel.__name__} OK")
    print(f"  generate_text_simple  : {generate_text_simple.__name__} OK")
    print(f"  GPT_CONFIG_124M keys  : {sorted(GPT_CONFIG_124M)}")

    print()
    print("--- 유틸 왕복 변환 (문자열 → ID → 문자열) ---")
    tokenizer = tiktoken.get_encoding("gpt2")
    for s in ["Every effort moves you", "Hello, I am", "the last he painted"]:
        ids = text_to_token_ids(s, tokenizer)
        back = token_ids_to_text(ids, tokenizer)
        print(f"  {s!r:26} → shape {tuple(ids.shape)} → {back!r}  일치 {back == s}")
