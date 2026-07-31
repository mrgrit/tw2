"""W14-G3 / W15-G2 — 교재 원문에서 배점표를 파싱해 합계를 검산한다.

손으로 더하지 않는다. 교재 markdown 을 직접 읽어 숫자를 뽑는다.
"""
import re

import sys
SRC = sys.argv[1] if len(sys.argv) > 1 else "/textbook_course/LLM_강의교재_Week14-15.md"
text = open(SRC, encoding="utf-8").read()


def table_after(heading, value_pat):
    """heading 다음의 첫 표에서 (항목, 값) 쌍을 뽑는다."""
    body = text.split(heading, 1)[1]
    rows = []
    for line in body.splitlines():
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2:
                m = re.fullmatch(value_pat, cells[1])
                if m:
                    rows.append((cells[0], int(m.group(1))))
        elif rows and (line.startswith("#") or line.startswith("---")):
            break
    return rows


print("=" * 66)
print("W14-G3 — 14.6 채점 루브릭 배점 합 = 100 인가")
print("=" * 66)
rubric = table_after("## 14.6 채점 루브릭", r"(\d+)")
for name, v in rubric:
    print(f"  {name:<20} {v:>4}")
total = sum(v for _, v in rubric)
print(f"  {'합계':<20} {total:>4}")
g3 = (total == 100)
print(f"  → W14-G3 판정: **{'PASS' if g3 else 'FAIL'}** (항목 {len(rubric)}개)")

print()
print("=" * 66)
print("W15-G2 — 15.6 기말 평가 배분 합 = 100% 인가")
print("=" * 66)
final = table_after("## 15.6 기말 평가 배분", r"(\d+)%")
for name, v in final:
    print(f"  {name:<26} {v:>4}%")
total2 = sum(v for _, v in final)
print(f"  {'합계':<26} {total2:>4}%")
g2 = (total2 == 100)
print(f"  → W15-G2 판정: **{'PASS' if g2 else 'FAIL'}** (항목 {len(final)}개)")

print()
print("=" * 66)
print("추가 검산 — 14.6 '결과 완성도' 내부 세부 배점")
print("=" * 66)
m = re.search(r"최소 통과 = (\d+), 기대 = (\d+), 도전 = (\d+)", text)
if m:
    lo, mid, hi = (int(x) for x in m.groups())
    cap = dict(rubric).get("결과 완성도")
    print(f"  최소 {lo} / 기대 {mid} / 도전 {hi}   (항목 배점 {cap})")
    ok = lo < mid < hi == cap
    print(f"  단조 증가하고 최대치가 항목 배점과 일치: "
          f"**{'PASS' if ok else 'FAIL'}**")
else:
    print("  세부 배점 문구를 찾지 못했다")

print()
print("=" * 66)
print("추가 검산 — 15.4 동료 평가 항목 수")
print("=" * 66)
peer = text.split("## 15.4 동료 평가")[1].split("##")[0]
n_peer = len([l for l in peer.splitlines()
              if l.startswith("|") and "---" not in l and "5점 기준" not in l])
print(f"  항목 {n_peer}개 × 5점 = {n_peer*5}점 만점")
print(f"  (교재는 '팀당 1분, 전원 제출' 만 명시하고 총점 환산 규칙은 없다)")
