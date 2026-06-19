# tw2 교수(강사) 매뉴얼

> 대상: 수업을 운영하는 **교수/강사(instructor)**.
> 코호트(분반) 구성, 공방전 출제·매칭, 실습 모니터링(진도·병목), 학생 피드백, SIEM 육안
> 확인까지 수업 운영 전반을 다룹니다.

> **권한 안내(중요)**: 현재 tw2 의 시스템 권한은 `student` / `admin` 2단계입니다.
> 코호트 관리·모니터링·피드백·시나리오 활성화 등 **교수 기능은 `admin` 권한으로 수행**합니다.
> 따라서 교수 계정은 관리자에게 **admin 권한 부여**를 받아야 합니다(관리자 매뉴얼 §사용자 관리).
> `instructor`/`ta` 는 코호트 멤버십의 역할 라벨로 별도 기록되며, 권한 경계는 admin 으로 통일됩니다.
> (향후 instructor 전용 RBAC 세분화는 로드맵 항목입니다.)

- 중앙 서버: `http://<host>:9200` (API) / UI `:5173`
- 관리 화면: 로그인 후 상단 **관리자** 메뉴 → 탭으로 전환.

---

## 0. 수업 운영 한 흐름

```
코호트 트리 생성(학과→학년→교과목→분반) → 학생 배치
   → (수업용) cohort-bound 공방전 로비 개설 → 학생 join → 시작
   → 실습 모니터링(진도·병목) → 막힌 학생 피드백 → 코호트 리더보드/통계
   → SIEM(el34-siem/Wazuh)으로 활동 육안 확인
```

---

## 1. 코호트(분반) 구성 — 관리자 → **코호트** 탭

코호트는 **지금 이 세션이 무슨 수업이냐**를 나타내는 가변 문맥입니다. 학생 등록 정보(인프라)는
신원만 담고, 과목/학년/분반 분리는 전적으로 코호트가 담당합니다(서버측 태깅).

### 1.1 트리 만들기
- 종류(kind): `department(학과) → grade(학년) → course(교과목) → section(분반) → team(팀)`.
- 노드 추가: 종류·이름·상위 노드 선택. 교과목 노드에는 `course_ref`(예: `course3`)를 넣어
  시나리오와 느슨하게 연결할 수 있습니다.
- 사이클(부모를 자기 자손으로 이동)은 자동 차단됩니다.

### 1.2 학생 배치 / 이동
- 노드의 **멤버** 패널에서 학생을 배치(역할: student/instructor/ta).
- **이동**: 한 분반에서 다른 분반으로 옮길 수 있습니다(학기/분반 변경). 다대다라 동일 학생이
  여러 코호트에 속해도 무방합니다(수업 밖 재사용 가능).

API 예:
```bash
# 트리 노드
curl -X POST $BASE/cohorts -H "authorization: Bearer $ADMIN" -H 'content-type: application/json' \
  -d '{"kind":"course","name":"웹해킹","course_ref":"course3"}'
# 학생 배치
curl -X POST $BASE/cohorts/<cohort_id>/members -H "authorization: Bearer $ADMIN" \
  -H 'content-type: application/json' -d '{"user_id":42,"role":"student"}'
# 이동
curl -X POST $BASE/cohorts/members/move -H "authorization: Bearer $ADMIN" \
  -H 'content-type: application/json' \
  -d '{"user_id":42,"from_cohort_id":3,"to_cohort_id":7}'
```

---

## 2. 공방전 출제·매칭

시나리오 카탈로그는 **128개(9트랙)** 입니다: `soc / soc-adv / attack / attack-adv / compliance /
web-vuln / cloud-container / secuops` 각 15개 + `secuops-easy` 6개(입문). 트랙·난이도에 맞춰
출제하세요.

### 2.1 cohort-bound 로비 (수업용)
**공방전** 화면에서 로비를 개설할 때 **코호트**를 선택하면 그 배틀이 분반에 묶입니다.
- 시나리오 선택 → 코호트 선택(선택) → 모드(duel/ffa) → 채점 모델(bastion/claude) → 힌트 허용 →
  타깃 앱(1~5 또는 랜덤) → **로비 개설**.
- 학생들이 직접 Red/Blue 로 join → 최소 인원 충족 시 시작.
- 코호트를 비우면 **신원-only** 모드(자유 연습)로 동작합니다.

### 2.2 cross-infra 듀얼
시나리오의 Red 미션이 `assess_target=opponent` 면, Red 학생은 **상대(Blue)의 el34** 를 공격해
흔적을 남겨야 채점됩니다. 외부 공격자 VM(`192.168.0.202`)에서 타깃의 공개 포트로 공격하면 출처
IP·payload 가 Suricata/ModSec/Wazuh 에 보존되어 타깃 인프라의 흔적으로 채점됩니다. 채점 무대(타깃
인프라)는 배틀 매칭(참가자 역할)으로 자동 결정되며, 학생은 본인 인프라만 등록합니다(임의 타인
인프라 지정 불가).

### 2.3 채점 모델
- **bastion**: 결정론 채점(Assessor `passed`) — 비용/LLM 0. 기본 권장.
  결정론 체크: `file_contains` / `log_contains` / `port_listening` / `process_running` / `wazuh_alert`.
- **claude**: claude CLI(claude-sonnet-4-6)의 의미 채점으로 결과가 모호할 때 보강 분석.
  그 외에는 결정론과 동일.

---

## 3. 실습 모니터링 — 관리자 → **실습 모니터링** 탭

채점과 **별개 트랙**으로, 학생 활동을 읽어 진도·병목을 봅니다(결정론, LLM 0).

1. battle 선택 → 학생×단계 **진도 매트릭스**(완료율, step n/N, 병목 플래그).
2. **막힌 학생**은 붉게 하이라이트됩니다(반복 실패 명령/과다 알림/진전 없음 등 결정론 신호).
3. **지금 점검(lab-tick)** 버튼: 폴링을 기다리지 않고 즉시 `/activity` pull + 진도 재계산.
   - `with_feedback=true` 로 실행하면 막힌 학생에게 자동으로 AI 피드백을 생성합니다.
4. 학생 행의 **타임라인** 버튼: 그 학생의 명령/파일변경/알림 타임라인을 드릴다운.
5. **피드백 생성** 버튼: 해당 학생에게 즉시 개인 피드백 작성.

> 진도의 "단계(step)"는 시나리오 미션입니다. 자동 채점기가 그 미션을 충족으로 판정하면
> 그 단계가 완료로 집계됩니다.

---

## 4. 학생 피드백 — 관리자 → **피드백** 탭

AI 코치(claude)가 활동 타임라인 + 진도 + 병목 + 채점 근거를 바탕으로 **개인화 피드백**을
작성합니다. 대상자 선별은 결정론(병목 신호)으로, **작성만 AI** 가 합니다.

- **트리거 3종**: ① 병목 임계 초과(자동) ② 실습/배틀 종료 ③ 강사 on-demand.
- **검토/재생성/발행**: 피드백 탭에서 목록을 보고, 필요 시 **재생성**.
- **전달 대상**: `student`(학생만) / `instructor`(강사만) / `both`. 학생에게 보낼 것만 학생
  대시보드에 노출됩니다.
- **원칙**: 사실을 지어내지 않으며, 정답·완전한 페이로드를 통째로 주지 않고 힌트 수준만 제공합니다.
- AI(claude) 가 가용하지 않은 환경에서는 입력 데이터 기반의 결정론 요약으로 안전하게 대체됩니다.

API:
```bash
# 강사 on-demand 생성
curl -X POST $BASE/feedback/students/<uid> -H "authorization: Bearer $ADMIN" \
  -H 'content-type: application/json' -d '{"battle_id":12,"delivered_to":"both"}'
# 검토
curl "$BASE/feedback?cohort_id=7" -H "authorization: Bearer $ADMIN"
```

---

## 5. 코호트 리더보드 / 통계

- **리더보드** 메뉴 상단의 코호트 필터로 우리 교과목/분반 서브트리만 집계해 봅니다.
- 관리자 → **통계** 탭의 코호트 필터로 사용자 수·배틀 수·Top scorer 를 코호트 범위로 스코프합니다.
- 관리자 → **공방전 관리** 탭에서도 코호트로 배틀 목록을 필터링합니다.

---

## 6. SIEM — 학생 활동 육안 확인

el34 의 **el34-siem(Wazuh)** 으로 학생 활동(공격 흔적·알림)을 눈으로 탐색합니다. 패킷 흐름
`FW → IPS(Suricata) → WAF(Apache+ModSec) → 앱` 전 계층의 이벤트와, 외부 공격자(`192.168.0.202`)의
출처 IP 까지 보존됩니다.

- 채점/모니터링은 Assessor 표면을 통해 프로그램적으로 이뤄지고(→ DB), Wazuh 는 그와 별개로
  강사가 **육안 확인**하는 용도입니다.
- 학생별 로컬 SIEM(Wazuh alert viewer)로 개별 인프라의 알림도 확인할 수 있습니다.

> 참고: 구 tubewar 의 중앙 OpenSearch 적재(lab_monitor)는 tw2 에서 비활성(OFF)입니다.
> 활동 확인은 el34-siem(Wazuh)으로 합니다.

---

## 7. 운영 팁 / 체크리스트

- 수업 전: 학생들이 el34 를 켜고 **smoke 가 healthy** 인지(학생 본인이 확인) 독려.
  (학생은 타깃 + 외부 공격자 **인프라 2개**를 등록해야 합니다.)
- 실습 중: **실습 모니터링** 탭을 띄워 막힌 학생을 조기 발견 → 타임라인 확인 → 피드백.
- duel: Red/Blue 인원·인프라가 모두 등록됐는지 확인 후 시작.
- 채점이 안 보이면: 학생 인프라 도달성(Assessor reachability, `192.168.0.151:9201`), 시나리오
  상태(`validated`), 미션 성공조건을 점검.
- 신원-only(코호트 없음) 연습도 정상 동작하므로, 가벼운 자율 연습은 코호트 없이 운영해도 됩니다.

---

## 8. 알아두면 좋은 제약

- 교수 기능은 admin 권한으로 수행(위 권한 안내). 본인 계정 강등/비활성화는 막혀 있습니다.
- 시나리오 신규 생성(자연어→시나리오)·dry-run·활성화/보관/삭제, 사용자 권한 변경, 감사 로그,
  배틀 강제 종료/삭제 등은 관리자 매뉴얼에서 상세히 다룹니다.
- el34/Bastion 은 불변입니다. tw2 는 el34 의 외부 표면(Assessor 등)만 호출합니다.
