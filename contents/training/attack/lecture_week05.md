# 공격기법 W05 — XSS(Reflected·Stored·DOM·WAF 우회) vs XSS 탐지·차단

> 공격기법 트랙 5주차. 선행: W04. 인프라: el34 (dvwa=차단, juice=탐지만). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 남의 브라우저에서 내 코드를

XSS(Cross-Site Scripting, A03)는 공격자의 JavaScript를 **피해자의 브라우저에서 실행**시킨다. 세션
탈취, 키로깅, 피싱, 워터링홀까지. WAF(ModSec 941)가 막고, 공격자는 우회한다.

---

## 2. XSS 3유형

| 유형 | 경로 | 특징 |
|------|------|------|
| **Reflected** | 요청 파라미터 → 즉시 응답에 반사 | 링크 클릭 유도(피싱) |
| **Stored** | 서버 저장(댓글/프로필) → 모든 방문자 | 가장 위험(지속·광범위) |
| **DOM-based** | 클라이언트 JS가 직접 DOM 조작 | 서버 안 거침(탐지 어려움) |

```bash
# Reflected XSS (dvwa 차단)
docker exec el34-attacker sh -c "curl -s -o /dev/null -w 'dvwa=%{http_code}\n' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=<script>alert(1)</script>'"
```

---

## 3. XSS payload 변형

```
 <script>alert(1)</script>            기본
 <img src=x onerror=alert(1)>         이벤트 핸들러
 <svg onload=alert(1)>                SVG
 <body onload=alert(1)>               태그 이벤트
 javascript:alert(1)                  스킴
```
- 태그/이벤트/스킴 다양화로 필터 우회 시도.

---

## 4. WAF 우회 + 한계

- 대소문자 `<ScRiPt>`, 인코딩(HTML entity/URL/유니코드), 분할, 주석.
- ModSec 941 룰군은 `<script`, `onerror=`, `javascript:` 등 수십 패턴 + 정규화로 잡는다.
- 단순 우회는 대부분 무력 — 고급 컨텍스트 우회(특정 sink) 필요.

---

## 5. 탐지·차단 + 방어

- **탐지**: ModSec 941xxx(XSS 룰군) → anomaly 누적 → 949110.
- **차단 vs 탐지**: dvwa(403) vs juice(200, DetectionOnly).
- **방어(근본)**: 출력 인코딩(context-aware) + CSP(Content-Security-Policy) + HttpOnly 쿠키 + 입력 검증.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **Reflected XSS**: dvwa → 403
3. **XSS 변형**: img/svg/event
4. **WAF 우회 시도**: tamper
5. **탐지 분석**: ModSec 941
6. **차단 vs 탐지**: dvwa vs juice
7. **방어**: 출력 인코딩 + CSP
8. **XSS 공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W06) 예고 — 권한 경계 넘기(IDOR·무차별대입·강제 브라우징)

W05는 XSS였다. W06은 접근 제어 우회 — IDOR, 강제 브라우징, 무차별 대입으로 권한 경계를 넘는다(A01·A07).
