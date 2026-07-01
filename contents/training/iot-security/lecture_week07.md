# iot-security W07 — BLE 해킹: 약한 페어링·스니핑·MITM

> **본 주차의 한 줄 요약**
>
> **BLE(Bluetooth Low Energy)** 는 웨어러블·비콘·스마트 잠금·의료 기기 등에 널리 쓰인다. BLE 보안의 핵심은
> **페어링(pairing)** — 두 장치가 암호 키를 교환하는 과정이다. 문제는 많은 IoT가 **약한 페어링 방식**을 쓴다는
> 것: ① **Just Works** — 사용자 확인 없이 페어링(MITM 방어 없음), 편의 위해 널리 쓰이지만 **중간자 공격에 무방비**,
> ② **Legacy Pairing**(BLE 4.0/4.1) — 암호화 키 교환이 약해 스니퍼로 **키 추출** 가능, ③ **정적 패스키/약한
> 인증**. 공격자는 BLE 스니퍼로 페어링을 캡처해 **키를 추출**하거나, **MITM**으로 두 장치 사이에 끼어 통신을
> 감청·변조한다(스마트 잠금 열기, 의료 기기 데이터 조작). 방어: **LE Secure Connections**(BLE 4.2+, ECDH 키
> 교환으로 스니핑 방어)와 **MITM 보호가 있는 페어링**(Numeric Comparison·Passkey Entry), **애플리케이션 계층
> 암호화**(BLE 위에 추가 암호), **연결 최소화**(필요할 때만 광고·연결). BLE는 편리하지만 약한 페어링은 스마트
> 잠금 같은 중요 장치를 노출시킨다. BLE는 실물 라디오 하드웨어가 필요해 시뮬레이션한다.
>
> **한 줄 결론**: BLE의 약한 페어링(Just Works·Legacy)은 스니핑·MITM으로 키 추출·통신 장악을 부른다. 방어 =
> **LE Secure Connections + MITM 보호 페어링 + 앱 계층 암호화**.

---

## 학습 목표

본 주차 종료 시 학생은 다음 5가지를 **본인 손으로** 할 수 있어야 한다.

1. BLE **페어링 방식**과 보안 차이를 설명한다.
2. **약한 페어링**(Just Works·Legacy)을 평가한다(PAIRING_WEAK).
3. **스니핑·MITM** 가능성을 판정한다(BLE_INTERCEPTABLE).
4. **LE Secure Connections·앱 암호화**로 강화한다(BLE_SECURED).
5. Just Works가 왜 MITM에 취약한지 설명한다.

> **이 주차의 시선** — 편의를 위한 약한 BLE 페어링을 평가하고, 강한 페어링으로 막는다.

---

## 0. 용어 해설 (BLE)

| 용어 | 영문 | 뜻 | 비유 |
|------|------|----|------|
| **BLE** | Bluetooth Low Energy | 저전력 블루투스 | 근거리 무선 |
| **페어링** | Pairing | 키 교환 | 상호 등록 |
| **Just Works** | — | 확인 없는 페어링 | 무검증 악수 |
| **LE Secure** | LE Secure Connections | ECDH 페어링 | 강한 악수 |
| **MITM** | Man-in-the-Middle | 중간자 | 가로채기 |

> **헷갈리기 쉬운 한 쌍** — *Just Works* 는 "사용자 확인 없음(MITM 취약)", *Numeric Comparison* 은 "양쪽 숫자
> 확인(MITM 방어)"이다. 확인 유무가 MITM 방어를 결정.

---

## 0.5 신입생 친화 핵심 개념

### 0.5.1 페어링이 BLE 보안의 핵심

```mermaid
graph TD
    A["폰"] -->|페어링(키 교환)| B["스마트 잠금"]
    ATK["MITM 공격자"] -.Just Works면 끼어듦.-> A
    ATK -.-> B
    style ATK fill:#f85149,color:#fff
```

두 장치가 안전하게 키를 교환해야 이후 통신이 암호화된다. **페어링이 약하면** 그 키가 노출되거나 MITM이 끼어들어
전체가 무력화된다.

### 0.5.2 Just Works — MITM에 무방비

**Just Works**는 사용자 확인 없이 자동 페어링한다(편리함). 하지만 **양쪽이 서로를 인증하지 않아**, 공격자가
두 장치 사이에 끼어(MITM) 각각과 페어링하면 통신을 **감청·변조**한다. 스마트 잠금이 Just Works면 열릴 수 있다.

### 0.5.3 스니핑·키 추출

- **Legacy Pairing(BLE 4.0/4.1)**: 키 교환(TK 기반)이 약해 스니퍼로 **키를 크래킹**. crackle 같은 도구.
- **MITM**: Just Works·약한 페어링에서 중간자로 세션 장악.
- **재전송·재연결**: 캡처한 명령 재전송, 강제 재페어링 유도.

### 0.5.4 방어 — LE Secure Connections

- **LE Secure Connections(BLE 4.2+)**: **ECDH** 키 교환으로 스니퍼가 키를 못 얻음(수동 스니핑 방어).
- **MITM 보호 페어링**: Numeric Comparison(양쪽 숫자 비교)·Passkey Entry로 중간자 차단.
- **앱 계층 암호화**: BLE 위에 추가 암호(BLE가 뚫려도 방어).
- **연결 최소화**: 필요할 때만 광고·페어링, 본딩 관리.
중요 장치(잠금·의료)는 반드시 강한 페어링을 쓴다.

### 0.5.5 el34 맥락

BLE는 실물 라디오(스니퍼·동글)가 필요하다. 본 실습은 **페어링 방식 평가·스니핑/MITM 가능성·방어 설계**를
결정론 시뮬로 익힌다. 물리 BLE 공격은 실물 하드웨어가 필요함을 명시한다.

---

## 1. 실습 안내 (5 미션)

실행 위치 el34 **호스트**(`ssh ccc@{{TARGET_IP}}`), GPU `http://211.170.162.139:10934`.
⚠️ 물리 BLE는 라디오 하드웨어 필요 → 본 실습은 페어링·스니핑·방어 로직 결정론 시뮬.

### STEP 1 — GPU 헬스체크 → GEN_OK
### STEP 2 — 페어링 취약성 → PAIRING_WEAK
### STEP 3 — 스니핑/MITM → BLE_INTERCEPTABLE
### STEP 4 — BLE 강화 → BLE_SECURED
### STEP 5 — 종합 → Assessment

---

## 2. 흔한 오해·관제자 노트

- **"BLE는 근거리라 안전"** — 스니퍼는 수십 미터. 약한 페어링은 뚫린다.
- **"Just Works가 편함"** — MITM 무방비. 중요 장치는 MITM 보호 페어링.
- **"BLE 암호면 충분"** — Legacy는 스니핑에 약함. LE Secure Connections.
- **관제 관점** — 중요 BLE 장치(잠금·의료)가 LE Secure Connections·MITM 보호를 쓰는지, 앱 계층 암호가 있는지
  점검한다. BLE 보안은 페어링 방식이 핵심.

---

## 3. 다음 주차 (W08) 예고 — 중간 평가: IoT 디바이스 침투 테스트

W01~W07로 IoT의 각 표면(프로토콜·하드웨어·펌웨어·웹·무선·BLE)을 배웠다. W08은 이를 종합한 **IoT 디바이스 침투
테스트** — 한 장치를 4대 표면에서 평가하고 방어를 제안하는 중간 평가다.
