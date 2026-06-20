# SOC W03 — 웹 공격 vs 네트워크/웹 로그(Apache·ModSec·Suricata) 교차 분석

> SOC 관제 트랙 3주차. 선행: W01–W02. 인프라: el34 (Apache+ModSec, Suricata, Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 한 공격, 세 개의 다른 흔적

같은 웹 공격(예: SQLi)이 **세 로그에 서로 다르게** 남는다. 분석가는 각 로그의 강점을 알고 **교차**로
봐야 전체 그림이 보인다.

```
 한 SQLi 요청
   ├─ Apache access.log → "GET /?id=1' UNION... 403"  (요청 사실 + 응답코드, 탐지는 없음)
   ├─ ModSec audit      → rule 942100 SQLi, 949110 차단, payload  (왜 막혔나 — WAF 판단)
   └─ Suricata eve.json → alert/http/flow event  (네트워크 관점 — 시그니처/세션)
```

| 로그 | 강점 | 약점 |
|------|------|------|
| Apache access | 모든 요청·응답코드(전체상) | 공격 판단 없음 |
| ModSec audit | WAF 탐지/차단 이유(rule/payload) | WAF 거친 것만 |
| Suricata eve | 네트워크 시그니처/세션 | HTTP 의미 약함 |

---

## 2. ModSec audit — 왜 막혔나

WAF audit는 "어떤 rule이 어떤 payload에 걸려 무슨 코드로 응답했나"를 담는다.
```bash
docker exec el34-web sh -c 'sudo tail -1 /var/log/apache2/modsec_audit.log | jq "{status:.response.status, remote:.transaction.remote_address, line:.request.request_line}"'
docker exec el34-web sh -c 'sudo tail -80 /var/log/apache2/modsec_audit.log | grep -oE "9[0-9]{5}" | sort | uniq -c'
```
- rule id: 942xxx(SQLi) / 941xxx(XSS) / 913xxx(scanner) / 949110(anomaly 누적 차단).
- `response.status` 403 = 차단(dvwa 차단 모드), 200 = 통과/탐지만(juice).
- `transaction.remote_address` = 실제 출발지(el34 출처 보존).

---

## 3. Suricata eve — 네트워크 관점

eve.json은 한 흐름을 여러 event_type으로 본다:
```bash
docker exec el34-ips sh -c 'tail -3000 /var/log/suricata/eve.json | jq -rc "select(.src_ip==\"10.20.30.202\")|.event_type" | sort | uniq -c'
```
- **alert**: 시그니처 매치(SQLi/scan 등) — 분석의 핵심.
- **http**: HTTP 트랜잭션 메타(host/url/UA).
- **flow**: 세션 통계(바이트/패킷).
- WAF가 못 본 비-HTTP 공격(포트 스캔 등)도 잡는 게 강점.

---

## 4. 교차 상관 — 같은 출발지

세 로그의 출발지가 같으면 한 공격자다. ModSec `remote_address` = Suricata `src_ip` = Apache access의
client IP → 한 사건. el34는 출처를 보존하므로 세 로그 모두 실제 공격자 IP를 본다.

> 교차의 가치: ModSec에 403(차단)이지만 Suricata flow에 대용량 전송이 보이면 → 다른 경로로 성공했을 수
> 있다. 한 로그만 보면 놓치는 것을 교차로 잡는다.

---

## 5. SIEM 통합 — 세 로그가 한 경보 스트림으로

web agent(apache/json)와 ips agent(eve)가 각 로그를 Wazuh로 ship → alerts.json 한 곳으로 수렴.
```bash
docker exec el34-siem sh -c 'tail -400 /var/ossec/logs/alerts/alerts.json | jq -rc "select(.data.srcip==\"10.20.30.202\" or .data.src_ip==\"10.20.30.202\")|.rule.description" | tail -5'
```
SIEM에서 한 출발지의 web/ids 경보를 모아 보면 세 로그를 일일이 안 열어도 사건이 보인다.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 세 로그(Apache access/ModSec audit/Suricata eve) 위치
2. **웹 공격 재현**: SQLi + XSS + 스캐너
3. **ModSec 분석**: rule id/payload/응답코드
4. **Apache access 분석**: 요청 라인 + 응답코드(전체상)
5. **Suricata eve 분석**: event_type 분포 + 시그니처
6. **교차 상관**: 세 로그 같은 출발지
7. **SIEM 통합**: Wazuh로 수렴한 웹 경보
8. **교차 분석 보고서**: 세 로그 종합

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 공격은 `docker exec el34-attacker`, 분석은 web/ips/siem.

---

## 7. 다음 주차 (W04) 예고 — Wazuh 관제·커스텀 룰

W03은 로그를 교차로 읽었다. W04는 그 로그를 평결로 만드는 Wazuh manager로 들어가 — decoder/rule을
점검하고, 특정 위협을 잡는 커스텀 룰을 직접 작성·검증한다(분석가가 탐지를 만드는 단계).
