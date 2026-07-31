"""P2-8 — 한국어/영어 토큰 효율 비교 실험.

같은 의미의 한국어/영어 문장 쌍 10개(일상 5 + 보안 5)를 gpt2 BPE 로 인코딩해
토큰 수와 비율을 표로 정리한다.
"""
import tiktoken

enc = tiktoken.get_encoding("gpt2")

# 일상 문장 5쌍
PAIRS = [
    ("오늘 날씨가 정말 좋아서 공원에 산책을 다녀왔다.",
     "The weather was so nice today that I took a walk in the park."),
    ("내일 아침 회의는 아홉 시에 시작합니다.",
     "Tomorrow morning's meeting starts at nine o'clock."),
    ("이 식당의 김치찌개가 이 동네에서 가장 맛있다.",
     "The kimchi stew at this restaurant is the best in this neighborhood."),
    ("지하철이 고장 나서 회사에 삼십 분 늦게 도착했다.",
     "The subway broke down so I arrived at work thirty minutes late."),
    ("어제 도서관에서 빌린 책을 아직 다 읽지 못했다.",
     "I have not finished reading the book I borrowed from the library yesterday."),
    # 보안 분야 문장 5쌍
    ("방화벽이 비정상 트래픽을 차단했다.",
     "The firewall blocked abnormal traffic."),
    ("공격자가 SQL 삽입 취약점을 이용해 인증을 우회했다.",
     "The attacker bypassed authentication using an SQL injection vulnerability."),
    ("침입 탐지 시스템이 포트 스캔 시도를 경고로 기록했다.",
     "The intrusion detection system logged a port scan attempt as an alert."),
    ("모든 관리자 계정에 다중 인증을 의무적으로 적용해야 한다.",
     "Multi-factor authentication must be enforced on all administrator accounts."),
    ("랜섬웨어 감염 이후 백업에서 시스템을 복구하는 데 이틀이 걸렸다.",
     "It took two days to restore the system from backup after the ransomware infection."),
]

rows = []
for i, (ko, en) in enumerate(PAIRS, start=1):
    ko_tokens = len(enc.encode(ko))
    en_tokens = len(enc.encode(en))
    ratio = ko_tokens / en_tokens
    rows.append((i, ko, en, ko_tokens, en_tokens, ratio))

lines = []
lines.append("# ko_en_result.md — 한국어/영어 토큰 효율 비교 (P2-8 산출물)")
lines.append("")
lines.append("토크나이저: tiktoken `gpt2` (어휘 50,257)")
lines.append("")
lines.append("| 번호 | 한국어 문장 | ko 토큰 수 | en 토큰 수 | 비율 |")
lines.append("|---|---|---|---|---|")
for i, ko, en, kt, et, r in rows:
    lines.append(f"| {i} | {ko} | {kt} | {et} | {r:.2f} |")

avg = sum(r[5] for r in rows) / len(rows)
lines.append("")
lines.append(f"**평균 비율: {avg:.2f}배**")
lines.append("")

mx = max(rows, key=lambda r: r[5])
mn = min(rows, key=lambda r: r[5])
lines.append("## 관찰 — 비율이 가장 큰 쌍과 가장 작은 쌍")
lines.append("")
lines.append(f"- **가장 큰 쌍 (#{mx[0]}, {mx[5]:.2f}배)**: {mx[1]}")
lines.append(f"  - ko {mx[3]} 토큰 / en {mx[4]} 토큰")
lines.append(f"- **가장 작은 쌍 (#{mn[0]}, {mn[5]:.2f}배)**: {mn[1]}")
lines.append(f"  - ko {mn[3]} 토큰 / en {mn[4]} 토큰")

with open("ko_en_result.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines))
