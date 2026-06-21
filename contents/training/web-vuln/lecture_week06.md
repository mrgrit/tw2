# 웹취약점 W06 — XSS/CSRF: 스크립트 주입 vs XSS 탐지·CSP 방어

> 웹취약점 트랙 6주차. 선행: W01–W05. 인프라: el34 (dvwa/juice). 플랫폼: tw2. WSTG-CLNT/INPV.

---

## 1. 이번 주의 통찰 — 브라우저를 노린다

XSS와 CSRF는 둘 다 **피해자의 브라우저**를 악용한다. XSS는 공격자 스크립트를 실행시키고, CSRF는
피해자의 인증된 세션으로 원치 않는 요청을 보내게 한다.

```
 XSS:  공격자 JS → 피해자 브라우저 실행 (세션 탈취/피싱)
 CSRF: 피해자 세션으로 위조 요청 (비번 변경/송금 등)
```

---

## 2. XSS (W05 attack 복습 + 심화)

- 유형: Reflected/Stored/DOM. payload: `<script>`, `<img onerror>`, `<svg onload>`.
- ModSec 941 룰군이 탐지 → dvwa 403. juice는 탐지만.
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=<script>alert(1)</script>'"
```

---

## 3. CSRF

- 피해자가 로그인된 상태에서 공격자 페이지의 폼/링크가 **자동으로 인증 요청** 전송.
- 방어 없으면: 비번 변경/이메일 변경/송금 등 상태 변경 요청이 위조됨.
- **CSRF 토큰**(예측 불가 토큰을 요청에 포함)이 없으면 취약.

---

## 4. 방어

- **XSS**: 출력 인코딩(context-aware) + **CSP**(Content-Security-Policy) + HttpOnly 쿠키.
- **CSRF**: CSRF 토큰(동기화 토큰), SameSite 쿠키, 재인증(민감 작업).

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **Reflected XSS**: script 주입 → 403
3. **XSS 변형**: img/svg
4. **CSRF 점검**: 토큰 유무 (상태변경 요청)
5. **탐지**: ModSec 941
6. **CSP 점검**: CSP 헤더 유무
7. **방어**: 인코딩+CSP+CSRF토큰
8. **XSS/CSRF 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. XSS payload 공백 %20. 인가된 실습만.

---

## 6. 다음 주차 (W07) 예고 — 업로드/경로순회/명령주입

W06은 XSS/CSRF였다. W07은 RCE 발판 — 파일 업로드/경로순회/명령주입과 입력검증 방어를 다룬다.
