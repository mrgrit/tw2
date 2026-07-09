#!/usr/bin/env python3
"""하네스: 커리큘럼 다양성 — 15주에 걸쳐 도구·공격기법이 다양한지 vs 반복인지 측정.
반복(같은 도구/기법이 대부분 주차 지배) = 낮은 학습가치. 사용: python3 diversity.py 'contents/training/attack/lab_week*.yaml'"""
import re, sys, glob, collections
TOOLS=['nmap','sqlmap','nikto','dalfox','ffuf','gobuster','hydra','wpscan','whatweb','scapy','osqueryi',
       'nc ','ncat','curl','wget','msfvenom','msfconsole','searchsploit','john','hashcat','tcpdump','wireshark',
       'burp','postman','wfuzz','arjun','jwt_tool','crackmapexec','responder','impacket','enum4linux','nuclei','amass','subfinder','httpx']
TECHS={'SQLi(UNION)':r'UNION%?\s?SELECT|UNION SELECT','SQLi(blind)':r'sleep\(|BENCHMARK|AND 1=1',
 'XSS':r'<script|onerror|onload|alert\(|<svg','SSRF':r'169\.254|http://127\.0\.0\.1|file://',
 '경로순회':r'\.\./|%2e%2e|/etc/passwd','명령주입':r';\s*id|`id`|\|\s*id|%3Bid','LFI/RFI':r'\.\./.*\.php|php://',
 'IDOR':r'/api/\w+/\d|Products/\d|basket/\d','인증우회':r'admin.*--|OR 1=1|jwt|Bearer ','파일업로드':r'multipart|Content-Disposition|\.php.*upload',
 '역직렬화':r'pickle|__reduce__|ObjectInputStream|O:\d+:','XXE':r'<!ENTITY|SYSTEM ',
 'brute':r'seq 1 \d+.*curl|hydra','권한상승':r'SUID|-perm -4000|sudo -l|GTFO','persistence':r'crontab|authorized_keys|useradd.*bash'}
def per_week(files):
    wt=collections.OrderedDict()
    for f in sorted(files):
        wk=re.search(r'week(\d+)',f).group(1); txt=open(f,encoding='utf-8').read()
        tools=set(t.strip() for t in TOOLS if re.search(r'\b'+re.escape(t.strip())+r'\b',txt))
        techs=set(k for k,pat in TECHS.items() if re.search(pat,txt,re.I))
        wt[wk]=(tools,techs)
    return wt
if __name__=='__main__':
    wt=per_week(glob.glob(sys.argv[1]))
    toolfreq=collections.Counter(); techfreq=collections.Counter()
    print("=== 주차별 도구·기법 ===")
    for wk,(tools,techs) in wt.items():
        for t in tools: toolfreq[t]+=1
        for k in techs: techfreq[k]+=1
        print(f" W{wk}: 도구[{','.join(sorted(tools)) or '-'}]  기법[{','.join(sorted(techs)) or '-'}]")
    nweeks=len(wt)
    print(f"\n=== 도구 다양성 (총 {len(toolfreq)}종, {nweeks}주) ===")
    for t,c in toolfreq.most_common(): 
        flag=' ← 거의 매주(반복)' if c>=nweeks*0.6 else ''
        print(f"  {c:2d}/{nweeks}주  {t}{flag}")
    print(f"\n=== 기법 다양성 (총 {len(techfreq)}종) ===")
    for k,c in techfreq.most_common(): print(f"  {c:2d}/{nweeks}주  {k}")
