# 공격기법 W13 — 로봇 공격자: MITRE Caldera로 ATT&CK 자동 에뮬레이션 vs 탐지·매핑

> 공격기법 트랙 13주차. 선행: W01–W12. 인프라: el34 (Caldera 설치, Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 공격을 자동화한다

지금까지 손으로 공격했다. **MITRE Caldera**는 ATT&CK 기법을 **자동으로 에뮬레이션**하는 레드팀
프레임워크 — adversary profile(기법 묶음)을 agent(sandcat)에 자동 실행시켜 일관된 공격 시나리오를 재현한다.
방어자는 이 자동 공격에 대한 **탐지 커버리지**를 ATT&CK 매트릭스로 측정한다.

```
 [Caldera 서버] → adversary profile(ATT&CK 기법들) → [agent(sandcat)] 자동 실행
                                                          │
                                          각 기법 = atomic 명령(discovery/persistence/exfil...)
                                                          ▼
                                          Wazuh/osquery 탐지 → ATT&CK 매트릭스 커버리지
```

---

## 2. Caldera 구조

- **서버**: 웹 UI + REST API, adversary/ability 관리(el34 호스트에 설치).
- **ability**: 단일 ATT&CK 기법 = atomic 명령(예: T1087 계정 열거 = `cat /etc/passwd`).
- **adversary**: ability 묶음(공격 시나리오).
- **agent(sandcat)**: 타깃에서 ability를 실행하고 결과를 서버로.

핵심: Caldera는 결국 **ATT&CK 기법별 atomic 명령을 자동 실행**하는 것. 손으로 하던 걸 일관·반복·자동으로.

---

## 3. ATT&CK 기법 = atomic 명령

Caldera ability(또는 Atomic Red Team)는 각 ATT&CK technique를 작은 명령으로 정의:
| Technique | atomic 명령 (Linux) |
|-----------|---------------------|
| T1082 System Info Discovery | `uname -a; cat /etc/os-release` |
| T1087 Account Discovery | `cat /etc/passwd` |
| T1083 File/Dir Discovery | `find / -name "*.conf"` |
| T1136 Create Account | `useradd backdoor` |
| T1059 Command Interpreter | `bash -c '...'` |

이걸 자동 실행 = 에뮬레이션. 방어자는 각 기법이 탐지됐는지 본다.

---

## 4. 탐지 커버리지 매핑 (방어)

에뮬레이션 후 각 ATT&CK 기법별로 "탐지됐나?"를 매트릭스로:
```
 T1082 discovery → osquery/sysmon 탐지?  ✅/❌
 T1136 account   → Wazuh/FIM 탐지?       ✅/❌
 T1059 exec      → sysmon ProcessCreate? ✅/❌
```
- 탐지 안 된 기법(❌) = **커버리지 갭** → 룰 보강 대상(W14).
- 자동 에뮬레이션의 가치 = 일관된 공격으로 탐지를 객관적으로 측정.

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: Caldera 설치 + Wazuh
2. **ATT&CK 에뮬레이션(discovery)**: T1082/T1087/T1083 atomic
3. **에뮬레이션(persistence)**: T1136 atomic
4. **에뮬레이션(execution)**: T1059 인코딩 명령
5. **탐지 매핑**: 각 기법의 Wazuh/sysmon 탐지
6. **커버리지 갭 식별**: 탐지 안 된 기법
7. **Caldera 자동화 이해**: 서버/ability/adversary
8. **에뮬레이션 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. atomic 기법은 self-clean. Caldera 서버는 설치돼 있어
> 별도로 UI 운영 가능. 인가된 실습만.

---

## 6. 다음 주차 (W14) 예고 — 탐지 커버리지 보강·재검증

W13은 에뮬레이션 + 갭 식별이었다. W14는 레드+블루 협업 — Caldera 에뮬레이션으로 갭을 찾고, Wazuh 룰로
보강하고, 다시 에뮬레이션해 커버리지를 재검증하는 purple team 사이클을 돈다.
