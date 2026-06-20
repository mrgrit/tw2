# 공격기법 W07 — 닿으면 안 될 곳에 닿기: SSRF·Path Traversal·악성 업로드 (A10·A05·A03)

> 공격기법 트랙 7주차. 선행: W01–W06. 인프라: el34 (dvwa). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 경계를 넘는 입력

세 공격 모두 "입력으로 **닿으면 안 될 곳에 닿는다**" — 파일시스템(Path Traversal), 내부 네트워크(SSRF),
서버 실행(악성 업로드). 사용자 입력을 신뢰한 대가다.

```
 Path Traversal(A05): ?file=../../etc/passwd → 경로 탈출, 임의 파일 읽기
 SSRF(A10):           ?url=http://내부IP    → 서버가 대신 내부에 요청(메타데이터/내부망)
 악성 업로드(A03):     webshell.php 업로드   → 서버에서 코드 실행
```

---

## 2. Path Traversal — 경로 탈출

`../`로 의도된 디렉토리를 벗어나 임의 파일 읽기.
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=../../etc/passwd'"
```
- ModSec 930xxx(LFI/path traversal)이 `../`, `/etc/passwd` 패턴을 잡는다 → 403.
- 변형: 인코딩(`%2e%2e%2f`), 절대경로, null byte(구식).

---

## 3. SSRF — 서버를 시켜 내부에 요청

서버가 사용자가 준 URL로 요청하면, 공격자는 **서버를 통해 내부 자원**에 닿는다.
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=http://169.254.169.254/'"
```
- 표적: 클라우드 메타데이터(169.254.169.254), 내부 서비스(localhost:관리포트), 내부망 스캔.
- ModSec/CRS가 내부 IP/위험 스킴 패턴을 일부 탐지.

---

## 4. 악성 업로드 — 서버에서 코드 실행

webshell(php/jsp)을 업로드해 실행 → RCE. 또는 위험 콘텐츠 주입.
```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=%3C%3Fphp%20system(%27id%27)%3B%20%3F%3E'"
```
- ModSec 933xxx(PHP injection)이 `<?php`, `system(` 패턴을 잡는다.
- 방어 우회: 확장자 변조(.phtml/.php5), MIME 위조, 이미지+코드(polyglot).

---

## 5. 탐지 + 방어

- **탐지**: ModSec 930(LFI)/931(RFI)/932(RCE)/933(PHP) 룰군 → anomaly → 949110.
- **방어**:
  - Path Traversal: 경로 정규화 + allowlist + 사용자 입력으로 파일 경로 구성 금지.
  - SSRF: URL allowlist, 내부 IP 차단, 메타데이터 엔드포인트 차단.
  - 업로드: 확장자/MIME allowlist, 실행 권한 제거, 업로드 디렉토리 분리.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **Path Traversal**: ../../etc/passwd → 403
3. **SSRF 시도**: 내부 IP/메타데이터
4. **악성 콘텐츠**: PHP 코드 주입 시도
5. **탐지 분석**: ModSec 930/932/933
6. **영향 정리**: 파일읽기/내부망/RCE
7. **방어**: 정규화/allowlist
8. **공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W08) 예고 — 중간고사 CTF

W07까지 개별 취약점을 익혔다. W08은 중간고사 CTF — 정찰부터 익스플로잇 체인까지 엮어 플래그(셸)를
캡처한다.
