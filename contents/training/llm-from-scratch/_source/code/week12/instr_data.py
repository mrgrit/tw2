"""P12-1 ~ P12-4 — 지시 데이터 파이프라인.

format_input(Alpaca 템플릿) → 3분할 → collate 3단계 진화 → InstructionDataset/로더.
모듈로 import 하면 함수만 쓸 수 있도록 실행부는 __main__ 아래에 둔다.
"""
import json

import torch
from torch.utils.data import Dataset

PAD_TOKEN_ID = 50256
IGNORE_INDEX = -100
FILE = "instruction-data.json"


def load_data(path=FILE):
    return json.load(open(path, encoding="utf-8"))


# ---------------------------------------------------------------------------
# P12-1 — Alpaca 프롬프트 포맷터
# ---------------------------------------------------------------------------

def format_input(entry):
    """지시(+입력)를 Alpaca 골격 문자열로 조립한다.

    input 이 비어 있으면 "### Input:" 블록을 **통째로** 빼야 한다.
    빈 블록을 남기면 모델이 "### Input:\n\n" 이라는 무의미한 패턴을 학습한다.
    """
    instruction_text = (
        f"Below is an instruction that describes a task. "
        f"Write a response that appropriately completes the request."
        f"\n\n### Instruction:\n{entry['instruction']}"
    )
    input_text = f"\n\n### Input:\n{entry['input']}" if entry["input"] else ""
    return instruction_text + input_text


# ---------------------------------------------------------------------------
# P12-2 — 3분할
# ---------------------------------------------------------------------------

def split_data(data, train_frac=0.85, test_frac=0.10):
    """85 / 10 / 5 분할. 원본 순서를 그대로 쓰므로 항상 같은 분할이 나온다."""
    train_portion = int(len(data) * train_frac)
    test_portion = int(len(data) * test_frac)
    train = data[:train_portion]
    test = data[train_portion:train_portion + test_portion]
    val = data[train_portion + test_portion:]
    return train, test, val


# ---------------------------------------------------------------------------
# P12-3 — collate 3단계 진화
# ---------------------------------------------------------------------------

def custom_collate_draft_1(batch, pad_token_id=PAD_TOKEN_ID, device="cpu"):
    """draft 1 — 배치 최장+1 까지 패딩하고 마지막 토큰을 뗀 inputs 만 반환.

    왜 '+1' 인가: 다음 단계에서 targets = inputs 를 한 칸 민 것으로 만들 텐데,
    그러려면 원래 시퀀스보다 토큰이 하나 더 있어야 한다. 그 하나가
    응답 끝을 알리는 <|endoftext|> 다.
    """
    batch_max_length = max(len(item) + 1 for item in batch)
    inputs_lst = []
    for item in batch:
        new_item = item.copy()
        new_item += [pad_token_id]
        padded = new_item + [pad_token_id] * (batch_max_length - len(new_item))
        inputs_lst.append(torch.tensor(padded[:-1]))
    return torch.stack(inputs_lst).to(device)


def custom_collate_draft_2(batch, pad_token_id=PAD_TOKEN_ID, device="cpu"):
    """draft 2 — inputs 와 함께 '한 칸 민' targets 도 반환 (3주차 원리 그대로)."""
    batch_max_length = max(len(item) + 1 for item in batch)
    inputs_lst, targets_lst = [], []
    for item in batch:
        new_item = item.copy()
        new_item += [pad_token_id]
        padded = new_item + [pad_token_id] * (batch_max_length - len(new_item))
        inputs_lst.append(torch.tensor(padded[:-1]))
        targets_lst.append(torch.tensor(padded[1:]))
    return (torch.stack(inputs_lst).to(device),
            torch.stack(targets_lst).to(device))


def custom_collate_fn(batch, pad_token_id=PAD_TOKEN_ID,
                      ignore_index=IGNORE_INDEX, allowed_max_length=None,
                      device="cpu"):
    """최종 — targets 의 패딩 중 **첫 50256 하나만 남기고** 나머지를 -100 으로.

    첫 50256 을 남기는 이유: 응답이 끝나면 <|endoftext|> 를 뱉으라는 것,
    즉 '멈추는 법' 도 학습 대상이기 때문이다. 전부 지우면 모델은 어디서
    말을 끝내야 할지 배우지 못한다.
    """
    batch_max_length = max(len(item) + 1 for item in batch)
    inputs_lst, targets_lst = [], []

    for item in batch:
        new_item = item.copy()
        new_item += [pad_token_id]
        padded = new_item + [pad_token_id] * (batch_max_length - len(new_item))
        inputs = torch.tensor(padded[:-1])
        targets = torch.tensor(padded[1:])

        # 패딩 위치를 찾아 두 번째부터 -100 으로 덮는다
        mask = targets == pad_token_id
        indices = torch.nonzero(mask).squeeze()
        if indices.numel() > 1:
            targets[indices[1:]] = ignore_index

        if allowed_max_length is not None:
            inputs = inputs[:allowed_max_length]
            targets = targets[:allowed_max_length]

        inputs_lst.append(inputs)
        targets_lst.append(targets)

    return (torch.stack(inputs_lst).to(device),
            torch.stack(targets_lst).to(device))


# ---------------------------------------------------------------------------
# P12-4 — InstructionDataset
# ---------------------------------------------------------------------------

class InstructionDataset(Dataset):
    """각 항목을 format_input + "### Response:" + 정답으로 조립해 인코딩·보관."""

    def __init__(self, data, tokenizer):
        self.data = data
        self.encoded_texts = []
        for entry in data:
            full_text = (format_input(entry)
                         + f"\n\n### Response:\n{entry['output']}")
            self.encoded_texts.append(tokenizer.encode(full_text))

    def __getitem__(self, index):
        return self.encoded_texts[index]

    def __len__(self):
        return len(self.data)


# ===========================================================================
if __name__ == "__main__":
    from functools import partial

    import tiktoken
    from torch.utils.data import DataLoader

    data = load_data()

    print("=" * 74)
    print("P12-1 — 프롬프트 포맷터")
    print("=" * 74)

    with_input = next(d for d in data if d["input"].strip())
    without_input = next(d for d in data if not d["input"].strip())

    for tag, entry in (("input 있음", with_input), ("input 없음", without_input)):
        print(f"\n───── [{tag}] format_input 출력 ─────")
        print(format_input(entry))
        print(f"\n───── [{tag}] + ### Response: → 완성 훈련 텍스트 ─────")
        print(format_input(entry) + f"\n\n### Response:\n{entry['output']}")

    print()
    print("[검증] input 이 빈 항목에서 '### Input:' 블록이 통째로 빠지는가: "
          f"{'### Input:' not in format_input(without_input)}")
    print(f"        (input 있는 항목에는 있는가: "
          f"{'### Input:' in format_input(with_input)})")

    # -----------------------------------------------------------------
    print()
    print("=" * 74)
    print("P12-2 — 3분할")
    print("=" * 74)
    train_data, test_data, val_data = split_data(data)
    print(f"| 분할 | 비율 | 건수 |")
    print(f"|---|---|---|")
    print(f"| train | 85% | **{len(train_data)}** |")
    print(f"| test  | 10% | **{len(test_data)}** |")
    print(f"| val   |  5% | **{len(val_data)}** |")
    total = len(train_data) + len(test_data) + len(val_data)
    print(f"| 합계 | 100% | {total} |")
    print(f"\n[검증] 합이 1,100 인가: {total == 1100}")
    print("재현성: 원본 JSON 순서를 그대로 슬라이스하므로 셔플 시드가 필요 없다. "
          "몇 번 돌려도 같은 분할이다.")

    # -----------------------------------------------------------------
    print()
    print("=" * 74)
    print("P12-3 — collate 3단계 진화 (장난감 배치)")
    print("=" * 74)
    toy = [[0, 1, 2, 3, 4], [5, 6], [7, 8, 9]]
    print(f"공통 입력: {toy}")
    print(f"배치 최장+1 = max(5+1, 2+1, 3+1) = "
          f"{max(len(i)+1 for i in toy)}")

    d1 = custom_collate_draft_1(toy)
    d2_in, d2_tg = custom_collate_draft_2(toy)
    f_in, f_tg = custom_collate_fn(toy)

    print("\n--- draft 1 (패딩만) ---")
    print(f"inputs:\n{d1}")
    print("\n--- draft 2 (+ 한 칸 민 targets) ---")
    print(f"inputs:\n{d2_in}\ntargets:\n{d2_tg}")
    print("\n--- 최종 (+ -100 치환) ---")
    print(f"inputs:\n{f_in}\ntargets:\n{f_tg}")

    print()
    print("[검증] 최종 targets 행별 판독")
    for r in range(f_tg.shape[0]):
        row = f_tg[r].tolist()
        pad_pos = [i for i, v in enumerate(d2_tg[r].tolist()) if v == PAD_TOKEN_ID]
        ign_pos = [i for i, v in enumerate(row) if v == IGNORE_INDEX]
        n_eos = sum(1 for v in row if v == PAD_TOKEN_ID)
        print(f"  {r+1}행 {row}")
        print(f"      draft2 의 패딩 위치 {pad_pos} → 첫 위치 "
              f"{pad_pos[0] if pad_pos else '없음'} 만 50256 유지, "
              f"-100 위치 {ign_pos}")
        print(f"      50256 개수 = {n_eos}  "
              f"{'(패딩이 하나뿐이라 -100 없음)' if not ign_pos else ''}")

    # collate_evolution.md
    def fmt(t):
        return "<br>".join(str(r) for r in t.tolist())

    lines = ["# collate_evolution.md — collate 3단계 진화 (P12-3 산출물)", ""]
    lines.append(f"공통 입력 장난감 배치: `{toy}`  ·  "
                 f"배치 최장+1 = **{max(len(i)+1 for i in toy)}**")
    lines.append("")
    lines.append("| 단계 | inputs | targets | 이 단계가 추가한 것 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| **draft 1** | {fmt(d1)} | — | "
                 f"배치 최장+1 까지 `50256` 패딩 후 마지막 토큰 제거. "
                 f"길이가 제각각인 시퀀스를 한 텐서로 묶을 수 있게 됐다. |")
    lines.append(f"| **draft 2** | {fmt(d2_in)} | {fmt(d2_tg)} | "
                 f"한 칸 민 `targets`. 3주차 슬라이딩 윈도우의 그 원리 — "
                 f"정답은 '다음 토큰'이다. |")
    lines.append(f"| **최종** | {fmt(f_in)} | {fmt(f_tg)} | "
                 f"패딩 중 **첫 `50256` 하나만 남기고** 나머지를 `-100` 으로. "
                 f"패딩을 손실에서 빼되 '멈추는 법'은 남긴다. "
                 f"(+ `allowed_max_length` 잘라내기, `device` 이동) |")
    lines.append("")
    lines.append("## 최종 targets 행별 판독")
    lines.append("")
    lines.append("| 행 | targets | 패딩 위치(draft2) | 50256 유지 | -100 위치 |")
    lines.append("|---|---|---|---|---|")
    for r in range(f_tg.shape[0]):
        row = f_tg[r].tolist()
        pad_pos = [i for i, v in enumerate(d2_tg[r].tolist()) if v == PAD_TOKEN_ID]
        ign_pos = [i for i, v in enumerate(row) if v == IGNORE_INDEX]
        lines.append(f"| {r+1} | `{row}` | {pad_pos} | 위치 {pad_pos[0]} | "
                     f"{ign_pos if ign_pos else '없음 (패딩이 하나뿐)'} |")
    lines.append("")
    lines.append("각 행에서 **50256 이 정확히 한 번** 살아남았다 — "
                 "\"여기서 멈춰라\"의 학습 신호다.")
    with open("collate_evolution.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n[저장] collate_evolution.md")

    # -----------------------------------------------------------------
    print()
    print("=" * 74)
    print("P12-4 — InstructionDataset 과 로더, 마스킹 지도")
    print("=" * 74)
    tokenizer = tiktoken.get_encoding("gpt2")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    collate = partial(custom_collate_fn, device=device, allowed_max_length=1024)

    torch.manual_seed(123)
    loaders = {}
    for name, d, shuffle, drop in (("train", train_data, True, True),
                                   ("val", val_data, False, False),
                                   ("test", test_data, False, False)):
        ds = InstructionDataset(d, tokenizer)
        loaders[name] = DataLoader(ds, batch_size=8, collate_fn=collate,
                                   shuffle=shuffle, drop_last=drop, num_workers=0)

    print("| 로더 | 샘플 | 배치 수 | 첫 배치 inputs | 첫 배치 targets |")
    print("|---|---|---|---|---|")
    for name in ("train", "val", "test"):
        x, y = next(iter(loaders[name]))
        print(f"| {name} | {len(loaders[name].dataset)} | {len(loaders[name])} | "
              f"{tuple(x.shape)} | {tuple(y.shape)} |")

    # 마스킹 지도
    x, y = next(iter(loaders["train"]))
    row = 0
    ids = x[row].tolist()
    tg = y[row].tolist()
    text = tokenizer.decode(ids)

    print()
    print("--- [마스킹 지도] 첫 배치 0번 샘플 ---")
    print("\n[inputs 디코딩 전문]")
    print(text)

    # targets 가 -100 인 위치를, 그 위치에 대응하는 inputs 토큰을 ▒ 로 덮어 표시
    covered = []
    for i, tok in enumerate(ids):
        piece = tokenizer.decode([tok])
        covered.append("▒" * max(1, len(piece)) if tg[i] == IGNORE_INDEX else piece)
    print("\n[마스킹 지도 — targets 가 -100 인 구간을 ▒ 로 덮음]")
    print("".join(covered))

    n_ign = sum(1 for v in tg if v == IGNORE_INDEX)
    first_ign = next((i for i, v in enumerate(tg) if v == IGNORE_INDEX), None)
    eos_pos = [i for i, v in enumerate(tg) if v == PAD_TOKEN_ID]
    print()
    print(f"[검증] 총 길이 {len(tg)} 중 -100 이 {n_ign}개")
    print(f"       targets 의 50256 위치: {eos_pos}  (응답 종료 지점)")
    print(f"       첫 -100 위치: {first_ign}")
    print(f"       -100 이 50256 바로 다음부터 끝까지 연속인가: "
          f"{first_ign == eos_pos[0] + 1 and n_ign == len(tg) - first_ign}")
    print()
    print("       → -100 구간은 **응답 종료 후 패딩 영역에만** 있다.")
    print("       → 이 기본 구성에서는 지시·입력 부분도 **학습에 포함된다**")
    print("         (그 구간의 targets 는 -100 이 아니라 실제 다음 토큰이다).")
    print("         응답만 학습시키려면 지시 구간도 -100 으로 덮어야 한다 — "
          "연습문제 7.2 의 논쟁거리다.")
