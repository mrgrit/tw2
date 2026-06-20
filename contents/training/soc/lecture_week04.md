# SOC W04 — Wazuh 관제(Manager/Agent)·커스텀 룰 작성·검증

> SOC 관제 트랙 4주차. 선행: W01–W03. 인프라: el34 (Wazuh manager). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 분석가가 탐지를 만든다

W01–W03은 이미 뜬 경보를 분석했다. 이번 주는 한 걸음 더 — **분석가가 직접 탐지를 만든다.** 기본 룰이
못 잡거나 너무 낮게 평가하는 위협을 커스텀 룰로 잡아 SOC의 눈을 확장한다.

```
 raw 로그  →  [decoder] 필드 추출  →  [rule] level/group  →  alerts.json
                                         ▲
                              여기에 분석가가 커스텀 룰 추가
                              (못 잡던 위협 탐지 / 우선순위 격상)
```

---

## 2. Wazuh 관제 구조 복습 (Manager/Agent)

| 구성 | 역할 |
|------|------|
| **Manager**(el34-siem) | decoder→rule 엔진(analysisd), agent 통신(remoted), 평결(alerts.json) |
| **Agent**(web 004/ips 003) | `<localfile>`로 로그 수집 → manager로 ship |

```bash
docker exec el34-siem /var/ossec/bin/wazuh-control status | grep -E "analysisd|remoted"
docker exec el34-siem /var/ossec/bin/agent_control -l
```

---

## 3. decoder 디버그 — wazuh-logtest

룰을 쓰기 전, 분석가는 raw 로그가 어떻게 파싱되는지 본다(어떤 필드가 뽑히나 = 룰이 쓸 재료).
```bash
echo 'Jan 1 00:00:00 web sshd[1]: Failed password for root from 9.9.9.9 port 22 ssh2' \
  | docker exec -i el34-siem /var/ossec/bin/wazuh-logtest
#  Phase2: decoder sshd, srcip 9.9.9.9 / Phase3: rule 5760 (sshd brute)
```

---

## 4. 커스텀 룰 작성 — local_rules.xml

`/var/ossec/etc/rules/local_rules.xml`에 룰을 쓴다. 핵심 요소:
```xml
<rule id="100440" level="10">
  <decoded_as>json</decoded_as>            <!-- 이 decoder가 잡은 로그만 -->
  <field name="alert_signature">CRITICAL_PATTERN</field>  <!-- 조건 -->
  <description>SOC W04 - custom detection</description>
</rule>
```
- **id**: 사용자 룰 100000+(본 트랙 soc = `1004xx`).
- **level**: 0–16. 못 잡던 위협을 적정 level로.
- **체이닝**: `<if_sid>`(특정 룰 뒤) / `<if_group>`(그룹 뒤)로 기존 탐지에 맥락 추가.

---

## 5. 검증 — 라이브 무중단 (wazuh-logtest)

공유 SIEM은 함부로 재시작하지 않는다. 룰을 쓰면 **wazuh-logtest로 발화를 검증**하고(라이브 analysisd
무중단) 끝나면 지운다(베이스 보존).
```bash
echo '{"alert_signature":"CRITICAL_PATTERN","src_ip":"9.9.9.9"}' | sudo /var/ossec/bin/wazuh-logtest
#  → Phase3: id 100440, level 10, "Alert to be generated."
```
- 실제 운영 적용은 `wazuh-control restart` 필요. 공유 환경에선 logtest 검증까지 + 룰 삭제.

---

## 6. 튜닝 — 오탐을 줄인다

탐지를 만들면 **오탐(false positive)**도 따라온다. 분석가는:
- 조건을 좁힌다(특정 필드/값으로 한정).
- level을 적정화(너무 높으면 alert fatigue).
- 정상 패턴은 예외 처리(`<if_group>`에서 제외, 화이트리스트).

좋은 룰 = "놓치지 않으면서(낮은 오탐) 묻히지 않게(적정 level)".

---

## 7. 실습(lab) 형식 — 8 미션

1. **점검**: manager(analysisd) + agent
2. **decoder 디버그**: wazuh-logtest로 파싱 확인(sshd→5760)
3. **탐지 갭 식별**: 못 잡거나 낮게 평가되는 위협
4. **커스텀 룰 작성**: local_rules.xml(id 100440)
5. **logtest 검증**: 발화 확인(라이브 무중단)
6. **실제 이벤트 검증**: 공격 재현 → 룰 로직 확인
7. **튜닝**: 오탐 줄이기 + 정리(베이스 보존)
8. **룰 문서화 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 룰은 logtest로만 검증 + 끝나면 삭제(공유 SIEM 보존).

---

## 8. 다음 주차 (W05) 예고 — 경보 폭주 vs 경보 분석·오탐 판정·억제

W04는 탐지를 만들었다. W05는 반대 — 경보가 너무 많을 때(폭주) level/groups/빈도로 분류하고, 오탐을
판정하고, 억제(suppression)해 진짜 위협만 남기는 alert 관리(alert fatigue 대응)를 다룬다.
