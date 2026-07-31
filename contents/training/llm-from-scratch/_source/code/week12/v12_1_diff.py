"""V12-1 — 교재 저장소 ch07 노트북의 format_input 출력과 문자 단위 diff.

노트북 셀 출력을 사람이 옮겨 적으면 그것 자체가 오차원이 된다.
그래서 ch07.ipynb 를 JSON 으로 파싱해 **저장된 출력 문자열을 그대로** 읽어 비교한다.
"""
import difflib
import json
import unicodedata
from pathlib import Path

from instr_data import format_input, load_data

NB = Path("/textbook/ch07/01_main-chapter-code/ch07.ipynb")
data = load_data()

nb = json.load(open(NB, encoding="utf-8"))

# format_input(data[N]) + desired_response 를 출력하는 셀을 찾아 (N, 출력) 을 모은다
refs = {}
for cell in nb["cells"]:
    if cell["cell_type"] != "code":
        continue
    src = "".join(cell["source"])
    if "format_input(data[" not in src or "print(" not in src:
        continue
    idx = int(src.split("format_input(data[")[1].split("]")[0])
    out = "".join("".join(o.get("text", [])) for o in cell.get("outputs", []))
    if out:
        refs[idx] = out

print(f"교재 노트북에서 찾은 대조 케이스: data[{sorted(refs)}]")
print()

all_ok = True
for idx in sorted(refs):
    entry = data[idx]
    mine = format_input(entry) + f"\n\n### Response:\n{entry['output']}"
    # print() 가 붙인 개행 하나를 벗겨 비교한다
    ref = refs[idx]
    ref_stripped = ref[:-1] if ref.endswith("\n") else ref

    print("=" * 72)
    print(f"data[{idx}]")
    print("=" * 72)
    ok = (mine == ref_stripped)
    all_ok &= ok
    print(f"  내 출력 길이 {len(mine)}자 / 교재 출력 길이 {len(ref_stripped)}자")
    print(f"  문자 단위 완전 일치: **{ok}**")

    if not ok:
        print("\n  --- 차이 위치 ---")
        for i, (a, b) in enumerate(zip(mine, ref_stripped)):
            if a != b:
                print(f"    첫 불일치 인덱스 {i}: 내 {a!r}"
                      f"({unicodedata.name(a, '?')}) vs 교재 {b!r}")
                print(f"    주변: 내 ...{mine[max(0,i-30):i+30]!r}")
                print(f"          교재 ...{ref_stripped[max(0,i-30):i+30]!r}")
                break
        else:
            print(f"    앞부분은 같고 길이만 다르다 "
                  f"(내 {len(mine)} vs 교재 {len(ref_stripped)})")
        print("\n  --- unified diff ---")
        for line in difflib.unified_diff(
                ref_stripped.splitlines(keepends=True),
                mine.splitlines(keepends=True),
                fromfile="교재", tofile="내출력"):
            print("   " + line.rstrip("\n"))
    else:
        # 일치할 때도 개행·공백 구성을 명시적으로 보여 준다
        print(f"  개행 수 {mine.count(chr(10))}개 일치, "
              f"'### ' 헤더 {mine.count('### ')}개 일치")

print()
print("=" * 72)
print(f"V12-1 통과 기준 (완전 일치): {'PASS' if all_ok else 'FAIL'}")
print("=" * 72)

# 추가 — input 이 빈 케이스도 검사되었는지 확인
for idx in sorted(refs):
    has = bool(data[idx]["input"].strip())
    print(f"  data[{idx}]: input {'있음' if has else '없음(### Input: 블록 생략 경로)'}")
