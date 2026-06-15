#!/usr/bin/env python3
"""나머지 IP placeholder 맥락별 구체화. <id>/<본인id>(학생·에이전트 식별자)·스크립트 usage·설정문법은 보존.

attacker(공격자) → 192.168.0.202, 대상/스캔/상대 → 192.168.0.161, siem → 10.20.32.100.
<ip>/<host>/<target> 는 라인 맥락(차단룰=공격자 .202, 스캔/분석=대상 .161)으로 판단.
usage: python scripts/el34_ipfix.py <file.yaml> [--write]
"""
import sys, re, difflib
ATT="192.168.0.202"; TGT="192.168.0.161"; SIEM="10.20.32.100"
BLOCK=re.compile(r"saddr|daddr|DROP|drop|-j DROP|-s <|-d <|블록|차단|deny|reject|grep <|select\(\.src_ip|/<attacker")

def fixline(ln):
    # 명시적 공격자/대상
    ln=ln.replace("<attacker_ip>",ATT).replace("<공격자IP>",ATT).replace("<attacker>",ATT)
    ln=ln.replace("<상대IP>",TGT).replace("<대상IP>",TGT).replace("<web>",TGT).replace("<VM_IP>",TGT)
    ln=ln.replace("<siem>",SIEM)
    # 스크립트 usage 메시지(예: echo "usage: $0 <ip>")·식별자는 유지
    if "usage:" in ln or "$0" in ln:
        return ln
    if re.search(r"<(ip|host|target)>", ln):
        repl = ATT if BLOCK.search(ln) else TGT   # 차단/분석=공격자, 스캔/접속=대상
        ln=re.sub(r"<(ip|host|target)>", repl, ln)
    return ln

def main():
    f=sys.argv[1]; write="--write" in sys.argv
    orig=open(f,encoding="utf-8").read()
    new="".join(fixline(l) for l in orig.splitlines(keepends=True))
    if orig==new: return
    diff=[d for d in difflib.unified_diff(orig.splitlines(),new.splitlines(),lineterm="",n=0)
          if d.startswith(("+","-")) and not d.startswith(("+++","---"))]
    print(f"{f}: {len(diff)} 변경")
    for d in diff[:20]: print("  "+d[:150])
    if write: open(f,"w",encoding="utf-8").write(new); print("  → WROTE")

if __name__=="__main__": main()
