"""P7-1 — generate_text_simple 구현 및 훈련 전 생성 관찰 (교재 4.7 절).

generate_text_simple(model, idx, max_new_tokens, context_size):
  루프마다:
    (1) 입력을 context_size 이내로 뒤에서 자름
    (2) 로짓 계산
    (3) 마지막 위치 로짓의 argmax 를 뽑아
    (4) idx 뒤에 이어붙임
  torch.no_grad() 사용

torch.manual_seed(123) -> GPT_CONFIG_124M 모델 생성 -> model.eval().
"Hello, I am" 을 인코딩해 6 개 토큰 생성 후 디코딩하여 출력.
생성 전 인코딩된 시작 토큰 ID 리스트와, 생성 후 전체 토큰 수를 함께 출력.
"""

import torch
import tiktoken
from pathlib import Path
import sys
from gpt_model import GPTModel, GPT_CONFIG_124M


def generate_text_simple(model, idx, max_new_tokens, context_size):
    """model 을 이용하여 idx 뒤에 max_new_tokens 를 생성 (교재 4.7节的 simplest sampling)."""
    
    for _ in range(max_new_tokens):
        context_start = max(0, len(idx) - context_size)
        context_ids = idx[context_start:]
        
        with torch.no_grad():
            input_tensor = torch.tensor([context_ids], dtype=torch.long)
            logits = model(input_tensor)  # (1, L, vocab_size)
        
        logits = logits[0, -1]  # 마지막 토큰의 로짓
        next_token_id = torch.argmax(logits).item()
        idx.append(next_token_id)
    
    return idx


if __name__ == "__main__":
    tokenizer = tiktoken.get_encoding("gpt2")
    
    start_text = "Hello, I am"
    start_ids = list(tokenizer.encode(start_text))  # convert to regular list
    
    print(f"[!] Original encoding of '{start_text}': {start_ids}")
    print(f"[!] Number of original tokens: {len(start_ids)}")
    
    torch.manual_seed(123)
    model = GPTModel(GPT_CONFIG_124M)
    model.eval()
    
    context_size = GPT_CONFIG_124M["context_length"]
    max_generated_tokens = 6
    
    generated_ids = generate_text_simple(model, start_ids, max_generated_tokens, context_size)
    
    print(f"[!] Generated token IDs: {generated_ids}")
    print(f"[!] Total tokens after generation (including original): {len(generated_ids)}")
    print(f"[!] Original + Generated text: {tokenizer.decode(start_ids[len(start_ids)-4:])}")
