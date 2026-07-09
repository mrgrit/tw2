#!/usr/bin/env python3
"""콘텐츠 품질 하네스 — 기계식 안티패턴 정적 탐지 (모든 훈련 과목 재사용).

사용: python3 anti_patterns.py 'contents/training/<course>/lab_week*.yaml'
원리(harness-engineering): 열거→규칙별 판정→매니페스트. 샘플링 불가(전수).
규칙은 아래 CATS 에 계속 추가한다. 각 규칙은 (이름, 심각도, 판정함수, 문맥판단필요?).
"""
import re, sys, glob, json

# el34 웹 vhost (모두 WAF 리버스프록시 뒤 — raw curl 대신 브라우저/Burp/Postman 이 사람 방식)
VHOSTS = r'(juice|dvwa|neobank|govportal|mediforum|adminconsole|ai)\.el34\.lab'
INTERNAL_IPS = ['10.20.30.1','10.20.31.2','10.20.32.80','10.20.32.100','10.20.32.110']

def _attacker_internal(ln):
    if 'ssh att@192.168.0.202' not in ln: return False
    return any(('http://'+ip in ln or 'https://'+ip in ln or ('-h http://'+ip) in ln
                or (t in ln and ip in ln)) for ip in INTERNAL_IPS for t in ['nikto','nmap','ffuf','curl'])

CATS = [
 # ── 기능 버그 (라이브 실행으로도 잡히지만 정적으로도) ──
 ('F-도달불가(attacker→내부IP)','★★★', lambda ln: _attacker_internal(ln)),
 ('F-구IP 10.20.30.202(→192.168.0.202)','★★', lambda ln: '10.20.30.202' in ln and 'ssh' in ln),
 ('F-sudo 없는 root명령','★★', lambda ln: re.search(r"ssh ccc@[0-9.]+ ['\"]?(nft |suricatasc|apache2ctl|wazuh-control|agent_control|conntrack |osqueryi|tail /var/log|/var/ossec)", ln) and 'sudo' not in ln.split('ssh ccc@')[1] if 'ssh ccc@' in ln else False),
 # ── 기계식 (사람 방식으로 바꿔야) ──
 ('M-docker exec 기계식','★★★', lambda ln: 'docker exec el34-' in ln),
 ('M-매직 -H Host+생IP','★★★', lambda ln: re.search(r'-H .Host:', ln) and re.search(r'(10\.20\.30\.1|192\.168\.0\.161|192\.168\.136)', ln)),
 ('M-제어API curl(기계 인터페이스)','★★★', lambda ln: re.search(r'curl.*(192\.168\.136|/api/(rule|scenario|status|config|siem|eve|conntrack|audit)|X-API-Key|:9201|scenario/check)', ln)),
 ('M-curl 리버스프록시=사람방식(브라우저/Burp) 병기필요','★★', lambda ln: re.search(r'curl\b', ln) and re.search('http://'+VHOSTS, ln) and 'sqlmap' not in ln and 'dalfox' not in ln),
 ('M-python -c (scapy·정당사유 외)','★★', lambda ln: re.search(r'python3? -c ', ln) and 'scapy' not in ln),
 ('M-cat<<EOF 보고서 텍스트 출력','★★', lambda ln: re.search(r"cat\s+<<'?EOF'?", ln)),
 ('M-echo 캔드 해석/결론(분석 박스체크)','★★★', lambda ln: re.search(r'echo "(→|해석|결론|정리)', ln) and '$' not in ln),
 ('M-공격인데 -o /dev/null(응답 안 봄)','★★', lambda ln: '-o /dev/null' in ln and re.search(r"\?(id|q|search|cat|x)=|UNION|<script|onerror|%27|/etc/passwd|/admin|/rest/user/login", ln)),
 ('M-2>/dev/null 에러 숨김','★', lambda ln: '2>/dev/null' in ln and re.search(r'\bssh ccc@', ln) and not re.search(r'\b(nmap|ffuf|gobuster|sqlmap|nikto|osqueryi|conntrack)\b', ln)),
 ('M-sleep 인위적 대기','★', lambda ln: re.search(r'\bsleep \d', ln)),
 ('M-grep -c/wc -l 숫자축소(verify 박스체크)','★', lambda ln: re.search(r'(grep -c |wc -l)', ln) and 'ssh ' in ln),
 ('M-for seq 반복요청(도구 대체?)','★', lambda ln: re.search(r'for .*seq 1 \d+.*curl', ln)),
]

# 병기(사람방식)가 있으면 curl/-o/dev/null 계열은 '해결'로 간주하는 카테고리
BYEONG_RESOLVABLE = ('M-curl 리버스프록시','M-공격인데 -o /dev/null')
def _steps(lines):
    """(start,end) 스텝 경계 목록 — '- order:' 기준."""
    idx=[i for i,l in enumerate(lines) if l.lstrip().startswith('- order:')]
    idx.append(len(lines)); return [(idx[k],idx[k+1]) for k in range(len(idx)-1)] or [(0,len(lines))]
def scan_file(f):
    lines=open(f,encoding='utf-8').read().split('\n'); hits={}
    steps=_steps(lines)
    def step_has_byeong(n):
        for a,b in steps:
            if a<=n-1<b:
                blk='\n'.join(lines[a:b])
                return ('브라우저' in blk) or ('Burp' in blk) or ('Postman' in blk)
        return False
    for n,ln in enumerate(lines,1):
        for name,sev,fn in CATS:
            try:
                if fn(ln):
                    if any(name.startswith(k) for k in BYEONG_RESOLVABLE) and step_has_byeong(n):
                        continue  # 병기 있음 → 해결
                    hits.setdefault(name,[]).append((n,ln.strip()))
            except: pass
    return hits

def main(pattern, show=3):
    files=sorted(glob.glob(pattern)); agg={}; per_file={}
    for f in files:
        h=scan_file(f); per_file[f.split('/')[-1]]=sum(len(v) for v in h.values())
        for name,lst in h.items(): agg[name]=agg.get(name,0)+len(lst)
    print(f"=== 안티패턴 전수 집계 ({len(files)} 파일) ===")
    total=0
    for name,sev,_ in CATS:
        c=agg.get(name,0); total+=c
        print(f"  {sev:4} {c:5d}  {name}")
    print(f"  {'':4} {total:5d}  TOTAL")
    print("\n=== 카테고리별 예시 ===")
    seen=set()
    for f in files:
        for name,lst in scan_file(f).items():
            if name not in seen and lst:
                seen.add(name); print(f"── {name} ({f.split('/')[-1]} L{lst[0][0]})\n     {lst[0][1][:95]}")
    return agg

if __name__=='__main__':
    main(sys.argv[1])
