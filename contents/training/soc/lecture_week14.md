# SOC W14 — 야간 근무는 잠들지 않는다: AI 자율 관제와 Active Response로 자동 대응

> SOC 관제 트랙 14주차. 선행: W04(룰)·W13(인텔). 인프라: el34 (Wazuh active-response). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 사람은 자지만 SOC는 안 잔다

위협은 야간·주말에 더 많다(사람이 적을 때). 분석가가 24/7 다 볼 순 없다. 답은 **자동화** —
규칙 기반 **Active Response**(자동 대응) + **AI 자율 관제**(자동 트리아지)로 사람 없이도 1차 대응한다.

```
 경보 → [AI/룰 자동 트리아지] → 고위험? → [Active Response 자동 대응] → 사람에게 보고
        (W04 룰 + W13 인텔)        level≥N      (firewall-drop 등)        (요약만)
```

사람은 **자동화가 거른 것**과 **모르는 위협**에만 개입 → 처리량 + 적시성.

---

## 2. Active Response — 자동 대응

Wazuh가 고위험 경보에 사람을 기다리지 않고 자동 조치(`ossec.conf`):
```xml
<command>
  <name>firewall-drop</name>
  <executable>firewall-drop</executable>
  <timeout_allowed>yes</timeout_allowed>
</command>
<active-response>
  <command>firewall-drop</command>
  <location>local</location>
  <level>12</level>        <!-- level≥12 경보에 -->
  <timeout>600</timeout>   <!-- 600초 후 자동 해제 -->
</active-response>
```
- 실행 기록: `/var/ossec/logs/active-responses.log`.
- el34 기본은 **주석 템플릿**(미활성). 활성 시 level≥12 → 자동 firewall-drop.

---

## 3. 안전장치 — 자동화의 양날

자동 대응은 잘못되면 **자가 DoS**(오탐 한 번에 정상 IP 영구 차단). 반드시:
- **timeout**: 자동 해제(영구 차단 방지).
- **화이트리스트**: 내부/중요 IP는 절대 차단 안 함.
- **level 임계**: 충분히 높은 확신(level≥12)에만 자동 대응. 낮으면 사람 확인.

> ⚠️ 공유 el34에선 실제 firewall-drop 활성/트리거 금지(다른 학생 차단). 설정 점검·설계까지.

---

## 4. AI 자율 관제 — 자동 트리아지

AI/규칙이 1차 트리아지를 대신한다:
- **자동 분류**: 룰(W04) + 인텔(W13) + 빈도(W05)로 우선순위 자동 결정.
- **자동 상관**: 같은 출발지 경보를 캠페인으로 묶음(W06).
- **자동 보고**: 사람에겐 요약만(고위험 N건, 자동 차단 M건).
- tw2 플랫폼의 관제(gwanje)가 이 자동 트리아지의 예 — deterministic 규칙 + 선택적 AI.

사람의 역할: 자동화 검증 + 모르는 위협 심층 분석(L3).

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: Wazuh + active-response 설정
2. **야간 위협 재현**: 고위험 공격
3. **Active Response 점검**: ossec.conf 템플릿(firewall-drop/timeout)
4. **자동 대응 룰 설계**: level≥12 → 자동 대응 (logtest)
5. **안전장치**: timeout/화이트리스트(자가 DoS 방지)
6. **AI 자율 트리아지**: 룰+인텔+빈도 자동 분류
7. **무인 대응 효과**: 24/7 적시성
8. **자동 대응 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. Active Response는 점검·설계만(실제 차단 금지).

---

## 6. 다음 주차 (W15) 예고 — 기말: APT 캠페인 종합

W14까지 SOC 전 역량을 익혔다. W15는 수료 시험 — 한 APT 캠페인을 SOC 전 역량(분석·트리아지·헌팅·IR·
인텔·자동화)으로 끝까지 분석·대응한다.
