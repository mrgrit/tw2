"""week13 공통 — 10주차(가중치 이식)·12주차(지시 데이터) 자산을 경로에 올린다.

10주차 openai_load 가 `import common` 을 하므로, 9·10주차 common 이 제공하던
이름을 여기서도 제공한다 (11주차 common.py 와 같은 이유).
"""
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for _w in ("week03", "week05", "week06", "week07", "week09", "week10", "week12"):
    sys.path.insert(0, str(_HERE.parent / _w))

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

WEEK09 = _HERE.parent / "week09"
MODEL_10EP = WEEK09 / "model_10ep.pth"
VERDICT = WEEK09 / "the-verdict.txt"
WEEK10_WEIGHTS = str(_HERE.parent / "week10" / "gpt2_weights")
INSTRUCTION_JSON = str(_HERE.parent / "week12" / "instruction-data.json")

# 컨테이너 안에서 호스트의 Ollama 에 닿는 주소.
#   localhost:11434 는 컨테이너 자기 자신을 가리켜 연결이 거부된다(교재 P13-3 의 함정).
#   docker0 브리지 게이트웨이 주소를 써야 한다.
OLLAMA_URL = "http://172.17.0.1:11434/api/chat"
JUDGE_MODEL = "llama3.1:8b"


def text_to_token_ids(text, tokenizer):
    encoded = tokenizer.encode(text, allowed_special={"<|endoftext|>"})
    return torch.tensor(encoded).unsqueeze(0)


def token_ids_to_text(token_ids, tokenizer):
    return tokenizer.decode(token_ids.squeeze(0).tolist())


def build_instruction_loaders(batch_size=8, allowed_max_length=1024, dev=None):
    """12주차 파이프라인 그대로 train/val/test 로더를 만든다."""
    from functools import partial

    import tiktoken
    from torch.utils.data import DataLoader

    from instr_data import (InstructionDataset, custom_collate_fn, load_data,
                            split_data)

    tokenizer = tiktoken.get_encoding("gpt2")
    data = load_data(INSTRUCTION_JSON)
    train_data, test_data, val_data = split_data(data)

    collate = partial(custom_collate_fn, device=dev or device,
                      allowed_max_length=allowed_max_length)

    torch.manual_seed(123)
    train_loader = DataLoader(InstructionDataset(train_data, tokenizer),
                              batch_size=batch_size, collate_fn=collate,
                              shuffle=True, drop_last=True, num_workers=0)
    val_loader = DataLoader(InstructionDataset(val_data, tokenizer),
                            batch_size=batch_size, collate_fn=collate,
                            shuffle=False, drop_last=False, num_workers=0)
    test_loader = DataLoader(InstructionDataset(test_data, tokenizer),
                             batch_size=batch_size, collate_fn=collate,
                             shuffle=False, drop_last=False, num_workers=0)
    return (train_loader, val_loader, test_loader,
            train_data, val_data, test_data, tokenizer)
