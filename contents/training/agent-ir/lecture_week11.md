# agent-ir W11 — Purple Round 1: Claude Code가 Bastion을 코치한다(클라이언트→서버 지식 이식)

> **본 주차의 한 줄 요약**
>
> Purple 자동화의 핵심 협업 구조를 배운다: **클라이언트 하네스(Claude Code)가 서버 하네스(Bastion)를 코치**한다.
> 왜 이 구조인가? 클라이언트 하네스(aisec W07)는 **사람과 함께 유연하게 탐색·설계**하는 데 강하고, 서버 하네스
> (aisec W05)는 **자동화·상시 운영·다중 VM**에 강하다. 그래서 최선은 **둘의 협업**: ① 사람+Claude Code가 새
> 공격(예: 신종 다형 SQLi)을 **탐색하며 탐지법을 설계**하고(클라이언트의 유연함), ② 그 탐지 지식을 **Bastion에
> 이식(coach)** 해 — skill·룰·playbook으로 codify하고, ③ Bastion이 그것을 **자동·상시 실행**(서버의 자동화)한다.
> 이것이 **harness engineering의 협업판**: 사람+클라이언트 에이전트가 발견한 것을 서버 에이전트의 **E.G(지식)**
> 로 이식해, 다음부턴 사람 없이 자동 대응하게 만든다. Purple(Red+Blue 합동)의 자동화가 이렇게 굴러간다.
>
> **한 줄 결론**: Claude Code(클라이언트, 탐색·설계) → Bastion(서버, 자동화)로 **탐지 지식을 코치·이식**한다.
> 사람+클라이언트가 발견한 것을 서버의 E.G로 옮겨, 다음부턴 자동 대응. 클라이언트의 유연함+서버의 자동화.

---

## 학습 목표

본 주차 종료 시 학생은 다음 5가지를 **본인 손으로** 할 수 있어야 한다.

1. **Claude Code→Bastion 코치** 구조와 그 이유(유연+자동화)를 설명한다.
2. 클라이언트(사람+Claude Code)로 탐지법을 **탐색·설계**한다(EXPLORED).
3. 탐지 지식을 Bastion에 **이식**(skill/룰로 codify)한다(COACHED).
4. Bastion이 그것을 **자동 실행**함을 확인한다(AUTOMATED).
5. 이것이 harness engineering·E.G의 협업판임을 설명한다.

> **이 주차의 시선** — 사람+클라이언트의 발견을 서버 에이전트의 자동 능력으로 이식하는 협업을 본다.

---

## 0. 용어 해설 (Purple 코치)

| 용어 | 영문 | 뜻 | 비유 |
|------|------|----|------|
| **코치(coach)** | Coach | 지식을 이식·훈련 | 사수→후임 교육 |
| **클라이언트 하네스** | Client Harness | Claude Code(탐색) | 연구원 |
| **서버 하네스** | Server Harness | Bastion(자동화) | 생산 라인 |
| **codify** | Codify | 지식을 룰·코드로 | 매뉴얼화 |
| **E.G 이식** | KG Transfer | 지식을 서버 E.G로 | 지식 이전 |

> **헷갈리기 쉬운 한 쌍** — *탐색(클라이언트)* 은 "사람과 유연히 발견", *자동화(서버)* 는 "발견을 상시 실행"이다.
> 코치는 전자를 후자로 옮기는 다리.

---

## 0.5 신입생 친화 핵심 개념

### 0.5.1 왜 클라이언트가 서버를 코치하나

```mermaid
graph TD
    H["사람 + Claude Code(클라이언트)"] -->|① 탐색·설계| DET["새 탐지법 발견<br/>(신종 공격 대응)"]
    DET -->|② 코치(codify)| EG["Bastion E.G<br/>(skill·룰·playbook)"]
    EG -->|③ 자동화| BAS["Bastion(서버)<br/>상시 자동 실행"]
    BAS -.④ 결과·경험.-> EG
    style H fill:#1f6feb,color:#fff
    style EG fill:#3fb950,color:#fff
    style BAS fill:#bc8cff,color:#fff
```

- **클라이언트(탐색)**: 신종 공격은 정해진 룰이 없다. 사람+Claude Code가 **유연하게 탐색**하며 탐지법을 찾는다.
- **코치(이식)**: 찾은 탐지법을 **Bastion의 E.G**(skill·룰·playbook)로 codify.
- **서버(자동화)**: Bastion이 그 지식을 **상시·다중 VM에 자동** 적용.

### 0.5.2 코치 = harness engineering의 협업판

aisec W04에서 "Manager가 harness engineering으로 구성요소를 조립하고 E.G를 얹는다"고 배웠다. Purple 코치는
그 **E.G를 사람+클라이언트가 채워주는** 것이다: 사람이 발견한 탐지 지식을 Bastion E.G에 이식하면, Bastion
Manager가 그 지식으로 harness를 더 잘 짠다. 사람의 통찰 + 서버의 자동화가 합쳐진다.

### 0.5.3 codify — 발견을 재사용 가능하게

"이 신종 SQLi는 이렇게 잡는다"는 통찰을 **재사용 가능한 형태**로 만든다: 탐지 룰(W09)·bastion skill·대응
playbook(aisec W06). codify하면 (1) Bastion이 자동 적용, (2) 다른 분석가와 공유, (3) 회귀 검증(W09) 가능.
발견이 **일회성**에 그치지 않고 **자산**이 된다.

### 0.5.4 왜 사람이 여전히 필요한가

신종 공격 탐지법 **발견**은 여전히 사람+클라이언트의 유연한 탐색이 강하다(서버 자동화는 아는 것만 잘한다).
사람은 **새로운 것을 발견·설계**하고, 서버는 **아는 것을 자동 실행**한다. Purple 코치는 이 역할 분담을
제도화한다 — 사람의 창의를 서버의 규모로 증폭.

### 0.5.5 el34에서의 실현

el34에서 Bastion은 skill(suricata·apache·wazuh 관찰)과 화이트리스트를 가진다. 코치는 사람+클라이언트가 발견한
탐지 로직을 이 Bastion 표면에 **매핑**하는 것: 예) "신종 다형 SQLi는 apache.error_log에서 이 불변 특성으로
잡는다"를 Bastion 룰로 이식. 이번 주 실습은 이 코치 흐름(탐색→codify→Bastion 자동 실행)을 재현한다.

---

## 1. 실습 안내 (5 미션)

실행 위치 el34 **호스트**(`ssh ccc@{{TARGET_IP}}`), GPU `http://211.170.162.139:10934`, bastion `el34-bastion:9100`.

### STEP 1 — GPU 헬스체크 → GEN_OK
### STEP 2 — 클라이언트 탐색·설계 → EXPLORED
- **왜/무엇을:** 사람+Claude Code(GPU 시연)로 신종 공격 탐지법 설계.
- **해석:** 유연한 탐색으로 발견.

### STEP 3 — Bastion 코치(codify) → COACHED
- **왜?** 지식 이식.
- **무엇을?** 발견한 탐지법을 Bastion 룰/skill로 codify.
- **해석:** 발견을 자산으로.

### STEP 4 — Bastion 자동 실행 → AUTOMATED
- **왜?** 자동화.
- **무엇을?** codify한 지식을 실물 Bastion이 관찰 skill로 자동 적용(실물 확인).
- **해석:** 사람 발견→서버 자동.

### STEP 5 — 종합 → Assessment
- 코치 구조·codify·자동화·E.G를 묶어 정리(Assessment).

---

## 2. 흔한 오해·블루팀 노트

- **"서버 자동화면 사람 불필요"** — 신종 발견은 사람+클라이언트. 서버는 아는 것 자동화.
- **"발견하면 끝"** — codify해야 재사용·자동화·공유. 일회성 발견은 자산이 안 됨.
- **"코치는 일방향"** — Bastion의 자동 실행 경험이 다시 E.G에 쌓여 다음 발견을 돕는다(양방향).
- **관제 관점** — 사람+클라이언트의 발견이 Bastion E.G로 codify되는지, 회귀 검증되는지, 자동 실행 결과가
  다시 축적되는지 점검한다. Purple 코치의 품질이 자동 방어의 성장 속도.

---

## 3. 다음 주차 (W12) 예고 — Purple Round 2: Experience → Playbook 자동 승격

W11이 "사람이 Bastion을 코치"였다면, W12는 한 걸음 더 — Bastion이 **경험(Experience)을 스스로 Playbook으로
자동 승격**한다. 반복된 성공 대응이 표준 절차로 자동 굳어지는, 자기 개선 루프의 자동화를 다룬다.
