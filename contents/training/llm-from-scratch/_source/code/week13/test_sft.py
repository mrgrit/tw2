"""V13-1 / P13-4 — 지시 튜닝·저지·LoRA 성질 테스트.

Ollama 가 떠 있지 않으면 저지 테스트는 skip 한다 (교재 V13-1 지시).
"""
import json

import pytest
import torch

import common  # noqa: F401
from common import WEEK10_WEIGHTS, device

import openai_load
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS

from lora import replace_linear_with_lora  # noqa: E402

BOGUS = "The weather is nice today."


def test_lora_identity_at_init():
    """LoRA 적용 직후 임의 입력의 출력이 원본과 allclose 여야 한다.

    B 를 0 으로 초기화했으므로 alpha * (x @ A @ B) 가 항상 0 이다.
    이 게이트가 깨지면 초기화나 alpha 스케일 적용이 잘못된 것이다.
    """
    torch.manual_seed(123)
    model, cfg, _ = openai_load.build("gpt2-medium (355M)")
    model.eval()

    torch.manual_seed(0)
    x = torch.randint(0, cfg["vocab_size"], (2, 24), device=device)
    with torch.no_grad():
        before = model(x).clone()

    replace_linear_with_lora(model, rank=16, alpha=16)
    model.to(device)
    model.eval()
    with torch.no_grad():
        after = model(x)

    assert torch.allclose(before, after, atol=1e-5), (
        f"LoRA 적용으로 출력이 바뀌었다. "
        f"최대 차이 {(before-after).abs().max().item():.3e}")
    # 완전히 같은지도 확인 — B=0 이면 비트 단위로 같아야 정상이다
    assert torch.equal(before, after), (
        "allclose 는 통과했으나 비트 단위로는 다르다 — "
        "곁가지가 0 이 아닌 값을 더하고 있을 수 있다")

    # LoRA 파라미터가 실제로 붙었는지도 확인 (교체가 안 됐는데 통과하면 무의미)
    n_lora = sum(1 for n, _ in model.named_parameters() if ".lora." in n)
    assert n_lora > 0, "LoRA 파라미터가 하나도 없다 — 교체가 일어나지 않았다"

    del model
    torch.cuda.empty_cache()


def _ollama_up():
    try:
        from judge import ollama_alive
        return ollama_alive() is not None
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama 미기동 — 저지 테스트 건너뜀")
def test_judge_upper_beats_lower():
    """저지 신뢰성 — 정답 자체(상한)가 무관한 문장(하한)보다 확실히 높아야 한다."""
    import statistics

    from judge import parse_score, query_model, score_prompt

    data = json.load(open("test_responses.json", encoding="utf-8"))[:5]

    upper, lower = [], []
    for e in data:
        u = parse_score(query_model(score_prompt(e, e["output"])))[0]
        low = parse_score(query_model(score_prompt(e, BOGUS)))[0]
        assert u is not None and low is not None, "저지 응답 파싱 실패"
        upper.append(u)
        lower.append(low)

    um, lm = statistics.mean(upper), statistics.mean(lower)
    assert um > lm + 20, (
        f"상한이 하한을 충분히 앞서지 못한다: 상한 {um:.1f} vs 하한 {lm:.1f}\n"
        f"  상한 점수 {upper}\n  하한 점수 {lower}")
    assert um >= 80, f"정답 자체의 평균이 {um:.1f} 로 낮다 — 저지를 신뢰하기 어렵다"
