"""워크북 렌더러(서비스) — prefill 로 학생 입력+채점이 docx 칸에 들어가는지(순수, DB 무관)."""
from __future__ import annotations
import io

from docx import Document

from app.services import workbook as wb


def _all_text(doc: Document) -> str:
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                parts.append(c.text)
    return "\n".join(parts)


def test_blank_workbook_has_hint_not_student_text():
    scn = {"title": "T", "description": "개요",
           "red_missions": [{"order": 1, "points": 10, "target_vm": "web", "instruction": "do X"}],
           "blue_missions": []}
    doc = wb.build_doc(scn)                      # prefill 없음 → 빈 칸(사전 배포본)
    text = _all_text(doc)
    assert "do X" in text                        # 미션 지시문은 렌더
    assert "붙여넣으세요" in text                  # 빈 칸 안내(hint)
    assert "통과" not in text                     # 채점 결과 없음


def test_filled_workbook_contains_student_input_and_grade():
    scn = {"title": "T", "description": "개요",
           "red_missions": [{"order": 1, "points": 10, "target_vm": "web", "instruction": "do X"}],
           "blue_missions": []}
    pf = {("red", 1): {
        "what_i_did": "nmap -sS 10.20.32.0/24", "what_happened": "5 hosts up",
        "description": "외부 정찰 분석", "grade_status": "graded", "verdict": "pass",
        "awarded_points": 9, "max_points": 10, "feedback": "근거 좋음",
        "criteria_met": ["생존 호스트 서술"], "criteria_missing": []}}
    doc = wb.build_doc(scn, prefill=pf)
    text = _all_text(doc)
    assert "nmap -sS 10.20.32.0/24" in text       # ▶ 실행 명령 칸 = what_i_did
    assert "5 hosts up" in text                    # ▶ 실행 결과 칸 = what_happened
    assert "외부 정찰 분석" in text                 # ▶ 설명/분석 칸 = description
    assert "통과" in text and "9/10" in text        # 채점 결과 블록
    assert "근거 좋음" in text


def test_prefill_from_submissions_latest_per_mission():
    class S:  # 가벼운 더미 — ORM 행 흉내
        def __init__(self, _id, side, order, cmd):
            self.id, self.mission_side, self.mission_order = _id, side, order
            self.what_i_did, self.what_happened, self.description = cmd, "", ""
            self.grade_status, self.verdict = "graded", "pass"
            self.awarded_points = self.max_points = None
            self.feedback = None; self.criteria_met = self.criteria_missing = []
    subs = [S(1, "red", 1, "first try"), S(2, "red", 1, "second try")]
    pf = wb.prefill_from_submissions(subs)
    assert pf[("red", 1)]["what_i_did"] == "second try"   # 최신(id 큰 것) 우선
