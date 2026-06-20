# W14 — 기다리지 말고 사냥하라: Threat Hunting (가설 → 질의 → Sighting)

> 보안운영 트랙 14주차. 선행: W07(osquery)·W11(sysmon)·W12–W13(인텔). 인프라: el34. 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 경보를 기다리지 마라

지금까지는 **경보가 오면 반응**했다. 하지만 잘 숨은 침입은 경보를 안 띄운다(조용한 persistence,
LOLBins, 정상처럼 보이는 계정). 능숙한 분석가는 다르다 — **가설을 세우고 먼저 사냥한다.**

```
 수동(reactive)              능동(threat hunting)
 ──────────────             ─────────────────────
 경보 대기 → 분석           가설 → 질의 → 발견 → 문서화 → 운영화
 "뜬 것만 본다"             "안 떴어도 있을 법한 것을 찾는다"
```

핵심 전제: **충분한 텔레메트리**(osquery 스냅샷 + sysmon 이벤트 + Wazuh 평결)가 있어야 사냥할 데이터가 있다.

---

## 2. 위협 헌팅 5단계

```
 ① 가설(Hypothesis)   "정찰이 있었으니 그 뒤 호스트에 persistence가 생겼을 것"
 ② 질의(Query)        osquery/sysmon/Wazuh로 실제 데이터를 캔다
 ③ 발견(Discover)     잠복한 발판(비정상 계정·cron·인코딩 프로세스)을 끄집어낸다
 ④ 문서화(Document)   STIX Sighting/Report + ATT&CK 매핑 + MISP TLP 공유
 ⑤ 운영화(Operationalize)  발견을 Wazuh 룰로 굳혀 재발 시 자동 탐지
```

가설이 좋아야 사냥이 산다. 가설은 보통 **ATT&CK technique**(persistence=TA0003)나 이전 단계의 정황
(정찰 로그)에서 나온다.

---

## 3. ① 가설 — ATT&CK에서 출발

좋은 헌팅 가설은 구체적이고 검증 가능해야 한다.

| 가설 | 근거(ATT&CK) | 질의 대상 |
|------|-------------|-----------|
| 백도어 계정이 생겼을 것 | T1136 Create Account | osquery `users` |
| cron/키로 지속성을 심었을 것 | T1053/T1098 | osquery `crontab`/authorized_keys |
| 인코딩 셸을 실행했을 것 | T1059/T1027 | sysmon ProcessCreate(cmdline) |
| 비표준 포트로 콜백할 것 | T1571 | osquery `listening_ports`/sysmon NetworkConnect |

---

## 4. ② 질의 — 스냅샷 + 이벤트로 캔다

W07(osquery 스냅샷)과 W11(sysmon 이벤트)을 **결합**해 사냥한다.

```bash
# 비정상 계정 (가설: 백도어 계정)
docker exec el34-web osqueryi --json 'SELECT username,uid,shell FROM users WHERE uid>=1000;'
# cron persistence (가설: 스케줄 지속성)
docker exec el34-web osqueryi --json 'SELECT command,path FROM crontab;'
# 인코딩 프로세스의 흔적 (가설: 인코딩 셸 — 단명이라 sysmon이 잡음)
grep -a "Linux-Sysmon" /var/log/syslog | grep -a "b64decode" | tail -3
```
- **스냅샷(osquery)**: 지금 남아있는 상태(계정/cron/키) — persistence 사냥에 강함.
- **이벤트(sysmon)**: 이미 죽은 단명/인코딩 프로세스 — 실행 흔적 사냥에 강함.
- 둘을 합치면 "지금 있는 것 + 과거에 일어난 것"을 모두 캔다.

---

## 5. ④ 문서화 — STIX Sighting + MISP TLP

발견을 사람 메모가 아니라 **표준**으로 남겨야 재사용·공유된다.
- **STIX Sighting**: "이 indicator를 (언제/어디서) 실제로 봤다"는 관측 기록 → indicator에 신뢰도를 더한다.
- **STIX Report**: 헌팅 결과(여러 객체 묶음)를 보고서 객체로.
- **MISP TLP**: 공유 범위 등급 — `TLP:RED`(비공개)/`AMBER`(제한)/`GREEN`(커뮤니티)/`CLEAR`(공개).
  민감 발견은 TLP를 붙여 적절한 범위로만 공유한다.

el34엔 OpenCTI/MISP가 가동 중이라, 운영에선 Sighting을 OpenCTI에 올리고 MISP로 TLP 공유한다.

---

## 6. ⑤ 운영화 — 발견을 Wazuh 룰로 굳힌다

헌팅의 마무리는 **재발 자동 탐지**다. 한 번 찾은 패턴은 Wazuh 룰(id 101401)로 굳혀 다음엔 경보가 뜨게.
```xml
<rule id="101401" level="12">
  <decoded_as>json</decoded_as>
  <field name="hunt_finding">backdoor-account</field>
  <description>EDU W14 - hunted persistence pattern, auto-detect on recurrence</description>
</rule>
```
- 수동 헌팅(1회)을 자동 탐지(상시)로 전환 — 헌터의 노력을 SIEM에 영구 저장하는 것.
- 공유 el34에서는 wazuh-logtest로 검증만 + 삭제(베이스 보존).

---

## 7. 실습(lab) 형식 — 9 미션

1. **점검**: 헌팅 텔레메트리(osquery+sysmon+Wazuh)
2. **가설 + 잠복 침투 재현**: 조용한 persistence(계정 huntme + cron) 심기(경보 안 뜸)
3. **질의 1 (osquery)**: 비정상 계정 헌팅 → huntme 발견
4. **질의 2 (osquery)**: cron/persistence 벡터 헌팅
5. **질의 3 (sysmon)**: 인코딩 프로세스 이벤트 헌팅
6. **운영화**: 발견을 Wazuh 룰(id 101401)로 굳힘 → logtest
7. **문서화/공유**: STIX Sighting + ATT&CK + MISP TLP
8. **종합 보고**: 헌팅 5단계 한 바퀴
9. **정리 확인**: 계정/cron/룰 잔재 0 (베이스 보존)

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>`(sysmon은 호스트 syslog).
> 룰은 logtest로만 검증, 실습 발판은 self-clean(공유 인프라 보존).

---

## 8. 다음 주차 (W15) 예고 — 기말: APT 캠페인 종합 (수료)

W14까지 14주의 무기를 다 익혔다. W15는 수료 시험 — 한 APT 그룹이 5단계 킬체인(정찰→웹 침투→호스트
발판→C2/유출→대응)으로 들어오고, 너는 방화벽·IDS·WAF·SIEM·osquery·sysmon·위협인텔을 **하나의 캠페인에
총동원**해 끝까지 막아내고 APT IR 보고서로 종합한다.
