"""CCC `contents/education/courseN/weekM/lecture.md` 컨텍스트 로더.

tubewar 는 CCC 와 별개 repo. 본 모듈은 환경변수 `CCC_CONTENT_ROOT`
(default `/home/opsclaw/ccc/contents`) 를 우선 참조해 lecture.md 를 읽는다.
운영 환경에서는 CCC content snapshot 을 별도 path 로 mount 권장.
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_ROOT = "/home/opsclaw/ccc/contents"


def _root() -> Path:
    return Path(os.environ.get("CCC_CONTENT_ROOT", DEFAULT_ROOT))


def find_course_dir(course_ref: str) -> Path | None:
    """e.g. 'course3' 또는 'course3-web-vuln' 또는 'course3 / web-vuln'."""
    norm = course_ref.strip().split()[0].split("/")[0].split("-")[0].lower()
    root = _root() / "education"
    if not root.exists():
        return None
    for child in root.iterdir():
        if child.is_dir() and child.name.lower().startswith(norm):
            return child
    return None


def parse_week_range(spec: str) -> list[int]:
    """'1-3' / '1,3,5' / '5' / 'week01..week03' → [1,2,3] 등."""
    s = spec.lower().replace("week", "").replace("주차", "").replace(" ", "")
    out: set[int] = set()
    for tok in re.split(r"[,/]", s):
        if "-" in tok or ".." in tok:
            tok = tok.replace("..", "-")
            a, b = tok.split("-", 1)
            try:
                out.update(range(int(a), int(b) + 1))
            except ValueError:
                continue
        else:
            try:
                out.add(int(tok))
            except ValueError:
                continue
    return sorted(out)


def load_lectures(course_ref: str, weeks: list[int], max_chars_per_week: int = 6000) -> list[dict]:
    """주차별 lecture.md 발췌. 너무 길면 max_chars_per_week 자르고 표시.

    반환: [{course, week, title, body, truncated}]
    """
    course_dir = find_course_dir(course_ref)
    if not course_dir:
        log.warning("course not found for ref=%r (root=%s)", course_ref, _root())
        return []
    docs: list[dict] = []
    for w in weeks:
        wname = f"week{w:02d}"
        path = course_dir / wname / "lecture.md"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning("failed to read %s: %s", path, e)
            continue
        title = ""
        m = re.match(r"#\s+(.*)", text)
        if m:
            title = m.group(1).strip()
        truncated = False
        if len(text) > max_chars_per_week:
            text = text[:max_chars_per_week]
            truncated = True
        docs.append({
            "course": course_dir.name,
            "week": w,
            "title": title,
            "body": text,
            "truncated": truncated,
        })
    return docs


def build_context_block(course_ref: str, weeks: list[int], max_chars_total: int = 24000) -> str:
    """LLM 프롬프트에 첨부할 컨텍스트 텍스트. 총 길이 cap."""
    docs = load_lectures(course_ref, weeks)
    if not docs:
        return f"(no lecture content found for course={course_ref!r}, weeks={weeks})"

    chunks: list[str] = []
    total = 0
    for d in docs:
        block = f"\n--- {d['course']} / week{d['week']:02d} ({d['title']}) ---\n{d['body']}"
        if d["truncated"]:
            block += "\n[...truncated...]"
        if total + len(block) > max_chars_total:
            block = block[: max_chars_total - total] + "\n[...truncated to fit context budget...]"
            chunks.append(block)
            break
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks)
