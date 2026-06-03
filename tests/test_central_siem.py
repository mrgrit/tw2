"""siem_export — 코호트 stamp, 데이터뷰/대시보드/RBAC 멱등 생성(mock OpenSearch),
재실행 중복 없음, RBAC 코호트 스코프."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TUBEWAR_FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services import siem_export as se  # noqa: E402


class FakeOpenSearch:
    """in-memory mock — 멱등 ensure_* 의미를 그대로 구현."""
    def __init__(self):
        self.indices: set[str] = set()
        self.docs: dict[str, list] = {}
        self.saved_objects: dict[tuple, dict] = {}
        self.roles: dict[str, str] = {}
        self.role_mappings: dict[str, list] = {}

    async def ensure_index(self, index):
        if index in self.indices:
            return False
        self.indices.add(index); self.docs.setdefault(index, [])
        return True

    async def bulk_index(self, index, docs):
        self.docs.setdefault(index, []).extend(docs)
        return len(docs)

    async def ensure_saved_object(self, otype, oid, attributes):
        key = (otype, oid)
        if key in self.saved_objects:
            return False
        self.saved_objects[key] = attributes
        return True

    async def ensure_role(self, name, index_pattern):
        if name in self.roles:
            return False
        self.roles[name] = index_pattern
        return True

    async def ensure_role_mapping(self, role, users):
        if role in self.role_mappings:
            return False
        self.role_mappings[role] = users
        return True


class C:
    """Cohort 스텁."""
    def __init__(self, id, kind, name, course_ref=None):
        self.id = id; self.kind = kind; self.name = name; self.course_ref = course_ref


CHAIN = [C(1, "department", "정보보안과"), C(2, "grade", "2학년"),
         C(3, "course", "웹해킹", course_ref="course3"), C(4, "section", "A분반")]


def test_cohort_path_and_physical_index():
    assert se.cohort_path_str(CHAIN) == "department:정보보안과/grade:2학년/course:웹해킹/section:A분반"
    # 물리 인덱스는 '큰 단위'(course) 기준 — section 별 인덱스 남발 금지
    assert se.physical_index_for(CHAIN) == "tubewar-activity-course3"


def test_stamp_fields():
    ev = {"user_id": 7, "infra_id": 3, "ts": "2026-06-03", "kind": "command",
          "scenario_step": 2, "payload": {"cmd": "nmap"}, "battle_id": 9}
    doc = se.stamp(ev, CHAIN)
    assert doc["student"] == 7 and doc["infra"] == 3 and doc["kind"] == "command"
    assert doc["scenario_step"] == 2
    assert doc["cohort_path"].endswith("section:A분반")
    assert doc["cohort_id"] == 4


@pytest.mark.asyncio
async def test_export_events_indexes_to_physical():
    fos = FakeOpenSearch()
    events = [{"user_id": 1, "infra_id": 1, "kind": "command", "payload": {"cmd": "ls"}},
              {"user_id": 1, "infra_id": 1, "kind": "alert", "payload": {"rule_id": 5710}}]
    res = await se.export_events(fos, events, CHAIN)
    assert res["index"] == "tubewar-activity-course3"
    assert res["indexed"] == 2
    assert len(fos.docs["tubewar-activity-course3"]) == 2
    assert all(d["cohort_id"] == 4 for d in fos.docs["tubewar-activity-course3"])


@pytest.mark.asyncio
async def test_ensure_cohort_objects_idempotent_and_rbac_scope():
    fos = FakeOpenSearch()
    r1 = await se.ensure_cohort_objects(fos, CHAIN)
    assert set(r1["created"]) == {"index-pattern:dv-4", "dashboard:dash-4",
                                  "role:cohort-4", "role_mapping:cohort-4"}
    # 재실행 → 중복 생성 없음
    r2 = await se.ensure_cohort_objects(fos, CHAIN)
    assert r2["created"] == []
    # RBAC 롤이 이 코호트 물리 인덱스로 스코프됨
    assert fos.roles["cohort-4"] == "tubewar-activity-course3*"
    # 데이터뷰는 cohort_id 로 필터
    assert fos.saved_objects[("index-pattern", "dv-4")]["filter"] == {"cohort_id": 4}


@pytest.mark.asyncio
async def test_disabled_client_is_noop():
    res = await se.export_events(None, [{"user_id": 1, "kind": "command"}], CHAIN)
    assert res["indexed"] == 0
    res2 = await se.ensure_cohort_objects(None, CHAIN)
    assert res2["disabled"] is True


def test_identity_only_index():
    # 코호트 없음(신원-only) → identity 인덱스
    assert se.physical_index_for([]) == "tubewar-activity-identity"
