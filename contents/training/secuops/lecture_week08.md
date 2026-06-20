# W08 — 중간고사: 한 침입 사슬을 5종 장비로 끝까지 막아내기

> 보안운영 트랙 8주차 (중간 평가). 선행: W01–W07.
> 인프라: el34 (단일 VM, 4-tier Docker 네트워크). 플랫폼: tw2.

---

## 1. 이 시험이 평가하는 것

지난 7주 동안 **5종 보안 솔루션**과 **엔드포인트 IR** 을 하나씩 익혔다.

| 주차 | 장비/주제 | el34 컴포넌트 | 핵심 능력 |
|------|----------|--------------|-----------|
| W02 | 방화벽 | el34-fw (nftables) | 정책·NAT·세그먼트 |
| W03 | IDS | el34-ips (Suricata) | 시그니처 정찰 탐지 |
| W04 | IDS 심화 | el34-ips | pcre/flowbits/threshold |
| W05 | WAF | el34-web (Apache+ModSec) | L7 anomaly 차단 |
| W06 | 호스트 가시화 | el34-web (osquery) | SQL 로 호스트 질의 |
| W07 | 엔드포인트 IR | el34-web (osquery+Wazuh) | 침해 호스트 조사·대응 |

중간고사는 **단일 장비 실력이 아니라**, 한 침입자가 시도하는 **공격 사슬(kill chain) 전체** 를
"어느 단계를 어느 장비로 끊을지" 판단하고 **5종을 모두 동원** 해 추적·대응하는 종합 능력을 본다.

> 핵심 메시지: 어떤 단일 장비도 사슬 전체를 못 막는다. 방화벽은 호스트 내부를 못 보고, osquery 는
> 네트워크 정찰을 못 본다. **다층 방어(defense in depth)** 와 **통합 가시성(SIEM 수렴)** 이 정답이다.

---

## 2. 한 침입 사슬 (kill chain) — 침입자의 3 단계

이번 시험의 시나리오는 한 외부 침입자(el34 외부 공격자, 출처 IP **10.20.30.202** — el34 는 SNAT 를
하지 않아 출처가 끝까지 보존된다)가 다음 사슬을 시도한다.

```
 ① 정찰(Recon)            ② 웹 침투(Exploit)           ③ 호스트 발판(Foothold)
 ─────────────            ──────────────────           ────────────────────
 스캐너 UA 로 표면 훑기   SQLi 로 웹앱 침투            비표준 포트 리스너 + 백도어 계정
 (sqlmap/nikto)           (UNION SELECT …)             (port 38088 / w08user)
        │                        │                            │
   IDS 가 잡는다           WAF 가 막는다               osquery 가 사냥한다
   (Suricata UA 룰)        (ModSec 942/949110 403)     (listening_ports/users)
        └────────────────────────┴────────────────────────────┘
                          모두 SIEM(Wazuh)으로 수렴
```

각 단계는 **서로 다른 장비의 관점** 에서 보인다. 같은 sqlmap 요청 하나가 —
- **WAF** 에는 HTTP 의미(SQLi 942 + 스캐너 UA 913)로,
- **IDS** 에는 네트워크 페이로드의 UA 문자열("sqlmap")로,

동시에 잡힌다. 두 장비가 같은 사건을 다른 층위로 본다는 것을 이해하는 것이 종합 평가의 핵심이다.

---

## 3. el34 의 진입 경로 — 방화벽과 L7 라우팅 (HAProxy 없음)

> ⚠️ 자주 하는 오해: "리버스 프록시가 HAProxy 다." **el34 에는 HAProxy 가 없다.**
> 공개 진입과 L7 라우팅이 다음 두 컴포넌트로 나뉜다.

```
외부 공격자(10.20.30.202)
   │  http://10.20.30.1  (Host: dvwa.el34.lab)
   ▼
[ el34-fw ]  nftables  ─ inet six_filter (필터)  +  ip six_nat (DNAT)
   │  공개 80/443 → DNAT → web 10.20.32.80      ※ SNAT 없음 → 출처 IP 보존
   ▼
[ el34-web ] Apache 2.4.52  ─ vhost(ServerName) 로 L7 라우팅 + ModSecurity(CRS) WAF
   │  dvwa/neobank/mediforum/govportal = 차단(403)  /  juice = 탐지만(200)
   ▼
  백엔드 웹앱 (DVWA 등)
```

- **방화벽 계층(el34-fw)**: 무엇이 들어오고(허용 포트) 어디로 가는지(DNAT) 를 결정. L4 정책.
- **L7 + WAF 계층(el34-web)**: HTTP 의미를 보고 vhost 라우팅 + 공격 페이로드 차단. L7 검사.
- **출처 IP 보존**: fw 가 SNAT 를 안 하므로 ModSec `remote_address`, Suricata `src_ip`,
  access.log 모두 **실제 공격자 IP(10.20.30.202)** 를 본다. 이것이 5계층을 **한 사건으로 엮는 키**다.

4-tier 세그먼트: `ext 10.20.30` / `pipe 10.20.31` / `dmz 10.20.32` / `int 10.20.40`.

---

## 4. 장비별 빠른 복습 — "무엇을 어디서 보나"

### 4.1 방화벽 (el34-fw / nftables)
```bash
docker exec el34-fw nft list ruleset | head -40        # 정책 + NAT 테이블
docker exec el34-fw nft list table ip six_nat          # DNAT 규칙
```
- baseline 정책을 **수정하지 말 것**(공유 인프라). 점검(list)만. 룰 추가 시 반드시 핸들로 삭제.

### 4.2 IDS (el34-ips / Suricata 6.0.4)
```bash
# 룰: /etc/suricata/rules/{local,suricata}.rules — local.rules 에만 추가
docker exec el34-ips sh -c 'sudo bash -c "cat >> /etc/suricata/rules/local.rules <<EOF
alert http any any -> any any (msg:\"...\"; http.user_agent; content:\"sqlmap\"; nocase; fast_pattern; sid:9008001; rev:1;)
EOF"'
docker exec el34-ips sh -c 'sudo suricata -T -S /etc/suricata/rules/local.rules'   # syntax
docker exec el34-ips sh -c 'sudo suricatasc -c reload-rules'                        # 무중단 reload
# 트리거 후: /var/log/suricata/eve.json 에서 sid 확인
docker exec el34-ips sh -c 'sudo sed -i "/sid:9008001/d" /etc/suricata/rules/local.rules'   # 정리(베이스 보존)
```
- **base 룰(sid 1000001–1000005)은 보존**. 내 룰은 `9008xxx` 네임스페이스 + 끝나면 sid 로 삭제.

### 4.3 WAF (el34-web / Apache + ModSecurity CRS)
```bash
docker exec el34-web sh -c 'sudo tail -1 /var/log/apache2/modsec_audit.log | jq "{status:.response.status, remote:.transaction.remote_address}"'
```
- SQLi 단일 룰(942100)이 아니라 **anomaly score 누적 → 949110 차단(403)**. dvwa 는 차단 모드.

### 4.4 호스트 (el34-web / osquery 5.23.0)
```bash
docker exec el34-web osqueryi --json 'SELECT pid,port FROM listening_ports WHERE port=38088;'
docker exec el34-web osqueryi --json 'SELECT username,uid FROM users WHERE username="w08user";'
```
- 네트워크 장비가 못 보는 **호스트 내부 발판**(리스너/계정/cron/키)을 SQL 로 사냥.

### 4.5 SIEM (el34-siem / Wazuh 4.10)
```bash
docker exec el34-siem /var/ossec/bin/agent_control -l        # 활성 agent: ips(003)+web(004)
docker exec el34-siem sh -c 'tail -n 200 /var/ossec/logs/alerts/alerts.json | jq -c .rule.description'
```
- ips·web agent 의 경보가 한 manager 로 수렴. **각 단계가 어느 장비에서 잡혔는지** 한 시간선으로.

---

## 5. 판단 프레임워크 — "어느 단계를 어느 장비로 끊나"

| 사슬 단계 | 1차 탐지/차단 | 보조(교차 확인) | 못 잡는 장비 |
|-----------|--------------|----------------|-------------|
| ① 정찰(스캐너 UA) | IDS(Suricata UA 룰) | WAF(913 scanner) | 방화벽(L4 라 UA 못 봄) |
| ② 웹 침투(SQLi) | WAF(942→949110 403) | IDS(payload 룰) | osquery(네트워크 못 봄) |
| ③ 호스트 발판 | osquery(listening_ports/users) | Wazuh FIM | 방화벽·IDS(호스트 내부 못 봄) |
| (전 단계 수렴) | SIEM(Wazuh) | — | — |

**시험의 채점 포인트**: 각 단계를 올바른 장비로 끊고, 그 증거(로그/audit/eve/osquery 결과)를
제시하며, 마지막에 5계층이 SIEM 으로 수렴함을 보이는 것.

---

## 6. 상관(correlation) — 5개의 관점, 하나의 사건

한 SQLi 요청이 남기는 5개의 흔적을 **출처 IP(10.20.30.202) + 시각** 으로 엮으면 하나의 타임라인이 된다.

| 장비 | 로그/질의 | 같은 사건의 다른 단서 |
|------|----------|----------------------|
| fw | (정책상 통과) | DNAT 경로 — 어떤 공개포트로 들어왔나 |
| ips | eve.json `src_ip` | UA 문자열 "sqlmap" 시그니처 매치 |
| web(WAF) | modsec_audit `remote_address` | 942100 SQLi + 949110 anomaly 403 |
| host | osquery `users`/`listening_ports` | 침투 후 심은 발판 |
| siem | alerts.json | 위 전부가 한 manager 로 수렴 |

이 표를 손으로 채울 수 있으면 중간고사의 종합 사고를 갖춘 것이다.

---

## 7. 실습(중간고사 lab) 형식 — 12 미션

1. **점검**: 5종 장비가 모두 살아있나 (fw/ips/web/host/siem)
2. **① 정찰 재현**: 외부 공격자 스캐너 UA 요청 → WAF 913 + IDS 관점
3. **① IDS 룰**: 스캐너 UA 탐지 룰(sid 9008001) 작성→reload→트리거→eve→정리
4. **② 웹 침투 재현**: SQLi → 403
5. **② WAF 확인**: 942 SQLi + 949110 anomaly 누적 차단
6. **방화벽 점검**: nftables 정책·DNAT 경로 (HAProxy 아님)
7. **③ 호스트 발판 재현**: 리스너 38088 + 계정 w08user (self-clean)
8. **③ osquery 사냥**: 발판 식별
9. **SIEM 수렴**: Wazuh 에 다계층 경보
10. **상관 분석**: 출처 IP 로 5계층 한 타임라인
11. **종합 보고서**: 사슬 단계별 끊은 장비 + 증거
12. **정리 확인**: 실습 흔적 0 (공유 인프라 보존)

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>` 로.
> 시험 단계는 **독립적**이다. 각 단계에서 심은 것은 그 단계에서 정리한다(self-clean).

---

## 8. 시험 수칙 — 공유 인프라 보존

- **baseline 을 수정/삭제하지 말 것**: fw 정책, suricata base 룰(1000001–5), apache vhost, 정상 계정.
- **내 흔적은 내가 정리**: IDS 룰은 sid 로 삭제, 리스너는 kill, 계정은 userdel, 파일은 rm.
- **네임스페이스**: IDS sid `9008xxx`, 리스너 포트 `38088`, 계정 `w08user` — 다른 학생과 안 겹치게.
- **증거 우선**: "막았다"가 아니라 **로그/audit/eve/osquery 결과를 제시**해야 점수.

---

## 9. 다음 주차 (W09) 예고 — SIEM 의 두뇌(Wazuh manager)

중간고사에서 "5계층이 SIEM 으로 수렴한다"를 확인했다. W09 부터는 그 SIEM 의 **내부** 로 들어간다 —
Wazuh manager 가 흩어진 로그를 어떻게 **디코더 → 룰 → 한 평결(alert)** 로 모으는지, 룰 레벨·그룹·
상관(correlation)이 어떻게 동작하는지를 배운다. 관제의 자동화가 시작된다.
