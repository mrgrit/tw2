"""W14-G1 검사자 — P14-1 산출물이 프롬프트의 요구와 제약을 지켰는가.

학생 역할로 만든 premortem.md 를 프롬프트 문면과 대조한다.
"""
import re

text = open("premortem.md", encoding="utf-8").read()

print("=" * 70)
print("W14-G1 — P14-1 사전 부검 프롬프트 준수 검사")
print("=" * 70)

checks = []

# 요구 1 — 실패 원인 5개
causes = re.findall(r"^### 원인 (\d+) \(([^)]+)\)", text, re.M)
n = len(causes)
checks.append(("실패 원인 5개", n == 5, f"{n}개"))

# 요구 1 — 기술·일정·협업 각 1개 이상
kinds = " ".join(k for _, k in causes)
for kind in ("기술", "일정", "협업"):
    has = kind in kinds
    checks.append((f"  분류 '{kind}' 1개 이상", has,
                   f"{kinds.count(kind)}개" if has else "없음"))

# 요구 2 — 원인마다 조기 신호 1개 + 예방 조치 1개
rows = re.findall(r"^\| (\d+) \| (.+?) \| (.+?) \|$", text, re.M)
checks.append(("원인별 (조기신호, 예방조치) 표 5행", len(rows) == 5, f"{len(rows)}행"))
empty = [r[0] for r in rows if not r[1].strip() or not r[2].strip()]
checks.append(("  빈 칸 없음", not empty, f"빈 칸 행 {empty}" if empty else "없음"))
ids = [int(r[0]) for r in rows]
checks.append(("  원인 번호 1~5 와 일치", ids == [1, 2, 3, 4, 5], str(ids)))

# 요구 2 — '화요일' 명시 (프롬프트가 '화요일에 감지할 수 있는' 을 요구)
checks.append(("'화요일' 시점 명시", "화요일" in text,
               f"{text.count('화요일')}회 언급"))

# 요구 3 — 성공 기준 비판 + 측정 방법 누락 지적
has_sec3 = "## 3. 성공 기준" in text
checks.append(("성공 기준 비판 절 존재", has_sec3, "있음" if has_sec3 else "없음"))
sec3 = text.split("## 3. 성공 기준")[-1] if has_sec3 else ""
n_crit = len(re.findall(r"^\*\*기준 \d+", sec3, re.M))
checks.append(("  성공 기준 3개를 각각 비판", n_crit == 3, f"{n_crit}개"))
mm = "측정 방법이" in sec3 and ("빠졌" in sec3 or "없다" in sec3)
checks.append(("  측정 방법 누락을 명시적으로 지적", mm,
               "지적함" if mm else "지적 없음"))

# 제약 — 대안 주제 제안 금지
#
# ⚠️ 검사 정의 정정 이력: 처음에는 금지어 목록에 `"대신 "` 를 넣었다가
#    "ctx 를 1024 **대신** 64로 낮춘 소형 설정" 을 오탐했다. 이는 주제 변경이
#    아니라 같은 주제 안의 파라미터 조정이다. 제약의 뜻은 "이 프로젝트 주제를
#    버리고 다른 주제를 하라고 권하지 말 것" 이므로, 검사도 그 뜻으로 좁힌다.
#    (테스트를 약화시킨 것이 아니라, 잘못 정의된 테스트를 정확하게 고친 것이다.
#     아래 OTHER_TRACKS 검사는 오히려 처음보다 촘촘하다.)

# (a) 다른 트랙으로 갈아타라는 권유
OTHER_TRACKS = ["트랙 B", "트랙 C", "트랙 D", "트랙 E", "트랙 F",
                "DPO", "Llama", "Qwen", "Gemma", "챗 UI", "서빙",
                "분산 훈련", "DDP", "스팸 분류"]
track_hits = [w for w in OTHER_TRACKS if w in text]

# (b) 주제 자체를 갈아타라는 표현
SWITCH_PAT = [
    r"주제를?\s*(바꾸|변경|교체)",
    r"다른\s*(주제|트랙|프로젝트)(를|을)?\s*(추천|제안|권|고려|검토)",
    r"차라리\s+\S+(를|을)\s*(하|해|추천|제안)",
    r"대신에?\s+\S*(트랙|주제|프로젝트)",
    r"(포기|철회)하고\s+\S+(를|을)",
]
switch_hits = [p for p in SWITCH_PAT if re.search(p, text)]

hits = track_hits + switch_hits
checks.append(("[제약] 대안 주제 제안 없음", not hits,
               f"금지 표현 발견: {hits}" if hits else
               "다른 트랙 언급 0건 · 주제 전환 표현 0건"))

# 제약 — 이 주제(KV 캐시) 안에서만 비판했는가 (주제어 밀도로 확인)
topic_words = ("캐시", "KV", "토큰", "마스크", "위치 임베딩", "tokens/sec")
density = sum(text.count(w) for w in topic_words)
checks.append(("  주제 내 비판 (주제어 언급)", density >= 20, f"{density}회"))

print()
print(f"{'검사 항목':<38}{'결과':<8}근거")
print("-" * 78)
ok = True
for name, passed, ev in checks:
    ok &= passed
    print(f"{name:<38}{'PASS' if passed else 'FAIL':<8}{ev}")

print()
print("--- 원인 분류 내역 ---")
for num, kind in causes:
    print(f"  원인 {num}: {kind}")

print()
print("=" * 70)
print(f"W14-G1 판정: **{'PASS' if ok else 'FAIL'}**")
print("=" * 70)
