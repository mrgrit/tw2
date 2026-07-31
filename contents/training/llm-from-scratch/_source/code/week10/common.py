"""P10-0 — 10주차 공통 유틸.

9주차 common.py 과 같은 역할이되, week09 도 경로에 넣어 pretrain.calc_loss_loader 를
그대로 재사용한다 (P10-5 의 "9주차 calc_loss_loader 로 측정" 지시 때문).
"""
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for _w in ("week03", "week05", "week06", "week07", "week09"):
    sys.path.insert(0, str(_HERE.parent / _w))

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 9주차 산출물 경로 (week10/ 에서 실행하므로 상대 경로로 접근)
WEEK09 = _HERE.parent / "week09"
MODEL_10EP = WEEK09 / "model_10ep.pth"
VERDICT = WEEK09 / "the-verdict.txt"


def text_to_token_ids(text, tokenizer):
    encoded = tokenizer.encode(text, allowed_special={"<|endoftext|>"})
    return torch.tensor(encoded).unsqueeze(0)


def token_ids_to_text(token_ids, tokenizer):
    flat = token_ids.squeeze(0)
    return tokenizer.decode(flat.tolist())
