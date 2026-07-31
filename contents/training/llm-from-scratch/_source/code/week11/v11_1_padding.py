"""V11-1 — 패딩 손검증. 짧은 샘플 하나를 골라 원문·토큰ID·패딩후를 나란히 본다."""
import tiktoken

from spam_data import PAD_TOKEN_ID, SpamDataset

tokenizer = tiktoken.get_encoding("gpt2")
ds = SpamDataset("train.csv", tokenizer, max_length=None)

# 가장 짧은 샘플을 고른다 (패딩 구간이 길어 눈으로 확인하기 좋다)
raw_lens = [len(tokenizer.encode(t)) for t in ds.data["Text"]]
i = int(min(range(len(raw_lens)), key=lambda k: raw_lens[k]))

text = ds.data.iloc[i]["Text"]
label = int(ds.data.iloc[i]["Label"])
encoded = tokenizer.encode(text)
padded, y = ds[i]

print("=" * 70)
print(f"샘플 #{i}  (레이블 {label} = {'spam' if label else 'ham'})")
print("=" * 70)
print(f"① 원문 텍스트   : {text!r}")
print(f"② 인코딩 토큰ID : {encoded}  (길이 {len(encoded)})")
print(f"③ 패딩 후 텐서  : shape {tuple(padded.shape)}")
print(f"   앞 {len(encoded)}개  : {padded[:len(encoded)].tolist()}")
print(f"   뒤 {ds.max_length - len(encoded)}개 : "
      f"{padded[len(encoded):].tolist()[:12]} ... (전부 같은 값)")
print()
print("--- 토큰 단위 대조 ---")
for j, tid in enumerate(encoded):
    print(f"   [{j:>3}] {tid:>6}  {tokenizer.decode([tid])!r}")
print(f"   [{len(encoded):>3}] {int(padded[len(encoded)]):>6}  "
      f"{tokenizer.decode([int(padded[len(encoded)])])!r}   ← 패딩 시작")

print()
print("=" * 70)
print("검증")
print("=" * 70)
print(f"  ① 앞 {len(encoded)}개가 인코딩과 정확히 일치: "
      f"{padded[:len(encoded)].tolist() == encoded}")
tail = padded[len(encoded):]
print(f"  ② 패딩 시작({len(encoded)})부터 끝({ds.max_length-1})까지 전부 {PAD_TOKEN_ID}: "
      f"{bool((tail == PAD_TOKEN_ID).all())}")
print(f"  ③ 총 길이가 max_length({ds.max_length})와 일치: "
      f"{len(padded) == ds.max_length}")
print(f"  ④ 반환 레이블이 원본과 일치: {int(y) == label}")

print()
print("전체 데이터셋 일괄 확인:")
bad_len = [k for k in range(len(ds)) if len(ds[k][0]) != ds.max_length]
bad_pad = []
for k in range(len(ds)):
    seq = ds[k][0]
    n = len(tokenizer.encode(ds.data.iloc[k]["Text"]))
    if n < ds.max_length and not bool((seq[n:] == PAD_TOKEN_ID).all()):
        bad_pad.append(k)
print(f"  길이가 {ds.max_length} 가 아닌 샘플: {len(bad_len)}개")
print(f"  패딩 구간에 {PAD_TOKEN_ID} 아닌 값이 섞인 샘플: {len(bad_pad)}개")
