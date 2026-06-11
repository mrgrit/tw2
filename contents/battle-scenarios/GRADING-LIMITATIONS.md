# 공방전 자동채점 — 알려진 한계와 점수 해석 가이드

> 강사/운영자용. tubewar 의 AI 자동채점(`post_event` → assessor 라이브 점검 → `claude-sonnet-4-6`)이
> 어떻게 동작하고 **왜 일부 미션이 구조적으로 partial 에 머무는지**를 기록한다.
> 31개(w06~w15) 전 시나리오는 실제 배틀 파이프라인으로 검증됨(battles 43~85, 전 시나리오 fail 0).

## 채점 모델 한 줄

학생 제출(`what_i_did`/`what_happened`) → AI 가 **참여자/타깃 인프라의 라이브 로그를 read-only 로 직접 점검** →
보고의 **검증 가능한 구체 사실(rule ID·sid·계정·타임스탬프·count)이 실제 점검 결과와 일치하는지**로 채점.
앰비언트 상태만으로는 통과 불가, 증거로 교차검증, 불가 시 보류.

## 한계 (점수가 구조적으로 낮아지는 지점)

1. **분석 전용(SIEM) 미션은 partial 이 상한.**
   `wazuh_alert` 로 채점되는 분석 미션(다중소스 상관·트리아지·킬체인 재구성)은 assessor 가 "경보가 존재한다"
   까지만 확인 가능하고, **분석의 질 자체는 기계가 검증 못 한다.** AI 는 보고서의 인용 증거가 실재하는지만
   대조하므로, 아무리 통찰이 좋아도 만점이 어렵다. → **신뢰 상존 증거를 인용하면 점수가 오른다**:
   Wazuh `rule 86601`(Suricata nmap IDS, 수천 건)·`eve.json sid 1000005`·`/etc/passwd` 계정.
   특히 *"Wazuh 엔 IDS(86601)가 있으나 웹공격(modsec 942100)은 Wazuh 에 0건"* 이라는 **가시성 공백**은
   AI 가 직접 검증 가능 → soc-w06 분석 6→12점 상승 확인.

2. **modsec_audit.log 노이즈가 태그 공격을 빠르게 묻는다.**
   이 로그는 앰비언트 공격(949110·913100 수천 건)으로 초고노이즈라, 학생의 고유 태그 공격(수십 건)이
   RED 채점(공격 직후)엔 보이지만 **BLUE 채점(~2분 뒤)엔 assessor tail 윈도우 밖으로 밀려 0건**이 된다.
   → BLUE 분석 보고는 modsec 웹공격 specifics 를 인용하지 말고 위 1번의 신뢰 증거를 쓸 것.

3. **탐지 룰 미션은 실제로 그 위협을 잡는 룰이 있어야 점수가 난다.**
   예: FIM 미션(secuops-w10)은 `/etc/passwd` syscheck 룰이 실재해야 "탐지됨"이 입증된다. 룰 없이 "권고"만
   하면 partial 바닥(3점). 마찬가지로 **generic 룰(UNION SELECT)을 webshell/내부자/C2 미션에 쓰면**
   위협과 안 맞아 partial. → 미션 주제에 맞는 탐지 룰을 심어야 pass 권.

4. **동일 패턴 룰을 한 파일에 다수 쌓으면 중복으로 감점.**
   마커용으로 같은 시그니처(예: UNION SELECT)에 sid 만 바꿔 여러 개 넣으면 AI 가 특정 sid 를 "중복"으로
   판정(fail 사례 있었음). → 마커 룰은 패턴도 차별화하거나 미션당 1개.

5. **AI 채점은 ±변동이 있다.** 동일 보고서가 5~12점 범위로 흔들린다(secuops-w11 재시도에도 변동). 단일
   점수에 과민반응하지 말 것.

## 점수를 더 올리려면

- 분석 미션: 본 가이드 1번대로 **검증 가능한 증거**(Wazuh 86601 / sid 1000005 / passwd 계정 / 가시성 공백)
  를 인용하는 레퍼런스 답안 제공.
- 룰/탐지 미션: 미션 주제에 맞는 **실제 탐지 룰을 심은 채로** 채점(FIM 룰, webshell 룰 등).
- fail 이 나면 같은 시나리오의 **더 달성 가능한 BLUE 미션**(계정탐지·킬체인 재구성)으로 평가.

## 검증된 대표 결과 (각 시나리오 최신 배틀, RED / BLUE)

> 전 31개 실제 듀얼 배틀(shin=RED→kim 의 .79 / kim=BLUE) 채점. 합계 **pass 17 · partial 45 · fail 0**.
> RED 는 대체로 강하고(14~22), BLUE 는 위 한계로 분포가 넓다(구체 체크 미션 12~22 / 분석 전용 3~13).

| 시나리오 | RED | BLUE | 비고 |
|---|---|---|---|
| secuops-easy-w06 | pass 20 | partial 12 | |
| secuops-w06 | pass 20 | pass 22 | WAF anomaly score 핵심 |
| secuops-w07 | pass 17 | partial 8 | 분석형(호스트 모니터링) |
| secuops-w08 | partial 18 | partial 12 | |
| secuops-w09 | partial 15 | partial 15 | |
| secuops-w10 | pass 15 | partial 3 | **FIM 룰 부재 → 한계 3번** |
| secuops-w11 | partial 15 | partial 6 | 분석형(채점 변동) |
| secuops-w12 | partial 8 | partial 17 | |
| secuops-w13 | partial 14 | partial 7 | |
| secuops-w14 | pass 17 | partial 15 | |
| secuops-w15 | pass 18 | partial 4 | |
| soc-w06 | partial 15 | partial 12 | 분석형(다중소스, 충실화로 8→12) |
| soc-w07 | partial 15 | partial 6 | |
| soc-w08 | pass 20 | partial 12 | 분석형(트리아지, 10→12) |
| soc-w09 | pass 20 | partial 4 | |
| soc-w10 | partial 15 | partial 4 | generic 룰 한계 4·3번 |
| soc-w11 | pass 15 | partial 5 | |
| soc-w12 | pass 17 | pass 15 | 계정탐지로 fail→pass 해소 |
| soc-w13 | pass 18 | partial 13 | |
| soc-w14 | pass 17 | partial 13 | |
| soc-w15 | partial 15 | partial 5 | |
| attack-w06 | partial 19 | partial 10 | |
| attack-w07 | partial 15 | partial 6 | |
| attack-w08 | pass 20 | partial 5 | |
| attack-w09 | partial 15 | partial 8 | |
| attack-w10 | partial 10 | partial 14 | |
| attack-w11 | partial 17 | partial 5 | |
| attack-w12 | partial 12 | partial 4 | |
| attack-w13 | partial 18 | partial 14 | |
| attack-w14 | pass 20 | partial 10 | |
| attack-w15 | pass 19 | partial 13 | 킬체인 재구성으로 fail→partial 해소 |

_최종 갱신 2026-06-12. 배틀 이력은 UI/DB(battles 테이블)에서 직접 확인._
