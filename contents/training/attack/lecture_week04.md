# 공격기법 W04 — SQL Injection(sqlmap·WAF 우회) vs SQLi 탐지·차단 분석

> 공격기법 트랙 4주차. 선행: W03. 인프라: el34 (dvwa=차단, juice=탐지만). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — SQLi와 WAF의 싸움

SQL Injection(SQLi)은 가장 고전적이고 강력한 웹 취약점(OWASP A03). 공격자는 sqlmap으로 자동화하고
WAF 우회를 시도하며, 방어자는 WAF(ModSec CRS)로 탐지·차단한다. 이번 주는 그 공방을 본다.

```
 공격: SQLi payload → sqlmap 자동화 → WAF 우회(tamper)
 방어: ModSec CRS(942) → anomaly 누적 → 949110 차단(403)
```

---

## 2. SQLi 유형

| 유형 | 설명 | 예 |
|------|------|----|
| **UNION-based** | UNION으로 데이터 추출 | `' UNION SELECT user,pass FROM users--` |
| **Boolean-based blind** | 참/거짓으로 1비트씩 | `' AND 1=1--` vs `' AND 1=2--` |
| **Time-based blind** | 응답 지연으로 추론 | `' AND SLEEP(5)--` |
| **Error-based** | 에러 메시지로 추출 | `' AND extractvalue(1,...)--` |

---

## 3. sqlmap — 자동화

```bash
docker exec el34-attacker sqlmap -u 'http://10.20.30.1/rest/products/search?q=test' --batch --level=1 --risk=1
```
- `--batch`: 자동 진행. `--level/--risk`: 테스트 깊이. `--technique`: B(boolean)/T(time)/U(union)/E(error).
- `--tamper`: WAF 우회 스크립트(space2comment, charencode 등).
- 자동화는 빠르지만 매우 시끄럽다(WAF/IDS에 다량 탐지).

---

## 4. WAF 우회(tamper) — 그리고 그 한계

WAF를 우회하려 payload를 변형:
- **주석 삽입**: `UN/**/ION SE/**/LECT` (공백 → 주석).
- **대소문자**: `UnIoN sElEcT`.
- **인코딩**: URL/hex/유니코드 인코딩.

하지만 ModSec **CRS는 정규화(normalization)** 후 검사 → 단순 tamper는 대부분 무력. CRS 942 룰군은
수십 개 변형을 잡는다. 우회는 점점 어렵다(고급 tamper 필요).

```bash
# dvwa(차단 모드): SQLi → 403. juice(탐지만): 같은 payload → 200(탐지는 기록)
docker exec el34-attacker sh -c "curl -s -o /dev/null -w 'dvwa=%{http_code}\n' -H 'Host: dvwa.el34.lab' \"http://10.20.30.1/?id=1%27%20UNION%20SELECT%201--\""
```

---

## 5. 탐지·차단 분석 (방어 관점)

- **탐지**: ModSec 942xxx(SQLi 룰군)이 payload 변형을 잡는다.
- **차단**: anomaly score 누적 → 949110 → 403(dvwa). juice는 DetectionOnly → 탐지만, 200.
- **모드 차이**: 차단(dvwa) vs 탐지만(juice) — 같은 공격, 다른 결과. 운영 정책의 선택.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: sqlmap + 대상
2. **수동 UNION SQLi**: dvwa → 403
3. **WAF 우회 시도**: tamper → 결과(CRS 한계)
4. **sqlmap 자동화**: 자동 SQLi 테스트
5. **탐지 분석**: ModSec 942
6. **차단 vs 탐지**: dvwa(403) vs juice(200)
7. **방어**: parameterized query + WAF
8. **SQLi 공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W05) 예고 — XSS

W04는 SQLi였다. W05는 XSS(Cross-Site Scripting) — Reflected/Stored/DOM 유형과 WAF 우회, 그리고
탐지·차단을 다룬다.
