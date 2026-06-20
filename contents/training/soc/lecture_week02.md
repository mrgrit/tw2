# SOC W02 — SSH 무차별 대입 vs 시스템 로그(sshd 인증) 분석·추적

> SOC 관제 트랙 2주차. 선행: W01. 인프라: el34 (호스트 .151 auth.log + Suricata + Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 인증 로그는 침입의 1차 증거

W01에서 인증 실패 경보를 "다발이다"로 분류했다. 이번 주는 그 **sshd 인증 로그 자체**를 깊게 판다.
인증 로그는 "누가 / 어떤 계정으로 / 몇 번 / 성공했나"를 담은 **침입의 1차 증거**다.

```
 sshd 인증 로그(/var/log/auth.log)에서 읽는 것
 ─────────────────────────────────────────
 누가(출발지 IP)  ·  어떤 계정(root/admin…)  ·  몇 번(빈도)  ·  결과(Failed/Accepted)
```

el34에서는 호스트(`ssh ccc@192.168.0.151`)의 `/var/log/auth.log`가 인증 분석의 원천이다(ccc는 adm
그룹이라 sudo 없이 읽음).

---

## 2. sshd 로그 메시지 — 무엇을 보나

| 메시지 | 의미 | 신호 |
|--------|------|------|
| `Failed password for <user> from <ip>` | 존재 계정 비번 실패 | 공격/오타 |
| `Invalid user <user> from <ip>` | 없는 계정 시도 | **강한 공격 신호**(존재 계정만 노리지 않음) |
| `Connection closed by ... [preauth]` | 인증 전 끊김 | 스크립트성 시도 |
| `Accepted password/publickey for <user>` | **로그인 성공** | 정상 or 침투 성공 |

핵심 판별: **`Invalid user` 다발 + 여러 계정** = 사전(wordlist) 기반 무차별 대입. 한두 번 `Failed`는
보통 사용자 오타(정상).

---

## 3. 무차별 대입 vs 정상 — 구분하는 법

```bash
# 실패 빈도 (짧은 시간 다발이면 공격)
grep -aE "Failed password|Invalid user" /var/log/auth.log | tail -20
# 노린 계정 분포 (여러 계정 = 사전 공격)
grep -aoE "Invalid user [a-z0-9]+" /var/log/auth.log | sort | uniq -c | sort -rn
# 성공 여부 (공격 후 Accepted가 있으면 침투 성공 — 최우선!)
grep -a "Accepted" /var/log/auth.log | tail -5
```
- **빈도**: 1분에 수십 건 = 자동화 공격. 하루 2~3건 = 정상 오타.
- **계정 다양성**: root, admin, test, oracle… 여러 계정 = wordlist 공격.
- **성공 추적**: 공격 출발지에서 `Accepted`가 나오면 **침투 성공** — 즉시 P1 격상.

---

## 4. 정찰과의 상관 — 대입 전엔 보통 스캔이 있다

무차별 대입 전에 공격자는 보통 포트를 스캔해 SSH 포트를 찾는다. **스캔 경보(Suricata)의 출발지**와
**인증 공격의 출발지**가 같으면 "정찰 → 대입"의 한 공격자다.

```bash
docker exec el34-ips sh -c 'tail -3000 /var/log/suricata/eve.json | jq -rc "select(.event_type==\"alert\")|.src_ip" | sort | uniq -c'
```
출발지 매칭으로 흩어진 단계를 한 사건으로 엮는다(el34 출처 보존이 전제).

---

## 5. 사건 타임라인 — 추적의 마무리

분석가는 시간순으로 사건을 재구성한다:
```
 T0  포트 스캔 (정찰)              ← Suricata eve
 T1  SSH 무차별 대입 시작 (다발)   ← auth.log Failed/Invalid
 T2  (성공 시) Accepted            ← auth.log Accepted  ← 여기 있으면 침투!
 T3  로그인 후 행위                ← 후속 분석(W09 IR로)
```
T2(성공)의 유무가 사건의 심각도를 가른다. 성공 흔적이 없으면 "시도(차단됨)", 있으면 "침해".

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 호스트 auth.log 접근 + sshd 이벤트
2. **무차별 대입 재현**: 실패 다발(여러 계정) + 정상 로그인 1건
3. **실패 패턴 분석**: Failed/Invalid 빈도
4. **표적 계정 분석**: 어떤 계정을 노렸나
5. **Accepted vs 공격 구분**: 정상 성공 vs 공격 실패
6. **정찰 상관**: 스캔 출발지 ↔ 인증 출발지
7. **사건 타임라인**: 정찰→대입→(성공?) 시간순
8. **분석 보고서**: 무차별 대입 판정 + 침투 여부

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 인증 분석은 `/var/log/auth.log`, 스캔은
> Suricata eve. 관측·분석 중심(인프라 변경 없음).

---

## 7. 다음 주차 (W03) 예고 — 웹 공격 vs 네트워크/웹 로그 분석

W02는 인증(sshd) 로그를 팠다. W03은 웹 공격을 Apache access·ModSec audit·Suricata eve 세 로그로
교차 분석한다 — 같은 웹 공격이 세 로그에 어떻게 다르게 남는지, 무엇을 교차로 봐야 하는지.
