#!/usr/bin/env python3
"""이니셔티브 게시판(Post, board=initiative) ← docs/ 마크다운 전부 upsert(멱등).

게시판은 DB Post 테이블이라 docs/*.md 편집만으로는 반영 안 된다 → 이 스크립트로 문서를 게시판에
올린다. (board, title) 로 upsert: 있으면 본문/고정 갱신, 없으면 생성. 재배포/문서수정 후 재실행하면
게시판이 문서와 동기화된다.

usage: .venv/bin/python scripts/seed_initiative_posts.py
"""
from __future__ import annotations
import os, sys, glob, asyncio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))

from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Post, User  # noqa: E402

BOARD = "initiative"
# gwanje-demo 는 기존 게시글(#1)을 그대로 갱신하도록 제목 고정(중복 방지).
TITLE_OVERRIDE = {
    "docs/initiatives/gwanje-demo.md": "[기획] AI 관제·모니터링 시연 영상",
}
# 상단 고정할 문서(핵심 기획/운영).
PIN_RELPATHS = {
    "docs/initiatives/gwanje-demo.md",
    "docs/initiatives/adaptive-siem-fields.md",
    "docs/operations.md",
    "docs/roadmap.md",
}


def h1_title(path: str) -> str:
    for line in open(path, encoding="utf-8"):
        if line.startswith("# "):
            return line[2:].strip()
    return os.path.splitext(os.path.basename(path))[0]


def title_for(rel: str, path: str) -> str:
    if rel in TITLE_OVERRIDE:
        return TITLE_OVERRIDE[rel]
    t = h1_title(path)
    # 문서 계열 접두어로 게시판 가독성↑ (이니셔티브는 원제목 유지).
    if rel.startswith("docs/initiatives/"):
        return t
    return f"[문서] {t}"


async def pick_author(session) -> User | None:
    # 기존 initiative 글 작성자 우선, 없으면 admin, 없으면 첫 사용자.
    p = (await session.execute(
        select(Post).where(Post.board == BOARD).order_by(Post.id))).scalars().first()
    if p and p.author_id:
        u = await session.get(User, p.author_id)
        if u:
            return u
    for cond in (getattr(User, "role", None) == "admin" if hasattr(User, "role") else None,
                 getattr(User, "is_admin", None) == True if hasattr(User, "is_admin") else None):  # noqa: E712
        if cond is None:
            continue
        u = (await session.execute(select(User).where(cond))).scalars().first()
        if u:
            return u
    return (await session.execute(select(User).order_by(User.id))).scalars().first()


async def main():
    files = sorted(glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True))
    async with SessionLocal() as s:
        author = await pick_author(s)
        existing = {p.title: p for p in
                    (await s.execute(select(Post).where(Post.board == BOARD))).scalars().all()}
        created = updated = 0
        for path in files:
            rel = os.path.relpath(path, ROOT)
            title = title_for(rel, path)
            body = open(path, encoding="utf-8").read()
            pinned = rel in PIN_RELPATHS
            if title in existing:
                p = existing[title]
                p.body = body
                p.pinned = pinned
                updated += 1
            else:
                s.add(Post(board=BOARD, title=title, body=body, pinned=pinned,
                           author_id=(author.id if author else None),
                           author_name=(author.name if author else "system")))
                created += 1
            print(f"  {'update' if title in existing else 'create'}: {title}  ← {rel}")
        await s.commit()
        print(f"완료: 생성 {created} · 갱신 {updated} · 총 {len(files)} 문서 → 게시판(board={BOARD})")


if __name__ == "__main__":
    asyncio.run(main())
