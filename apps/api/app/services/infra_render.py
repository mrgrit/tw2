"""시나리오 미션 텍스트의 인프라 IP **런타임 치환**.

콘텐츠(YAML→DB)는 실제 IP 대신 플레이스홀더를 담는다:
  - ``{{TARGET_IP}}``   : 타깃 VM(el34) 관리/SSH/Assessor 호스트 IP
  - ``{{WEB_ENTRY}}``   : 타깃 웹 진입(공격 인입) IP — 보통 타깃과 별도 IP
  - ``{{ATTACKER_IP}}`` : 외부 공격자 VM IP

직렬화 시점(미션을 학생에게 줄 때)에, **그 학생/배틀이 등록한 인프라**의 IP로 치환한다.
등록 인프라가 없으면 배포별 기준 IP(``config.Settings.ref_*`` — env override 가능)로 폴백한다.
→ 특정 IP가 콘텐츠/코드에 하드코딩되지 않고, 배포 환경마다 설정/등록으로 결정된다.
"""
from __future__ import annotations
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Infra

_TOKEN = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")


def _attr(obj: Any, name: str) -> Any:
    return getattr(obj, name, None) if obj is not None else None


def build_vars(target_infra: Any | None, attacker_infra: Any | None) -> dict[str, str]:
    """타깃/공격자 Infra → 치환 변수 dict. 누락 필드는 배포 기준 IP로 폴백."""
    s = get_settings()
    target_ip = _attr(target_infra, "vm_ip") or s.ref_target_ip
    web_entry = (
        _attr(target_infra, "web_entry_ip")
        or _attr(target_infra, "vm_ip")
        or s.ref_web_entry
    )
    attacker_ip = _attr(attacker_infra, "vm_ip") or s.ref_attacker_ip
    return {
        "TARGET_IP": str(target_ip),
        "WEB_ENTRY": str(web_entry),
        "ATTACKER_IP": str(attacker_ip),
    }


def render(obj: Any, variables: dict[str, str]) -> Any:
    """str/dict/list 를 재귀 순회하며 ``{{KEY}}`` 치환. 모르는 키는 그대로 둔다."""
    if isinstance(obj, str):
        return _TOKEN.sub(lambda m: variables.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: render(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, variables) for v in obj]
    return obj


def split_infras(infras: list[Any]) -> tuple[Any | None, Any | None]:
    """학생이 등록한 인프라 목록 → (target, attacker).

    분류 기준: ``kind`` 필드(target|attacker) 우선, 없으면 name 휴리스틱
    ("att"/"공격" 포함 → attacker). 한쪽만 있으면 양쪽에 동일 인프라 사용.
    """
    target: Any | None = None
    attacker: Any | None = None
    for inf in infras:
        kind = (_attr(inf, "kind") or "").lower()
        name = (_attr(inf, "name") or "").lower()
        is_attacker = kind == "attacker" or (
            kind not in ("target",) and ("att" in name or "공격" in name)
        )
        if is_attacker:
            attacker = attacker or inf
        else:
            target = target or inf
    if target is None and attacker is None and infras:
        target = attacker = infras[0]
    return (target or attacker), (attacker or target)


async def vars_for_user(session: AsyncSession, user_id: int) -> dict[str, str]:
    """해당 사용자가 등록한 인프라 기준 치환 변수."""
    rows = (
        await session.scalars(select(Infra).where(Infra.owner_id == user_id))
    ).all()
    target, attacker = split_infras(list(rows))
    return build_vars(target, attacker)


def vars_for_battle(role_infra: dict[str, Any]) -> dict[str, str]:
    """배틀 역할→Infra 매핑 기준 치환 변수.

    듀얼: 공격자=red 인프라, 타깃=blue(방어자) 인프라.
    solo/ffa: 양쪽 role 이 동일 인프라로 매핑돼 있으므로 그대로 동작.
    """
    target = role_infra.get("blue") or role_infra.get("red")
    attacker = role_infra.get("red") or role_infra.get("blue")
    return build_vars(target, attacker)
