# 공격기법 W06 — 잠기지 않은 문: 무차별대입·IDOR·강제 브라우징으로 권한 경계 넘기 (A01·A07)

> 공격기법 트랙 6주차. 선행: W01–W05. 인프라: el34 (juiceshop). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 인증보다 인가가 약하다

많은 앱이 **인증(authentication, 누구냐)** 은 신경 쓰지만 **인가(authorization, 무엇을 할 수 있냐)** 는
허술하다. OWASP **A01(Broken Access Control)** 이 1위인 이유. 잠기지 않은 문(권한 검사 누락)을 찾는다.

```
 인증 우회(A07): 로그인 뚫기 (W03 SQLi)
 인가 우회(A01): 로그인 후/없이 남의 권한/자원 접근
   ├─ IDOR: ID만 바꿔 남의 데이터
   ├─ 강제 브라우징: 링크 없는 경로 직접 접근
   └─ 권한 상승: 일반→관리자
```

---

## 2. 강제 브라우징(Forced Browsing) — 링크 없는 문

UI에 링크가 없어도 경로를 직접 요청하면 열린다(접근 제어 누락).
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/ftp"
```
- juiceshop `/ftp` = 디렉토리 리스팅(민감 파일 노출). UI엔 없지만 직접 접근 가능.
- W02의 dir brute가 이런 숨은 경로를 찾는다.

---

## 3. Broken Access Control (A01) — 무인증 관리 기능

관리자 전용이어야 할 엔드포인트가 인증 없이 열린다.
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: juice.el34.lab' http://10.20.30.1/rest/admin/application-configuration"
```
- 200이면 **무인증 노출**(A01). 401/403이면 접근 제어 정상.
- 대조: `/api/Users`(401, 보호됨) vs `/rest/admin/...`(200, 노출) — 같은 앱 안에서도 일관성 없음.

---

## 4. IDOR (Insecure Direct Object Reference)

자원을 ID로 직접 참조하는데 소유권 검사가 없으면, ID만 바꿔 남의 자원에 접근.
```
 /api/BasketItems/1  (내 것)  →  /api/BasketItems/2  (남의 것, 검사 없으면 노출)
```
- 순차 ID(1,2,3…)일수록 쉽다. UUID여도 노출되면 위험.

---

## 5. 탐지 + 방어

- **탐지**: 강제 브라우징/IDOR은 대량 404/403/순차 ID 요청 → access.log 패턴, IDS.
- **방어(A01)**: 모든 자원 접근에 **서버측 인가 검사**(소유권/역할). 기본 deny. UI 숨김은 방어 아님.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: juiceshop 도달
2. **강제 브라우징**: /ftp 디렉토리/파일
3. **Broken Access(A01)**: 무인증 관리 엔드포인트
4. **접근 제어 비교**: 보호됨(401) vs 노출(200)
5. **IDOR 개념/시도**: 순차 자원 접근
6. **탐지**: access.log 강제 브라우징 패턴
7. **방어**: 서버측 인가 검사
8. **접근 제어 공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W07) 예고 — SSRF·Path Traversal·악성 업로드

W06은 접근 제어였다. W07은 닿으면 안 될 곳에 닿기 — SSRF(서버가 대신 요청), Path Traversal(경로 탈출),
악성 파일 업로드(A10·A05·A03).
