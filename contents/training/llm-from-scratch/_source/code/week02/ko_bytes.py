"""P2-9 — 한국어 문장의 바이트 수준 관찰.

한국어 문장 하나를 gpt2 BPE 로 encode 한 뒤 토큰 ID 를 하나씩 decode 해서
"글자 중간에서 잘려 사람이 읽을 수 없는 조각(바이트 조각)"을 표시한다.
"""
import tiktoken

enc = tiktoken.get_encoding("gpt2")

sentence = "방화벽이 비정상 트래픽을 차단했다."
ids = enc.encode(sentence)

print(f"문장: {sentence}")
print(f"토큰 수: {len(ids)}")
print(f"UTF-8 바이트 수: {len(sentence.encode('utf-8'))}")
print(f"문자 수: {len(sentence)}")
print()

print("| # | ID | 복원 조각 | 읽을 수 있는가 |")
print("|---|---|---|---|")
broken = 0
for n, i in enumerate(ids, start=1):
    # 단일 토큰을 그대로 decode 하면 불완전한 UTF-8 바이트열이 될 수 있다.
    # errors='replace' 를 쓰면 깨진 자리가 U+FFFD 로 보인다.
    piece_bytes = enc.decode_single_token_bytes(i)
    try:
        piece = piece_bytes.decode("utf-8")
        readable = "O"
    except UnicodeDecodeError:
        piece = piece_bytes.decode("utf-8", errors="replace")
        readable = "X (바이트 조각)"
        broken += 1
    print(f"| {n} | {i} | `{piece}` ({piece_bytes.hex()}) | {readable} |")

print()
print(f"사람이 읽을 수 없는 바이트 조각 토큰: {broken} / {len(ids)}개")
print()
print("=== 바이트 수 대비 토큰 수 ===")
nbytes = len(sentence.encode("utf-8"))
print(f"UTF-8 바이트 {nbytes} → 토큰 {len(ids)}  (토큰당 평균 {nbytes/len(ids):.2f} 바이트)")
print()
print("=== 대조: 같은 뜻의 영어 문장 ===")
en = "The firewall blocked abnormal traffic."
en_ids = enc.encode(en)
print(f"'{en}'")
print(f"UTF-8 바이트 {len(en.encode('utf-8'))} → 토큰 {len(en_ids)}  "
      f"(토큰당 평균 {len(en.encode('utf-8'))/len(en_ids):.2f} 바이트)")
print(f"조각: {[enc.decode([i]) for i in en_ids]}")
