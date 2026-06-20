# SOC W11 — 악성코드 감염: C2 비콘을 IOC로 잡고 호스트를 격리하기

> SOC 관제 트랙 11주차. 선행: W07(osquery)·W09(IR)·W12(W08 인텔 개념). 인프라: el34. 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 악성코드는 집에 전화한다(C2 beacon)

감염된 호스트의 악성코드는 **C2(Command & Control) 서버에 주기적으로 연결**한다(비콘, beacon). 이
주기적 외부 통신이 악성코드의 가장 큰 약점 — **IOC(Indicator of Compromise)** 로 잡힌다.

```
 감염 호스트 ──(주기적 비콘)──→ C2 서버
   │  IOC: C2 IP/포트, 프로세스 cmdline, 파일 해시, 비콘 주기
   ▼
 osquery(연결/프로세스) + sysmon(NetworkConnect) + Suricata(C2 시그니처)로 탐지
```

---

## 2. ① Identify + IOC 추출

감염을 식별하고 **재사용 가능한 IOC**를 뽑는다:
- **네트워크 IOC**: C2 IP/포트(비표준), 비콘 주기.
- **호스트 IOC**: 악성 프로세스 cmdline/경로, 파일 해시.
```bash
docker exec el34-web osqueryi --json 'SELECT pid,name,cmdline FROM processes WHERE cmdline LIKE "%c2%";'
docker exec el34-web osqueryi --json 'SELECT pid,remote_address,remote_port FROM process_open_sockets WHERE remote_port>40000;'
```
IOC는 W12-13의 위협인텔처럼 CDB list로 만들어 재발 자동 탐지.

---

## 3. ② Hunt — 감염 범위

한 호스트만인가, 더 퍼졌나? 같은 IOC(C2 연결/프로세스)를 여러 호스트에서 헌팅.
```bash
docker exec el34-web osqueryi --json 'SELECT pid,port FROM listening_ports WHERE port=45511;'
```
- 같은 C2로 연결하는 다른 호스트 = 확산. 비콘 주기가 같으면 같은 악성코드.

---

## 4. ③ Contain — 호스트 네트워크 격리

비콘을 끊는다 = C2 통신 차단:
- **C2 차단**: Suricata/firewall로 C2 IP/포트 차단(sid 9511001).
- **호스트 격리**: 감염 호스트를 네트워크에서 분리(비콘 끊김 → 악성코드 무력화).
```
alert ip any any -> any 45511 (msg:"SOC W11 C2 beacon block"; sid:9511001;)
```

---

## 5. ④⑤ Eradicate + Recover + IOC 공유

- **Eradicate**: 악성 프로세스 종료(kill) + 파일/persistence 제거.
- **Recover**: 정상성 검증 + 재감염 감시.
- **IOC 공유**: 추출한 IOC를 CDB list(W12)/MISP로 공유 → 조직 전체가 같은 악성코드 자동 탐지.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: osquery + 네트워크 가시성
2. **감염 재현**: 악성 프로세스(C2 비콘) + C2 리스너
3. **Identify + IOC 추출**: 프로세스/연결 IOC
4. **Hunt**: 감염 범위(C2 포트/연결)
5. **Contain**: C2 차단 룰(sid 9511001)
6. **Eradicate**: 악성코드 제거
7. **Recover + IOC 공유**: 정상성 + IOC CDB
8. **악성코드 IR 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 차단 룰/악성코드는 self-clean(공유 인프라 보존).

---

## 7. 다음 주차 (W12) 예고 — 내부 위협(UEBA)

W11은 외부 악성코드였다. W12는 내부 위협 — 인가된 사용자의 권한 남용을 UEBA(행위 기반)로 잡고 증거를
보전하는, 가장 까다로운 위협을 다룬다.
