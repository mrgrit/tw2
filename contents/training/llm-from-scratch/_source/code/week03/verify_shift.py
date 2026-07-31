"""V3-1 항목2 — 시프트 관계를 코드로 일반 검증.

shuffle=False 로더에서 연속한 샘플 10쌍을 뽑아
  · target[i] == input[i] 를 한 칸 민 것
  · input[i+1] == input[i] 를 stride 만큼 민 것
이 항상 성립하는지 assert 로 확인한다.
"""
import tiktoken

from dataset import GPTDatasetV1

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

tokenizer = tiktoken.get_encoding("gpt2")
token_ids = tokenizer.encode(raw_text)

results = []

for max_length, stride in [(4, 1), (4, 2), (8, 3), (256, 128)]:
    ds = GPTDatasetV1(raw_text, tokenizer, max_length, stride)

    # 1) target[i] == input[i] 를 한 칸 민 것
    for i in range(10):
        inp, tgt = ds[i]
        assert inp[1:].tolist() == tgt[:-1].tolist(), \
            f"(ml={max_length},st={stride}) 샘플 {i}: 한 칸 시프트 불성립"
        # 정답의 마지막 원소는 원본 토큰열에서 입력 창 바로 다음 토큰이어야 한다
        assert tgt[-1].item() == token_ids[i * stride + max_length], \
            f"(ml={max_length},st={stride}) 샘플 {i}: 정답 마지막 원소 불일치"

    # 2) input[i+1] == input[i] 를 stride 만큼 민 것
    for i in range(10):
        inp_a, _ = ds[i]
        inp_b, _ = ds[i + 1]
        assert inp_a[stride:].tolist() == inp_b[:max_length - stride].tolist(), \
            f"(ml={max_length},st={stride}) 샘플 {i}: stride 시프트 불성립"

    results.append((max_length, stride, len(ds), "PASS"))

print("| max_length | stride | len(dataset) | 검증 항목 | 결과 |")
print("|---|---|---|---|---|")
for ml, st, n, r in results:
    print(f"| {ml} | {st} | {n} | 한 칸 시프트 / stride 시프트 (각 10쌍, assert) | {r} |")

print()
print("두 항목 모두 4개 설정 × 10쌍 = 40회 assert 통과")
