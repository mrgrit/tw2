r"""P2-5 — SimpleTokenizerV2 (특수 토큰 지원).

V1과의 차이는 encode 한 곳뿐이다: 사전에 없는 토큰을 <|unk|> 의 ID 로 치환한다.
어휘사전에는 <|endoftext|> 와 <|unk|> 를 추가한다 (1130 → 1132).
"""
import re

SPLIT_PATTERN = r'([,.:;?_!"()\']|--|\s)'


def build_vocab_v2(tokens):
    """V1 사전 + 특수 토큰 2개. 특수 토큰을 맨 뒤에 붙여 기존 ID를 흔들지 않는다."""
    all_tokens = sorted(set(tokens))
    all_tokens.extend(["<|endoftext|>", "<|unk|>"])
    return {token: integer for integer, token in enumerate(all_tokens)}


class SimpleTokenizerV2:
    """미등록 단어를 <|unk|> 로 치환해 OOV 에서 죽지 않는 토크나이저."""

    def __init__(self, vocab):
        self.str_to_int = vocab
        self.int_to_str = {i: s for s, i in vocab.items()}

    def encode(self, text):
        """V1과 동일하게 분리한 뒤, 사전에 없는 토큰만 <|unk|> 로 바꾼다."""
        preprocessed = re.split(SPLIT_PATTERN, text)
        preprocessed = [item.strip() for item in preprocessed if item.strip()]
        # 여기가 V1과의 유일한 차이 — 이제 KeyError 가 나지 않는다
        preprocessed = [
            item if item in self.str_to_int else "<|unk|>"
            for item in preprocessed
        ]
        return [self.str_to_int[s] for s in preprocessed]

    def decode(self, ids):
        """ID → 텍스트. 구두점 앞 공백 제거 (V1과 동일 규칙 + 콜론 포함)."""
        text = " ".join([self.int_to_str[i] for i in ids])
        text = re.sub(r'\s+([,.:;?!"()\'])', r'\1', text)
        return text


if __name__ == "__main__":
    from step1_split import split_tokens

    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    vocab = build_vocab_v2(split_tokens(raw_text))
    print("새 어휘사전 크기:", len(vocab))
    print("마지막 5개:", list(vocab.items())[-5:])

    tokenizer = SimpleTokenizerV2(vocab)

    text = "Hello, do you like tea? <|endoftext|> In the sunlit terraces of the palace."
    print("\n원문   :", text)
    ids = tokenizer.encode(text)
    print("encode :", ids)
    decoded = tokenizer.decode(ids)
    print("decode :", decoded)

    # 어떤 단어가 <|unk|> 로 바뀌었는지 짚어준다
    import re as _re
    orig = [t for t in _re.split(SPLIT_PATTERN, text) if t.strip()]
    unk_words = [t for t in orig if t not in vocab]
    print("\n<|unk|> 로 바뀐 단어:", unk_words)
