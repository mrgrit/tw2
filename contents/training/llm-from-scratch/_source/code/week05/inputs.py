"""P4-0 — 교재 3장의 장난감 입력 텐서 (모든 정답지 수치의 기준).

문장 "Your journey starts with one step" 의 6개 토큰을 3차원 벡터로 표현한 6x3 텐서.
값을 임의로 바꾸면 이후 모든 정답지가 어긋난다.
"""
import torch

tokens = ["Your", "journey", "starts", "with", "one", "step"]

inputs = torch.tensor([
    [0.43, 0.15, 0.89],  # Your     (x^1)
    [0.55, 0.87, 0.66],  # journey  (x^2)
    [0.57, 0.85, 0.64],  # starts   (x^3)
    [0.22, 0.58, 0.33],  # with     (x^4)
    [0.77, 0.25, 0.10],  # one      (x^5)
    [0.05, 0.80, 0.55],  # step     (x^6)
])
