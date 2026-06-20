# 공격기법 W02 — 정찰 심화(nmap·nikto·디렉토리 brute) vs IDS/WAF 탐지

> 공격기법 트랙 2주차. 선행: W01. 인프라: el34 (el34-attacker 도구 완비). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 표면 아래를 판다

W01의 기본 정찰을 넘어 **숨은 자산**을 찾는다 — nmap 고급 스캔, nikto 웹 취약점 스캐너, 디렉토리
brute-force(숨은 경로). 더 깊은 정찰 = 더 많은 익스플로잇 기회. 단, 더 시끄럽다(IDS/WAF 탐지↑).

```
 기본 정찰(W01)         심화 정찰(W02)
 포트/서비스           + 웹 취약점(nikto) + 숨은 경로(gobuster) + 스크립트 스캔(nmap NSE)
 (얕고 조용)            (깊고 시끄러움 — 탐지 trade-off)
```

---

## 2. nmap 심화 — NSE 스크립트

```bash
docker exec el34-attacker nmap -sV --script=http-headers,http-title -p 80 10.20.30.1 -T4
```
- `--script`: NSE 스크립트(http-title, http-headers, vuln 카테고리 등)로 자동 정보 수집.
- 깊은 스캔일수록 Suricata 탐지 가능성↑(많은 요청).

---

## 3. nikto — 웹 취약점 스캐너

```bash
docker exec el34-attacker nikto -h http://10.20.30.1 -Tuning 1 2>&1 | head
```
- 알려진 취약 파일/설정/헤더 누락을 자동 점검. UA에 "Nikto"가 박혀 WAF(913 scanner)에 잡힌다.
- 빠르지만 시끄러움 — WAF audit에 scanner 탐지로 명확히 남는다.

---

## 4. 디렉토리 brute-force — 숨은 경로

```bash
docker exec el34-attacker gobuster dir -u http://10.20.30.1 -w <wordlist> -H "Host: dvwa.el34.lab" -q
```
- 워드리스트로 숨은 경로(/admin, /backup, /api …)를 찾는다 — 노출되지 않은 익스플로잇 표면.
- 404가 대부분, 200/403/301이 "있는 것" — 대량 요청이라 access.log/IDS에 폭주로 남는다.

---

## 5. 탐지 trade-off — 깊이 vs 은밀

심화 정찰은 정보를 많이 주지만 시끄럽다:

| 기법 | 정보량 | 탐지 위험 | 완화(고급) |
|------|--------|-----------|-----------|
| nikto | 높음 | 매우 높음(UA 노출) | UA 변조, 느린 스캔 |
| dir brute | 높음 | 높음(요청 폭주) | rate-limit, 작은 wordlist |
| nmap NSE | 중간 | 중간 | 스크립트 선별 |

공격자는 "얼마나 알아낼까"와 "얼마나 들킬까"를 저울질한다.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 심화 도구(nikto/gobuster/ffuf)
2. **nmap NSE**: 스크립트 스캔
3. **nikto**: 웹 취약점 스캔
4. **디렉토리 brute**: 숨은 경로 발견
5. **방어 탐지**: nikto/스캔의 WAF/IDS 흔적
6. **숨은 표면 매핑**: 발견 경로 정리
7. **탐지 trade-off**: 깊이 vs 은밀
8. **심화 정찰 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W03) 예고 — 웹앱 구조·API·JWT 공격

W02는 표면을 깊게 팠다. W03은 웹앱 내부 — API 엔드포인트, JWT 토큰의 약점을 공격하고 API 남용을
탐지하는 법을 본다.
