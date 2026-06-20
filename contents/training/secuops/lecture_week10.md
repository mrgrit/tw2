# W10 — 분석가의 조종석: Wazuh dashboard + FIM + Active Response

> 보안운영 트랙 10주차. 선행: W01–W09. 인프라: el34 (el34-wazuh-dashboard / -indexer / el34-siem). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 평결을 "운영"하는 조종석

W09에서 manager가 평결(alerts.json)을 만드는 법을 배웠다. 이번 주는 그 평결을 **운영**하는 분석가의
조종석 세 가지를 다룬다:

```
 ① 한 화면 관제          ② 파일 변조 감지          ③ 자동 대응
 ─────────────          ─────────────────          ─────────────
 dashboard 5 패널        FIM(syscheck) delta        Active Response
 (Overview/Agents/…)     /etc·/home 변경 즉시       firewall-drop 자동 차단
```

탐지(W01–W09)에서 한 걸음 더 — **보고(visualize) → 변조 감지(FIM) → 자동 대응(AR)** 으로 나아간다.

---

## 2. dashboard 와 indexer — 평결이 화면이 되는 길

```
alerts.json  →  filebeat/shipper  →  [el34-wazuh-indexer]  →  [el34-wazuh-dashboard]
(manager 평결)    적재               OpenSearch (색인·검색)     Web UI (siem.el34.lab)
```

- **indexer (OpenSearch)** = 별도 컨테이너 `el34-wazuh-indexer`. 평결을 `wazuh-alerts-*` 인덱스로
  색인해 **빠른 검색/집계**를 가능하게 한다. (인증 보호 — `https://…:9200`, 401 = 살아있음.)
- **dashboard** = 별도 컨테이너 `el34-wazuh-dashboard` (vhost `siem.el34.lab`). indexer를 읽어 패널을 그린다.
- **5 패널**:

| 패널 | 용도 |
|------|------|
| Overview | 전체 경보 추이·심각도 분포 |
| Agents | agent별 상태·이벤트 |
| Modules | FIM/SCA/Vulnerability 등 모듈별 뷰 |
| Discovery | raw event 탐색(쿼리·필터) |
| Rules | 룰 검색·관리 |

> 패널이 비면 보통 **shipper/indexer** 문제 — 평결은 있는데(alerts.json) 색인이 안 된 것.
> 데이터 경로(alerts.json → indexer → dashboard)를 거꾸로 짚으면 원인이 나온다.

---

## 3. FIM (File Integrity Monitoring) — 무엇이 언제 바뀌었나

syscheck가 지정한 디렉터리의 파일을 주기적/실시간으로 해싱해 **변경(delta)** 을 잡는다.

el34-web agent의 두 가지 감시 방식(`ossec.conf` `<syscheck>`):

| 대상 | 방식 | 반응 |
|------|------|------|
| `/etc, /usr/bin, /bin, /boot` | `frequency 43200`(12h 주기) | 다음 스캔 때 |
| `/etc/apache2, /etc/modsecurity, /home/ccc` | **realtime="yes"**(+whodata/report_changes) | **즉시(초)** |

```bash
# 실시간 감시 경로 변경 → 즉시 syscheck 경보
docker exec el34-web sh -c 'echo x > /home/ccc/canary.txt'
sleep 12
docker exec el34-siem sh -c 'tail -400 /var/ossec/logs/alerts/alerts.json \
  | jq -c "select(.syscheck.path?|test(\"canary\"))|{path:.syscheck.path,event:.syscheck.event,rule:.rule.id}"'
#   → {"path":"/home/ccc/canary.txt","event":"added","rule":"554"}   (rule 554 = File added)
```
- **realtime vs periodic**: 민감 경로는 realtime로, 광범위 경로는 주기 스캔으로. 비용/적시성 트레이드오프.
- `report_changes`는 **무엇이 바뀌었는지**(diff)까지, `whodata`는 **누가 바꿨는지**(감사 추적)까지 준다.

---

## 4. FIM 격상 — 변조의 위험도를 구분 (커스텀 룰)

모든 FIM 변경이 같은 위험은 아니다. `/etc/passwd`에 계정이 끼어든 변조는 백도어 신호 → 상위 level로
격상한다(W09의 커스텀 룰 패턴 재사용).

```xml
<group name="edu,syscheck,">
  <rule id="101010" level="12">
    <if_group>syscheck</if_group>          <!-- FIM 경보 뒤에 체이닝 -->
    <field name="file">/etc/passwd</field>  <!-- 특정 민감 파일만 -->
    <description>EDU W10 - /etc/passwd tampered (possible backdoor)</description>
  </rule>
</group>
```
- **라이브 반영엔 `wazuh-control restart` 필요** → 공유 el34에서는 **룰 작성 + `wazuh-logtest`로 문법/로딩
  검증까지만** 하고 끝나면 삭제(베이스 보존). (syscheck 이벤트는 내부 발생이라 logtest로 직접 발화시키긴
  어렵다 — 룰셋이 에러 없이 로드되는지로 검증한다.)

---

## 5. Active Response — 손 안 대고 되받아치기

고위험 경보에 사람을 기다리지 않고 **자동 대응**한다. manager `ossec.conf`의 `<command>` +
`<active-response>`로 특정 룰/레벨 트리거 시 `firewall-drop`을 실행하게 매핑한다.

```xml
<command>
  <name>firewall-drop</name>
  <executable>firewall-drop</executable>
  <timeout_allowed>yes</timeout_allowed>
</command>
<active-response>
  <command>firewall-drop</command>
  <location>local</location>
  <level>12</level>          <!-- level≥12 경보에 -->
  <timeout>600</timeout>     <!-- 600초 후 자동 해제 (무한 차단 방지) -->
</active-response>
```
- **반드시 `timeout` + 화이트리스트**: timeout 없으면 오탐 한 번에 **자가 DoS**(정상 IP 영구 차단). el34
  기본 `ossec.conf`엔 active-response가 **주석 템플릿**으로만 있다(미활성).
- 실행 기록: `/var/ossec/logs/active-responses.log`.
- ⚠️ **공유 인프라에서 실제 firewall-drop 활성/트리거 금지** — 설정 점검과 설계 서술까지만(다른 학생 차단 위험).

---

## 6. 5개 소스가 한 조종석으로

dashboard의 힘은 **여러 소스를 한 화면에 모으는** 것:

| 소스 | 경로 | dashboard 패널 |
|------|------|----------------|
| ModSec audit(WAF) | web agent apache | Discovery / web 그룹 |
| Suricata eve(IDS) | ips agent json | Discovery / ids 그룹 |
| osquery | web agent | Modules |
| syscheck(FIM) | web agent realtime | Modules(FIM) |
| 호스트 이벤트 | agent syslog | Agents |

출처 IP(10.20.30.202) 보존으로 W08의 상관 분석을 이 한 화면에서 그대로 한다.

---

## 7. 실습(lab) 형식 — 9 미션

1. **점검**: manager(analysisd) + dashboard/indexer 컨테이너 + indexer 생존
2. **FIM 설정**: web syscheck realtime 경로
3. **FIM 실시간 탐지**: /home/ccc canary → syscheck added(rule 554) → self-clean
4. **FIM 격상 룰**: local_rules.xml id 101010 작성 → logtest 로드 검증 → self-clean
5. **Active Response 점검**: ossec.conf 템플릿 + firewall-drop/timeout 설계(읽기전용)
6. **다소스 수렴**: 웹공격 재현 → alerts.json ids+syscheck 함께
7. **agent ship**: web Wazuh agent 가동
8. **종합 보고**: 조종석 3요소(관제/FIM/AR)
9. **정리 확인**: 커스텀 룰·canary 잔재 0

> 모든 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-<comp>` 로.
> 커스텀 룰은 logtest 검증만, active-response는 점검만(라이브 restart·차단 금지) — 공유 인프라 보존.

---

## 8. 다음 주차 (W11) 예고 — 호스트의 비행기록장치(sysmon for Linux)

W10까지 네트워크·WAF·FIM·자동대응을 다뤘다. W11은 호스트의 **그 순간**을 잡는다 — sysmon for Linux로
프로세스 생성·네트워크 연결·인코딩 명령(리버스셸)을 이벤트 단위로 기록하는 "비행기록장치"를 배운다.
