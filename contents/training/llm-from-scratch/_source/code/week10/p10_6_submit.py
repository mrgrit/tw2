"""P10-6 — week10 제출 마감 점검."""
import fnmatch
import os
import subprocess

REQUIRED = [
    "decoding.py", "temp_plot.png", "sampling_grid.md", "resume_experiment.md",
    "openai_load.py", "compare_generation.md", "test_decoding.py",
]
OPTIONAL = ["gutenberg_run.md"]

print("=" * 70)
print("1. 필수 산출물 점검")
print("=" * 70)
ok = True
for f in REQUIRED:
    exists = os.path.exists(f)
    ok &= exists
    size = f"{os.path.getsize(f):,} B" if exists else "—"
    print(f"  [{'O' if exists else 'X'}] {f:<26} {size}")
print("\n  (선택)")
for f in OPTIONAL:
    print(f"  [{'O' if os.path.exists(f) else '-'}] {f}  "
          f"{'(미션 6 선택 확장 — 미수행)' if not os.path.exists(f) else ''}")

print()
print("=" * 70)
print("2. 대용량 파일이 .gitignore 로 걸러지는가")
print("=" * 70)
patterns = [l.strip() for l in open(".gitignore") if l.strip() and not l.startswith("#")]
big = []
for root, dirs, files in os.walk("."):
    for name in files:
        p = os.path.join(root, name)
        sz = os.path.getsize(p)
        if sz > 5_000_000:
            rel = os.path.relpath(p, ".")
            ignored = any(fnmatch.fnmatch(rel, pat) or
                          fnmatch.fnmatch(os.path.basename(rel), pat) or
                          rel.startswith(pat.rstrip("/") + "/")
                          for pat in patterns)
            big.append((rel, sz, ignored))
big.sort(key=lambda x: -x[1])
for rel, sz, ig in big:
    print(f"  [{'무시됨' if ig else '커밋됨!'}] {sz/1e6:8.1f} MB  {rel}")
leaked = [b for b in big if not b[2]]
print(f"\n  5MB 초과 파일 {len(big)}개 중 커밋 대상: {len(leaked)}개 "
      f"→ {'PASS' if not leaked else 'FAIL'}")
print(f"  총 무시 용량: {sum(s for _, s, i in big if i)/1e9:.2f} GB")

print()
print("=" * 70)
print("3. pytest 최종 실행")
print("=" * 70)
r = subprocess.run(["python3", "-m", "pytest", "test_decoding.py", "-q"],
                   capture_output=True, text=True)
print("  " + [l for l in r.stdout.strip().split("\n") if "passed" in l or "failed" in l][-1])

print()
print("=" * 70)
print("4. report.md 템플릿 생성")
print("=" * 70)
if not os.path.exists("report.md"):
    with open("report.md", "w", encoding="utf-8") as f:
        f.write("""# Week 10 리포트 — 말투를 조절하다

## 1. temperature 가 분포를 바꾸는 원리
(로짓/T 수식 · temp_plot.png · 엔트로피 표를 인용해 서술)

## 2. top-k 와 -inf 트릭
(5주차 코잘 마스크와의 연결)

## 3. 체크포인트와 이어 훈련
(resume_experiment.md 의 3수치 인용)

## 4. 가중치 이식에서 겪은 규약 차이
- 합쳐진 QKV 행렬 분할
- Linear 가중치 전치 (4주차 연습문제 3.1 연결)
- qkv_bias / context_length

## 5. 4모델 비교표 — 일반화는 데이터에서 나온다
(compare_generation.md 인용)

## 6. 생각해볼 문제 답
""")
    print("  report.md 생성")
else:
    print("  report.md 이미 존재")

print()
print(f"제출 판정: {'PASS' if ok and not leaked else 'FAIL'}")
