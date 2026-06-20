# 공격기법 W01 — 침투 환경·정찰 개시 vs 방어 가시성 확인

> 공격기법 트랙 1주차. 인프라: el34 (공격자 el34-attacker → 대상 web/fw, 방어 Suricata/ModSec). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 공격은 정찰에서 시작한다

침투 테스트(penetration test)는 무작정 공격하지 않는다. **교전 규칙(RoE)** 안에서 **정찰
(reconnaissance)** 부터 — 무엇이 있고, 어디가 열렸고, 무슨 기술을 쓰는지 파악한 뒤에 익스플로잇한다.

```
 PTES 방법론
 ① 정찰(Intelligence Gathering) ← 이번 주
 ② 위협 모델링 → ③ 취약점 분석 → ④ 익스플로잇 → ⑤ 포스트 익스플로잇 → ⑥ 보고
```

> ⚠️ 이 트랙은 **인가된 환경(el34 실습)** 에서만. 실제 시스템 무단 공격은 불법. RoE(범위/시간/방법)를 지킨다.

---

## 2. 공방 통합 — 공격하며 방어를 본다

el34는 공격자 출처 IP를 fw→ips→web 전 계층에 보존한다. 그래서 공격하면서 **그 공격이 방어 스택에
어떻게 보이는지** 동시에 학습한다(공격 과목이지만 방어 가시성도).

```
 공격자(el34-attacker 10.20.30.202) ──정찰──→ 대상(fw 10.20.30.1 → web)
                                                  │
                                          Suricata eve / ModSec audit 에 탐지
```

좋은 공격자는 자기 행동이 어떻게 탐지되는지 안다 → 탐지 회피의 출발점.

---

## 3. 정찰 1 — 도달성 + 포트 발견 (nmap)

대상에 도달 가능한지, 어떤 포트/서비스가 열렸는지.
```bash
docker exec el34-attacker nmap -sV -p 80,443,8001-8007,9100 10.20.30.1 -T4 --max-retries 1
```
- `-sV`: 서비스/버전 식별. `-p`: 포트 지정. el34 fw가 DNAT한 공개 포트(80/443/8001-8007)가 보인다.
- 이 스캔은 Suricata에 "scan" 탐지로 남는다(방어 가시성).

---

## 4. 정찰 2 — 웹 자산 핑거프린팅 (curl/whatweb)

열린 웹 포트의 기술 스택/엔드포인트 식별 → 익스플로잇 표면 매핑.
```bash
docker exec el34-attacker sh -c "curl -sI -H 'Host: dvwa.el34.lab' http://10.20.30.1/"
```
- `Server:` 헤더(Apache 버전), 응답 코드, 리다이렉트 → 기술 스택 단서.
- el34 web vhost(dvwa/juice/neobank…)별로 다른 앱 → 각각 다른 익스플로잇 표면.

---

## 5. 방어 가시성 — 내 정찰이 보이나

공격자 관점에서 "내가 얼마나 시끄러운가"를 안다.
```bash
docker exec el34-ips sh -c 'tail -2000 /var/log/suricata/eve.json | jq -rc "select(.event_type==\"alert\" and .src_ip==\"10.20.30.202\")|.alert.signature" | sort | uniq -c'
```
- 스캔이 Suricata에 잡히면 "탐지됨" — 느린 스캔(`-T2`)·분산으로 회피 가능(고급).

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 공격자 도구(nmap/curl) + 대상 도달성
2. **포트 스캔**: 열린 포트/서비스 발견
3. **서비스 버전 식별**: nmap -sV
4. **웹 핑거프린팅**: curl -I 기술 스택
5. **방어 가시성**: Suricata 스캔 탐지(공격자 관점)
6. **공격 표면 매핑**: 발견 자산/포트 정리
7. **정찰 방법론**: PTES + RoE
8. **정찰 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습 환경만.

---

## 7. 다음 주차 (W02) 예고 — 정찰 심화

W01은 정찰 개시였다. W02는 정찰 심화 — nmap 고급 옵션, nikto 웹 스캔, 디렉토리 brute(gobuster/ffuf)로
숨은 자산을 찾고, 그게 IDS/WAF에 어떻게 탐지되는지 본다.
