"""V10-2 — 디코딩 성질 테스트 3개.

3번은 top-k 의 정의를 성질로 옮긴 테스트다 (5·7주차에 이은 세 번째 성질 테스트 자산).
"""
import tiktoken
import torch

import common  # noqa: F401  — sys.path 에 week03/05/06/07/09 등록
from common import MODEL_10EP, device, text_to_token_ids
from decoding import generate
from generate import generate_text_simple
from gpt_model import GPT_CONFIG_124M, GPTModel

CFG = dict(GPT_CONFIG_124M, context_length=256)
START = "Every effort moves you"


def _model():
    m = GPTModel(CFG)
    m.load_state_dict(torch.load(MODEL_10EP, map_location="cpu"))
    m.to(device)
    m.eval()
    return m


MODEL = _model()
TOKENIZER = tiktoken.get_encoding("gpt2")
IDX = text_to_token_ids(START, TOKENIZER).to(device)


def test_greedy_fallback():
    """temperature=0.0, top_k=None 이면 week07 generate_text_simple 과 완전히 동일."""
    with torch.no_grad():
        ref = generate_text_simple(MODEL, IDX, max_new_tokens=30,
                                   context_size=CFG["context_length"])
    out = generate(MODEL, IDX, max_new_tokens=30,
                   context_size=CFG["context_length"],
                   temperature=0.0, top_k=None)
    assert torch.equal(ref, out), (
        f"greedy 폴백 불일치\n ref={ref.tolist()}\n out={out.tolist()}")


def test_seed_reproducibility():
    """같은 시드·같은 설정(T=1.0, k=25) 두 번 생성은 동일해야 한다."""
    torch.manual_seed(123)
    a = generate(MODEL, IDX, max_new_tokens=30,
                 context_size=CFG["context_length"], temperature=1.0, top_k=25)
    torch.manual_seed(123)
    b = generate(MODEL, IDX, max_new_tokens=30,
                 context_size=CFG["context_length"], temperature=1.0, top_k=25)
    assert torch.equal(a, b), "같은 시드인데 결과가 다르다"
    # 시드가 다르면 달라져야 샘플링이 실제로 동작하는 것 (테스트가 무의미해지지 않도록)
    torch.manual_seed(999)
    c = generate(MODEL, IDX, max_new_tokens=30,
                 context_size=CFG["context_length"], temperature=1.0, top_k=25)
    assert not torch.equal(a, c), "시드를 바꿔도 같다 — 샘플링이 아니라 greedy 로 동작 중"


def test_topk_constraint():
    """T=1.0, k=5 로 50토큰 생성 시 매 스텝 선택 토큰이 그 시점 로짓 상위 5개 안에 있어야."""
    K = 5
    torch.manual_seed(123)
    out = generate(MODEL, IDX, max_new_tokens=50,
                   context_size=CFG["context_length"], temperature=1.0, top_k=K)

    n_start = IDX.shape[1]
    violations = []
    for step in range(n_start, out.shape[1]):
        prefix = out[:, :step][:, -CFG["context_length"]:]
        with torch.no_grad():
            logits = MODEL(prefix)[:, -1, :]
        top_ids = torch.topk(logits, K, dim=-1).indices[0]
        chosen = out[0, step]
        if chosen not in top_ids:
            rank = int((logits[0] > logits[0, chosen]).sum()) + 1
            violations.append((step - n_start, int(chosen), rank))

    assert not violations, (
        f"top-{K} 밖의 토큰이 선택된 스텝 {len(violations)}개: {violations[:5]}")
    assert out.shape[1] == n_start + 50, "50 토큰이 생성되지 않았다"


# ===========================================================================
# V10-3 — OpenAI 가중치 이식의 정합성
# ===========================================================================
import pytest  # noqa: E402

import openai_load  # noqa: E402
from pretrain import build_loaders, calc_loss_loader  # noqa: E402

_GPT124 = None


def _gpt124():
    """124M 은 로드 비용이 크므로 한 번만 만들어 재사용한다."""
    global _GPT124
    if _GPT124 is None:
        _GPT124 = openai_load.build("gpt2-small (124M)")
    return _GPT124


def test_qkv_bias_false_fails():
    """qkv_bias=False 로 124M 을 로드하면 반드시 실패해야 한다.

    이유: 원본 GPT-2 체크포인트에는 `h.N.attn.c_attn.bias` 가 존재한다.
    qkv_bias=False 면 우리 nn.Linear 의 .bias 가 None 이라 실을 자리가 없다.
    '오류가 나야 정상'인 실패 테스트다 — 조용히 넘어가면 bias 를 통째로
    버린 채 추론하게 되고, 손실이 치솟는데 원인을 찾기 어려워진다.
    """
    with pytest.raises(Exception) as exc:
        openai_load.build("gpt2-small (124M)", qkv_bias=False)
    msg = f"{type(exc.value).__name__}: {exc.value}"
    assert "bias" in msg.lower() or "NoneType" in msg, (
        f"예상과 다른 오류가 났다 — {msg}")


def test_openai_greedy_deterministic():
    """로드된 124M 의 greedy 생성을 두 번 실행하면 완전히 동일해야 한다."""
    gpt, cfg, _ = _gpt124()
    idx = text_to_token_ids(START, tokenizer=TOKENIZER).to(device)
    a = generate(gpt, idx, max_new_tokens=25,
                 context_size=cfg["context_length"], temperature=0.0)
    b = generate(gpt, idx, max_new_tokens=25,
                 context_size=cfg["context_length"], temperature=0.0)
    assert torch.equal(a, b), "greedy 인데 두 실행이 다르다"


def test_openai_val_loss_gate():
    """[품질 게이트] 로드된 124M 의 the-verdict val 손실이 5.0 미만이어야 한다.

    이식 성공 여부는 '돌아간다'가 아니라 '손실이 낮다'로 판정한다.
    전치를 빼먹거나 QKV 분할 순서를 틀리면 shape 검사는 통과해도
    손실이 10 근처(= 무작위 초기화 수준)로 치솟는다.
    """
    gpt, _, _ = _gpt124()
    with open(common.VERDICT, "r", encoding="utf-8") as f:
        text_data = f.read()
    train_loader, val_loader, _, _ = build_loaders(text_data)
    val = calc_loss_loader(val_loader, gpt, device)
    assert val < 5.0, f"val 손실 {val:.4f} — 이식이 어긋났다"
    # 무작위 초기화(≈10.98) 수준이 아니라는 것도 명시적으로 확인
    assert val < 6.0, f"val 손실 {val:.4f} 가 우리 10에폭 모델(6.3)보다 나쁘다"
