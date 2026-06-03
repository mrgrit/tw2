"""Cohort 위계 트리 헬퍼 — 서브트리 ID 수집 + 멤버 user_id 수집.

cohorts 라우터(트리 CRUD)와 cohort 필터 뷰(leaderboard/stats/battle 목록)가 공유한다.
트리는 깊이가 얕고(학과→학년→교과목→분반→팀, 최대 5단계) 노드 수도 적으므로
재귀 CTE 대신 단순 BFS(파이썬 측)로 충분하다 — DB 독립적이고 sqlite/pg 모두 동일 동작.
"""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Cohort, CohortMembership


async def subtree_ids(session: AsyncSession, root_id: int) -> list[int]:
    """root_id 와 그 모든 하위 노드의 id 목록 (root 포함). root 없으면 빈 리스트."""
    root = await session.get(Cohort, root_id)
    if not root:
        return []
    # parent_id → [child_id] 인접 리스트 한 번에 로드.
    rows = (await session.execute(select(Cohort.id, Cohort.parent_id))).all()
    children: dict[int, list[int]] = {}
    for cid, pid in rows:
        if pid is not None:
            children.setdefault(pid, []).append(cid)

    out: list[int] = []
    stack = [root_id]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


async def user_ids_in_subtree(session: AsyncSession, root_id: int) -> set[int]:
    """서브트리(root 포함)의 모든 Cohort 에 소속된 학생 user_id 집합."""
    ids = await subtree_ids(session, root_id)
    if not ids:
        return set()
    rows = (await session.scalars(
        select(CohortMembership.user_id).where(CohortMembership.cohort_id.in_(ids))
    )).all()
    return set(rows)


async def ancestor_chain(session: AsyncSession, cohort_id: int) -> list[Cohort]:
    """root → node 순서의 조상 체인 (node 포함). cohort_path stamp 에 사용."""
    chain: list[Cohort] = []
    cur = await session.get(Cohort, cohort_id)
    seen: set[int] = set()
    while cur and cur.id not in seen:
        seen.add(cur.id)
        chain.append(cur)
        cur = await session.get(Cohort, cur.parent_id) if cur.parent_id else None
    chain.reverse()
    return chain


async def would_create_cycle(session: AsyncSession, node_id: int, new_parent_id: int) -> bool:
    """node_id 의 parent 를 new_parent_id 로 바꾸면 사이클이 생기는가.

    new_parent_id 가 node_id 자신이거나 node_id 의 서브트리 안에 있으면 사이클.
    """
    if node_id == new_parent_id:
        return True
    descendants = set(await subtree_ids(session, node_id))
    return new_parent_id in descendants
