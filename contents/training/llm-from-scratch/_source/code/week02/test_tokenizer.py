"""V2-2 — SimpleTokenizerV2 pytest 3개."""
import pytest

from step1_split import split_tokens
from tokenizer_v2 import build_vocab_v2, SimpleTokenizerV2


@pytest.fixture(scope="module")
def vocab():
    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()
    return build_vocab_v2(split_tokens(raw_text))


@pytest.fixture(scope="module")
def tokenizer(vocab):
    return SimpleTokenizerV2(vocab)


def test_roundtrip(tokenizer):
    """사전에 있는 단어로만 된 문장은 encode→decode 가 원문을 복원한다.

    주의: 아포스트로피(')나 여는 따옴표(")가 들어간 문장은 이 토크나이저의 decode 규칙상
    복원되지 않는다(구두점 '앞'의 공백만 지우므로 '뒤'의 공백이 남는다). 그래서 이 테스트는
    아포스트로피·따옴표가 없는 문장을 쓴다 — 테스트를 약화시킨 것이 아니라, 복원이 성립하는
    조건을 정확히 명시한 것이다.
    """
    # 모든 단어가 the-verdict.txt 어휘사전에 실재하는지 먼저 확인한다
    text = "In the sunlit terraces of the last he painted was there."
    for word in text.replace(",", "").replace(".", "").split():
        assert word in tokenizer.str_to_int, f"{word!r} 가 사전에 없다 — 테스트 문장을 잘못 골랐다"
    assert tokenizer.decode(tokenizer.encode(text)) == text


def test_unknown(tokenizer, vocab):
    """사전에 없는 단어가 <|unk|> 의 ID 로 치환된다."""
    unk_id = vocab["<|unk|>"]
    # 'Hello' 와 'palace' 는 the-verdict.txt 에 없다
    assert "Hello" not in vocab
    assert "palace" not in vocab

    ids = tokenizer.encode("Hello, do you like tea? <|endoftext|> In the sunlit terraces of the palace.")
    assert ids[0] == unk_id          # Hello
    assert ids[-2] == unk_id         # palace
    assert tokenizer.decode(ids).startswith("<|unk|>,")


def test_vocab_size(vocab):
    """V2 어휘사전 크기는 1132 (고유 토큰 1130 + <|endoftext|> + <|unk|>)."""
    assert len(vocab) == 1132
