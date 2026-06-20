# SOC W05 — 경보 폭주 vs 경보 분석(level·groups·빈도)·오탐 판정·억제

> SOC 관제 트랙 5주차. 선행: W01–W04. 인프라: el34 (Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 경보가 너무 많다

SOC의 진짜 적은 공격이 아니라 **경보 폭주(alert fatigue)** 다. 하루 수만 건 중 진짜 위협은 몇 건.
분석가가 다 보면 중요한 걸 놓친다. 이번 주는 **폭주를 분류·판정·억제**해 진짜만 남기는 기술이다.

```
 경보 폭주 (수만 건)
   │ level 분포    → 높은 level부터
   │ groups 분포   → 어떤 종류가 폭주하나
   │ 빈도(top)     → 누가/무엇이 노이즈인가
   ▼
 오탐 판정 → 억제(suppress) → 진짜 위협만 (수 건)
```

---

## 2. 분류 축 1 — level (심각도)

Wazuh level 0–16. 폭주를 줄이는 첫 칼질 = level로 거르기.
```bash
docker exec el34-siem sh -c 'tail -2000 /var/ossec/logs/alerts/alerts.json | jq .rule.level | sort -n | uniq -c'
```
- level 0–4: 정보성(대부분 무시 가능). level 7+: 주목. level 12+: 고위험(먼저).
- 폭주의 대부분은 낮은 level. 높은 level부터 보는 게 트리아지의 기본.

---

## 3. 분류 축 2 — groups (종류)

어떤 종류의 경보가 폭주하는지.
```bash
docker exec el34-siem sh -c 'tail -2000 /var/ossec/logs/alerts/alerts.json | jq -rc .rule.groups | sort | uniq -c | sort -rn | head'
```
- 특정 그룹(예: syscheck FIM, ids)이 압도적이면 → 그 소스에 노이즈가 있다는 신호.
- 그룹별로 보면 "무엇이 폭주의 원인인가"가 보인다.

---

## 4. 분류 축 3 — 빈도 (top talkers)

누가(출발지)·무엇(rule)이 경보를 쏟아내나.
```bash
docker exec el34-siem sh -c 'tail -2000 /var/ossec/logs/alerts/alerts.json | jq -rc "[.rule.id,.rule.description]|@tsv" | sort | uniq -c | sort -rn | head'
```
- 한 rule이 폭주의 대부분 → 그 rule을 의심(오탐 후보 or 진행형 공격).
- 한 출발지가 폭주 → 집중 공격 or 노이즈 소스.

---

## 5. 오탐 판정 — 진짜인가 노이즈인가

폭주하는 경보가 오탐(false positive)인지 판정:
- **정상 업무인가?** (예: 모니터링 봇의 반복 요청, 정기 스캔).
- **맥락이 양성인가?** (내부 자산의 정상 동작).
- **빈도가 일정한가?** (자동화된 정상 작업은 규칙적, 공격은 불규칙/버스트).

판정 결과: 오탐이면 **억제**, 진짜면 **격상**(W04 커스텀 룰).

---

## 6. 억제(suppression) — 노이즈를 끈다

오탐으로 판정한 경보는 억제해 화면에서 치운다. Wazuh에서:
```xml
<!-- 특정 노이즈 rule을 level 0(미기록)으로 억제 -->
<rule id="100450" level="0">
  <if_sid>31108</if_sid>            <!-- 억제할 기존 rule -->
  <field name="url">/healthcheck</field>  <!-- 정상 패턴만 -->
  <description>SOC W05 - suppress benign healthcheck noise</description>
</rule>
```
- **level 0** = alert 안 만듦(억제). 단, **너무 넓게 억제하면 진짜를 놓친다** — 정상 패턴만 좁게.
- 억제는 양날의 칼 — 노이즈는 끄되 위협은 남겨야. 조건을 정밀하게.

> ⚠️ 공유 el34에선 wazuh-logtest로 억제 로직(level 0)만 검증 + 룰 삭제(라이브 무중단).

---

## 7. 실습(lab) 형식 — 8 미션

1. **점검**: alerts.json 경보량
2. **경보 폭주 재현**: 반복 공격으로 다발 생성
3. **level 분포 분석**: 심각도별
4. **groups 분포 분석**: 종류별 폭주 원인
5. **빈도 분석**: top rule/출발지
6. **오탐 판정**: 노이즈 vs 진짜
7. **억제 룰**: level 0 suppression → logtest 검증 + 정리
8. **경보 관리 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 억제 룰은 logtest로만 검증 + 삭제(공유 SIEM 보존).

---

## 8. 다음 주차 (W06) 예고 — ATT&CK으로 캠페인 엮기

W05는 경보를 줄였다. W06은 남은 경보를 ATT&CK 매트릭스로 읽어 — 흩어진 경보를 전술/기술 단계로
매핑하고, 한 공격자의 캠페인으로 엮어 "지금 어느 단계까지 왔나"를 본다.
