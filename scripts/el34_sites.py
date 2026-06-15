#!/usr/bin/env python3
"""미션 타깃을 맥락에 맞는 취약웹 + 구체 IP(192.168.0.161)로 수정. <대상_공개IP> placeholder 제거.

원칙: 맹목 dvwa 디폴트 탈피 — 시나리오 테마에 맞는 사이트(아래 SITE 매핑, 내가 판단)로.
각 사이트 실경로(SITE_EP)로 dvwa 전용 경로(/vulnerabilities/...)를 치환하되 payload·태그는 보존.
vhost(*.6v6.lab)는 el34 에서도 유효. grading 은 태그-in-modsec 라 사이트 무관(이건 학생 정확성).

usage: python scripts/el34_sites.py <file.yaml> [--write]   (SITE 에 없으면 IP만 .161 로)
"""
import sys, re, difflib, os.path as osp

IP = "192.168.0.161"
# 취약웹 vhost: juice/dvwa/neobank(은행)/govportal(정부·PII)/mediforum(의료게시판)/admin(RCE·XXE·SSRF)/ai(LLM)
SITE_EP = {  # 사이트별 대표 취약 엔드포인트(경로). dvwa 는 기존 경로 유지(None).
    "dvwa": None,
    "juice": "/rest/products/search",
    "neobank": "/api/login",
    "govportal": "/api/citizens/export.csv",
    "mediforum": "/api/debug/echo",
    "admin": "/files/read",
    "ai": "/api/chat",
}
# 시나리오 → 사이트(테마 기반 내 판단). 미지정 시 dvwa(IP만 치환).
SITE = {
    # compliance: PII→govportal, 금융/PCI→neobank, RCE·설정→admin
    "compliance-w01":"govportal","compliance-w02":"govportal","compliance-w03":"neobank",
    "compliance-w04":"admin","compliance-w05":"govportal","compliance-w06":"neobank",
    "compliance-w07":"admin","compliance-w08":"admin","compliance-w09":"dvwa",
    "compliance-w10":"govportal","compliance-w11":"dvwa","compliance-w12":"admin",
    "compliance-w13":"admin","compliance-w14":"mediforum","compliance-w15":"govportal",
    # web-vuln: 종합/모던→juice, 고전→dvwa, IDOR/API→neobank, 업로드→mediforum
    "web-vuln-w01":"dvwa","web-vuln-w02":"dvwa","web-vuln-w03":"dvwa","web-vuln-w04":"neobank",
    "web-vuln-w05":"dvwa","web-vuln-w06":"mediforum","web-vuln-w07":"mediforum","web-vuln-w08":"juice",
    "web-vuln-w09":"neobank","web-vuln-w10":"dvwa","web-vuln-w11":"admin","web-vuln-w12":"neobank",
    "web-vuln-w13":"juice","web-vuln-w14":"juice","web-vuln-w15":"juice",
    # attack-adv: SSRF/XXE/SSTI→admin, 인증→neobank, 클라우드메타→admin, AD 시뮬→dvwa
    "attack-adv-w04":"admin","attack-adv-w05":"neobank","attack-adv-w13":"admin",
    # cloud-container: 메타데이터·SSRF·소켓 노출 → admin
    "cloud-container-w01":"admin","cloud-container-w02":"admin","cloud-container-w04":"admin",
    "cloud-container-w09":"admin",
}

def adapt(text, sid):
    site = SITE.get(sid, "dvwa")
    out = text.replace("<대상_공개IP>", IP)
    if site != "dvwa":
        vhost = f"{site}.6v6.lab"
        out = out.replace("Host: dvwa.6v6.lab", f"Host: {vhost}")
        ep = SITE_EP[site]
        # dvwa 전용 경로(/vulnerabilities/<x>/) → 사이트 대표 엔드포인트(뒤따르는 ?쿼리=payload·태그 보존)
        if ep:
            out = re.sub(r"/vulnerabilities/[a-z_]+/", ep, out)
            # 경로 없는 루트 공격(http://IP/?...) → 사이트 엔드포인트
            out = out.replace(f"http://{IP}/?", f"http://{IP}{ep}?")
    return out

def main():
    f = sys.argv[1]; write = "--write" in sys.argv
    sid = osp.splitext(osp.basename(f))[0]
    orig = open(f, encoding="utf-8").read()
    new = adapt(orig, sid)
    if orig == new: print(f"{sid}: 변경 없음 (site={SITE.get(sid,'dvwa')})"); return
    diff=[d for d in difflib.unified_diff(orig.splitlines(),new.splitlines(),lineterm="",n=0)
          if d.startswith(("+","-")) and not d.startswith(("+++","---"))]
    print(f"{sid} (site={SITE.get(sid,'dvwa')}): {len(diff)} 변경")
    for d in diff[:30]: print("  "+d[:160])
    if "<대상_공개IP>" in new: print("  ⚠️ placeholder 잔존!")
    if write: open(f,"w",encoding="utf-8").write(new); print("  → WROTE")

if __name__=="__main__": main()
