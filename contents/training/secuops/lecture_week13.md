# W13 — 맥락이 평결을 바꾼다: enrichment와 빈도로 경보 우선순위 자동 조정

> 보안운영 트랙 13주차. 선행: W12(IOC/CDB). 인프라: el34 (Wazuh + OpenCTI/MISP). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 같은 경보, 다른 평결

W12는 "알려진 악성인가(IOC 매칭)"만 봤다. 하지만 현실에선 **같은 경보라도 맥락이 위험도를 바꾼다.**

```
 같은 SQLi 경보, 다른 맥락                          평결
 ────────────────────────                          ──────
 출발지가 처음 보는 평범한 IP, 1회                  P3 (보통)
 출발지가 평판 불량(VirusTotal/abuse.ch)            P2 (주의)
 출발지가 적대 국가(GeoIP) + 2분에 5회 반복         P1 (고위험) ← 자동 격상
```

CTI 운영의 성숙은 정적 매칭(W12)을 넘어 **enrichment(맥락 보강) + 빈도(반복)** 로 우선순위를 **동적**으로
조정하는 것이다. 그리고 그걸 **자동화**(Stream Connector)한다.

---

## 2. enrichment — 경보에 맥락을 붙인다

raw 경보(출발지 IP, 공격 유형)에 외부 지식을 덧붙여 판단을 돕는다.

| enrichment | 출처 | 격상 신호 |
|------------|------|-----------|
| **GeoIP** | MaxMind/GeoLite | 적대/이상 국가 출발지 |
| **평판(reputation)** | VirusTotal·abuse.ch·MISP | 알려진 악성/봇넷 IP |
| **자산 가치** | 내부 CMDB | 중요 자산 대상 공격 |
| **빈도(frequency)** | Wazuh 상관 | 짧은 시간 반복 |

- Wazuh는 alert에 GeoLocation을 붙이거나(GeoIP 설정 시), CDB list로 평판을 조회해 맥락을 더한다.
- 핵심: enrichment는 **경보를 지우거나 만들지 않고, 우선순위(level)를 바꾼다.**

---

## 3. 빈도 격상 — frequency / timeframe (이번 주의 핵심)

Wazuh 상관 룰은 "정해진 시간(timeframe) 안에 N번(frequency) 이상 매칭되면 격상"한다.
```xml
<group name="edu_w13,">
  <rule id="101300" level="5">              <!-- base: IOC 1회 -->
    <decoded_as>json</decoded_as>
    <field name="tool">sqlmap</field>
    <description>EDU W13 base - known-bad tool</description>
  </rule>
  <rule id="101301" level="13" frequency="3" timeframe="120">  <!-- 120초내 3회+ → 격상 -->
    <if_matched_sid>101300</if_matched_sid>
    <description>EDU W13 - repeated known-bad tool, escalate to critical</description>
  </rule>
</group>
```
```bash
# 같은 IOC를 여러 번 → 빈도 룰이 고위험으로 격상 (wazuh-logtest로 검증)
printf '%s\n%s\n%s\n%s\n%s\n' '{"tool":"sqlmap"}' '{"tool":"sqlmap"}' '{"tool":"sqlmap"}' \
  '{"tool":"sqlmap"}' '{"tool":"sqlmap"}' | sudo /var/ossec/bin/wazuh-logtest
#  → id 101301, level 13, frequency 3, "Alert to be generated."  (반복 → 격상!)
```
- `if_matched_sid`(특정 룰 반복) / `if_matched_group`(그룹 반복) + `same_source_ip`/`same_field`로
  "같은 출발지의 반복"만 격상하게 좁힐 수 있다.
- ⚠️ 라이브 적용은 restart 필요 → 공유 el34에서는 **wazuh-logtest로 격상 로직만 검증** + 룰 삭제.

---

## 4. 평판 enrichment 격상 — 맥락 필드로 올린다

빈도 외에 **평판 맥락** 도 격상 신호다. enrichment로 붙은 reputation 필드를 룰이 본다.
```xml
<rule id="101302" level="12">
  <decoded_as>json</decoded_as>
  <field name="reputation">known-bad</field>   <!-- enrichment 결과 -->
  <description>EDU W13 - bad-reputation source, escalate</description>
</rule>
```
- 운영에선 CDB list(평판 IOC) + `<list lookup>`로 src_ip를 조회해 reputation을 판정하고 격상한다.
- enrichment(평판/지역) + 빈도(반복)를 **결합**하면 "평판 불량 + 반복" = 즉시 P1이 된다.

---

## 5. 자동화 — OpenCTI Stream Connector → CDB sync

수작업으로 IOC를 CDB에 넣는 건 한계가 있다. 운영에선 **OpenCTI Stream Connector**(또는 Python
스크립트)가 OpenCTI의 indicator 변경을 실시간 구독해 Wazuh CDB list로 자동 sync한다.

```
[OpenCTI] indicator 추가/갱신
   │ (live stream / TAXII poll)
   ▼
[Stream Connector] STIX → key:value 변환
   │
   ▼
[Wazuh CDB list] 자동 갱신 → 매칭 룰이 즉시 새 IOC 인식
```
- el34엔 OpenCTI connector들(MITRE, import/export STIX, opencti)이 가동 중이다. 이 그림을 이해하면
  "인텔이 들어오면 SIEM이 자동으로 알아본다"는 운영 자동화의 끝그림이 보인다.

---

## 6. 실습(lab) 형식 — 9 미션

1. **점검**: Wazuh manager + 인텔 스택
2. **enrichment 개념 + 평판 격상 룰(id 101302)**: reputation 필드 → logtest 격상
3. **반복 IOC 공격**: 같은 출발지에서 sqlmap 반복
4. **빈도 격상 룰(id 101301)**: frequency/timeframe → logtest 격상(level 13)
5. **결합 분석**: enrichment + 빈도 → 동적 우선순위(P1)
6. **자동화**: OpenCTI Stream Connector → CDB sync (가동 connector 확인)
7. **반복 공격 수렴**: alerts.json 같은 출처 반복(출처 보존)
8. **종합 보고**: 맥락(평판/지역/빈도)이 평결을 바꾼다
9. **정리 확인**: 커스텀 룰 잔재 0 (베이스 보존)

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>` 로.
> 격상 룰은 logtest로만 검증(라이브 restart 금지) + 끝나면 삭제(공유 인프라 보존).

---

## 7. 다음 주차 (W14) 예고 — 기다리지 말고 사냥하라(Threat Hunting)

W13까지는 경보가 오면 반응했다. W14는 능동 — **가설을 세우고(이 호스트에 인코딩 셸이 있을까?),
데이터를 질의하고(osquery/Wazuh/sysmon), 발견을 Sighting으로 남긴다.** 경보를 기다리지 않는 헌팅.
