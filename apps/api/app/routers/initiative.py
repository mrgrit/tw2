"""이니셔티브 게시판 — 보드별 마크다운 게시물.

열람=인증 사용자, 작성/수정/삭제=관리자. 점수 권위(battle_events)와 무관한 단순 공지/연구 게시판.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Post, User
from ..schemas import PostIn, PostOut
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/initiative", tags=["initiative"])
BOARD = "initiative"


@router.get("", response_model=list[PostOut])
async def list_posts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PostOut]:
    q = (
        select(Post)
        .where(Post.board == BOARD)
        .order_by(Post.pinned.desc(), Post.created_at.desc(), Post.id.desc())
    )
    rows = (await session.scalars(q)).all()
    return [PostOut.model_validate(p) for p in rows]


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PostOut:
    p = await session.get(Post, post_id)
    if not p or p.board != BOARD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    return PostOut.model_validate(p)


@router.post("", response_model=PostOut, status_code=201)
async def create_post(
    body: PostIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PostOut:
    p = Post(
        board=BOARD, title=body.title, body=body.body,
        author_id=admin.id, author_name=admin.name, pinned=body.pinned,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return PostOut.model_validate(p)


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    body: PostIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PostOut:
    p = await session.get(Post, post_id)
    if not p or p.board != BOARD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    p.title = body.title
    p.body = body.body
    p.pinned = body.pinned
    await session.commit()
    await session.refresh(p)
    return PostOut.model_validate(p)


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    p = await session.get(Post, post_id)
    if not p or p.board != BOARD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    await session.delete(p)
    await session.commit()
