# 컴플라이언스 W09 — 보안 구성 평가 (SCA / CIS 자동 점검)

> 컴플라이언스 트랙 9주차. 선행: W01–W08. 인프라: el34 (siem/web). 플랫폼: tw2. 표준: CIS Benchmark, Wazuh SCA.

---

## 1. 이번 주의 통찰 — 수백 개 항목을 사람이 다 볼 수 없다

CIS 벤치마크는 한 OS/앱에 수백 개 점검 항목이 있다. 수작업은 느리고 누락된다. **SCA(Security
Configuration Assessment)** 는 이 점검을 자동·정기 수행하고 pass/fail 점수를 낸다. Wazuh가 SCA 모듈을
내장한다.

```
 SCA 흐름
 CIS 정책(yml) → 에이전트가 각 항목 자동 점검(rule/command) → pass/fail → 점수 + 알림
```

---

## 2. SCA 모듈 활성 확인

```bash
docker exec el34-web sh -c "grep -A4 '<sca>' /var/ossec/etc/ossec.conf"
```
- el34-web: `<sca><enabled>yes</enabled><scan_on_start>yes</scan_on_start><interval>12h</interval>` →
  12시간마다 자동 구성 평가(준수).

---

## 3. SCA 정책 (CIS Benchmark)

```bash
docker exec el34-siem sh -c "ls /var/ossec/ruleset/sca/"
```
- 다수 CIS 정책 내장(`cis_apache_24.yml`, OS별 CIS 등). 대상에 맞는 정책을 활성화해 점검.

---

## 4. SCA 점검 항목 (예: ServerTokens)

```bash
docker exec el34-siem sh -c "grep -A3 'ServerTokens' /var/ossec/ruleset/sca/cis_apache_24.yml.disabled"
```
- CIS Apache 8.1 항목: *"Ensure ServerTokens is Set to 'Prod'"* — rationale/remediation/compliance(cis 8.1)
  포함. **W01에서 수동 발견한 갭이 SCA 정책에 그대로 정의**되어 있다 = 자동·수동 점검의 일치.

---

## 5. 자동 점검 ↔ 수동 검증

SCA가 fail 판정한 항목은 **실제 설정으로 재확인**해 오탐을 거른다.

```bash
docker exec el34-web sh -c "grep -rhiE '^[[:space:]]*ServerTokens' /etc/apache2/"
```
- 실제 `ServerTokens OS` → CIS 요구(Prod) 미달 = SCA fail과 일치. 자동 결과를 증적으로 확정.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **SCA 활성**: ossec.conf
3. **SCA 정책**: CIS 목록
4. **SCA 결과**: 적재 확인
5. **점검 항목**: ServerTokens(CIS 8.1)
6. **수동 검증**: 실제 설정 대조
7. **점수·조치**: pass/fail·remediation
8. **SCA 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-X` 로. 신규 설치 없음.

---

## 7. 다음 주차 (W10) 예고 — 변경관리·무결성(FIM)

W09는 구성 평가였다. W10은 변경관리와 파일 무결성 모니터링(FIM, Wazuh syscheck)을 다룬다.
