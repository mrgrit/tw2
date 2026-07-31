"""V12-2 — collate 성질 테스트 3개."""
import torch

from instr_data import (IGNORE_INDEX, PAD_TOKEN_ID, custom_collate_draft_2,
                        custom_collate_fn)

TOY = [[0, 1, 2, 3, 4], [5, 6], [7, 8, 9]]


def test_collate_shapes():
    """inputs 와 targets 의 shape 가 같아야 한다."""
    inputs, targets = custom_collate_fn(TOY)
    assert inputs.shape == targets.shape, (
        f"shape 불일치: inputs {inputs.shape} vs targets {targets.shape}")
    # 배치 최장+1 에서 한 칸 뗀 길이여야 한다
    expected = max(len(i) + 1 for i in TOY) - 1
    assert inputs.shape == (len(TOY), expected), (
        f"기대 {(len(TOY), expected)} vs 실제 {tuple(inputs.shape)}")

    # allowed_max_length 를 걸어도 둘이 같이 잘려야 한다
    i2, t2 = custom_collate_fn(TOY, allowed_max_length=3)
    assert i2.shape == t2.shape == (len(TOY), 3)


def test_one_eos_survives():
    """각 행의 targets 에 50256 이 정확히 1개 있어야 한다."""
    _, targets = custom_collate_fn(TOY)
    for r in range(targets.shape[0]):
        n = int((targets[r] == PAD_TOKEN_ID).sum())
        assert n == 1, (
            f"{r}행에 50256 이 {n}개다 (1개여야 함): {targets[r].tolist()}")

    # 살아남은 50256 이 '첫 번째 패딩' 자리인지도 확인한다
    _, raw = custom_collate_draft_2(TOY)
    for r in range(targets.shape[0]):
        first_pad = int(torch.nonzero(raw[r] == PAD_TOKEN_ID)[0])
        assert int(targets[r][first_pad]) == PAD_TOKEN_ID, (
            f"{r}행: 살아남은 자리가 첫 패딩 위치({first_pad})가 아니다")
        # 그 뒤는 전부 -100
        after = targets[r][first_pad + 1:]
        assert bool((after == IGNORE_INDEX).all()), (
            f"{r}행: 첫 패딩 이후에 -100 아닌 값이 있다: {after.tolist()}")


def test_ignore_index_equivalence():
    """-100 위치는 손실에서 통째로 빠진다 — 2토큰 손실 == 3토큰(-100) 손실."""
    logits_2 = torch.tensor([[-1.0, 1.0], [-0.5, 1.5]])
    targets_2 = torch.tensor([0, 1])
    loss_2 = torch.nn.functional.cross_entropy(logits_2, targets_2)

    logits_3 = torch.cat([logits_2, torch.tensor([[-0.5, 1.5]])])
    targets_3 = torch.tensor([0, 1, IGNORE_INDEX])
    loss_3 = torch.nn.functional.cross_entropy(logits_3, targets_3)

    assert torch.equal(loss_2, loss_3), (
        f"손실이 다르다: 2토큰 {loss_2.item():.10f} vs "
        f"3토큰(-100) {loss_3.item():.10f}")

    # 대조군 — 진짜 라벨을 넣으면 달라져야 한다 (테스트가 무의미해지지 않도록)
    loss_3_real = torch.nn.functional.cross_entropy(
        logits_3, torch.tensor([0, 1, 1]))
    assert not torch.equal(loss_2, loss_3_real), (
        "세 번째를 진짜 라벨로 둬도 손실이 같다 — 대조가 성립하지 않는다")
