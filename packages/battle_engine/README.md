# battle_engine

CCC `packages/battle_engine/` 에서 이식. tubewar 의 공방전 상태 머신·이벤트·점수 처리 코어.

| 항목 | 설명 |
|------|------|
| EventType | attack / defend / detect / block / exploit / alert / score / system |
| BattleState | 진행중 공방전의 in-memory 상태 (battle_id, scores, events, time) |
| 함수 | create_battle / start_battle / add_event / end_battle / get_events / battle_stats |

## Phase 1 상태

CCC 원본 그대로 (in-memory dict). tubewar Phase 2 에서:

- `_battles` dict → DB persistence (`apps/api/app/models.py::Battle`)
- mode 확장: `solo` / `duel` (CCC `1v1` 와 동의어) / `ffa` (n인)
- `monitor` 이벤트 producer 는 Bastion API + Claude Code 두 백엔드 선택
- 점수 reflect 시 BattleParticipant.score 업데이트
