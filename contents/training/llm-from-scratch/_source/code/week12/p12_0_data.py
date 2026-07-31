"""P12-0 — instruction-data.json 확보와 구조 파악."""
import json
import os
import urllib.request

URL = ("https://raw.githubusercontent.com/rasbt/LLMs-from-scratch/main/ch07/"
       "01_main-chapter-code/instruction-data.json")
FILE = "instruction-data.json"

if not os.path.exists(FILE):
    with urllib.request.urlopen(URL, timeout=120) as r:
        open(FILE, "wb").write(r.read())
    print(f"다운로드 완료 → {FILE} ({os.path.getsize(FILE):,} B)")
else:
    print(f"{FILE} 이미 존재 ({os.path.getsize(FILE):,} B)")

data = json.load(open(FILE, encoding="utf-8"))

print()
print("=" * 68)
print("1. 항목 수와 필드 구조")
print("=" * 68)
print(f"  전체 항목 수: **{len(data)}**")
keys = sorted({k for d in data for k in d})
print(f"  필드: {keys}")
for k in keys:
    n_empty = sum(1 for d in data if not d.get(k, "").strip())
    print(f"    - {k:<12}: 존재 {sum(1 for d in data if k in d):>5} / "
          f"빈 문자열 {n_empty:>5}")

print()
print("=" * 68)
print("2. 예제 원문")
print("=" * 68)
with_input = next(d for d in data if d["input"].strip())
without_input = next(d for d in data if not d["input"].strip())

print("\n  [input 이 있는 예제]")
print(json.dumps(with_input, indent=2, ensure_ascii=False))
print("\n  [input 이 비어 있는 예제]")
print(json.dumps(without_input, indent=2, ensure_ascii=False))

print()
print("=" * 68)
print(f"[검증] 항목 수가 1,100 인가: {len(data) == 1100}  (실측 {len(data)})")
print("=" * 68)
