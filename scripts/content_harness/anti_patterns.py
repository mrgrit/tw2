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
 ('F-병합 YAML키(verify/answer_detail 흡수)','★★★', lambda ln: any(ln.find('    '+k)>0 and ln[:ln.find('    '+k)].strip() and not ln.lstrip().startswith(k) for k in ('answer_detail:','verify:','expected_output:','hint:'))),
 ('F-깨진 코드펜스(``` 병합)','★★★', lambda ln: ln.rstrip().endswith('```') and ln.strip()!='```' and not ln.strip().startswith('```') and ln.rstrip()[:-3].replace('>','').strip()!=''),
 ('F-도달불가(attacker→내부IP)','★★★', lambda ln: _attacker_internal(ln)),
 ('F-구IP 10.20.30.202(→192.168.0.202)','★★', lambda ln: '10.20.30.202' in ln and 'ssh' in ln),
 ('F-sudo 없는 root명령','★★', lambda ln: re.search(r"ssh ccc@[0-9.]+ ['\"]?(nft |suricatasc|apache2ctl|wazuh-control|agent_control|conntrack |osqueryi|tail /var/log|/var/ossec)", ln) and 'sudo' not in ln.split('ssh ccc@')[1] if 'ssh ccc@' in ln else False),
 # ── 기계식 (사람 방식으로 바꿔야) ──
 ('M-docker exec 기계식','★★★', lambda ln: 'docker exec el34-' in ln and 'docker-ok' not in ln),
 ('M-매직 -H Host+생IP','★★★', lambda ln: re.search(r'-H .Host:', ln) and re.search(r'(10\.20\.30\.1|192\.168\.0\.161|192\.168\.136)', ln)),
 ('M-제어API curl(기계 인터페이스)','★★★', lambda ln: re.search(r'curl.*(192\.168\.136|/api/(rule|scenario|status|config|siem|eve|conntrack|audit)|X-API-Key|:9201|scenario/check)', ln) and 'curl-ok' not in ln),
 # ★★★ 공격을 curl 로 (진짜 도구 sqlmap/dalfox/nikto/ffuf/wfuzz/hydra/nmap/nc/hping3 써야). 꼭 필요하면 '# curl-ok:<이유>'.
 ('M-공격을 curl로(진짜 공격도구 써라)','★★★', lambda ln: re.search(r'\bcurl\b', ln) and 'curl-ok' not in ln and re.search(r"UNION\s+SELECT|UNION%20SELECT|<script|%3Cscript|onerror\s*=|onerror%3d|OR\s+['\x27]?1['\x27]?\s*=\s*['\x27]?1|%27%20OR|\.\./\.\./|%2e%2e%2f|/etc/passwd|<\?php|%3C%3Fphp|;cat\s|%3Bcat|SLEEP\(|information_schema|-A\s+[\"']?(sqlmap|nikto|nmap|masscan|nuclei)", ln, re.I)),
 # ★★ curl 사용금지 — 꼭 필요한 경우(줄에 '# curl-ok') 아니면 진짜 도구/브라우저로. 노트 병기로는 해결 안 됨.
 ('M-curl 사용금지(진짜 도구/브라우저로)','★★', lambda ln: re.search(r'\bcurl\b', ln) and 'curl-ok' not in ln and not re.search(r'localhost|127\.0\.0\.1', ln) and re.search(r'https?://|\.el34\.lab|192\.168\.0\.(161|202)', ln) and not re.search(r"UNION\s+SELECT|UNION%20SELECT|<script|%3Cscript|onerror|%27%20OR|\.\./\.\./|%2e%2e%2f|/etc/passwd|<\?php|%3C%3Fphp|;cat\s|SLEEP\(|information_schema|-A\s+[\"']?(sqlmap|nikto|nmap)", ln, re.I)),
 # ★★ curl 을 채점 acceptable_methods/(권장) 라벨로 추천 — 진짜 도구(nc/whatweb/ffuf/hydra) 권장으로. 'curl-ok' 예외.
 ('M-curl 채점권장 라벨(진짜 도구 권장으로)','★★', lambda ln: re.search(r'\bcurl\b', ln) and 'curl-ok' not in ln and ('acceptable_methods' in ln or '(권장)' in ln)),
 # ★★ 강의/프로즈의 실제 curl 명령(curl -flag / curl /path / curl http). 부정("curl 아니라 ssh로")·IOC/탐지 시그니처는 제외.
 ('M-강의 curl 명령(nc/진짜 도구로)','★★', lambda ln: (re.search(r"\bcurl\s+[\"']?(-[A-Za-z]|/|https?://)", ln) or re.search(r'curl\s*·|·\s*curl|curl robots|curl 루프', ln)) and 'curl-ok' not in ln and not re.search(r'localhost|127\.0\.0\.1', ln) and not re.search(r'(아니라|아니고|않고|않는|않게|우회하지|말고|금지|대신|하지\s?않)', ln) and not re.search(r'user_agent|흔적|시그니처|탐지|IOC|남긴다|남는다', ln, re.I)),
 # ★★ curl 을 '표준/주력 도구' 로 소개·정의하는 프로즈(튜토리얼 섹션) — nc(raw HTTP) 소개로 재집필. 부정문·탐지·curl-ok 제외.
 ('M-curl 개념정의/주력도구(nc 소개로 재집필)','★★', lambda ln: re.search(r'\bcurl\b', ln) and 'curl-ok' not in ln and re.search(r'(\*\*curl\*\*|`curl`|용어\s*—\s*curl|curl\s*—|주력 도구는[^.\n]*curl|쓰는 도구가[^.\n]*curl)', ln) and re.search(r'도구|클라이언트|주력|표준|HTTP 요청|주문서', ln) and not re.search(r'(아니라|아니고|않고|않는|않게|우회하지|말고|금지|대신|하지\s?않)', ln) and not re.search(r'user_agent|흔적|시그니처|탐지|IOC|남긴|스캐너|cmdline', ln, re.I) and not re.search(r'악성코드|내려받|다운로드|공격자|침투|베이스 이미지|distroless|미니멀|이미지에', ln)),
 # output 파싱을 python-c 로 하는 기계식만 플래그. 공격 페이로드(nohup exec b64decode = 헌팅 대상 위협)·scapy 제외.
 ('M-python -c (scapy·정당사유 외)','★★', lambda ln: re.search(r'python3? -c ', ln) and 'scapy' not in ln and not re.search(r'nohup|exec\(|b64decode|c2_beacon|beacon|time\.sleep', ln) and not re.search(r'-c [\x27"]\s*$', ln)),
 ('M-cat<<EOF 보고서 텍스트 출력','★★', lambda ln: re.search(r"cat\s+<<'?EOF'?", ln)),
 ('M-echo 캔드 해석/결론(분석 박스체크)','★★★', lambda ln: re.search(r'echo "(→|해석|결론|정리)', ln) and '$' not in ln),
 ('M-2>/dev/null 에러 숨김','★', lambda ln: '2>/dev/null' in ln and re.search(r'\bssh ccc@', ln) and not re.search(r'\b(nmap|ffuf|gobuster|sqlmap|nikto|osqueryi|conntrack|find|jq)\b', ln)),
 ('M-sleep 인위적 대기','★', lambda ln: re.search(r'\bsleep \d', ln)),
 # 표시용 카운트만 플래그. VAR=$(…wc -l…) 는 오프셋/델타 캡처(tail -n + 격리·delta)라 계산 입력 → 제외.
 ('M-grep -c/wc -l 숫자축소(verify 박스체크)','★', lambda ln: re.search(r'(grep -c |wc -l)', ln) and 'ssh ' in ln and not re.search(r'\w+=\$\(', ln)),
 ('M-for seq 반복요청(도구 대체?)','★', lambda ln: re.search(r'for .*seq 1 \d+.*curl', ln)),
]

# ★ curl 은 노트 병기로 해결 안 됨 — 진짜 도구/브라우저로 대체하거나 '# curl-ok:<이유>' 로 명시 예외.
BYEONG_RESOLVABLE = ()
def _steps(lines):
    """(start,end) 스텝 경계 목록 — '- order:' 기준."""
    idx=[i for i,l in enumerate(lines) if l.lstrip().startswith('- order:')]
    idx.append(len(lines)); return [(idx[k],idx[k+1]) for k in range(len(idx)-1)] or [(0,len(lines))]
def scan_file(f):
    lines=open(f,encoding='utf-8').read().split('\n'); hits={}
    steps=_steps(lines)
    def step_has_byeong(n):
        return False
    for n,ln in enumerate(lines,1):
        for name,sev,fn in CATS:
            try:
                if fn(ln):
                    if any(name.startswith(k) for k in BYEONG_RESOLVABLE) and step_has_byeong(n):
                        continue  # (비활성)
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
