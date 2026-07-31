"""P13-2 — 테스트셋 110개 응답 일괄 생성.

[제약] 생성은 결정적(greedy)으로. 평가 파이프라인에서는 다양성보다 재현성이 우선이다 —
10주차에서 배운 다이얼(T, k)을 여기서는 일부러 끈다.
"""
import argparse
import json
import random
import time

import torch

import common  # noqa: F401
from common import (INSTRUCTION_JSON, WEEK10_WEIGHTS, device,
                    text_to_token_ids, token_ids_to_text)

import openai_load
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

from decoding import generate                                    # noqa: E402
from instr_data import format_input, load_data, split_data       # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ckpt", default="sft_355m.pth")
ap.add_argument("--out", default="test_responses.json")
ap.add_argument("--lora", default=None,
                help="LoRA 설정 'rank,alpha' 를 주면 LoRA 구조로 모델을 만든 뒤 로드")
args = ap.parse_args()

data = load_data(INSTRUCTION_JSON)
_, test_data, _ = split_data(data)

model, cfg, _ = openai_load.build("gpt2-medium (355M)")
if args.lora:
    from lora import replace_linear_with_lora
    rank, alpha = (int(x) for x in args.lora.split(","))
    replace_linear_with_lora(model, rank=rank, alpha=alpha)
    model.to(device)
model.load_state_dict(torch.load(args.ckpt, map_location=device))
model.to(device)
model.eval()
print(f"{args.ckpt} 로드 완료"
      f"{f' (LoRA r={args.lora})' if args.lora else ''}")

import tiktoken
tokenizer = tiktoken.get_encoding("gpt2")

t0 = time.time()
results = []
for i, entry in enumerate(test_data, 1):
    prompt = format_input(entry)
    ids = text_to_token_ids(prompt, tokenizer).to(device)
    out = generate(model, ids, max_new_tokens=256,
                   context_size=cfg["context_length"],
                   temperature=0.0, eos_id=50256)
    full = token_ids_to_text(out, tokenizer)
    # "### Response:" 이후만 추출·정리
    tail = full[len(prompt):]
    resp = tail.replace("### Response:", "").strip()
    # 모델이 다음 문제를 지어내기 시작하면 거기서 자른다
    for stop in ("### Instruction:", "### Input:", "### Response:"):
        if stop in resp:
            resp = resp.split(stop)[0].strip()
    results.append(dict(entry, model_response=resp))
    if i % 10 == 0 or i == len(test_data):
        print(f"  {i:3d}/{len(test_data)}  ({i/len(test_data)*100:5.1f}%) "
              f"{time.time()-t0:.0f}초", flush=True)

json.dump(results, open(args.out, "w"), ensure_ascii=False, indent=2)
print(f"\n[저장] {args.out} ({len(results)}건, {time.time()-t0:.1f}초)")

empty = [i for i, r in enumerate(results) if not r["model_response"].strip()]
print(f"\n[검증] model_response 가 비어 있는 항목: **{len(empty)}건** {empty}")
print(f"        → {'PASS' if not empty else 'FAIL'} (110개 전부 비어 있지 않아야 함)")

lens = [len(tokenizer.encode(r["model_response"])) for r in results]
print(f"        응답 토큰 길이: 최소 {min(lens)} / 중앙값 {sorted(lens)[len(lens)//2]} "
      f"/ 최대 {max(lens)} / 평균 {sum(lens)/len(lens):.1f}")

print()
print("=" * 74)
print("무작위 3개 대조")
print("=" * 74)
random.seed(123)
for k in random.sample(range(len(results)), 3):
    r = results[k]
    print(f"\n[{k}] 지시: {r['instruction']}")
    if r["input"].strip():
        print(f"     입력: {r['input']}")
    print(f"     정답: {r['output']}")
    print(f"     모델: {r['model_response']}")
