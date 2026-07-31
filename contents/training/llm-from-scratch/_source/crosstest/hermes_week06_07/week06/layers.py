"""P6-1 + P6-2 + P6-3 — LayerNorm, GELU, FeedForward (교재 4.2~4.3절)."""
import torch
import torch.nn as nn


class LayerNorm(nn.Module):
    """각 토큰 벡터를 그 벡터 안에서 평균 0, 분산 1로 정규화한 뒤 scale·shift 를 적용한다.

    배치 정규화와 달리 배치 크기와 무관하게 동작하므로 배치 구성이 유동적인 LLM에 적합하다.
    """

    def __init__(self, emb_dim):
        super().__init__()
        self.eps = 1e-5                                # 분모가 0이 되는 것을 막는다
        self.scale = nn.Parameter(torch.ones(emb_dim))  # 학습 가능한 곱
        self.shift = nn.Parameter(torch.zeros(emb_dim))  # 학습 가능한 더하기

    def forward(self, x):
        mean = x.mean(dim=-1, keepdim=True)
        # unbiased=False (모분산). 정규화가 목적이므로 표본분산 보정을 쓰지 않는다.
        # unbiased=True 로 두면 분산이 1이 아니라 n/(n-1) 배가 되어 테스트가 깨진다.
        var = x.var(dim=-1, keepdim=True, unbiased=False)
        norm_x = (x - mean) / torch.sqrt(var + self.eps)
        return self.scale * norm_x + self.shift


class GELU(nn.Module):
    """GPT-2가 쓰는 tanh 근사식 GELU.

    ReLU는 음수를 전부 0으로 자르고 원점에서 꺾인다. GELU는 음수도 조금 통과시키며
    모든 지점에서 매끄럽게 미분된다.
    """

    def forward(self, x):
        return 0.5 * x * (
            1 + torch.tanh(
                torch.sqrt(torch.tensor(2.0 / torch.pi))
                * (x + 0.044715 * torch.pow(x, 3))
            )
        )


class FeedForward(nn.Module):
    """토큰 하나 안에서 표현을 4배로 넓혔다 다시 압축하는 2층 신경망.

    어텐션이 "토큰들 사이"를 섞는 부품이라면, FFN은 "토큰 하나 안에서" 가공하는 부품이다.
    """

    def __init__(self, cfg):
        super().__init__()
        emb_dim = cfg["emb_dim"]
        self.layers = nn.Sequential(
            nn.Linear(emb_dim, 4 * emb_dim),
            GELU(),
            nn.Linear(4 * emb_dim, emb_dim),
        )

    def forward(self, x):
        return self.layers(x)
