#!/usr/bin/env python3
"""시나리오 텍스트를 el34 인프라에 맞게 적응(학생 대상 정확성). 채점 로직 무관(검증은 라이브 테스트).

핵심: 망가지기 쉬운 '▸ 공격자 위치' 캐비엇 블록은 **사전작성된 깔끔한 el34 블록으로 통째 치환**(비문 방지).
그 외는 안전한 구문 스왑(attacker-ext→외부 VM .202, 6v6→el34(vhost .6v6.lab 보존), 구 outsider IP→.202).
diff 요약 출력 → 파일별 검토 후 --write, 이후 정적검증 + 라이브 테스트로 확인.

usage: python scripts/el34_adapt.py <file.yaml> [--write]
"""
import sys, re, difflib

VH = "\x00VH\x00"

# 표준 el34 '공격자 위치' 캐비엇(들여쓰기 4칸, description 블록 내부)
STD_CAVEAT = (
    "  ▸ 공격자 위치(중요)\n"
    "    이 주차의 Red 미션은 **망 외부 공격자 VM(192.168.0.202)** 기준이다. el34 는 공격자의 출처 IP를\n"
    "    fw→ips→web(WAF) 전 계층에 그대로 보존하므로(HAProxy 제거·NAT 출처소실 없음), Red 채점은 **대상\n"
    "    (el34) 인프라에 남은 탐지 흔적**(WAF audit / IPS / 호스트 계정·포트)과 **출처 IP(192.168.0.202)·\n"
    "    고유 태그 상관**으로 한다. 반드시 **고유 태그**를 붙여 앰비언트 노이즈와 구분되게 한다.\n"
)

def adapt(text):
    out = text
    # 1) '▸ 공격자 위치' 블록 통째 치환(다음 빈줄+▸ 또는 빈줄+키 전까지). DOTALL.
    out = re.sub(r"  ▸ 공격자 위치.*?(?=\n\n)", STD_CAVEAT.rstrip("\n"), out, count=1, flags=re.S)
    # 2) vhost 보호
    out = out.replace("6v6.lab", VH)
    # 3) attacker-ext (포트표기 포함) → 외부 공격자 VM(.202)
    out = re.sub(r"\(attacker-ext, ?SSH ?2203\)", "(외부 공격자 VM 192.168.0.202)", out)
    out = re.sub(r"\(attacker-ext\)", "(외부 공격자 VM 192.168.0.202)", out)
    out = re.sub(r"attacker-ext ?\(SSH ?2203\)", "외부 공격자 VM(192.168.0.202)", out)
    out = out.replace("attacker-ext", "외부 공격자 VM(192.168.0.202)")
    # 4) 구 outsider wan IP → 신규 외부 VM
    out = out.replace("10.20.20.202", "192.168.0.202")
    # 5) 남은 SSH 2203 정리
    out = re.sub(r" ?\(SSH ?2203\)", "", out)
    out = re.sub(r"SSH ?2203", "외부 공격자 VM(192.168.0.202)", out)
    out = re.sub(r"\b2203\b", "192.168.0.202", out)
    # 6) 인프라명 6v6 → el34 (vhost 보호됨)
    out = out.replace("6v6", "el34")
    # 7) vhost 복원
    out = out.replace(VH, "6v6.lab")
    return out

def main():
    f = sys.argv[1]; write = "--write" in sys.argv
    orig = open(f, encoding="utf-8").read()
    new = adapt(orig)
    if orig == new:
        print(f"{f}: 변경 없음"); return
    diff = [d for d in difflib.unified_diff(orig.splitlines(), new.splitlines(), lineterm="", n=0)
            if d.startswith(("+","-")) and not d.startswith(("+++","---"))]
    print(f"{f}: {len(diff)} 변경 라인")
    for d in diff[:50]:
        print("  " + d[:170])
    if "6v6.lab" in orig and "6v6.lab" not in new:
        print("  ⚠️ vhost 소실! 보류"); return
    if write:
        open(f, "w", encoding="utf-8").write(new); print("  → WROTE")

if __name__ == "__main__":
    main()
