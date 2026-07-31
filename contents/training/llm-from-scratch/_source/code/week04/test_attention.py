"""V4-2 — 어텐션 pytest 3개."""
import torch

from attention_v1v2 import SelfAttention_v1, SelfAttention_v2
from inputs import inputs


def test_weights_sum_to_one():
    """단순 어텐션 가중치 행 합이 모두 1."""
    attn_weights = torch.softmax(inputs @ inputs.T, dim=-1)
    row_sums = attn_weights.sum(dim=-1)
    assert torch.allclose(row_sums, torch.ones(inputs.shape[0]), atol=1e-6), \
        f"행 합이 1이 아니다: {row_sums.tolist()}"


def test_loop_equals_matrix():
    """루프 버전과 행렬 버전 문맥이 allclose."""
    # 루프 버전
    contexts_loop = torch.empty(inputs.shape[0], inputs.shape[1])
    for q_idx, q in enumerate(inputs):
        scores = torch.stack([torch.dot(x_i, q) for x_i in inputs])
        w = torch.softmax(scores, dim=0)
        contexts_loop[q_idx] = (w.unsqueeze(-1) * inputs).sum(dim=0)

    # 행렬 버전
    contexts_matrix = torch.softmax(inputs @ inputs.T, dim=-1) @ inputs

    assert torch.allclose(contexts_loop, contexts_matrix, atol=1e-6)


def test_v1_equals_v2_after_transfer():
    """가중치 이식(전치 포함) 후 v1 과 v2 출력이 allclose."""
    torch.manual_seed(789)
    v2 = SelfAttention_v2(d_in=3, d_out=2)
    v1 = SelfAttention_v1(d_in=3, d_out=2)

    # nn.Linear 는 (out, in) 으로 저장하므로 전치해서 옮긴다
    v1.W_query.data = v2.W_query.weight.data.T.clone()
    v1.W_key.data = v2.W_key.weight.data.T.clone()
    v1.W_value.data = v2.W_value.weight.data.T.clone()

    assert torch.allclose(v1(inputs), v2(inputs), atol=1e-6)

    # 전치를 빼면 실패해야 한다 — 테스트가 실제로 전치를 검사하고 있음을 보증
    v1_bad = SelfAttention_v1(d_in=2, d_out=2)
    v2_bad = SelfAttention_v2(d_in=2, d_out=2)
    v1_bad.W_query.data = v2_bad.W_query.weight.data.clone()   # 전치 누락
    v1_bad.W_key.data = v2_bad.W_key.weight.data.T.clone()
    v1_bad.W_value.data = v2_bad.W_value.weight.data.T.clone()
    x2 = torch.rand(6, 2)
    assert not torch.allclose(v1_bad(x2), v2_bad(x2), atol=1e-6), \
        "전치를 누락했는데도 같은 결과가 나왔다 — 테스트가 무의미하다"
