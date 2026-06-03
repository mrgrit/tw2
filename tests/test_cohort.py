"""Cohort 위계 — 트리 CRUD, membership 다대다, 학기/분반 이동, 서브트리, admin-only 권한."""
from __future__ import annotations
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TUBEWAR_JWT_SECRET", "test-secret-32-chars-please-not-shorter")
os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.main import app  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


async def _new() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _signup(client, email, name) -> tuple[str, int]:
    r = await client.post("/auth/signup", json={
        "email": email, "password": "pass12345", "name": name,
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()["user"]["id"]


async def _make_admin(email):
    from app.models import User
    from sqlalchemy import select
    async with SessionLocal() as s:
        u = (await s.scalars(select(User).where(User.email == email))).first()
        u.role = "admin"
        await s.commit()


async def _admin_client(client) -> dict:
    await _signup(client, "rooty@example.com", "rooty")
    await _make_admin("rooty@example.com")
    tok = (await client.post("/auth/login", json={
        "email": "rooty@example.com", "password": "pass12345"})).json()["access_token"]
    return {"authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_cohort_tree_crud_parent_child() -> None:
    async with await _new() as client:
        ah = await _admin_client(client)

        # 학과 → 학년 → 교과목 → 분반 → 팀 트리
        dept = (await client.post("/cohorts", headers=ah, json={
            "kind": "department", "name": "정보보안과"})).json()
        grade = (await client.post("/cohorts", headers=ah, json={
            "kind": "grade", "name": "2학년", "parent_id": dept["id"]})).json()
        course = (await client.post("/cohorts", headers=ah, json={
            "kind": "course", "name": "웹해킹", "parent_id": grade["id"],
            "course_ref": "course3"})).json()
        section = (await client.post("/cohorts", headers=ah, json={
            "kind": "section", "name": "A분반", "parent_id": course["id"]})).json()

        assert grade["parent_id"] == dept["id"]
        assert course["course_ref"] == "course3"

        # 트리 조회 — 루트 1개, 자식 체인
        tree = (await client.get("/cohorts/tree", headers=ah)).json()
        assert len(tree) == 1
        assert tree[0]["id"] == dept["id"]
        assert tree[0]["children"][0]["id"] == grade["id"]
        assert tree[0]["children"][0]["children"][0]["id"] == course["id"]

        # 서브트리 (course 부터)
        sub = (await client.get(f"/cohorts/{course['id']}/subtree", headers=ah)).json()
        assert sub[0]["id"] == course["id"]
        assert sub[0]["children"][0]["id"] == section["id"]

        # 잘못된 parent → 400
        bad = await client.post("/cohorts", headers=ah, json={
            "kind": "team", "name": "x", "parent_id": 99999})
        assert bad.status_code == 400

        # patch — 이름 변경 + 사이클 방지(부모를 자기 자손으로 못 옮김)
        cyc = await client.patch(f"/cohorts/{dept['id']}", headers=ah,
                                 json={"parent_id": section["id"]})
        assert cyc.status_code == 400
        assert "cycle" in cyc.json()["detail"]

        ren = await client.patch(f"/cohorts/{section['id']}", headers=ah,
                                 json={"name": "A반"})
        assert ren.status_code == 200 and ren.json()["name"] == "A반"

        # delete dept → cascade 로 전부 삭제
        d = await client.delete(f"/cohorts/{dept['id']}", headers=ah)
        assert d.status_code == 204
        assert (await client.get("/cohorts", headers=ah)).json() == []


@pytest.mark.asyncio
async def test_membership_many_to_many_and_move() -> None:
    async with await _new() as client:
        ah = await _admin_client(client)
        _, sid = await _signup(client, "stud@example.com", "Stud")

        # 두 분반(학기 이동 시나리오)
        c1 = (await client.post("/cohorts", headers=ah, json={
            "kind": "section", "name": "1학기-A"})).json()
        c2 = (await client.post("/cohorts", headers=ah, json={
            "kind": "section", "name": "2학기-B"})).json()

        # c1 배치
        m = await client.post(f"/cohorts/{c1['id']}/members", headers=ah,
                              json={"user_id": sid, "role": "student"})
        assert m.status_code == 201
        assert m.json()["user_name"] == "Stud"

        # 중복 배치 → 409
        dup = await client.post(f"/cohorts/{c1['id']}/members", headers=ah,
                                json={"user_id": sid})
        assert dup.status_code == 409

        # 다대다: 동일 학생을 c2 에도 직접 배치 가능 (수업 밖 재사용)
        m2 = await client.post(f"/cohorts/{c2['id']}/members", headers=ah,
                               json={"user_id": sid, "role": "ta"})
        assert m2.status_code == 201
        assert len((await client.get(f"/cohorts/{c1['id']}/members", headers=ah)).json()) == 1
        assert len((await client.get(f"/cohorts/{c2['id']}/members", headers=ah)).json()) == 1

        # 이동: c1 → c2 (c2 에 이미 있으니 role 갱신 + c1 제거)
        mv = await client.post("/cohorts/members/move", headers=ah, json={
            "user_id": sid, "from_cohort_id": c1["id"], "to_cohort_id": c2["id"],
            "role": "student"})
        assert mv.status_code == 200
        assert (await client.get(f"/cohorts/{c1['id']}/members", headers=ah)).json() == []
        c2_members = (await client.get(f"/cohorts/{c2['id']}/members", headers=ah)).json()
        assert len(c2_members) == 1 and c2_members[0]["role"] == "student"

        # member_count 반영
        c2_node = (await client.get(f"/cohorts/{c2['id']}", headers=ah)).json()
        assert c2_node["member_count"] == 1

        # 멤버 제거
        rm = await client.delete(f"/cohorts/{c2['id']}/members/{sid}", headers=ah)
        assert rm.status_code == 204


@pytest.mark.asyncio
async def test_cohort_admin_only() -> None:
    async with await _new() as client:
        ah = await _admin_client(client)
        # 학생 토큰
        stok, sid = await _signup(client, "s@example.com", "S")
        sh = {"authorization": f"Bearer {stok}"}

        node = (await client.post("/cohorts", headers=ah, json={
            "kind": "team", "name": "T"})).json()

        # 학생은 읽기 가능
        assert (await client.get("/cohorts", headers=sh)).status_code == 200
        assert (await client.get(f"/cohorts/{node['id']}", headers=sh)).status_code == 200

        # 학생은 생성/수정/삭제/배치 불가 (403)
        assert (await client.post("/cohorts", headers=sh, json={
            "kind": "team", "name": "X"})).status_code == 403
        assert (await client.patch(f"/cohorts/{node['id']}", headers=sh,
                                   json={"name": "Y"})).status_code == 403
        assert (await client.delete(f"/cohorts/{node['id']}", headers=sh)).status_code == 403
        assert (await client.post(f"/cohorts/{node['id']}/members", headers=sh,
                                  json={"user_id": sid})).status_code == 403
