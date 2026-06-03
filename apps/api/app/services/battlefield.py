"""cross-infra 듀얼 — 미션 채점 대상(infra) 해석.

배틀의 battlefield(타깃 infra)는 미션의 `assess_target`(self|opponent)으로 결정된다.

- blue 미션(방어)은 기본 self → 방어자 본인 infra 에서 채점.
- red 미션(공격)이 `assess_target=opponent` 면 상대(피해자) infra 에서 채점
  → red 가 상대 vm_ip 를 공격해 만든 흔적을 상대 인프라의 Assessor 로 확인.

권한 원칙: 학생은 **본인 infra 만 등록**하고, 공격 타깃은 battle 매칭(참가자 role)으로
결정된다. 즉 어떤 infra 를 채점하느냐는 시나리오+배틀 구성이 정하지, 학생이 임의로
타인 infra 를 지정할 수 없다.
"""
from __future__ import annotations
from typing import Any

_OPPOSITE = {"red": "blue", "blue": "red"}


def resolve_target_infra(
    side: str, assess_target: str, role_infra: dict[str, Any],
) -> Any | None:
    """채점할 infra 반환.

    role_infra: 논리 role("red"/"blue") → Infra. solo/ffa 는 양쪽 role 을 동일 infra 로
    매핑해 둔 dict 를 넘긴다.
    """
    target = (assess_target or "self").lower()
    opp = _OPPOSITE.get(side, side)
    target_role = side if target == "self" else opp
    return role_infra.get(target_role) or role_infra.get(side)


def normalize_assess_target(value: Any) -> str:
    return "opponent" if str(value or "").lower() == "opponent" else "self"
