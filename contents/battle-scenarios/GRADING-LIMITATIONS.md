# 공방전 자동채점 — 알려진 한계와 점수 해석 가이드

> 강사/운영자용. tw2 의 AI 자동채점이 el34 인프라 위에서 어떻게 동작하고,
> **왜 일부 미션이 구조적으로 partial 에 머물거나 자동채점 불가인지**를 기록한다.

## 채점 모델 한 줄

학생 제출(`what_i_did`/`what_happened`) → **el34 Assessor 가 타깃 인프라의 라이브 로그·상태를
read-only 결정론 점검**(file/log/port/process/wazuh_alert) + **`claude-sonnet-4-6` 이 보고의
검증 가능한 구체 사실(rule ID·sid·트랜잭션·출처 IP·계정·count)이 실제와 일치하는지 의미 채점**.
앰비언트 상태만으론 통과 불가, 증거로 교차검증, 불가 시 보류(review).
외부 공격자(192.168.0.202)의 출처 IP가 Suricata·ModSec·Wazuh 전 계층에 보존돼 RED 채점·SOC 분석에 활용.

## A. el34 인프라가 **자동채점 불가**인 미션 (인프라 한계 — 회귀 아님)

el34 는 Linux 웹/네트워크 중심 인프라라, 아래 텔레메트리를 보유하지 않는다. 해당 체크 미션은
결정론 점검이 항상 `passed=False` → 자동 fail. **콘텐츠/하니스 버그가 아니라 인프라 범위의 문제.**

| 미션 유형 (verify) | 왜 불가 | 비고 |
|---|---|---|
| `wazuh_alert groups=authentication_failed` | el34 컨테이너 sshd 가 stderr/docker-logs 로만 로깅, Wazuh 에이전트가 SSH auth 미수집 | SSH 무차별 대입 탐지 |
| `wazuh_alert groups=windows` / `sysmon` | el34 에 **Windows/Sysmon 호스트 없음**(전부 Linux) | 윈도우 이벤트/Sysmon 분석 |
| 엔드포인트 타임라인(RDP→실행 등) | 엔드포인트(EDR/Sysmon) 텔레메트리 미보유 | |

→ 해결하려면 el34 측 인프라 보강 필요(rsyslog+sshd→syslog 라우팅, Windows/Sysmon 에이전트 등).
정식 보강 전까지는 **강사 수동 평가** 또는 해당 미션 제외 권장.

## B. 자동 하니스가 **개념 작업을 시뮬레이션 못 하는** 미션 (semantic 상한)

결정론 체크는 통과해도, 미션의 실제 의도가 *사람의 분석/문서 산출물*이라 의미 채점이 낮다.

- **STIX 2.1 위협 표현 · ATT&CK 매핑**, **Sysmon/osquery 설치**, **위협 모델링/CTI 작성** 등.
- 자동 하니스는 "프로세스 실행/파일 존재" 같은 프록시 체크만 만족시키고 실제 산출물은 못 만든다 → partial/fail.

## C. 분석 전용(SIEM) 미션은 partial 이 상한

`wazuh_alert`/`log_contains` 분석 미션은 Assessor 가 "증거가 존재한다"까지만 확인 가능하고
**분석의 질 자체는 기계가 검증 못 한다.** → **검증 가능한 구체 증거를 인용하면 점수가 오른다**:
Suricata 시그니처(`6V6 Bot UA - sqlmap`, `6V6 SQL Injection`)·Wazuh rule `86601`·ModSec 트랜잭션 ID·
발화 룰 ID(942100 등)·출처 IP `192.168.0.202`. 하니스(`scripts/play_scenario.py _observe`)는
분석 미션마다 신선한 공격을 보장 생성한 뒤 실제 로그의 구체값을 인용하도록 개선됨.

## D. 룰/설정 미션 주의

- **탐지 룰 미션**은 미션 주제에 맞는 실제 룰을 심어야 "탐지됨" 입증(generic UNION SELECT 룰을 webshell/C2 에 쓰면 partial).
- **설정 파일 미션**(nftables/ossec.conf): 라이브 설정 파일은 **덮어쓰기 금지**(방화벽/매니저 붕괴 위험) →
  하니스가 주석/단일라인 블록으로 비파괴 추가 → 결정론 체크는 통과하나 의미 채점은 부분점수일 수 있음.
- **AI 채점 ±변동**: 동일 보고서가 수 점 범위로 흔들린다. 단일 점수에 과민반응 금지.

## 점수 해석 / 운영 팁

- `fail` 이 A(인프라 한계)·B(개념)에 해당하면 **회귀가 아니다** — 강사 수동 평가 또는 제외.
- 분석 미션은 위 C 의 검증 가능 증거를 인용하는 레퍼런스 답안 제공 시 점수 상승.
- 채점기(`claude` CLI)가 PATH 에 없으면 모든 채점이 `review`(보류)로 남는다(플랫폼은 정상 동작).
- 배틀별 채점 근거는 UI 의 "채점 근거 ▼" 또는 DB(`battles`/`missions`)에서 직접 확인.

_el34 이식 기준 갱신. 9개 트랙(soc·soc-adv·attack·attack-adv·compliance·web-vuln·cloud-container·secuops·secuops-easy)
전체가 el34 라이브 파이프라인으로 검수됨 — 운영 미션은 pass/partial, 잔여 fail 은 위 A·B 한계로 한정._
