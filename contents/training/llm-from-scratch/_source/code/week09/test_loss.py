"""V9-1 — 손실 pytest 2개."""
import math

import torch
import torch.nn.functional as F

import common  # noqa: F401  — sys.path 에 week03/05/06/07 을 등록한다
from gpt_model import GPT_CONFIG_124M, GPTModel

CFG = dict(GPT_CONFIG_124M, context_length=256)
INPUTS = torch.tensor([[16833, 3626, 6100], [40, 1107, 588]])
TARGETS = torch.tensor([[3626, 6100, 345], [1107, 588, 11311]])


def _logits():
    torch.manual_seed(123)
    model = GPTModel(CFG).eval()
    with torch.no_grad():
        return model(INPUTS)


def test_manual_equals_builtin():
    """수동 계산(softmax → 정답 확률 → log → 평균 → 부호반전)과 F.cross_entropy 가 allclose."""
    logits = _logits()
    probas = torch.softmax(logits, dim=-1)

    picked = []
    for b in range(INPUTS.shape[0]):
        picked.append(probas[b, torch.arange(TARGETS.shape[1]), TARGETS[b]])
    manual = -torch.mean(torch.log(torch.cat(picked)))

    auto = F.cross_entropy(logits.flatten(0, 1), TARGETS.flatten())
    assert torch.allclose(manual, auto, atol=1e-5), \
        f"수동 {manual.item():.6f} != 자동 {auto.item():.6f}"


def test_initial_loss_near_uniform():
    """시드 고정 무작위 모델의 손실이 ln(50257) ± 0.5 안에 있는지.

    앞으로 모델을 개조할 때마다 '초기화가 망가지지 않았는지' 잡아주는 회귀 검증이다.
    """
    logits = _logits()
    loss = F.cross_entropy(logits.flatten(0, 1), TARGETS.flatten()).item()
    ln_vocab = math.log(CFG["vocab_size"])
    assert abs(loss - ln_vocab) < 0.5, \
        f"초기 손실 {loss:.4f} 가 ln({CFG['vocab_size']})={ln_vocab:.4f} ± 0.5 범위를 벗어났다"
