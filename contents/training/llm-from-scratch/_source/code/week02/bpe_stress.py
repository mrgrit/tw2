"""V2-3 — BPE 무손실 왕복 스트레스 테스트.

무작위 영숫자·기호 문자열 5개(길이 10~30)를 encode→decode 해서
원문과 정확히 일치하는지 표로 보고한다. 불일치가 있으면 바이트 단위로 분석한다.
"""
import random
import string

import tiktoken

enc = tiktoken.get_encoding("gpt2")
random.seed(123)

CHARS = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{};:,.<>?/~"

rows = []
for n in range(1, 6):
    length = random.randint(10, 30)
    s = "".join(random.choice(CHARS) for _ in range(length))
    ids = enc.encode(s)
    back = enc.decode(ids)
    rows.append((n, s, len(ids), back == s, back))

print("| # | 문자열 | 길이 | 토큰수 | 일치 |")
print("|---|---|---|---|---|")
for n, s, ntok, ok, back in rows:
    mark = "O" if ok else "X"
    print(f"| {n} | `{s}` | {len(s)} | {ntok} | {mark} |")

bad = [r for r in rows if not r[3]]
print()
print(f"불일치: {len(bad)}건")
for n, s, ntok, ok, back in bad:
    print(f"  #{n} 원문 바이트: {s.encode('utf-8').hex()}")
    print(f"  #{n} 복원 바이트: {back.encode('utf-8').hex()}")

print()
print("판정:", "PASS — 5/5 일치" if not bad else f"FAIL — {len(bad)}건 불일치")
