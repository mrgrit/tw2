# 웹취약점 W04 — 인증/세션: 약한 PW·JWT·세션 고정 vs 인증 보안 점검

> 웹취약점 트랙 4주차. 선행: W01–W03. 인프라: el34 (juiceshop, dvwa). 플랫폼: tw2. WSTG-ATHN/SESS.

---

## 1. 이번 주의 통찰 — 인증은 자주 약하다

인증/세션은 OWASP A07. 약한 비밀번호, 무차별 대입, SQLi 인증 우회, JWT 약점, 세션 고정/탈취 —
점검할 게 많다. WSTG-ATHN(인증)·WSTG-SESS(세션)를 따른다.

---

## 2. 인증 공격

| 공격 | 설명 |
|------|------|
| 무차별 대입 | 약한 PW를 사전/조합으로(rate-limit 없으면) |
| 자격증명 스터핑 | 유출 계정 재사용 |
| SQLi 인증 우회 | `' OR 1=1--`로 로그인 우회(W03 attack) |
| 기본 계정 | admin/admin 등 |
```bash
# SQLi 인증 우회 → JWT 획득 (juiceshop)
curl -s -H 'Host: juice.el34.lab' -H 'Content-Type: application/json' -d @sqli.json http://10.20.30.1/rest/user/login
```

---

## 3. JWT 약점 (WSTG-SESS)

- payload 누구나 디코드(민감정보 노출), `alg:none`, 약한 서명키, 만료/서명 미검증.
- JWT는 세션 상태를 클라이언트가 들고 있어 **검증 부실 시 위조** 가능.

---

## 4. 세션 점검

- **쿠키 플래그**: `HttpOnly`(JS 접근 차단), `Secure`(HTTPS만), `SameSite`(CSRF 완화).
- **세션 고정(fixation)**: 로그인 후 세션 ID 재발급 안 하면 공격자가 심은 ID로 탈취.
- **세션 만료**: 로그아웃/타임아웃 시 무효화되나.
```bash
curl -sI -H 'Host: dvwa.el34.lab' http://10.20.30.1/ | grep -i 'set-cookie'
```

---

## 5. 방어

- 강한 PW 정책 + rate-limit + MFA, 기본 계정 제거.
- parameterized query(SQLi 우회 차단), JWT 강한 키·alg 고정·엄격 검증.
- 쿠키 HttpOnly/Secure/SameSite, 로그인 시 세션 재발급, 적절한 만료.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 로그인 API
2. **무차별 대입**: 반복 로그인 시도
3. **SQLi 인증 우회**: ' OR 1=1-- → JWT
4. **JWT 분석**: payload 디코드
5. **세션 쿠키**: HttpOnly/Secure 점검
6. **탐지**: 로그인 남용
7. **방어**: 강한 인증 + 세션 보안
8. **인증 점검 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W05) 예고 — SQL Injection 심화

W04는 인증/세션이었다. W05는 SQLi 본격 — Error/Union/Blind 유형과 탐지·방어를 깊게 다룬다.
