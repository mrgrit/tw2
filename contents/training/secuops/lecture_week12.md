# W12 — 위협의 언어: 알려진 악성 지표(STIX)를 Wazuh가 알아보게 만들기

> 보안운영 트랙 12주차. 선행: W09–W11(Wazuh). 인프라: el34 (OpenCTI/MISP 가동 + Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 세상은 이미 "이건 악성"이라고 안다

W09–W11은 우리 환경의 로그를 분석했다. 하지만 세상엔 이미 **"이 IP·도구·해시는 악성"** 이라고 정리된
**위협 인텔리전스(CTI)** 가 있다. 문제는 그걸 **우리 SIEM이 알아듣게** 만드는 것.

```
 외부 CTI (이미 아는 악성)         우리 SIEM (Wazuh)
 ────────────────────             ─────────────────
 OpenCTI / MISP / 피드            평범한 경보로 들어옴
 "sqlmap = known-bad-tool"   →    IOC 매칭 룰로 "알려진 위협"으로 격상
 (STIX 2.1 표준 객체)              (CDB list + 매칭 룰)
```

핵심: 같은 sqlmap 공격이 평범한 경보로 묻히지 않고, **"알려진 악성 도구"로 격상**돼 분석가의 시선을
먼저 끌게 만든다. 그러려면 외부 지식(IOC)을 SIEM의 언어(룰)로 옮겨야 한다.

---

## 2. STIX 2.1 / TAXII 2.1 — 위협의 표준 언어

위협을 사람 메모가 아니라 **기계가 읽는 표준 객체**로 적어야 공유·자동화된다.

| STIX 2.1 객체 | 뜻 | 예 |
|---------------|----|----|
| **indicator** | 탐지 패턴 | `[network-traffic:...]`, 도구 UA "sqlmap" |
| **malware** / **tool** | 악성 도구/코드 | sqlmap, nikto |
| **attack-pattern** | ATT&CK technique | T1190(공개 앱 익스플로잇) |
| **relationship** | 객체 연결 | indicator —indicates→ malware |

- **TAXII 2.1**: STIX를 주고받는 전송 프로토콜(server/client, collection). 피드 구독의 표준.
- el34에는 **OpenCTI**(STIX 저장·시각화·ATT&CK 연동)와 **MISP**(IOC 공유 플랫폼)가 실제 가동 중이다.

---

## 3. el34의 위협인텔 스택 — OpenCTI + MISP + Wazuh

```
[ MISP ]  IOC 공유          [ OpenCTI ]  STIX 저장/ATT&CK/시각화
   │                            │  (connector: MITRE, import/export STIX…)
   └──────────┬─────────────────┘
              ▼ (IOC 추출)
    Wazuh CDB list (/var/ossec/etc/lists/)   ←  IOC를 SIEM이 읽는 형식(key:value)
              ▼
    매칭 룰 (local_rules.xml)  →  IOC 매칭 시 경보 격상
```

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep -iE 'opencti|misp|mitre'
#  el34-opencti-1 (healthy), el34-misp-core-1 (healthy), el34-connector-mitre-1 …
```
- OpenCTI는 ATT&CK·악성코드·indicator를 STIX로 보관하고 connector로 피드를 자동 수집한다.
- 운영에선 OpenCTI/MISP → (stream connector/스크립트) → Wazuh CDB list로 IOC를 내려보낸다.

---

## 4. Wazuh CDB list — IOC를 SIEM이 읽는 형식

**CDB(Constant Database) list** 는 `key:value` 형식의 빠른 조회 테이블이다(`/var/ossec/etc/lists/`).
IOC를 여기 넣고 룰이 참조한다.
```bash
# /var/ossec/etc/lists/edu-w12-ioc
sqlmap:known-bad-tool
nikto:known-bad-tool
```
- **운영 적용**: `ossec.conf`에 `<list>`로 등록 + manager가 `.cdb`로 컴파일(restart 필요) + 룰에서
  `<list field="..." lookup="match_key">etc/lists/edu-w12-ioc</list>`로 조회.
- ⚠️ 공유 el34에서는 manager를 재시작하지 않는다 → **IOC 저장소(list 파일)는 만들어 보이고,
  매칭/격상 로직은 `wazuh-logtest`로 검증**한다(아래 §5).

---

## 5. IOC 매칭/격상 룰 — 평범한 경보를 "알려진 위협"으로

IOC가 탐지에 나타나면 경보를 상위 level로 격상하는 룰을 쓴다(W09 커스텀 룰 패턴 재사용).
```xml
<group name="edu_w12,">
  <rule id="101210" level="12">
    <decoded_as>json</decoded_as>
    <field name="tool">sqlmap</field>     <!-- IOC: 알려진 악성 도구 -->
    <description>EDU W12 - known IOC (sqlmap) matched, escalate</description>
  </rule>
</group>
```
```bash
echo '{"tool":"sqlmap","src_ip":"9.9.9.9"}' | sudo /var/ossec/bin/wazuh-logtest
#  → Phase 3: id 101210, level 12, "Alert to be generated."   (IOC 격상 확인)
```
- 운영에선 `<field>` 대신 `<list lookup>`로 CDB의 수백~수천 IOC를 한 번에 조회한다. 여기선 격상 **로직**을
  field-match로 logtest 검증하고, 끝나면 룰을 지운다(베이스 보존).
- **id 네임스페이스**: 사용자 룰 100000+, 본 트랙 W12 = `1012xx`.

---

## 6. ATT&CK 매핑 — IOC에 맥락을 더한다

IOC 하나도 ATT&CK technique에 연결하면 "어느 단계의 공격인가"라는 맥락이 생긴다.

| IOC/행위 | ATT&CK technique |
|----------|------------------|
| sqlmap SQLi (공개 웹 익스플로잇) | **T1190** Exploit Public-Facing Application |
| base64 인코딩 셸(W11) | **T1059** Command and Scripting Interpreter |
| 백도어 계정(W08/W11) | **T1136** Create Account |

OpenCTI의 MITRE connector가 이 attack-pattern 객체를 STIX로 보관하므로, indicator를 technique에
relationship으로 연결해두면 분석가가 IOC를 보는 순간 ATT&CK 맥락을 같이 본다.

---

## 7. 실습(lab) 형식 — 9 미션

1. **점검**: Wazuh manager + OpenCTI/MISP 인텔 플랫폼 가동
2. **IOC 공격 재현**: 알려진 악성 도구(sqlmap)로 공격 → telemetry에 IOC 출현
3. **CDB list 작성**: IOC 저장소(`edu-w12-ioc`) key:value
4. **IOC 매칭/격상 룰(id 101210)**: field-match → logtest 격상(level 12) → self-clean
5. **ATT&CK 매핑**: IOC → technique(T1190 등)
6. **인텔 플랫폼**: OpenCTI(STIX/ATT&CK) + MISP 가동 + MITRE connector
7. **IOC in telemetry**: alerts.json/audit에 IOC(sqlmap) + 출처 보존
8. **종합 보고**: STIX → CDB → Wazuh 격상 흐름
9. **정리 확인**: 커스텀 룰/list 잔재 0 (베이스 보존)

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>` 로.
> 매칭 룰은 logtest로만 검증(라이브 restart 금지) + 끝나면 룰·list 삭제(공유 인프라 보존).

---

## 8. 다음 주차 (W13) 예고 — 맥락이 평결을 바꾼다(enrichment + 빈도)

W12는 IOC를 "아느냐 모르냐"로 격상했다. W13은 한 걸음 더 — **enrichment**(평판·지리·자산 가치)와
**빈도**(같은 출발지의 반복)를 결합해 경보 우선순위를 동적으로 조정한다. 같은 경보라도 맥락이 평결을 바꾼다.
