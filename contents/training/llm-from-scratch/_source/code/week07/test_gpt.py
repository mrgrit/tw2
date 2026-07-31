"""V7-2 — GPT 모델 pytest 3개 (모두 시드 고정, eval 모드)."""
import tiktoken
import torch

from generate import generate_text_simple
from gpt_model import GPT_CONFIG_124M, GPTModel


def _model():
    torch.manual_seed(123)
    m = GPTModel(GPT_CONFIG_124M)
    m.eval()
    return m


def test_greedy_deterministic():
    """같은 시작 토큰으로 두 번 생성한 결과가 완전히 동일 (greedy 의 정의)."""
    model = _model()
    tok = tiktoken.get_encoding("gpt2")
    idx = torch.tensor([tok.encode("Hello, I am")])

    out1 = generate_text_simple(model, idx, 6, GPT_CONFIG_124M["context_length"])
    out2 = generate_text_simple(model, idx, 6, GPT_CONFIG_124M["context_length"])
    assert torch.equal(out1, out2), \
        f"greedy 인데 결과가 다르다:\n {out1.tolist()}\n {out2.tolist()}"


def test_context_crop():
    """context_size 보다 긴 입력을 줘도 오류 없이 동작하고
    출력 길이가 입력 길이 + max_new_tokens 이다."""
    cfg = dict(GPT_CONFIG_124M)
    cfg["context_length"] = 8          # 크롭을 실제로 발동시키기 위해 작게
    torch.manual_seed(123)
    model = GPTModel(cfg).eval()

    input_len = 20                     # context_size(8) 보다 길다
    idx = torch.randint(0, cfg["vocab_size"], (1, input_len))
    max_new = 5

    out = generate_text_simple(model, idx, max_new, cfg["context_length"])
    assert out.shape[1] == input_len + max_new, \
        f"출력 길이 {out.shape[1]} != {input_len} + {max_new}"
    # 입력 부분이 그대로 보존되는지도 확인
    assert torch.equal(out[:, :input_len], idx)


def test_logits_shape():
    """[2,4] 입력에 대해 로짓 [2,4,50257]."""
    model = _model()
    idx = torch.randint(0, GPT_CONFIG_124M["vocab_size"], (2, 4))
    with torch.no_grad():
        logits = model(idx)
    assert tuple(logits.shape) == (2, 4, 50257)
