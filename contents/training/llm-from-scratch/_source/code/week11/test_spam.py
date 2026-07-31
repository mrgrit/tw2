"""V11-1 / V11-2 — 스팸 분류 파이프라인 성질 테스트."""
import tiktoken
import torch

from spam_data import PAD_TOKEN_ID, SpamDataset

TOKENIZER = tiktoken.get_encoding("gpt2")

EX_A = ("You are a winner you have been specially selected to receive "
        "$1000 cash or a $2000 award.")
EX_B = ("Hey, just wanted to check if we're still on for dinner tonight? "
        "Let me know!")

_MODEL = None


def _model():
    """훈련된 분류기를 한 번만 만들어 재사용한다."""
    global _MODEL
    if _MODEL is None:
        import common  # noqa: F401
        from common import device
        from spam_finetune import load_and_modify
        m, _ = load_and_modify("gpt2-small (124M)", strategy="b", verbose=False)
        m.load_state_dict(torch.load("spam_classifier.pth", map_location=device))
        m.to(device)
        m.eval()
        _MODEL = (m, device)
    return _MODEL


def test_padding():
    """전 샘플의 길이가 120 으로 동일하고, 패딩 구간 값이 전부 50256 이어야 한다."""
    train_ds = SpamDataset("train.csv", TOKENIZER, max_length=None)
    assert train_ds.max_length == 120, (
        f"train max_length 가 120 이 아니다: {train_ds.max_length}")

    for name in ("train.csv", "validation.csv", "test.csv"):
        ds = SpamDataset(name, TOKENIZER, max_length=train_ds.max_length)
        for i in range(len(ds)):
            seq, _ = ds[i]
            assert len(seq) == 120, f"{name}#{i} 길이 {len(seq)} != 120"

            n_real = min(len(TOKENIZER.encode(ds.data.iloc[i]["Text"])), 120)
            pad_region = seq[n_real:]
            assert bool((pad_region == PAD_TOKEN_ID).all()), (
                f"{name}#{i} 패딩 구간에 {PAD_TOKEN_ID} 아닌 값이 있다: "
                f"{pad_region[pad_region != PAD_TOKEN_ID][:5].tolist()}")


def test_known_examples():
    """교재 예문 2개를 정확히 판정해야 한다."""
    from spam_finetune import classify_review
    model, device = _model()
    a = classify_review(EX_A, model, TOKENIZER, device, max_length=120)
    b = classify_review(EX_B, model, TOKENIZER, device, max_length=120)
    assert a == "spam", f"예문 a 를 {a} 로 판정했다"
    assert b == "not spam", f"예문 b 를 {b} 로 판정했다"


def test_deterministic():
    """같은 입력을 두 번 넣으면 같은 판정이어야 한다 (argmax 이므로 무작위성 없음)."""
    from spam_finetune import classify_review
    model, device = _model()
    for txt in (EX_A, EX_B):
        r1 = classify_review(txt, model, TOKENIZER, device, max_length=120)
        r2 = classify_review(txt, model, TOKENIZER, device, max_length=120)
        assert r1 == r2, f"두 번 판정이 다르다: {r1} vs {r2}"
