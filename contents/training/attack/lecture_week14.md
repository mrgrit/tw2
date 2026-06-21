# 공격기법 W14 — 레드와 블루가 함께: Caldera+Wazuh로 탐지 커버리지 측정·보강·재검증

> 공격기법 트랙 14주차. 선행: W13(에뮬레이션). 인프라: el34 (Caldera, Wazuh). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — Purple Team 사이클

레드(공격)와 블루(방어)가 따로 노는 게 아니라 **함께** 탐지를 개선한다. Caldera로 ATT&CK을
에뮬레이션(레드)하고, 안 잡힌 갭을 Wazuh 룰로 보강(블루)하고, 다시 에뮬레이션해 **재검증**한다. 이
반복이 **purple team** — 탐지 커버리지를 객관적·지속적으로 끌어올린다.

```
 ① 에뮬레이션(Caldera) → ② 커버리지 측정(잡혔나?) → ③ 갭 보강(Wazuh 룰) → ④ 재에뮬레이션(재검증) → ①…
```

---

## 2. ① 측정 — 무엇이 안 잡히나

W13에서 본 갭(예: discovery 기법)을 구체화. 에뮬레이션 후 Wazuh alerts.json에 해당 기법 경보가
없으면 = 커버리지 갭(❌).
```
 T1136 account → ✅ 잡힘
 T1087 discovery(cat passwd) → ❌ 안 잡힘 = 갭
```

---

## 3. ② 보강 — 갭을 메우는 룰

갭 기법을 탐지하는 Wazuh 룰을 쓴다(W04 패턴). 예: 특정 discovery 행위/마커를 escalate.
```xml
<rule id="101414" level="10">
  <decoded_as>json</decoded_as>
  <field name="technique">T1087</field>
  <description>ATK W14 - account discovery detected (coverage gap closed)</description>
</rule>
```
- wazuh-logtest로 발화 검증(라이브 무중단).

---

## 4. ③ 재검증 — 보강이 효과 있나

룰 보강 후 **같은 기법을 다시 에뮬레이션** → 이제 잡히나? 잡히면 갭이 닫힘(❌→✅). 안 잡히면 룰 수정.
이 재검증이 purple team의 핵심 — "고쳤다고 믿지 말고 다시 공격해 확인".

---

## 5. 커버리지 매트릭스

| Tactic | 기법 | 보강 전 | 보강 후 |
|--------|------|---------|---------|
| Discovery | T1087 | ❌ | ✅ |
| Persistence | T1136 | ✅ | ✅ |
| Execution | T1059 | ✅ | ✅ |

매트릭스로 커버리지를 시각화하고 갭을 우선순위화 → 지속 개선.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: Caldera + Wazuh
2. **갭 재현**: 안 잡히는 기법(discovery) 에뮬레이션
3. **커버리지 측정**: 갭 확인(미탐지)
4. **갭 보강 룰**: Wazuh 룰(id 101414) → logtest
5. **재검증**: 룰 후 같은 기법 → 탐지
6. **커버리지 매트릭스**: 보강 전후
7. **purple 사이클 정리**
8. **커버리지 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 룰은 logtest 검증 + 삭제(공유 SIEM 보존). 인가된 실습만.

---

## 7. 다음 주차 (W15) 예고 — 캡스톤(PTES 완주)

W14는 purple 사이클이었다. W15는 수료 캡스톤 — PTES 7단계로 침투를 완주하고, 방어가 킬체인을
재구성해 막는 종합 시험.
