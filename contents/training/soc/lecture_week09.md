# SOC W09 — 사고 발생 첫 60분: 식별·격리·제거·복구·교훈의 IR 절차

> SOC 관제 트랙 9주차. 선행: W01–W08. 인프라: el34. 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 분석에서 대응으로

W08까지는 **분석**이었다. 사고가 터지면 분석만으론 부족하다 — **대응(Incident Response)** 이 필요하다.
IR은 즉흥이 아니라 **정해진 절차**다. 첫 60분의 행동이 피해를 가른다.

```
 IR 라이프사이클 (NIST 기반)
 ① Identify(식별)  → ② Contain(격리)  → ③ Eradicate(제거)  → ④ Recover(복구)  → ⑤ Lessons(교훈)
 무슨 일?            확산 차단            위협 뿌리 제거         정상화/검증           재발 방지
```

---

## 2. ① Identify — 무슨 일이 일어났나

- **범위(scope)**: 어느 자산이, 어떤 공격으로, 언제부터.
- **심각도**: 침투 성공? 데이터 접근? (W08의 분석을 활용).
- **증거 보전**: 로그/타임라인을 기록(나중에 법무/포렌식).
```bash
# 사고의 출발지/시각/단계 식별 (W01-W08 분석 활용)
docker exec el34-siem sh -c 'tail -1000 /var/ossec/logs/alerts/alerts.json | jq -rc "select(.data.src_ip==\"10.20.30.202\")|[.timestamp,.rule.description]|@tsv" | tail -5'
```

---

## 3. ② Contain — 확산을 막아라

위협이 더 퍼지기 전에 격리. **차단 우선, 분석 나중**.
- **네트워크 격리**: 공격 출발지 차단(방화벽/IDS), 감염 호스트 분리.
- IDS 차단/탐지 룰로 출발지 플래그(Suricata sid 9509001).
```
alert ip 10.20.30.202 any -> any any (msg:"IR contain - flag attacker source"; sid:9509001;)
```
> ⚠️ 공유 el34에선 drop 대신 **alert(탐지 플래그)** 룰로 격리를 시연 + self-clean. 운영은 firewall drop.
> 격리는 빠르되 정밀하게 — 너무 넓으면 정상 서비스도 끊긴다.

---

## 4. ③ Eradicate — 뿌리를 뽑아라

격리 후 위협의 흔적을 완전 제거.
- **persistence 제거**: 백도어 계정(userdel), cron/키, 웹쉘 파일(rm).
- osquery로 빠짐없이 헌팅(W07/W14) 후 제거.
```bash
docker exec el34-web osqueryi --json 'SELECT username FROM users WHERE username="socw9bd";'  # 백도어 계정
docker exec el34-web sh -c 'userdel -r socw9bd; rm -f /var/www/.../shell.php'                # 제거
```
- 하나라도 남으면 재침투. 빠짐없이.

---

## 5. ④ Recover — 정상으로 되돌려라

- 서비스 정상 동작 검증(헬스체크).
- 변경된 설정/파일 복원(백업).
- 모니터링 강화(재발 감시).
```bash
docker exec el34-web sh -c 'curl -s -o /dev/null -w "web=%{http_code}\n" -H "Host: dvwa.el34.lab" http://localhost/'
```

---

## 6. ⑤ Lessons Learned — 교훈

- **타임라인**: 사고 전체를 시간순으로.
- **근본 원인(root cause)**: 어떻게 들어왔나(패치 미적용? 약한 비번?).
- **재발 방지**: 탐지 룰 추가(W04), 설정 강화, 절차 개선.
- IR 보고서로 문서화 → 조직 학습.

---

## 7. 실습(lab) 형식 — 8 미션

1. **점검**: IR 준비(로그/도구)
2. **사고 재현**: 침투 + 발판(백도어 계정/웹쉘)
3. **Identify**: 범위/심각도 식별
4. **Contain**: 출발지 격리 룰(sid 9509001) → 검증 → 정리
5. **Eradicate**: persistence 제거(osquery)
6. **Recover**: 서비스 정상성 검증
7. **Lessons**: 타임라인 + 근본 원인
8. **IR 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 격리 룰은 alert로 시연 + self-clean(공유 인프라 보존).

---

## 8. 다음 주차 (W10) 예고 — 웹쉘 침해 포렌식

W09는 IR 절차 전반을 다뤘다. W10은 특정 사고 — SQLi→웹쉘→콜백을 웹 로그로 포렌식하고 헌팅해 끊어내는
웹 침해 대응을 깊게 다룬다.
