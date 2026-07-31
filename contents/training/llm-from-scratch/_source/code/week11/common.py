"""week11 공통 — 10주차 가중치 이식 자산과 앞선 주차 모듈을 경로에 올린다.

주의: 10주차 `openai_load.py` 도 `import common` 을 하는데, 파이썬은 먼저 로드된
모듈을 재사용하므로 그때 잡히는 것이 이 파일이다. 그래서 9·10주차 common 이
제공하던 이름(VERDICT, MODEL_10EP, text_to_token_ids, token_ids_to_text)을
여기서도 그대로 제공해야 한다.
"""
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for _w in ("week03", "week05", "week06", "week07", "week09", "week10"):
    sys.path.insert(0, str(_HERE.parent / _w))

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

WEEK09 = _HERE.parent / "week09"
MODEL_10EP = WEEK09 / "model_10ep.pth"
VERDICT = WEEK09 / "the-verdict.txt"

# 10주차에서 이미 받아 둔 가중치를 재사용한다 (다시 받지 않는다)
WEEK10_WEIGHTS = str(_HERE.parent / "week10" / "gpt2_weights")


def text_to_token_ids(text, tokenizer):
    encoded = tokenizer.encode(text, allowed_special={"<|endoftext|>"})
    return torch.tensor(encoded).unsqueeze(0)


def token_ids_to_text(token_ids, tokenizer):
    return tokenizer.decode(token_ids.squeeze(0).tolist())
