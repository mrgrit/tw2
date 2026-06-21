# 웹취약점 W02 — 점검 도구: 스캐너 공격 vs 스캐너 탐지·핑거프린팅 방어

> 웹취약점 트랙 2주차. 선행: W01. 인프라: el34 (nikto/whatweb/ffuf). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 자동 점검 도구

수동 HTTP 점검(W01)을 넘어 **자동 스캐너**로 빠르게 표면을 훑는다 — nikto(취약점), whatweb(핑거프린팅),
ffuf(디렉토리). 방어자는 스캐너의 시끄러운 패턴을 탐지하고, 핑거프린팅으로부터 정보를 숨긴다.

```
 점검 도구: nikto(웹 취약점) / whatweb(기술 스택) / ffuf(숨은 경로)
 방어:      스캐너 UA/요청 폭주 탐지(WAF 913) + 서버 정보 숨김(핑거프린팅 축소)
```

---

## 2. 스캐너 도구

```bash
docker exec el34-attacker sh -c 'nikto -h http://10.20.30.1 -maxtime 25s 2>&1 | head'   # 취약점
docker exec el34-attacker sh -c "whatweb -H 'Host: dvwa.el34.lab' http://10.20.30.1 2>&1 | head"  # 핑거프린팅
docker exec el34-attacker ffuf -u http://10.20.30.1/FUZZ -w <wl> -H 'Host: dvwa.el34.lab' -mc 200,403  # 경로
```
- 빠르지만 매우 시끄럽다 — UA 노출(Nikto/WhatWeb) + 요청 폭주.

---

## 3. 스캐너 탐지 (방어)

- **UA 기반**: ModSec 913(scanner UA: nikto/sqlmap/nmap 등) → 즉시 탐지.
- **빈도 기반**: 짧은 시간 다량 요청 → IDS/WAF rate 탐지.
- 스캐너는 탐지 회피용 UA 변조/느린 스캔으로 우회 시도.

---

## 4. 핑거프린팅 방어

- 서버 정보 숨김: `ServerTokens Prod`, `ServerSignature Off`(버전 숨김).
- 기술 스택 헤더 제거(X-Powered-By 등).
- 오류 페이지 일반화(기술 노출 차단).

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: 스캐너 도구
2. **nikto 스캔**: 웹 취약점
3. **whatweb 핑거프린팅**: 기술 스택
4. **ffuf 디렉토리**: 숨은 경로
5. **스캐너 탐지**: WAF 913
6. **핑거프린팅 정보**: 노출되는 정보
7. **방어**: 정보 숨김 + 스캐너 탐지
8. **스캐너 점검 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 6. 다음 주차 (W03) 예고 — 정보수집(Recon)

W02는 스캐너였다. W03은 체계적 정보수집(WSTG-INFO) — 메타데이터/주석/백업파일 등 정보 노출과 그 축소를 다룬다.
