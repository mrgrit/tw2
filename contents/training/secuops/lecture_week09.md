# W09 — SIEM의 두뇌: 흩어진 로그를 Wazuh가 어떻게 한 평결로 모으나

> 보안운영 트랙 9주차. 선행: W01–W08. 인프라: el34 (el34-siem = Wazuh manager 4.10). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — raw 로그는 그대로는 쓸모가 적다

W08 중간고사에서 "5계층 흔적이 SIEM 한 곳으로 수렴한다"를 확인했다. 이번 주는 그 **SIEM의 내부**로
들어간다. 핵심 통찰 하나:

```
raw 로그            decoder            rule              alert (평결)
─────────         ─────────         ─────────         ──────────────
"...sqlmap..."  →  필드 추출      →  심각도 부여     →  alerts.json 한 줄
(텍스트 덩어리)     src_ip, url…       level, group        (관제 가능한 사건)
```

같은 raw 로그라도 **decoder가 파싱**해 필드를 뽑고, **rule이 심각도를 매겨**, **alerts.json이라는
정규화된 한 평결**로 바뀌어야 비로소 "관제"가 된다. Wazuh manager가 이 변환을 한다.

---

## 2. Wazuh manager 4.10 — 11개 daemon, 그중 심장은 analysisd

el34-siem 의 Wazuh manager는 여러 daemon으로 돈다. 역할만 알면 된다:

| daemon | 역할 | 비유 |
|--------|------|------|
| **wazuh-analysisd** | decoder → rule 엔진 (평결 생성) | **심장** |
| wazuh-remoted | agent 통신 (1514/1515) 수신 | 우편함 |
| wazuh-logcollector | 로컬 로그 수집 | 수집원 |
| wazuh-db | 상태/FIM DB | 장부 |
| wazuh-monitord / execd / syscheckd | 모니터/대응실행/FIM | 보조 |

```bash
docker exec el34-siem /var/ossec/bin/wazuh-control status     # daemon 상태
docker exec el34-siem /var/ossec/bin/agent_control -l         # 등록 agent
```

> **analysisd가 멈추면 평결이 안 나온다.** 로그는 들어와도 alert이 생성되지 않는다.
> el34 활성 agent: `000`(manager 자신) / `003`(ips) / `004`(web).

---

## 3. 데이터 흐름 — agent에서 alerts.json까지

```
[el34-web/ips agent]                  [el34-siem manager]
 ossec.conf <localfile>                remoted(수신)
   apache(modsec audit) ─┐               │
   json(suricata eve)  ──┼─→ 1514 ─→ ────┤
   syslog              ──┘               ▼
                                     analysisd
                                   ┌───────────┐
                                   │ decoder    │ 필드 추출
                                   │   ↓        │
                                   │ rule       │ level/group 부여
                                   └───────────┘
                                         ▼
                              /var/ossec/logs/alerts/alerts.json
                              (ids·web·syscheck… 그룹이 한 곳으로 수렴)
```

- **두 ingest 소스**: web agent의 `apache`(ModSec audit) + ips agent의 `json`(Suricata eve.json).
  둘 다 같은 manager로 올라가 같은 alerts.json으로 **수렴**한다.
- el34 alerts.json 실제 분포(예): `ids/suricata` 다수 + `syscheck`(FIM) + `pam/sudo` + `sca`.

---

## 4. decoder — raw를 필드로 (wazuh-logtest로 디버그)

decoder는 raw 로그에서 필드(src_ip, url, user…)를 뽑는다. **`wazuh-logtest`**로 한 줄씩 넣어
어떤 decoder가 잡고 어떤 rule에 매치되는지 3단계로 본다.

```bash
echo 'Jan  1 00:00:00 web sshd[1]: Failed password for root from 9.9.9.9 port 22 ssh2' \
  | docker exec -i el34-siem /var/ossec/bin/wazuh-logtest
```
출력 3 phase:
- **Phase 1 pre-decoding**: 시간/호스트/프로그램 분해
- **Phase 2 decoding**: decoder 매치 + 필드 추출 (예: `decoder: sshd`, `srcip: 9.9.9.9`)
- **Phase 3 filtering(rules)**: 매치된 rule id + level (예: sshd 인증실패 → rule **5760**, MITRE T1110)

> wazuh-logtest는 **현재 룰셋을 새로 읽어** 테스트 인스턴스에서 돌린다 → 라이브 manager를 건드리지
> 않고 decoder/rule을 검증할 수 있다(공유 인프라에서 안전).

JSON 로그(예: Suricata eve, ModSec)는 `json` decoder가 잡아 키를 그대로 필드로 만든다.

---

## 5. rule — 심각도와 맥락 (level / group / 체이닝)

rule은 decoder가 뽑은 필드를 조건으로 **level(0–16)** 과 **group**을 부여한다.

```xml
<rule id="100909" level="11">
  <decoded_as>json</decoded_as>      <!-- 이 decoder가 잡은 로그만 -->
  <field name="eduw09">FIREME</field><!-- 특정 필드 값 매치 -->
  <description>...</description>
</rule>
```
- **level**: 0(무시)~16(치명). 보통 ≥7이 alerts.json에 기록, ≥12는 고위험.
- **group**: `web` / `ids` / `syscheck` 등 분류 → 대시보드/상관에서 묶임.
- **체이닝**: `<if_sid>5710</if_sid>`(특정 rule 뒤) / `<if_group>web|ids</if_group>`(그룹 뒤)로
  기존 탐지에 맥락을 더해 **격상**한다. 예: "스캐너 UA 경보"를 더 높은 level로.

---

## 6. 커스텀 룰 — local_rules.xml (격상의 실제)

기본 룰(Wazuh 내장 + Suricata/CRS 디코딩)은 평범한 level로 들어온다. 운영자는 **`local_rules.xml`**에
커스텀 룰을 써서 특정 위협을 상위 level로 격상한다.

```bash
# /var/ossec/etc/rules/local_rules.xml 에 추가
# id 네임스페이스: 100000+ (사용자 룰). 본 트랙 training = 1009xx.
sudo bash -c 'cat >> /var/ossec/etc/rules/local_rules.xml <<EOF
<group name="edu_w09,">
  <rule id="100909" level="11">
    <decoded_as>json</decoded_as>
    <field name="eduw09">FIREME</field>
    <description>EDU W09 - JSON marker escalated</description>
  </rule>
</group>
EOF'
# 검증: 라이브 restart 없이 wazuh-logtest 로 발화 확인 (공유 인프라 안전)
echo '{"eduw09":"FIREME","src_ip":"9.9.9.9"}' | sudo /var/ossec/bin/wazuh-logtest
#   → Phase 3: id 100909, level 11, "Alert to be generated."
```

- **라이브 반영**: 실제 운영 적용은 `wazuh-control restart`가 필요하지만, 공유 el34에서는
  **wazuh-logtest로 검증만** 하고 끝나면 룰을 지운다(베이스 보존). XML 문법 오류 시 analysisd 로딩 실패에
  주의 — `wazuh-logtest`가 시작 시 룰셋 로드 에러를 보여준다.
- **id 충돌 금지**: 100000 미만은 Wazuh 예약. 본 트랙은 `1009xx`로 격리하고 끝나면 그룹째 삭제.

---

## 7. 두 소스가 한 평결로 (ingest 추적)

운영자는 공격을 재현한 뒤 두 ingest 소스가 모두 alerts.json으로 수렴하는지 추적한다.

```bash
# 웹공격 재현(외부 공격자) → modsec(apache) + suricata(eve) 두 소스 발생
docker exec el34-attacker sh -c 'curl -s -A sqlmap/1.7 -H "Host: dvwa.el34.lab" \
  "http://10.20.30.1/?id=1%27%20UNION%20SELECT%201,2--%20-"'
sleep 8
# alerts.json 에 ids 그룹 경보(출처 보존) 적재 확인
docker exec el34-siem sh -c 'tail -300 /var/ossec/logs/alerts/alerts.json \
  | jq -c "select(.rule.groups|index(\"ids\"))|{r:.rule.id,d:.rule.description,s:.data.src_ip}" | tail -2'
#   → {"r":"86601","d":"Suricata: ... UNION SELECT","s":"10.20.30.202"}
```
출처 IP(10.20.30.202)가 그대로 보존돼 들어오므로 W08의 상관 분석과 그대로 이어진다.

---

## 8. agent는 무엇을 수집하나 — ossec.conf의 localfile

manager가 받는 로그는 agent가 보낸다. agent의 `ossec.conf`/`agent.conf`의 **`<localfile>`** 이
어떤 로그를 수집할지 정의한다.

```bash
docker exec el34-web sh -c 'grep -A1 localfile /var/ossec/etc/ossec.conf | grep log_format'
#  web agent: apache(modsec audit) · json · syslog · full_command
docker exec el34-ips sh -c 'grep -A1 localfile /var/ossec/etc/ossec.conf | grep log_format'
#  ips agent: json(suricata eve) · syslog · command
```
- `<log_format>`이 decoder 선택의 1차 힌트(apache/json/syslog). 수집 소스를 빼면 그 계층은 SIEM에서
  사라진다 — 가시성의 출발점.

---

## 9. 실습(lab) 형식 — 9 미션

1. **점검**: manager daemon(analysisd 심장) + agent
2. **데이터 흐름**: alerts.json 그룹 분포(여러 소스 수렴)
3. **decoder**: wazuh-logtest 3 phase (sshd → 5760)
4. **커스텀 룰**: local_rules.xml 격상 룰(id 100909) → logtest 발화 → self-clean
5. **ingest 추적**: 웹공격 → alerts.json ids 그룹(출처 보존)
6. **agent 수집**: ossec.conf localfile (수집 소스)
7. **수렴 확인**: 두 소스(ids+syscheck 등) 한 곳에
8. **종합 보고**: raw→decoder→rule→alert 평결 흐름
9. **정리 확인**: 커스텀 룰 잔재 0 (베이스 보존)

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>` 로.
> 커스텀 룰은 wazuh-logtest로만 검증(라이브 restart 금지) + 끝나면 그룹째 삭제(공유 인프라 보존).

---

## 10. 다음 주차 (W10) 예고 — 분석가의 조종석(Wazuh dashboard + active response)

W09에서 manager가 평결(alert)을 만드는 법을 배웠다. W10은 그 평결을 **한 화면(dashboard)** 에서 보고,
**FIM(파일 변조)** 을 잡고, **active response** 로 자동 되받아치는 — 분석가의 조종석을 다룬다.
탐지에서 자동 대응으로 한 걸음 더 나간다.
