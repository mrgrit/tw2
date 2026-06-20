# SOC W07 — 한 번 쓰면 어디서나: SIGMA로 쓰고 Wazuh·Suricata 두 곳에 이식

> SOC 관제 트랙 7주차. 선행: W04(Wazuh 룰). 인프라: el34 (~/el34/sigma + Wazuh sigma_rules.xml). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 벤더마다 다시 쓰지 마라

W04에서 Wazuh 룰을 직접 썼다. 문제: 같은 탐지를 Suricata엔 Suricata 문법으로, Splunk엔 SPL로… **벤더마다
다시** 써야 한다. **SIGMA**는 탐지의 **표준 언어(YAML)** — 한 번 쓰고 여러 백엔드로 **변환(이식)** 한다.

```
              ┌─→ Wazuh 룰 (sigma2wazuh)
 SIGMA(YAML)  ┼─→ Suricata 룰
 한 번 작성    ├─→ Splunk SPL
              └─→ Elastic EQL …
```

---

## 2. SIGMA 룰 구조 — YAML

```yaml
title: Web SQLi keywords
logsource:                    # 어떤 로그에
    product: apache
    category: webserver
detection:                    # 무엇을 (탐지 로직)
    selection:
        keywords:
            - 'union select'
            - 'OR 1=1'
            - 'information_schema'
    condition: selection
level: high
tags:                         # ATT&CK 매핑
    - attack.initial_access
    - attack.t1190
```
- **logsource**: 적용 대상 로그(product/category).
- **detection**: selection(조건) + condition(조합 로직).
- **tags**: ATT&CK technique 매핑(표준에 내장).

el34엔 `~/el34/sigma/rules/`에 SIGMA 룰(ssh-bruteforce/web-sqli/linux-cmd)이 있다.

---

## 3. 변환 — sigma2wazuh.py

SIGMA YAML을 Wazuh 룰로 변환하는 컨버터(`~/el34/sigma/sigma2wazuh.py`).
```bash
cd ~/el34/sigma && python3 sigma2wazuh.py rules/      # stdout으로 Wazuh XML 출력
```
출력 예(web-sqli → Wazuh):
```xml
<rule id="200002" level="10">
  <regex type="pcre2">(union select|OR 1=1|' OR '|information_schema|sleep\()</regex>
  <description>[Sigma] ... SQLi ...</description>
  <group>sigma,apache,webserver,</group>
</rule>
```
- SIGMA의 keywords → Wazuh `<regex>`로. level/tags → Wazuh level/group으로.
- 운영 적용: `sigma2wazuh.py rules/ > /var/ossec/etc/rules/sigma_rules.xml` + restart. (el34엔 이미 적용돼 있다.)

---

## 4. 검증 — wazuh-logtest

변환된 룰이 실제로 발화하는지 logtest로 확인.
```bash
echo '1.2.3.4 - - [x] "GET /?id=1 union select 1,2 HTTP/1.1" 403' \
  | docker exec -i el34-siem /var/ossec/bin/wazuh-logtest
#  → id 200002, level 10, groups [sigma,apache,webserver], "Alert to be generated."
```
한 SIGMA 룰이 Wazuh에서 실제 경보가 된다.

---

## 5. Suricata 이식 — 같은 탐지, 다른 백엔드

SIGMA는 Suricata 백엔드도 지원한다(공식 sigma-cli `sigma convert -t suricata`). 같은 web-sqli SIGMA가
Suricata 룰로도 변환돼, **네트워크(Suricata)와 호스트/로그(Wazuh) 양쪽에서 같은 탐지**를 한다.
```
 web-sqli.yml ─┬─ sigma2wazuh.py  → Wazuh <regex> 룰 (로그 탐지)
               └─ sigma -t suricata → Suricata content 룰 (네트워크 탐지)
```
"한 번 쓰고 어디서나" — 탐지 자산을 벤더 종속 없이 관리하는 SOC의 성숙.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: SIGMA 설정(rules/ + 컨버터 + Wazuh sigma_rules.xml)
2. **SIGMA 룰 읽기**: web-sqli.yml(logsource/detection/tags)
3. **변환**: sigma2wazuh.py rules/ → Wazuh XML(stdout)
4. **logtest 검증**: 변환 룰(200002) 발화
5. **Suricata 이식**: SIGMA → Suricata 백엔드(개념)
6. **실제 탐지**: SQLi 공격 → Wazuh sigma 경보
7. **다중 플랫폼 가치**: 한 번 쓰고 어디서나
8. **SIGMA 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 컨버터는 stdout 출력(라이브 sigma_rules.xml 미변경).

---

## 7. 다음 주차 (W08) 예고 — 중간고사: 교차 분석 종합

W08은 중간 평가 — 흩어진 로그(인증/웹/네트워크/SIEM)를 교차 분석해 하나의 공격 서사로 종합하는
SOC 분석가의 종합 역량을 점검한다.
