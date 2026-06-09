# SOC 관제 리포트 (AI 에이전트 자동 생성)

이 디렉토리는 **AI 에이전트가 tubewar 중앙 SIEM(OpenSearch)을 읽고 수행한 보안관제(SOC)
결과**를 주기적으로 적재한다. 사람이 쓰지 않는다 — 에이전트가 매 관제 사이클마다 갱신·푸시한다.

## 무엇을, 어떻게

- **대상**: 학생 6v6 공방전에서 쌓이는 활동 로그 — Suricata/IPS 경보, Wazuh HIDS 경보,
  공격자 셸 명령, 파일/프로세스 증거, AI 채점 verdict.
- **데이터 출처**: 중앙 SIEM `OpenSearch :9201` 의 `tubewar-activity-*` 인덱스 **읽기 전용**.
  6v6 인프라 자체에는 일절 접근하지 않는다(외부 노출 표면만 의존하는 tubewar 원칙).
- **권위 vs 탐색**: 채점 권위는 Postgres, 본 관제는 탐색용 lake(OpenSearch) 기반.
  따라서 본 리포트는 *관제 관점의 해석*이며 성적/채점의 정정본이 아니다.

## 디렉토리 규약

```
soc-reports/
  README.md                     ← 이 파일
  LATEST.md                     ← 최신 사이클 요약(항상 최신 1건)
  YYYY-MM-DD/
    cycle-NNN_HHMMKST.md        ← 사이클별 전체 관제 리포트
```

## 리포트 한 장의 구성

1. 관제 윈도우 & 데이터 출처 메타
2. 상황 인식(situational picture) — 볼륨/참가자/인프라
3. 탐지된 위협·인시던트(INC-NNN) + 증거
4. 출처(source IP) 귀속 분석
5. 탐지 커버리지 / 사각지대
6. 권고 대응(real-SOC 관점)
7. 다음 사이클에서 볼 것

## 관련

- 방법론 설계(경험 누적): [`../soc-methodology/`](../soc-methodology/)
- SIEM 아키텍처: [`../docs/central_siem.md`](../docs/central_siem.md)
</content>
</invoke>
