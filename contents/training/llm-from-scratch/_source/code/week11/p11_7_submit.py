"""P11-7 — week11 제출 마감 점검."""
import fnmatch
import os
import subprocess

REQUIRED = ["spam_data.py", "spam_finetune.py", "acc_curve.png",
            "confusion.md", "matrix_experiment.md", "test_spam.py"]

print("=" * 70)
print("1. 필수 산출물")
print("=" * 70)
ok = True
for f in REQUIRED:
    e = os.path.exists(f)
    ok &= e
    print(f"  [{'O' if e else 'X'}] {f:<24} "
          f"{f'{os.path.getsize(f):,} B' if e else '—'}")

print()
print("=" * 70)
print("2. 원본 데이터·체크포인트가 .gitignore 대상인가")
print("=" * 70)
pats = [l.strip() for l in open(".gitignore") if l.strip() and not l.startswith("#")]


def ignored(rel):
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p)
               or rel.startswith(p.rstrip("/") + "/") for p in pats)


targets = ["sms_spam_collection/SMSSpamCollection.tsv", "sms_spam_collection.zip",
           "train.csv", "validation.csv", "test.csv", "spam_classifier.pth"]
for t in targets:
    if os.path.exists(t):
        print(f"  [{'무시됨' if ignored(t) else '커밋됨!'}] "
              f"{os.path.getsize(t)/1e6:8.2f} MB  {t}")
leak = [t for t in targets if os.path.exists(t) and not ignored(t)]
print(f"\n  누출 {len(leak)}건 → {'PASS' if not leak else 'FAIL'}")

print()
print("=" * 70)
print("3. pytest 최종 실행")
print("=" * 70)
r = subprocess.run(["python3", "-m", "pytest", "test_spam.py", "-q"],
                   capture_output=True, text=True)
print("  " + [l for l in r.stdout.strip().split("\n")
              if "passed" in l or "failed" in l][-1])

print()
print("=" * 70)
print("4. report.md 템플릿")
print("=" * 70)
if not os.path.exists("report.md"):
    open("report.md", "w", encoding="utf-8").write("""# Week 11 리포트 — 분류기가 된 GPT

## 1. 훈련 가능 파라미터 손계산 (7주차 분해표 재사용)
(블록 + 최종LN + 새 헤드. qkv_bias 설정에 주의)

## 2. ±1%p 재현 게이트 통과 여부
(교재 train 97.21 / val 97.32 / test 95.67 대비)

## 3. 오분류 3건 — 사람이 봐도 헷갈릴 만한가
(confusion.md 인용)

## 4. 한국어 입력 관찰 — '돌아간다'와 '믿을 수 있다'는 다르다

## 5. 매트릭스 해석 과제 — 나는 ___까지 풀겠다
**(에이전트 사용 금지 · 이번 주 채점 포인트 · 직접 작성할 것)**
정확도·시간·메모리 세 축에서 논증하고,
데이터가 지금의 100배라면 결론이 바뀔지 한 줄 덧붙일 것.

## 6. 생각해볼 문제 답
""")
    print("  report.md 생성")
else:
    print("  report.md 이미 존재")

print()
print(f"제출 판정: {'PASS' if ok and not leak else 'FAIL'}")
