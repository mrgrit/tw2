r"""P2-2 — 어휘사전 구축과 SimpleTokenizerV1.

파이프라인: 정규식 분리 → 중복 제거·정렬 → 토큰→ID dict → encode/decode.
"""
import re

SPLIT_PATTERN = r'([,.:;?_!"()\']|--|\s)'


def build_vocab(tokens):
    """토큰 리스트에서 중복을 제거하고 정렬해 (토큰 → ID) 사전을 만든다.
    정렬하는 이유: 같은 텍스트라면 누가 언제 만들어도 같은 ID가 나와야 재현이 된다."""
    all_words = sorted(set(tokens))
    return {token: integer for integer, token in enumerate(all_words)}


class SimpleTokenizerV1:
    """가장 원시적인 토크나이저. 사전에 없는 단어(OOV)는 처리하지 못한다."""

    def __init__(self, vocab):
        # 토큰 → ID (인코딩용)
        self.str_to_int = vocab
        # ID → 토큰 (디코딩용). 사전을 뒤집어 보관한다
        self.int_to_str = {i: s for s, i in vocab.items()}

    def encode(self, text):
        """텍스트 → ID 리스트. 분리 규칙은 사전을 만들 때와 반드시 동일해야 한다."""
        preprocessed = re.split(SPLIT_PATTERN, text)
        preprocessed = [item.strip() for item in preprocessed if item.strip()]
        # 사전에 없는 토큰이면 여기서 KeyError 가 난다 — 그것이 V1의 한계다
        return [self.str_to_int[s] for s in preprocessed]

    def decode(self, ids):
        """ID 리스트 → 텍스트. 공백으로 이어붙인 뒤 구두점 앞의 공백만 되돌린다."""
        text = " ".join([self.int_to_str[i] for i in ids])
        # "hello , world ." → "hello, world."
        text = re.sub(r'\s+([,.?!"()\'])', r'\1', text)
        return text


if __name__ == "__main__":
    from step1_split import split_tokens

    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    tokens = split_tokens(raw_text)
    vocab = build_vocab(tokens)

    print("어휘사전 크기:", len(vocab))

    items = list(vocab.items())
    print("\n첫 10개 항목 (토큰, ID):")
    for tok, idx in items[:10]:
        print(f"  {tok!r:12} {idx}")
    print("\n마지막 5개 항목 (토큰, ID):")
    for tok, idx in items[-5:]:
        print(f"  {tok!r:12} {idx}")
