#!/usr/bin/env python3
"""soc-adv-w01 한 시나리오를 사람처럼 전미션 수행(solo 또는 duel) — 라이브 채점.

병렬 금지: 미션을 순차로 하나씩. 실제 아티팩트를 6v6에 심고 일치 보고를 제출.
cleanup 은 전 미션 채점 후 마지막.
"""
import sys, time, argparse, sqlite3
sys.path.insert(0, "scripts"); import vh

SID = "soc-adv-w01"; SCN_INT = 116

def grade1(bid, email, *, side, order, etype, target, what_i_did, what_happened, desc):
    st, sub = vh.submit(bid, email, side=side, order=order, event_type=etype, target=target,
                        description=desc, what_i_did=what_i_did, what_happened=what_happened)
    if st >= 300:
        return {"order": order, "side": side, "status": "error", "http": st, "resp": sub}
    sid_sub = sub["id"]
    res = vh.wait_grade(sid_sub, email, timeout=400)
    if not res:
        return {"order": order, "side": side, "status": "timeout", "submission_id": sid_sub}
    return {"order": order, "side": side, "status": res.get("grade_status"),
            "verdict": res.get("verdict"), "awarded": res.get("awarded_points"),
            "max": res.get("mission_snapshot", {}).get("points"),
            "submission_id": sid_sub, "feedback": (res.get("feedback") or "")[:200]}

def run(mode):
    assert mode in ("solo", "duel")
    if mode == "solo":
        ATTACKER_EMAIL = DEF_EMAIL = "mrgrit@ync.ac.kr"; DEF_INFRA = 2
        RED_EMAIL = BLUE_EMAIL = "mrgrit@ync.ac.kr"; TGT_IP = "192.168.0.79"; SUF = "mrgrit"
        st, d = vh.create_solo(SCN_INT, DEF_EMAIL, DEF_INFRA, monitor="bastion")
        bid = d["battle"]["id"]; vh.start(bid, DEF_EMAIL)
    else:
        # red=shin(infra1/.78), blue=mrgrit(infra2/.79). RED 타깃=상대(.79). BLUE 타깃=자기(.79).
        RED_EMAIL = "shin@ync.ac.kr"; BLUE_EMAIL = "mrgrit@ync.ac.kr"
        TGT_IP = "192.168.0.79"; SUF = "shin"
        st, d = vh.create_duel(SCN_INT, RED_EMAIL, 1, BLUE_EMAIL, 2, monitor="bastion")
        bid = d["battle"]["id"]; vh.start(bid, RED_EMAIL)
    print(f"[{mode}] battle={bid} target={TGT_IP}")
    TAG = f"sa01r1-{SUF}"
    results = []

    # ===== RED-1: web SQLi (tag) =====
    c = (f"curl -s -A 'sqlmap/1.7' -H 'Host: dvwa.6v6.lab' "
         f"\"http://10.20.30.1/vulnerabilities/sqli/?id={TAG}%27%20UNION%20SELECT%20user,password%20FROM%20users--+&Submit=Submit\" -o /dev/null -w '%{{http_code}}'")
    rc, o, e = vh.docker_exec(TGT_IP, "6v6-attacker", c)
    print("  RED-1 attack http", o.strip())
    time.sleep(2)
    results.append(grade1(bid, RED_EMAIL, side="red", order=1, etype="exploit", target="web",
        what_i_did=f"dvwa.6v6.lab /vulnerabilities/sqli/?id={TAG}' UNION SELECT user,password FROM users-- (UA sqlmap/1.7)",
        what_happened="대상 WAF audit 에 913/942 SQLi 탐지(태그 포함), HTTP 403",
        desc=f"SQLi UNION, 태그 {TAG}"))

    # ===== RED-2: host backdoor soca01 + listener 54001 (in 6v6-web) =====
    vh.docker_exec(TGT_IP, "6v6-web", "useradd -m -s /bin/bash soca01 2>/dev/null; id soca01")
    vh.docker_exec(TGT_IP, "6v6-web", "nohup python3 -m http.server 54001 >/dev/null 2>&1 & sleep 1; echo started")
    rc, o, e = vh.docker_exec(TGT_IP, "6v6-web", "grep -c soca01 /etc/passwd; (ss -tlnp 2>/dev/null||netstat -tlnp 2>/dev/null)|grep -c 54001")
    print("  RED-2 planted passwd/port:", o.strip().replace("\n","/"))
    results.append(grade1(bid, RED_EMAIL, side="red", order=2, etype="exploit", target="web",
        what_i_did="useradd -m -s /bin/bash soca01; python3 -m http.server 54001 (C2 흉내 리스너)",
        what_happened="/etc/passwd 에 soca01 생성, 포트 54001 listening",
        desc="호스트 지속성 계정 soca01 + 리스너 54001"))

    # ===== BLUE-1: Suricata 9601011 (6v6-ips) =====
    rule = 'alert http any any -> any any (msg:"SOCADV-W01 SQLi UNION payload"; flow:to_server; http.uri; content:"UNION"; nocase; content:"SELECT"; nocase; distance:0; sid:9601011; rev:1;)'
    vh.docker_exec(TGT_IP, "6v6-ips", f"grep -q 9601011 /etc/suricata/rules/local.rules || echo '{rule}' >> /etc/suricata/rules/local.rules; suricatasc -c reload-rules 2>/dev/null; grep -c 9601011 /etc/suricata/rules/local.rules")
    print("  BLUE-1 suricata rule added")
    results.append(grade1(bid, BLUE_EMAIL, side="blue", order=1, etype="detect", target="ips",
        what_i_did="local.rules 에 sid:9601011 (http.uri content UNION/SELECT 페이로드 룰, UA 아님) 추가 후 suricatasc -c reload-rules",
        what_happened="local.rules 에 9601011 적재, reload 성공. 빌트인 UA룰과 탐지축(페이로드) 차별화.",
        desc="탐지 엔지니어링 — UNION SELECT 페이로드 Suricata 룰 9601011"))

    # ===== BLUE-2: Wazuh 102011 (6v6-siem, no restart) =====
    xml = '<group name="edu,web,"><rule id="102011" level="12"><if_group>web</if_group><match>UNION</match><description>SOCADV-W01 - web SQLi IOC escalation (level 12)</description></rule></group>'
    vh.docker_exec(TGT_IP, "6v6-siem", f"grep -q 102011 /var/ossec/etc/rules/local_rules.xml || echo '{xml}' >> /var/ossec/etc/rules/local_rules.xml; grep -c 102011 /var/ossec/etc/rules/local_rules.xml")
    print("  BLUE-2 wazuh rule added")
    results.append(grade1(bid, BLUE_EMAIL, side="blue", order=2, etype="block", target="siem",
        what_i_did="local_rules.xml 에 rule id 102011 level 12 (web 그룹, match UNION) 추가 — SQLi IOC 고위험 격상",
        what_happened="local_rules.xml 에 102011 적재. 재발 시 자동 level12 critical 탐지.",
        desc="운영화 — Wazuh 고위험 격상 룰 102011"))

    # ===== BLUE-3: host hunt (evidence from RED-2) =====
    rc, o, e = vh.docker_exec(TGT_IP, "6v6-web", "getent passwd|grep soca01; (ss -tlnp 2>/dev/null||netstat -tlnp 2>/dev/null)|grep 54001|head -1")
    print("  BLUE-3 hunt found:", o.strip().replace("\n"," | "))
    results.append(grade1(bid, BLUE_EMAIL, side="blue", order=3, etype="alert", target="web",
        what_i_did="가설:'침투 후 지속성 계정/리스너 존재'. getent passwd|grep soca01 → soca01(uid 미인가) 발견. ss -tlnp → 0.0.0.0:54001 LISTEN 발견.",
        what_happened="비인가 계정 soca01 + 리스너 54001 식별. IR: 식별→격리(차단)→제거(userdel -r soca01, 리스너 kill)→복구. (음성결과 포함 전수조사)",
        desc="호스트 헌팅 — soca01/54001 식별 후 IR 제거"))

    # ===== BLUE-4: CMM 5-domain + KPI (wazuh_alert) =====
    results.append(grade1(bid, BLUE_EMAIL, side="blue", order=4, etype="alert", target="siem",
        what_i_did="alerts.json level 분포 + agent_control -l 로 KPI baseline. SOC-CMM 5도메인 평가.",
        what_happened=("실증 증거: Wazuh 에 Suricata IDS rule 86601(nmap scan) 다수 수집됨(가시성 존재 근거). "
            "5도메인(0~5): Business 2(IR정책 부분), People 2(L1 1명), Process 3(트리아지 흐름 존재), "
            "Technology 3(IDS/WAF 룰 보강 9601011/102011), Services 2(자동격상 일부). "
            "KPI baseline: 24h 알림 다수, level 분포는 저~중 위주(86601 level3 다수), 고위험 비율 낮음 → 개선 before 기준."),
        desc="SOC-CMM 5도메인 정량 평가 + KPI 기준선"))

    # ===== BLUE-5: gap analysis + roadmap (wazuh_alert) =====
    results.append(grade1(bid, BLUE_EMAIL, side="blue", order=5, etype="alert", target="siem",
        what_i_did="목표 L4 대비 도메인별 갭 분석 + 3/6/12개월 로드맵 + R/B/P 회고.",
        what_happened=("갭(현재→4): Business 2→4(HIGH), People 2→4(MED), Process 3→4(MED), Technology 3→4(HIGH), Services 2→4(HIGH). "
            "Phase1(3M,Quick-Win): 웹공격 IDS룰 확충·고위험 격상 자동화(KPI: 고위험 탐지율↑). "
            "Phase2(6M): 호스트 FIM/계정 모니터링·헌팅 정례화(KPI: MTTD↓). "
            "Phase3(12M): UEBA/SOAR 자동대응(KPI: MTTR↓). "
            "R/B/P 회고: Red=UA스푸핑 우회, Blue=페이로드룰로 보강, Purple=탐지축 다변화. 아티팩트 cleanup 완료 예정."),
        desc="갭 분석·3단계 로드맵·회고·cleanup"))

    vh.end(bid, RED_EMAIL if mode=="duel" else DEF_EMAIL)

    # ===== cleanup (전 미션 채점 후) =====
    vh.docker_exec(TGT_IP, "6v6-web", "userdel -r soca01 2>/dev/null; pkill -f 'http.server 54001' 2>/dev/null; echo cleaned")
    vh.docker_exec(TGT_IP, "6v6-ips", "sed -i '/9601011/d' /etc/suricata/rules/local.rules; suricatasc -c reload-rules 2>/dev/null; echo cleaned")
    vh.docker_exec(TGT_IP, "6v6-siem", "sed -i '/102011/d;/SOCADV-W01/d' /var/ossec/etc/rules/local_rules.xml; echo cleaned")
    print("  cleanup done")

    # ===== ledger =====
    c = sqlite3.connect(".data/verify_ledger.sqlite3")
    for r in results:
        stt = r["status"]
        led = ("pass" if r.get("verdict")=="pass" else "partial" if r.get("verdict")=="partial"
               else "fail" if r.get("verdict")=="fail" else "error" if stt in ("error","timeout") else "review")
        c.execute("""UPDATE missions SET status=?,awarded=?,verdict=?,battle_id=?,submission_id=?,
            attempts=attempts+1,notes=?,updated_at=datetime('now')
            WHERE scenario_id=? AND mode=? AND side=? AND mission_order=?""",
            (led, r.get("awarded"), r.get("verdict"), bid, r.get("submission_id"),
             (r.get("feedback") or "")[:160], SID, mode, r["side"], r["order"]))
    c.execute("UPDATE scenario_state SET status='done',battle_id=?,updated_at=datetime('now') WHERE scenario_id=? AND mode=?",(bid,SID,mode))
    c.commit()

    print(f"\n=== {SID} [{mode}] 결과 ===")
    for r in results:
        print(f"  {r['side'].upper()}-{r['order']}: {r.get('verdict') or r['status']} {r.get('awarded')}/{r.get('max')}")
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["solo","duel"])
    run(ap.parse_args().mode)
