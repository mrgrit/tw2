# 웹취약점 W07 — 파일 업로드/경로순회/명령주입: RCE 발판 vs 입력검증 방어

> 웹취약점 트랙 7주차. 선행: W01–W06. 인프라: el34 (dvwa). 플랫폼: tw2. WSTG-INPV.

---

## 1. 이번 주의 통찰 — RCE로 가는 길

이 세 취약점은 **코드 실행(RCE)** 또는 임의 파일 접근으로 이어진다 — 가장 심각한 등급. 입력을
신뢰한 결과다.

```
 파일 업로드: webshell.php 업로드 → 실행 → RCE
 경로순회:    ../../etc/passwd → 임의 파일 읽기
 명령주입:    ; id / | whoami → OS 명령 실행 → RCE
```

---

## 2. 경로순회 (Path Traversal)

```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=../../etc/passwd'"
```
- ModSec 930(LFI) 탐지 → 403. 인코딩(%2e%2e)도 정규화로 차단.

---

## 3. 명령주입 (Command Injection)

```bash
docker exec el34-attacker sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Host: dvwa.el34.lab' 'http://10.20.30.1/?q=;id'"
```
- `; & | $()`로 OS 명령 연결. ModSec 932(RCE) 탐지. 성공 시 완전 장악.

---

## 4. 파일 업로드

- webshell(php/jsp) 업로드 → 웹에서 접근 시 코드 실행. 우회: 확장자(.phtml/.php5), MIME 위조, polyglot.
- ModSec 933(PHP) 탐지.

---

## 5. 방어 — 입력검증

- 경로순회: 경로 정규화 + allowlist, 사용자 입력으로 경로 구성 금지.
- 명령주입: OS 명령 호출 회피(API 사용), 불가피하면 엄격 allowlist + 인자 이스케이프.
- 업로드: 확장자/MIME allowlist, 실행 권한 제거, 디렉토리 분리.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **경로순회**: ../../etc/passwd → 403
3. **명령주입**: ;id → 탐지
4. **PHP 주입**: <?php → 403
5. **탐지**: ModSec 930/932/933
6. **영향**: 파일읽기/RCE
7. **방어**: 입력검증/allowlist
8. **점검 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W08) 예고 — 중간고사

W07까지 개별 취약점을 익혔다. W08은 중간고사 — JuiceShop 종합 점검(W01~W07) + 통합 보고.
