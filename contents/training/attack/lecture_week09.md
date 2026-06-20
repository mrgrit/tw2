# 공격기법 W09 — 패킷을 직접 만들다: scapy 크래프팅·비정상 스캔 vs 패킷 분석·네트워크 탐지룰

> 공격기법 트랙 9주차. 선행: W01–W08. 인프라: el34 (scapy 2.7, Suricata). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 도구 대신 패킷을 만든다

nmap 같은 완성 도구를 넘어 **패킷을 직접 만든다(scapy)**. 플래그·필드를 임의로 조작해 비정상 스캔
(FIN/XMAS/NULL), 방화벽 우회, 프로토콜 fuzzing을 한다. 방어자는 이 비정상 패킷을 탐지룰로 잡는다.

```
 scapy: IP()/TCP(flags='S') 직접 조립 → 전송 → 응답 분석
   비정상 플래그(FIN/XMAS/NULL) → 일부 방화벽/스택 우회 시도
   대량 SYN → Suricata 스캔 탐지
```

---

## 2. scapy 기본 — 패킷 조립·전송

```bash
docker exec el34-attacker python3 -c "from scapy.all import *; \
  ans,unans=sr(IP(dst='10.20.30.1')/TCP(dport=[22,80,443],flags='S'),timeout=3,verbose=0); \
  print('open:', [p[1].sport for p in ans if p[1][TCP].flags==0x12])"
```
- `sr()`: 전송+응답 수신. SYN-ACK(flags 0x12)=open, RST(0x14)=closed.
- 포트/플래그/페이로드를 임의 조작 = 도구가 안 주는 유연성.

---

## 3. 비정상 스캔 — FIN/XMAS/NULL

표준 SYN 스캔 대신 비정상 플래그로 일부 필터/스택 우회 시도:
| 스캔 | 플래그 | 원리 |
|------|--------|------|
| FIN | `F` | 닫힌 포트만 RST(열린 건 무응답) |
| XMAS | `FPU` | FIN+PSH+URG |
| NULL | (없음) | 플래그 0 |
```bash
docker exec el34-attacker python3 -c "from scapy.all import *; sr(IP(dst='10.20.30.1')/TCP(dport=80,flags='F'),timeout=2,verbose=0); print('FIN sent')"
```

---

## 4. 탐지 — 대량/비정상 패킷

- 대량 SYN(많은 포트) → Suricata 스캔 임계 초과 → "scan" 탐지.
- 비정상 플래그 조합(NULL/XMAS) → Suricata anomaly/룰 탐지.
- 소규모는 임계 미달(은밀) — 공격자는 느린/소량으로 회피, 방어자는 임계 튜닝.

---

## 5. 네트워크 탐지룰 + 패킷 분석 (방어)

- Suricata `local.rules`로 비정상 플래그 탐지(예: NULL 스캔: flags:0).
- eve.json의 flow/alert로 스캔 출발지·패턴 분석. tcpdump/scapy sniff로 raw 패킷 검사.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: scapy
2. **SYN 크래프팅**: 포트 스캔 → open 식별
3. **비정상 스캔**: FIN/XMAS/NULL
4. **대규모 스캔 → 탐지**: Suricata scan 탐지
5. **패킷 분석**: 응답 플래그 해석
6. **네트워크 탐지룰**: 비정상 플래그 룰(sid 9409001)
7. **은밀 vs 탐지**: 소량/느린 스캔
8. **scapy 공격 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 룰은 self-clean. 인가된 실습만.

---

## 7. 다음 주차 (W10) 예고 — 필터 우회(인코딩·분할·난독화)

W09는 네트워크 계층 크래프팅이었다. W10은 애플리케이션 계층 우회 — 인코딩·분할·난독화로 WAF 필터를
빠져나가는 기법과 정규화 방어를 다룬다.
