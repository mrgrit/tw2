# battle_factory

CCC `apps/battle-factory/` 에서 이식. CVE/CTI 또는 자연어 프롬프트 → 공방전 시나리오 YAML 생성기.

## 파일

| 파일 | 역할 |
|------|------|
| `generator.py` | CTI JSON / CVE ID → battle YAML. Anthropic Claude 우선, Ollama fallback. |
| `threat_special.py` | special 위협 시나리오 템플릿. |

## Phase 1 상태

**원본 보존만**. CCC 경로 (`contents/threats/`, `contents/labs/battle-auto/`) 가 코드에 박혀 있어
**그대로 실행 X**. Phase 4 에서 다음과 같이 리팩터:

1. 경로 상수를 `apps/api/app/config.py` 의 설정 객체로 주입.
2. 출력처: tubewar DB `Scenario` 테이블 + `contents/battle-scenarios/auto/*.yaml`.
3. 호출처: 관리자 페이지 → POST `/admin/scenarios/generate` → 백그라운드 task.
4. 검증 단계: 학생 6v6 인프라 한 대를 잡아 dry-run → mission_red/blue 의 단계가 실제로
   실행 가능한지 확인 + 채점 기준 자동 작성.

## 시나리오 카탈로그

`contents/battle-scenarios/*.yaml` (17 개) — CCC 의 검증된 시나리오 그대로.
초기 admin 부트스트랩 시 DB 로 import 해서 시작 자료로 활용 예정.
