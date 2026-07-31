"""P12-6 — week12 제출 마감 점검."""
import os
import subprocess

REQUIRED = ["instr_data.py", "collate_evolution.md", "quality_report.md",
            "test_collate.py", "length_hist.png"]

print("=" * 68)
print("1. 필수 산출물")
print("=" * 68)
ok = True
for f in REQUIRED:
    e = os.path.exists(f)
    ok &= e
    print(f"  [{'O' if e else 'X'}] {f:<24} "
          f"{f'{os.path.getsize(f):,} B' if e else '—'}")

print()
print("=" * 68)
print("2. pytest 최종 실행")
print("=" * 68)
r = subprocess.run(["python3", "-m", "pytest", "test_collate.py", "-q"],
                   capture_output=True, text=True)
line = [l for l in r.stdout.strip().split("\n")
        if "passed" in l or "failed" in l][-1]
print("  " + line)

print()
print("=" * 68)
print("3. report.md 템플릿")
print("=" * 68)
if not os.path.exists("report.md"):
    open("report.md", "w", encoding="utf-8").write("""# Week 12 리포트 — 데이터가 절반이다

## 1. collate 3단계 — 각 단계가 왜 필요한가
(collate_evolution.md 의 장난감 배치 출력을 인용)

## 2. -100 실증의 의미 (자기 언어로)
(2토큰 손실 == 3토큰(-100) 손실. 분모까지 빠진다는 뜻)

## 3. 품질 리포트의 결론과 근거
(완전 중복 20그룹 / 스타일 모순 / 최장 91토큰)

## 4. 생각해볼 문제 답
1. -100 없이 패딩을 전부 학습시키면?
2. endoftext 를 하나도 안 남기면?
3. [연습문제 7.2] 지시 구간도 학습 vs 응답만 학습 — 내 입장
4. 훈련/추론 템플릿 미묘한 차이의 증상과 이를 잡는 테스트 설계
5. 1,100 vs Alpaca 52,000
""")
    print("  report.md 생성")
else:
    print("  report.md 이미 존재")

print()
print(f"제출 판정: {'PASS' if ok and 'failed' not in line else 'FAIL'}")
