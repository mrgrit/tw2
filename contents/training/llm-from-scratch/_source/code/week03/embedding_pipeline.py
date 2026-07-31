"""P3-4 — 배치 → 토큰 임베딩 → 위치 임베딩 합성까지 전체 파이프라인 (GPT-2 규모)."""
import torch
import torch.nn as nn

from dataset import create_dataloader_v1

VOCAB_SIZE = 50257
OUTPUT_DIM = 256
MAX_LENGTH = 4
BATCH_SIZE = 8

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

# 1) 로더에서 첫 배치
dataloader = create_dataloader_v1(
    raw_text, batch_size=BATCH_SIZE, max_length=MAX_LENGTH,
    stride=MAX_LENGTH, shuffle=False, drop_last=True,
)
inputs, targets = next(iter(dataloader))

# 2) 토큰 임베딩 층
torch.manual_seed(123)
token_embedding_layer = nn.Embedding(VOCAB_SIZE, OUTPUT_DIM)
token_embeddings = token_embedding_layer(inputs)

# 3) 위치 임베딩 층 — 입력은 torch.arange(max_length)
context_length = MAX_LENGTH
pos_embedding_layer = nn.Embedding(context_length, OUTPUT_DIM)
pos_embeddings = pos_embedding_layer(torch.arange(context_length))

# 4) 합성
input_embeddings = token_embeddings + pos_embeddings

# 5) shape 흐름
print("=== shape 흐름 ===")
print(f"  배치(토큰 ID)   : {tuple(inputs.shape)}")
print(f"  토큰 임베딩     : {tuple(token_embeddings.shape)}")
print(f"  위치 임베딩     : {tuple(pos_embeddings.shape)}")
print(f"  최종 합         : {tuple(input_embeddings.shape)}")

# 6) 파라미터 개수
tok_params = sum(p.numel() for p in token_embedding_layer.parameters())
pos_params = sum(p.numel() for p in pos_embedding_layer.parameters())
print()
print("=== 파라미터 개수 ===")
print(f"  토큰 임베딩 층: {tok_params:,}  (= {VOCAB_SIZE:,} x {OUTPUT_DIM})")
print(f"  위치 임베딩 층: {pos_params:,}  (= {context_length} x {OUTPUT_DIM})")
print(f"  손계산 대조   : {VOCAB_SIZE} * {OUTPUT_DIM} = {VOCAB_SIZE * OUTPUT_DIM:,} "
      f"→ 일치 {tok_params == VOCAB_SIZE * OUTPUT_DIM}")

print()
print("=== 브로드캐스팅 검증 ===")
print(f"  위치 임베딩 {tuple(pos_embeddings.shape)} 가 "
      f"토큰 임베딩 {tuple(token_embeddings.shape)} 에 더해진다.")
print("  PyTorch 브로드캐스팅 규칙: 뒤에서부터 차원을 맞춘다.")
print(f"    [{BATCH_SIZE}, {MAX_LENGTH}, {OUTPUT_DIM}]")
print(f"    [{'':>{len(str(BATCH_SIZE))}}  {MAX_LENGTH}, {OUTPUT_DIM}]  <- 앞에 크기 1 차원이 삽입된 것으로 취급")
print(f"    → [1, {MAX_LENGTH}, {OUTPUT_DIM}] 이 배치 축으로 {BATCH_SIZE}번 복제되어 더해진다.")
print("  의미: 배치 안의 8개 시퀀스가 '같은' 위치 벡터를 공유한다. 위치 0의 벡터는")
print("        어느 시퀀스에서든 동일하다 — 위치는 시퀀스 내용과 무관한 정보이기 때문이다.")

# 브로드캐스팅이 실제로 그렇게 동작하는지 확인
manual = token_embeddings + pos_embeddings.unsqueeze(0).expand(BATCH_SIZE, -1, -1)
print(f"  수동 expand 결과와 allclose: {torch.allclose(input_embeddings, manual)}")
