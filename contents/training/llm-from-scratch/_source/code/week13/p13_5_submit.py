"""P13-5 — week13 제출 마감 점검."""
import fnmatch
import os
import subprocess

REQUIRED = ["instr_finetune.py", "sft_loss_curve.png", "test_responses.json",
            "judge.py", "judge_report.md", "lora.py", "lora_compare.md",
            "test_sft.py"]

print("=" * 70)
print("1. 필수 산출물")
print("=" * 70)
ok = True
for f in REQUIRED:
    e = os.path.exists(f)
    ok &= e
    print(f"  [{'O' if e else 'X'}] {f:<24} {f'{os.path.getsize(f):,} B' if e else '—'}")

print()
print("=" * 70)
print("2. 체크포인트가 .gitignore 대상인가")
print("=" * 70)
pats = [l.strip() for l in open(".gitignore") if l.strip() and not l.startswith("#")]
tot = 0
for f in sorted(os.listdir(".")):
    if os.path.isfile(f) and os.path.getsize(f) > 5_000_000:
        ig = any(fnmatch.fnmatch(f, p) for p in pats)
        tot += os.path.getsize(f) if ig else 0
        print(f"  [{'무시됨' if ig else '커밋됨!'}] {os.path.getsize(f)/1e6:8.1f} MB  {f}")
print(f"\n  총 무시 용량 {tot/1e9:.2f} GB")

print()
print("=" * 70)
print("3. pytest 최종 실행 (Ollama 스킵 항목 표시 포함)")
print("=" * 70)
r = subprocess.run(["python3", "-m", "pytest", "test_sft.py", "-q", "-rs"],
                   capture_output=True, text=True)
for l in r.stdout.strip().split("\n")[-4:]:
    print("  " + l)

print()
print("=" * 70)
print("4. report.md 템플릿")
print("=" * 70)
if not os.path.exists("report.md"):
    open("report.md", "w", encoding="utf-8").write("""# Week 13 리포트 — 지시를 따르는 모델, 그리고 심판

## 1. "손실 함수는 그대로, 데이터만 바뀐다"
(P13-0 튜닝 전 3.8172 → P13-1 튜닝 후 0.6131. train_model_simple 은 9주차 코드 그대로)

## 2. 저지 신뢰성 3종 검증 결과
(상한 93.0 / 하한 41.9 / 결정성 — judge_report.md 인용)

## 3. 상위 2개·하위 2개 응답 직접 읽기 + 저지 한계 사례
**(에이전트 금지 · 이번 주 채점 포인트 · 직접 작성할 것)**
- 상위 2개에 동의하는가?
- 하위 2개에 동의하는가?
- 저지의 한계 사례 최소 1개:

## 4. LoRA 게이트의 의미와 3축 비교표 자기 기준
(lora_compare.md 인용. 언제 LoRA, 언제 풀 튜닝?)

## 5. 생각해볼 문제 답
""")
    print("  report.md 생성")
else:
    print("  report.md 이미 존재")

print()
print(f"제출 판정: {'PASS' if ok else 'FAIL'}")
