# 시나리오 퀄리티 일관성 감사 (Task 1)

> 생성: 2026-06-14 · 도구: `scripts/quality_audit.py` (정적 구조 측정) + 수기 검토
> 대상: `contents/battle-scenarios/*.yaml` 145개

## 요약 — 퀄리티는 "동일"하지 않다. 3개 품질 티어로 갈린다.

| 티어 | 트랙(개수) | 구조 | 마커/채점 | 평가 |
|------|-----------|------|-----------|------|
| **A. 신규 고급** | soc-adv·attack-adv·compliance·web-vuln·cloud-container (75) | 골드 구조 통일(2 RED + 3 or 5 BLUE), assess_target/target_vm/verify+semantic 완비 | 주차별 고유 마커(태그/Suricata sid/Wazuh id/계정/포트) 완비, 안티패턴 0 | ✅ 가장 일관 |
| **B. 구 표준** | soc·attack·secuops·secuops-easy (51) | 표준 구조이나 BLUE 미션 수 가변(3~5) | **폐기된 채점 안티패턴 14개 잔존**, 고유태그 문서화율 27~33% | ⚠️ 채점 결함 위험 |
| **C. 레거시 데모** | apt-phase1~3·championship·*-vs-*·precinct6-*·incident-response 등 (19) | 자유형식, 미션 수 0~8, 점수 30~230 | 표준 instruction 섹션·semantic 거의 없음 | ❌ 품질 바 상이 |

## 티어별 측정값 (트랙 단위)

```
track             n  difficulty            red blue  pts(min-max)  고유태그%  안티패턴
attack-adv       15  hard:15                2    3     100-100      87%       0
soc-adv          15  hard:15                2    5     117-118      60%       0
compliance       15  medium:14,hard:1       2    3      95-95      100%       0
web-vuln         15  medium:13,hard:2       2    3      95-98      100%       0
cloud-container  15  medium:11,hard:4       2    3      95-98      100%       0
─────────────────────────────────────────────────────────────────────────────
soc              15  medium:12,hard:3       2  3~5      85-120      27%       5
attack           15  medium:3,hard:12       2  2~3      65-100      27%       6
secuops          15  medium:5,hard:10       2  4~5     102-125      33%       5
secuops-easy      6  easy:6                 2  4~5      95-125       0%       6
─────────────────────────────────────────────────────────────────────────────
legacy-misc      19  easy/medium/hard 혼재  가변  가변   30-230       0%       0
```

## 발견된 결함 (우선순위)

### 🔴 P1 — 폐기된 채점 surface (라이브 채점 실패 예상) — 14개
`verify`가 `log_contains suricata pattern:"scan"` 을 쓰는 RED 미션. 6v6에 nmap SYN 스캔
앰비언트 노이즈(rule 86601)가 상존 → assessor는 True를 주지만 **claude 채점은 학생 행위로
귀속 거부**(정확함) → RED 미션이 구조적으로 fail/저점.
(근거: 메모리 e2e-grading-harness 채점교훈 #4)

- attack-w01, attack-w02, attack-w03, attack-w09
- secuops-w01, secuops-w02, secuops-w04, secuops-w05
- secuops-easy-w01, secuops-easy-w02, secuops-easy-w03
- soc-w01, soc-w02, soc-w03, soc-w05

**수정 방향**: 신규 트랙처럼 RED에 **주차별 고유 태그** 부여 + 채점 surface를
WAF audit(modsec, 태그 또는 913 scanner룰) 또는 호스트 계정/포트로 전환.

### 🟡 P2 — 트랙 간 instruction 헤더 스타일 불일치 (경미)
내용은 모두 존재. 헤더 형식만 다름:
- 4개 분리: `### 상황` / `### 할 일` / `### 채점 방법` / `### 합격 기준` (soc-adv, attack-adv, compliance-w01~06)
- 병합: `### 채점 방법 / 합격 기준` (compliance-w07~15)
- 상황 생략 + 병합: `### 할 일` 바로 시작 (cloud-container, web-vuln 전체)

### 🟡 P3 — 난이도 progression 비일관
같은 "W1"이라도 트랙마다 easy~hard 제각각. 트랙 내에서도 medium/hard 혼재
(예: cloud-container medium11/hard4). 의도된 난이도 곡선인지 확인 필요.

### ⚪ P4 — 레거시 데모 19개는 별도 품질 기준
자유형식·미션 수/점수 편차 큼. 신규 145 체계와 통합할지(표준 구조로 재작성) 또는
"데모/특별전"으로 분리 유지할지 정책 결정 필요.

## 라이브 검수(Task 2)와의 연결
정적 감사는 1차 필터일 뿐. 실제 퀄리티(채점이 의도대로 동작하는가)는 solo/duel
라이브 채점으로만 확정된다. P1 14개는 라이브에서 fail 재현 → 수정 → 재테스트로 해소.
```
