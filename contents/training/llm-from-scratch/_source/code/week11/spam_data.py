"""P11-1 + P11-2 — 균형화·3분할과 SpamDataset/로더.

모듈로 import 하면 SpamDataset 과 로더 생성 함수만 가져다 쓸 수 있도록
실행부는 __main__ 아래에 둔다.
"""
from pathlib import Path

import pandas as pd
import tiktoken
import torch
from torch.utils.data import DataLoader, Dataset

DATA_FILE = Path("sms_spam_collection") / "SMSSpamCollection.tsv"
PAD_TOKEN_ID = 50256          # <|endoftext|> — 2주차의 그 토큰이 '빈칸 채우기'로 재활용된다
SEED = 123


def create_balanced_dataset(df):
    """ham 을 spam 개수만큼 무작위 언더샘플링해 50:50 을 맞춘다."""
    num_spam = df[df["Label"] == "spam"].shape[0]
    ham_subset = df[df["Label"] == "ham"].sample(num_spam, random_state=SEED)
    return pd.concat([ham_subset, df[df["Label"] == "spam"]])


def random_split(df, train_frac=0.7, validation_frac=0.1):
    """셔플 후 70/10/20 분할."""
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    train_end = int(len(df) * train_frac)
    validation_end = train_end + int(len(df) * validation_frac)
    return (df[:train_end], df[train_end:validation_end], df[validation_end:])


class SpamDataset(Dataset):
    """문자 메시지를 토큰화하고 max_length 까지 50256 으로 패딩한다."""

    def __init__(self, csv_file, tokenizer, max_length=None,
                 pad_token_id=PAD_TOKEN_ID):
        self.data = pd.read_csv(csv_file)
        self.encoded_texts = [tokenizer.encode(t) for t in self.data["Text"]]

        if max_length is None:
            # 데이터 안의 최장 시퀀스에 맞춘다 (train 에서만 이렇게 결정한다)
            self.max_length = max(len(e) for e in self.encoded_texts)
        else:
            self.max_length = max_length
            # 지정된 길이를 넘는 것은 잘라낸다
            self.encoded_texts = [e[:self.max_length] for e in self.encoded_texts]

        # 모자란 자리를 패딩으로 채운다
        self.encoded_texts = [
            e + [pad_token_id] * (self.max_length - len(e))
            for e in self.encoded_texts
        ]

    def __getitem__(self, index):
        return (torch.tensor(self.encoded_texts[index], dtype=torch.long),
                torch.tensor(int(self.data.iloc[index]["Label"]), dtype=torch.long))

    def __len__(self):
        return len(self.data)


def build_loaders(batch_size=8, num_workers=0):
    """train/val/test 로더 3개. train 의 max_length 를 val/test 에 강제한다."""
    tokenizer = tiktoken.get_encoding("gpt2")
    train_ds = SpamDataset("train.csv", tokenizer, max_length=None)
    val_ds = SpamDataset("validation.csv", tokenizer, max_length=train_ds.max_length)
    test_ds = SpamDataset("test.csv", tokenizer, max_length=train_ds.max_length)

    torch.manual_seed(SEED)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=num_workers, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            num_workers=num_workers, drop_last=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False,
                             num_workers=num_workers, drop_last=False)
    return train_loader, val_loader, test_loader, train_ds, val_ds, test_ds


if __name__ == "__main__":
    print("=" * 70)
    print("P11-1 — 균형화와 3분할")
    print("=" * 70)

    df = pd.read_csv(DATA_FILE, sep="\t", header=None, names=["Label", "Text"])
    print(f"원본 {len(df):,} 건 — {dict(df['Label'].value_counts())}")

    balanced = create_balanced_dataset(df)
    print(f"균형화 후 {len(balanced):,} 건 — {dict(balanced['Label'].value_counts())}")
    print(f"  (버린 ham: {(df['Label']=='ham').sum() - (balanced['Label']=='ham').sum():,} 건)")

    balanced["Label"] = balanced["Label"].map({"ham": 0, "spam": 1})

    train_df, val_df, test_df = random_split(balanced)
    train_df.to_csv("train.csv", index=None)
    val_df.to_csv("validation.csv", index=None)
    test_df.to_csv("test.csv", index=None)

    print()
    print("| 분할 | 건수 | ham(0) | spam(1) | spam 비율 |")
    print("|---|---|---|---|---|")
    for name, d in (("train", train_df), ("validation", val_df), ("test", test_df)):
        n0 = int((d["Label"] == 0).sum())
        n1 = int((d["Label"] == 1).sum())
        print(f"| {name} | {len(d)} | {n0} | {n1} | {n1/len(d)*100:.1f}% |")
    print(f"| 합계 | {len(train_df)+len(val_df)+len(test_df)} | | | |")

    print()
    print("=" * 70)
    print("P11-2 — SpamDataset 과 로더")
    print("=" * 70)

    tokenizer = tiktoken.get_encoding("gpt2")
    train_ds = SpamDataset("train.csv", tokenizer, max_length=None)
    print(f"train max_length (데이터 내 최장 시퀀스) = **{train_ds.max_length}**")

    val_ds = SpamDataset("validation.csv", tokenizer, max_length=train_ds.max_length)
    test_ds = SpamDataset("test.csv", tokenizer, max_length=train_ds.max_length)
    print(f"val/test 에는 train 의 {train_ds.max_length} 를 강제")

    # 강제하지 않았다면 각각 얼마가 됐을지도 보여준다 (설명 근거)
    val_own = max(len(tokenizer.encode(t)) for t in
                  pd.read_csv("validation.csv")["Text"])
    test_own = max(len(tokenizer.encode(t)) for t in
                   pd.read_csv("test.csv")["Text"])
    print(f"  (강제하지 않았다면 val={val_own}, test={test_own} 이 됐을 것)")

    train_loader, val_loader, test_loader, *_ = build_loaders(batch_size=8)
    print()
    print("| 로더 | 샘플 | 배치 수 | 첫 배치 shape | shuffle | drop_last |")
    print("|---|---|---|---|---|---|")
    for name, ld, ds, sh, dl in (
        ("train", train_loader, train_ds, "O", "O"),
        ("val", val_loader, val_ds, "X", "X"),
        ("test", test_loader, test_ds, "X", "X"),
    ):
        x, y = next(iter(ld))
        print(f"| {name} | {len(ds)} | {len(ld)} | {tuple(x.shape)} | {sh} | {dl} |")

    print()
    print("=" * 70)
    print("[검증] val/test 에 train 의 max_length 를 강제하는 이유")
    print("=" * 70)
    print(f"""
훈련-평가 조건을 일치시키기 위해서다.

분류 판단은 **마지막 토큰 위치의 로짓**으로 한다. 그런데 이 모델에는 학습된
위치 임베딩이 있어서, "위치 {train_ds.max_length - 1}" 과 "위치 {val_own - 1}" 은 모델에게 서로 다른
입력이다. train 을 {train_ds.max_length} 길이로 훈련해 놓고 val 을 {val_own} 길이로 평가하면,
모델은 훈련 중 한 번도 판단해 본 적 없는 위치에서 판단하게 된다.
평가가 재는 것이 '분류 실력'이 아니라 '길이 변화에 대한 내성'이 되어버린다.

두 번째 이유는 잘림의 일관성이다. train 의 최장이 {train_ds.max_length} 이므로 train 에서는
아무 메시지도 잘리지 않았다. val/test 에 각자의 최장({val_own}, {test_own})을 쓰면 역시
아무것도 안 잘린다 — 얼핏 문제없어 보인다. 하지만 이 세 값은 데이터를 어떻게
나눴느냐에 따라 우연히 정해진 값이다. 분할 시드를 바꾸면 셋 다 달라지고,
평가 점수도 따라 달라진다. train 기준으로 고정해야 **평가가 재현된다.**

실전에서는 더 분명하다. 배포된 모델은 자기가 훈련된 max_length 를 들고 다니며
들어오는 모든 입력에 그 길이를 적용한다. val/test 는 그 배포 상황의 예행연습이므로
train 의 값을 그대로 써야 한다.""")
