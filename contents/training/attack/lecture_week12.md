# 공격기법 W12 — 숨고 버티기: 다중 persistence + 안티포렌식 vs 전수 헌팅·로그 무결성

> 공격기법 트랙 12주차. 선행: W11(root). 인프라: el34 (osquery/Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 한 번 들어왔으면 계속 있고 싶다

장악 후 공격자의 목표는 **지속(persistence)** + **은폐(anti-forensics)**. 재부팅·패치 후에도 살아남게
여러 발판을 심고, 흔적을 지운다. 방어자는 **전수 헌팅**(빠짐없이)과 **로그 무결성**으로 맞선다.

```
 persistence(다중): 백도어 계정 + cron + SSH키 + SUID + 서비스 …(하나 지워도 다른 게 남게)
 anti-forensics:    로그 삭제/변조, 타임스톰프, 히스토리 삭제
```

---

## 2. 다중 persistence — 중복이 핵심

한 가지만 심으면 발견 시 끝. 공격자는 **여러 독립 발판**을:
| 벡터 | 예 |
|------|----|
| 백도어 계정 | `useradd` (uid 0 또는 sudo) |
| cron | `/etc/cron.d/` 주기 실행 |
| SSH 키 | `~/.ssh/authorized_keys` 추가 |
| SUID | 셸에 SUID 비트 |
| 서비스/시작 | systemd/rc 스크립트 |

방어자가 하나 지워도 다른 게 재침투를 부른다 → **전수** 제거가 필수.

---

## 3. 안티포렌식 — 흔적 지우기

- **로그 삭제/변조**: `/var/log/*` 삭제, 특정 라인 제거.
- **타임스톰프**: `touch -t`로 파일 시각 위조(생성 시점 은폐).
- **히스토리**: `history -c`, `~/.bash_history` 삭제.
- **한계**: 중앙 수집 로그(Wazuh)·FIM·외부 백업은 못 지운다 → 안티포렌식의 약점.

---

## 4. 방어 — 전수 헌팅 + 로그 무결성

```bash
# 전수 헌팅(osquery): 모든 persistence 벡터를 한 번에
docker exec el34-web osqueryi --json 'SELECT username,uid FROM users WHERE uid>=1000;'
docker exec el34-web osqueryi --json 'SELECT command,path FROM crontab;'
docker exec el34-web osqueryi --json 'SELECT * FROM authorized_keys LIMIT 5;' 2>/dev/null
```
- **전수**: 한 벡터만 보면 놓친다 — 계정/cron/키/SUID/서비스 모두.
- **로그 무결성**: 중앙 수집(Wazuh) + FIM(syscheck) → 로컬 로그를 지워도 중앙엔 남음. 불변(append-only) 로그.

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: osquery
2. **다중 persistence 심기**: 계정 + cron + 키
3. **안티포렌식 시도**: 로그/히스토리 정리
4. **전수 헌팅(osquery)**: 모든 벡터 발견
5. **로그 무결성**: 중앙 수집/FIM이 안티포렌식 무력화
6. **전수 제거(self-clean)**: 모든 벡터 제거
7. **방어**: 전수 헌팅 + 불변 로그
8. **persistence 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 심은 발판은 self-clean(공유 인프라 보존). 인가된 실습만.

---

## 6. 다음 주차 (W13) 예고 — MITRE Caldera 자동 에뮬레이션

W12는 수동 persistence였다. W13은 자동화 — MITRE Caldera로 ATT&CK 기법을 자동 에뮬레이션하고
방어 탐지에 매핑한다.
