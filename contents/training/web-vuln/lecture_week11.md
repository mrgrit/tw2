# 웹취약점 W11 — 에러/정보 노출: 배너·스택·DB에러 점검 vs 정보 최소화

> 웹취약점 트랙 11주차. 선행: W01–W10. 인프라: el34 (juice/dvwa). 플랫폼: tw2. WSTG-ERRH/INFO.

---

## 1. 이번 주의 통찰 — 공격자에게 지도를 주지 마라

A05 Security Misconfiguration. 버전 배너·상세 에러·스택트레이스·DB 에러는 직접 침해는 아니지만,
**공격자의 정찰을 가속**한다 — 어떤 버전(알려진 CVE)인지, 어떤 DB인지, 내부 경로가 무엇인지.

```
 정보 노출 경로
 ① 배너:    Server: Apache/2.4.52 → 버전→CVE 매핑
 ② 에러:    Unexpected path: /api/... → 내부 경로/구조 노출
 ③ DB 에러: SQLITE_ERROR ... syntax error → DB 엔진 + SQLi 표면 확인
 ④ 헤더:    X-Powered-By / X-Recruiting → 기술 스택/숨은 경로
```

---

## 2. 배너/헤더 점검

```bash
curl -sk -D - -o /dev/null -H 'Host: juice.el34.lab' http://10.20.30.1/ | grep -iE 'server:|x-powered|x-recruiting'
```
- el34: `Server: Apache/2.4.52 (Ubuntu)`(버전 노출), `X-Recruiting: /#/jobs`(숨은 경로 힌트).

---

## 3. 상세 에러 페이지

```bash
curl -sk -H 'Host: juice.el34.lab' http://10.20.30.1/api/Nonexistent123 | head
```
- `Error: Unexpected path: /api/Nonexistent123` → 라우팅 구조/내부 경로 노출.

---

## 4. DB 에러 노출 (가장 위험)

```bash
curl -sk -H 'Host: juice.el34.lab' "http://10.20.30.1/rest/products/search?q=test'"
```
- `SQLITE_ERROR: near "'%'": syntax error` → **DB 엔진(SQLite) 확정 + SQLi 표면 입증**. 공격자에게
  주입 지점과 문법을 알려준다.

---

## 5. 방어 — 정보 최소화

- 배너 억제: Apache `ServerTokens Prod` / `ServerSignature Off`, `X-Powered-By` 제거.
- 커스텀 에러 페이지: 상세 메시지/스택 숨기고 일반 메시지 + 서버측 로깅.
- DB 에러: 사용자에게 노출 금지(generic 메시지), 상세는 로그로만.
- 불필요 헤더 제거(X-Recruiting 등).

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **배너 노출**: Server 버전
3. **상세 에러**: Unexpected path
4. **DB 에러**: SQLITE_ERROR
5. **헤더 누출**: X-Recruiting
6. **영향**: 정찰 가속
7. **방어**: 배너억제/커스텀에러
8. **정보 노출 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.
> 신규 도구 설치 없음 — curl 기본 탑재.

---

## 7. 다음 주차 (W12) 예고 — API 보안

W11은 정보 노출이었다. W12는 API 취약점(BOLA/과다 데이터 노출/mass assignment)을 다룬다.
