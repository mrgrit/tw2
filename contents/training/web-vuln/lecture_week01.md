# 웹취약점 W01 — HTTP 기초: 위험 메서드·헤더 악용 vs HTTP 보안 점검

> 웹취약점 트랙 1주차. 인프라: el34 (web vhost). 플랫폼: tw2. 방법론: OWASP WSTG.

---

## 1. 이번 주의 통찰 — HTTP를 알아야 웹을 친다

웹 취약점 점검(WSTG)의 출발은 **HTTP 프로토콜** 이해다. 메서드(GET/POST/PUT/DELETE/TRACE), 헤더,
응답 코드를 알아야 무엇이 위험한지 보인다.

```
 위험 메서드: PUT(파일 업로드), DELETE(삭제), TRACE(XST), OPTIONS(메서드 노출)
 위험 헤더:   Host(호스트 인젝션), X-Forwarded-For(우회), 누락된 보안 헤더
```

---

## 2. HTTP 메서드 — OPTIONS로 열거

```bash
curl -s -i -X OPTIONS -H 'Host: dvwa.el34.lab' http://10.20.30.1/ | grep -i '^Allow'
```
- `Allow:` 헤더가 허용 메서드 노출. **PUT/DELETE**가 열려 있으면 파일 변조/삭제 위험.
- **TRACE**: 활성 시 XST(Cross-Site Tracing)로 쿠키 탈취 가능 → 비활성화 필수.

---

## 3. 보안 헤더 점검

응답 헤더에서 **누락된 보안 헤더**를 찾는다:
| 헤더 | 역할 |
|------|------|
| `Strict-Transport-Security` | HTTPS 강제(HSTS) |
| `Content-Security-Policy` | XSS 완화(CSP) |
| `X-Frame-Options` | 클릭재킹 방지 |
| `X-Content-Type-Options: nosniff` | MIME 스니핑 방지 |
```bash
curl -sI -H 'Host: dvwa.el34.lab' http://10.20.30.1/ | grep -iE 'strict-transport|content-security|x-frame|x-content'
```
누락 = 취약점(낮음~중간), 보고 대상.

---

## 4. 헤더 악용

- **Host 헤더 인젝션**: `Host: evil.com` → 비밀번호 재설정 링크 변조, 캐시 포이즌.
- **X-Forwarded-For**: 위조해 IP 기반 접근 제어/로깅 우회 시도.
- **Referer/Origin**: CSRF 방어 우회 단서.

---

## 5. 탐지 + 방어

- **탐지**: 비정상 메서드(PUT/TRACE) 요청, 다수 OPTIONS는 WAF/access.log에.
- **방어**: 불필요 메서드 비활성(`<LimitExcept>`), TRACE off, 보안 헤더 추가, Host 검증.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상 도달
2. **메서드 열거**: OPTIONS → Allow
3. **위험 메서드**: PUT/DELETE/TRACE 시도
4. **보안 헤더 점검**: 누락 헤더
5. **헤더 악용**: Host/X-Forwarded-For
6. **탐지**: 비정상 메서드 흔적
7. **방어**: 메서드 제한 + 헤더
8. **HTTP 점검 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W02) 예고 — 점검 도구(스캐너)

W01은 HTTP 수동 점검이었다. W02는 자동 점검 도구(nikto/whatweb 등) 스캐너 공격과 그 탐지·핑거프린팅
방어를 다룬다.
