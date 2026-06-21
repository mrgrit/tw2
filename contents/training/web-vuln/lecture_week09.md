# 웹취약점 W09 — 접근제어: IDOR/권한상승/인가우회 vs 인가 통제 점검

> 웹취약점 트랙 9주차. 선행: W01–W08. 인프라: el34 (juiceshop). 플랫폼: tw2. WSTG-ATHZ.

---

## 1. 이번 주의 통찰 — 인가는 1위 취약점

OWASP A01 Broken Access Control. 인증(누구냐)은 통과해도 인가(무엇을 할 수 있냐)가 허술하면 남의
자원/권한에 접근한다. WSTG-ATHZ 점검.

```
 IDOR: ID만 바꿔 남의 자원 / 권한상승: 일반→관리자 / 인가우회: 무인증 접근(강제 브라우징)
```

---

## 2. 점검 항목

```bash
# 무인증 관리 엔드포인트(A01)
curl -s -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/rest/admin/application-configuration
# 강제 브라우징
curl -s -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/ftp
# 보호 엔드포인트(대조)
curl -s -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/api/Users
```
- 200(무인증 노출)=취약, 401/403(보호)=정상. 일관성 부재가 약점.

---

## 3. IDOR

순차 자원 ID를 바꿔 소유권 검사 없는 곳을 찾는다. 보호 자원(basket/user)이 IDOR이면 치명적.

---

## 4. 방어 — 서버측 인가

모든 자원 접근에 서버측 인가(소유권/역할) 검사, 기본 deny. UI 숨김/순차ID 회피는 방어 아님.

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **무인증 관리(A01)**: admin-config
3. **강제 브라우징**: /ftp
4. **인가 일관성**: 보호(401) vs 노출(200)
5. **IDOR 시도**: 순차 자원
6. **탐지**: access.log
7. **방어**: 서버측 인가
8. **접근제어 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 6. 다음 주차 (W10) 예고 — 암호화/통신(TLS)

W09는 접근제어였다. W10은 전송 보안 — 약한 TLS/cipher 점검과 전송 보안 강화를 다룬다.
