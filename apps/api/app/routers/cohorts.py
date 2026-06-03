"""Cohort 위계 라우터 — 학과–학년–교과목–분반–팀 트리 CRUD + 학생 배치/이동.

읽기(목록/트리/서브트리/멤버 조회)는 인증 사용자 누구나, 변경(생성/수정/삭제/배치/이동)은
admin 전용. 클라이언트는 dumb — 트리 구성·필터링은 전부 서버가 책임진다.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Cohort, CohortMembership, User
from ..schemas import (
    CohortIn, CohortMembershipIn, CohortMembershipOut, CohortMoveIn,
    CohortOut, CohortPatchIn, CohortTreeOut,
)
from ..security import get_current_user, require_admin
from ..services import audit
from ..services import cohort_service as cs

router = APIRouter(prefix="/cohorts", tags=["cohorts"])


async def _member_counts(session: AsyncSession) -> dict[int, int]:
    rows = (await session.execute(
        select(CohortMembership.cohort_id, func.count(CohortMembership.id))
        .group_by(CohortMembership.cohort_id)
    )).all()
    return {cid: int(n) for cid, n in rows}


def _to_out(c: Cohort, counts: dict[int, int]) -> CohortOut:
    return CohortOut(
        id=c.id, kind=c.kind, name=c.name, parent_id=c.parent_id,
        course_ref=c.course_ref, created_at=c.created_at,
        member_count=counts.get(c.id, 0),
    )


def _build_tree(nodes: list[Cohort], counts: dict[int, int],
                root_id: int | None) -> list[CohortTreeOut]:
    """nodes 전체로부터 root_id(None=forest 루트들) 아래 트리를 구성."""
    by_parent: dict[int | None, list[Cohort]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    def make(c: Cohort) -> CohortTreeOut:
        kids = sorted(by_parent.get(c.id, []), key=lambda x: (x.name, x.id))
        return CohortTreeOut(
            id=c.id, kind=c.kind, name=c.name, parent_id=c.parent_id,
            course_ref=c.course_ref, created_at=c.created_at,
            member_count=counts.get(c.id, 0),
            children=[make(k) for k in kids],
        )

    if root_id is None:
        roots = sorted(by_parent.get(None, []), key=lambda x: (x.name, x.id))
        return [make(r) for r in roots]
    root = next((n for n in nodes if n.id == root_id), None)
    return [make(root)] if root else []


# ── 트리 조회 ───────────────────────────────────────
@router.get("", response_model=list[CohortOut])
async def list_cohorts(
    kind: str | None = None,
    parent_id: int | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CohortOut]:
    q = select(Cohort).order_by(Cohort.id.asc())
    if kind:
        q = q.where(Cohort.kind == kind)
    if parent_id is not None:
        q = q.where(Cohort.parent_id == parent_id)
    rows = (await session.scalars(q)).all()
    counts = await _member_counts(session)
    return [_to_out(c, counts) for c in rows]


@router.get("/tree", response_model=list[CohortTreeOut])
async def cohort_forest(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CohortTreeOut]:
    nodes = (await session.scalars(select(Cohort))).all()
    counts = await _member_counts(session)
    return _build_tree(list(nodes), counts, root_id=None)


@router.get("/{cohort_id}", response_model=CohortOut)
async def get_cohort(
    cohort_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CohortOut:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    counts = await _member_counts(session)
    return _to_out(c, counts)


@router.get("/{cohort_id}/subtree", response_model=list[CohortTreeOut])
async def get_subtree(
    cohort_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CohortTreeOut]:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    nodes = (await session.scalars(select(Cohort))).all()
    counts = await _member_counts(session)
    return _build_tree(list(nodes), counts, root_id=cohort_id)


# ── 트리 변경 (admin) ───────────────────────────────
@router.post("", response_model=CohortOut, status_code=201)
async def create_cohort(
    body: CohortIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CohortOut:
    if body.parent_id is not None:
        parent = await session.get(Cohort, body.parent_id)
        if not parent:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"parent cohort {body.parent_id} not found")
    c = Cohort(kind=body.kind, name=body.name, parent_id=body.parent_id,
               course_ref=body.course_ref)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    await audit.record(
        session, actor=admin, action="cohort.create",
        target_type="cohort", target_id=c.id,
        detail={"kind": c.kind, "name": c.name, "parent_id": c.parent_id},
        request=request,
    )
    counts = await _member_counts(session)
    return _to_out(c, counts)


@router.patch("/{cohort_id}", response_model=CohortOut)
async def patch_cohort(
    cohort_id: int,
    body: CohortPatchIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CohortOut:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    fields = body.model_dump(exclude_unset=True)
    if "parent_id" in fields and fields["parent_id"] is not None:
        new_parent = fields["parent_id"]
        if not await session.get(Cohort, new_parent):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"parent cohort {new_parent} not found")
        if await cs.would_create_cycle(session, cohort_id, new_parent):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "move would create a cycle")
    prev = {"name": c.name, "parent_id": c.parent_id, "course_ref": c.course_ref}
    if "name" in fields:
        c.name = fields["name"]
    if "parent_id" in fields:
        c.parent_id = fields["parent_id"]
    if "course_ref" in fields:
        c.course_ref = fields["course_ref"]
    await session.commit()
    await session.refresh(c)
    await audit.record(
        session, actor=admin, action="cohort.patch",
        target_type="cohort", target_id=cohort_id,
        detail={"prev": prev, "next": {"name": c.name, "parent_id": c.parent_id,
                                       "course_ref": c.course_ref}},
        request=request,
    )
    counts = await _member_counts(session)
    return _to_out(c, counts)


@router.delete("/{cohort_id}", status_code=204)
async def delete_cohort(
    cohort_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    name = c.name
    await session.delete(c)  # children + memberships cascade
    await session.commit()
    await audit.record(
        session, actor=admin, action="cohort.delete",
        target_type="cohort", target_id=cohort_id,
        detail={"name": name},
        request=request,
    )


# ── 멤버십 (학생 배치/이동) ─────────────────────────
@router.get("/{cohort_id}/members", response_model=list[CohortMembershipOut])
async def list_members(
    cohort_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CohortMembershipOut]:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    rows = (await session.scalars(
        select(CohortMembership).where(CohortMembership.cohort_id == cohort_id)
        .order_by(CohortMembership.id.asc())
    )).all()
    users = {
        u.id: u for u in (await session.scalars(
            select(User).where(User.id.in_([r.user_id for r in rows]))
        )).all()
    } if rows else {}
    out: list[CohortMembershipOut] = []
    for r in rows:
        u = users.get(r.user_id)
        out.append(CohortMembershipOut(
            id=r.id, cohort_id=r.cohort_id, user_id=r.user_id,
            user_name=u.name if u else None, user_email=u.email if u else None,
            role=r.role, created_at=r.created_at,
        ))
    return out


@router.post("/{cohort_id}/members", response_model=CohortMembershipOut, status_code=201)
async def add_member(
    cohort_id: int,
    body: CohortMembershipIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CohortMembershipOut:
    c = await session.get(Cohort, cohort_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cohort not found")
    u = await session.get(User, body.user_id)
    if not u:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"user {body.user_id} not found")
    existing = await session.scalar(
        select(CohortMembership).where(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.user_id == body.user_id,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "user already in this cohort")
    m = CohortMembership(cohort_id=cohort_id, user_id=body.user_id, role=body.role)
    session.add(m)
    await session.commit()
    await session.refresh(m)
    await audit.record(
        session, actor=admin, action="cohort.member_add",
        target_type="cohort", target_id=cohort_id,
        detail={"user_id": body.user_id, "role": body.role},
        request=request,
    )
    return CohortMembershipOut(
        id=m.id, cohort_id=m.cohort_id, user_id=m.user_id,
        user_name=u.name, user_email=u.email, role=m.role, created_at=m.created_at,
    )


@router.delete("/{cohort_id}/members/{user_id}", status_code=204)
async def remove_member(
    cohort_id: int,
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    m = await session.scalar(
        select(CohortMembership).where(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.user_id == user_id,
        )
    )
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membership not found")
    await session.delete(m)
    await session.commit()
    await audit.record(
        session, actor=admin, action="cohort.member_remove",
        target_type="cohort", target_id=cohort_id,
        detail={"user_id": user_id},
        request=request,
    )


@router.post("/members/move", response_model=CohortMembershipOut)
async def move_member(
    body: CohortMoveIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CohortMembershipOut:
    """학생을 from_cohort 에서 to_cohort 로 이동 (학기/분반 변경).

    from 에 멤버십이 없어도 to 로 신규 배치(멱등)되도록 허용 — 단 from 에 있으면 제거.
    """
    src = await session.scalar(
        select(CohortMembership).where(
            CohortMembership.cohort_id == body.from_cohort_id,
            CohortMembership.user_id == body.user_id,
        )
    )
    to = await session.get(Cohort, body.to_cohort_id)
    if not to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"target cohort {body.to_cohort_id} not found")
    u = await session.get(User, body.user_id)
    if not u:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"user {body.user_id} not found")

    role = body.role or (src.role if src else None)
    if src:
        await session.delete(src)
    # 이미 to 에 있으면 role 만 갱신, 없으면 신규 생성.
    dst = await session.scalar(
        select(CohortMembership).where(
            CohortMembership.cohort_id == body.to_cohort_id,
            CohortMembership.user_id == body.user_id,
        )
    )
    if dst:
        dst.role = role
    else:
        dst = CohortMembership(cohort_id=body.to_cohort_id, user_id=body.user_id, role=role)
        session.add(dst)
    await session.commit()
    await session.refresh(dst)
    await audit.record(
        session, actor=admin, action="cohort.member_move",
        target_type="cohort", target_id=body.to_cohort_id,
        detail={"user_id": body.user_id, "from": body.from_cohort_id, "to": body.to_cohort_id},
        request=request,
    )
    return CohortMembershipOut(
        id=dst.id, cohort_id=dst.cohort_id, user_id=dst.user_id,
        user_name=u.name, user_email=u.email, role=dst.role, created_at=dst.created_at,
    )
