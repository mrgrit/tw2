# 웹취약점 W12 — API 보안: BOLA/과다 데이터 노출/mass assignment vs API 인가

> 웹취약점 트랙 12주차. 선행: W01–W11. 인프라: el34 (juice REST). 플랫폼: tw2. OWASP API Top 10.

---

## 1. 이번 주의 통찰 — API는 UI 없는 공격 표면

현대 앱은 REST/GraphQL API 위에 선다. UI 검증을 우회해 API에 직접 요청하면 통제 누락이 드러난다.
OWASP **API Security Top 10**의 핵심:

```
 API1 BOLA(객체수준 인가):   /api/Users/{id} — 남의 id 접근
 API3 과다 데이터 노출:       응답에 불필요 필드(이메일/내부ID) 포함
 API6 Mass Assignment:        요청 본문에 isAdmin:true 등 추가 필드 주입
 API2 인증 취약:              토큰 검증 부실
```

---

## 2. API 정찰 — 공개 vs 보호

```bash
curl -sk -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/api/Products   # 공개(200)
curl -sk -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/api/Users      # 보호(401)
```
- 공개 자원과 보호 자원의 경계를 매핑한다.

---

## 3. BOLA (API1) — 객체수준 인가

```bash
for id in 1 2 3; do curl -sk -o /dev/null -w "$id=%{http_code} " -H 'Host: juice.el34.lab' http://10.20.30.1/api/Users/$id; done
```
- 순차 id로 남의 객체 접근. el34 juice는 `/api/Users` 401 보호(양호). 보호 안 되면 API1 치명.

---

## 4. 과다 데이터 노출 (API3)

```bash
curl -sk -H 'Host: juice.el34.lab' http://10.20.30.1/api/Feedbacks
```
- el34: `/api/Feedbacks` 무인증 200 + **UserId·이메일 조각** 포함 → 응답이 필요 이상 노출(API3).
  클라이언트가 안 쓰는 필드까지 내려주면 노출이다.

---

## 5. Mass Assignment (API6)

- 생성/수정 요청 본문에 `{"role":"admin","isAdmin":true}` 같은 미허용 필드를 추가 → 서버가 무비판
  바인딩하면 권한 상승. 방어 = 입력 allowlist(DTO), 민감 필드 바인딩 차단.

---

## 6. 방어 — API 인가

- **객체수준 인가**: 모든 객체 접근에 소유권 검사(BOLA).
- **응답 최소화**: 필요한 필드만(과다 노출 차단), 직렬화 allowlist.
- **입력 바인딩 allowlist**: mass assignment 차단.
- 인증 토큰 검증 강화, 속도 제한, API 게이트웨이 로깅.

---

## 7. 실습(lab) 형식 — 8 미션

1. **점검**: API 도달
2. **공개 자원**: /api/Products 200
3. **보호 자원**: /api/Users 401
4. **과다 노출(API3)**: /api/Feedbacks → UserId
5. **BOLA(API1)**: 순차 id
6. **영향**: 데이터 노출/권한상승
7. **방어**: 객체인가/응답최소화/allowlist
8. **API 보안 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.
> 신규 도구 설치 없음 — curl 기본 탑재.

---

## 8. 다음 주차 (W13) 예고 — 자동화 스캐닝(nuclei)

W12는 API 보안이었다. W13은 자동화 취약점 스캐닝(nuclei) — 템플릿 기반 대량 점검과 그 한계를 다룬다.
