# 웹취약점 W05 — SQL Injection: Error/Union/Blind vs SQLi 탐지·방어

> 웹취약점 트랙 5주차. 선행: W01–W04. 인프라: el34 (dvwa 차단/juice 탐지만). 플랫폼: tw2. WSTG-INPV-05.

---

## 1. 이번 주의 통찰 — SQLi 유형별 추출 기법

SQLi(A03)는 추출 방식에 따라 유형이 갈린다 — Error/Union(직접 추출), Blind(간접 추론). 유형을 알아야
효율적으로 데이터를 뽑고, 방어자는 모든 유형을 막아야 한다.

```
 Error-based:  에러 메시지에 데이터 노출 (extractvalue 등)
 Union-based:  UNION SELECT로 결과에 직접 추출
 Blind(Boolean): 참/거짓 응답 차이로 1비트씩
 Blind(Time):  응답 지연(SLEEP)으로 추론
```

---

## 2. 유형별 페이로드

```bash
# Union (결과에 직접)
?id=1' UNION SELECT user,password FROM users-- -
# Boolean blind (참/거짓)
?id=1' AND 1=1-- -   vs   ?id=1' AND 1=2-- -
# Time blind (지연)
?id=1' AND SLEEP(5)-- -
# Error (에러 노출)
?id=1' AND extractvalue(1,concat(0x7e,version()))-- -
```

---

## 3. 탐지 (WSTG/방어)

- ModSec 942 룰군이 UNION/AND/OR/SLEEP/주석 등 SQLi 패턴 탐지 → 949110 차단(dvwa 403).
- Blind는 페이로드가 미묘(AND 1=1)해도 942가 잡는 변형 다수.
- juice(DetectionOnly): 탐지만 200, dvwa(차단): 403.

---

## 4. 방어 — parameterized query

- **근본**: prepared statement/parameterized query(입력을 데이터로만).
- 보조: 입력 검증(allowlist), 최소권한 DB 계정, 에러 숨김(Error-based 차단), WAF.

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **Union-based**: UNION SELECT
3. **Boolean blind**: AND 1=1 vs 1=2
4. **Time blind**: SLEEP
5. **탐지**: ModSec 942 (유형별)
6. **차단 vs 탐지**: dvwa vs juice
7. **방어**: parameterized query
8. **SQLi 점검 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 6. 다음 주차 (W06) 예고 — XSS/CSRF

W05는 SQLi였다. W06은 XSS/CSRF — 스크립트 주입과 요청 위조, CSP 방어를 다룬다.
