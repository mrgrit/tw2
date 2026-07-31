"""P3-1 — 슬라이딩 윈도우 데이터셋 (교재 2장 GPTDatasetV1과 동일 동작)."""
import tiktoken
import torch
from torch.utils.data import DataLoader, Dataset


class GPTDatasetV1(Dataset):
    """긴 텍스트 위에 길이 max_length 짜리 창을 stride 만큼 밀며 (입력, 정답) 쌍을 만든다.

    정답은 입력을 왼쪽으로 한 칸 민 것이다 — 각 위치에서 "그다음에 올 토큰"이 정답이므로
    별도의 라벨링이 필요 없다. 텍스트 자체가 라벨이다.
    """

    def __init__(self, txt, tokenizer, max_length, stride):
        self.input_ids = []
        self.target_ids = []

        # 전체 텍스트를 한 번에 인코딩한다
        token_ids = tokenizer.encode(txt)

        # 창을 stride 만큼 밀며 청크를 뜯어낸다.
        # 끝을 len - max_length 로 잡는 이유: 정답 청크가 한 칸 더 필요하기 때문
        for i in range(0, len(token_ids) - max_length, stride):
            input_chunk = token_ids[i:i + max_length]
            target_chunk = token_ids[i + 1:i + max_length + 1]
            self.input_ids.append(torch.tensor(input_chunk))
            self.target_ids.append(torch.tensor(target_chunk))

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, idx):
        return self.input_ids[idx], self.target_ids[idx]


def create_dataloader_v1(txt, batch_size=4, max_length=256, stride=128,
                         shuffle=True, drop_last=True, num_workers=0):
    """GPTDatasetV1 을 감싼 DataLoader 를 만든다."""
    tokenizer = tiktoken.get_encoding("gpt2")
    dataset = GPTDatasetV1(txt, tokenizer, max_length, stride)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        drop_last=drop_last,
        num_workers=num_workers,
    )


if __name__ == "__main__":
    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    # shuffle=False 로 난수 요소를 제거한다 (재현성)
    dataloader = create_dataloader_v1(
        raw_text, batch_size=1, max_length=4, stride=1,
        shuffle=False, drop_last=True,
    )

    data_iter = iter(dataloader)
    first_batch = next(data_iter)
    second_batch = next(data_iter)

    print("첫 배치")
    print("  입력:", first_batch[0].tolist())
    print("  정답:", first_batch[1].tolist())
    print("두 번째 배치")
    print("  입력:", second_batch[0].tolist())
    print("  정답:", second_batch[1].tolist())

    print()
    print("=== 검증: 정답이 입력을 한 칸 민 것인가 ===")
    inp = first_batch[0][0].tolist()
    tgt = first_batch[1][0].tolist()
    print(f"  입력      : {inp}")
    print(f"  입력[1:]  : {inp[1:]}")
    print(f"  정답[:-1] : {tgt[:-1]}")
    print(f"  → 입력[1:] == 정답[:-1] ? {inp[1:] == tgt[:-1]}")
    print(f"  정답의 마지막 {tgt[-1]} 은 입력 창 바로 다음 토큰이다")

    print()
    print("=== stride=1 이므로 창이 한 칸 밀렸는가 ===")
    inp2 = second_batch[0][0].tolist()
    print(f"  1번째 입력: {inp}")
    print(f"  2번째 입력: {inp2}")
    print(f"  → 1번째 정답 == 2번째 입력 ? {tgt == inp2}")
