# battle_factory

CCC `apps/battle-factory/` 에서 이식. CVE/CTI 또는 자연어 프롬프트 → 공방전 시나리오 YAML 생성기.

## 파일

| 파일 | 역할 |
|------|------|
| `generator.py` | CTI JSON / CVE ID → battle YAML. Anthropic Claude 우선, Ollama fallback. |
| `threat_special.py` | special 위협 시나리오 템플릿. |

## 현재 상태

**원본 보존(미사용)**. 자동 생성기는 CCC 경로가 코드에 박혀 있어 그대로 실행하지 않는다.
현행 콘텐츠는 `contents/battle-scenarios/*.yaml`(128개) 을 직접 관리하며, **el34 라이브 검수는
`scripts/play_scenario.py`(RED/BLUE 증거 심기) + `scripts/grind_track.py`(claude 채점)** 하니스로 수행한다.
자동 생성을 되살릴 경우: 경로 상수를 `apps/api/app/config.py` 로 주입, 출력처를 DB `Scenario` +
`contents/battle-scenarios/`, 검증을 el34 타깃(192.168.0.80) dry-run 으로 연결한다.

## 시나리오 카탈로그

`contents/battle-scenarios/*.yaml` (128 개, 9 트랙) — el34 인프라에 맞춰 적응·라이브검수 완료.
앱 startup(lifespan)이 DB 로 자동 import (`apps/api/app/services/scenario_loader.py`).
