"""training 콘텐츠 서빙 — 강의(lecture_weekNN.md) + 실습(lab_weekNN.yaml).

DB 없이 `contents/training/<track>/` 파일을 읽어 제공한다(시나리오 카탈로그와 동일 발상).
공방전(battle)은 RED/BLUE 적대 채점, training 은 단계별 가이드 실습/강의 — 별개 메뉴.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..models import User
from ..security import get_current_user
from ..services import workbook as wb

router = APIRouter(prefix="/training", tags=["training"])
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_ROOT = Path(__file__).resolve().parents[4] / "contents" / "training"
_SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")  # 경로 traversal 방지(트랙명)

# 트랙 표시명(공방전과 동일 매핑 재사용 + training 전용)
TRACK_LABEL = {
    "secuops": "보안운영", "secuops-easy": "보안운영 입문", "soc": "SOC 관제",
    "soc-adv": "SOC 관제 심화", "attack": "공격기법", "attack-adv": "공격기법 심화",
    "web-vuln": "웹 취약점", "cloud-container": "클라우드·컨테이너", "compliance": "컴플라이언스",
    "wazuh-special": "Wazuh 특강",
    "ai-agent": "AI 에이전트", "ai-safety": "AI 안전(레드팀)", "ai-safety-adv": "AI 안전 심화",
    "ai-security": "AI 시스템 보안", "aisec": "AI 보안 종합",
    "agent-ir": "AI 에이전트 사고대응", "agent-ir-adv": "AI 에이전트 사고대응 심화",
}


def _track_dir(track: str) -> Path:
    if not _SAFE.match(track):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid track")
    return _ROOT / track


def _weeks(d: Path) -> list[int]:
    ws: set[int] = set()
    for pat in ("lecture_week*.md", "lab_week*.yaml"):
        for p in d.glob(pat):
            m = re.search(r"week(\d+)", p.name)
            if m:
                ws.add(int(m.group(1)))
    return sorted(ws)


# 주차 제목 앞의 "Week 01 —" / "W01 —" / "W01:" 접두 제거용
_WEEK_PREFIX = re.compile(r"^(특강\s*)?(week\s*\d+|w\d+)\s*[—:．.\-]+\s*", re.IGNORECASE)
# "(본 주차의) 한 줄 요약" 라벨 제거용
_SUMMARY_LABEL = re.compile(r"^.*?한\s*줄\s*요약\**\s*[—:\-]?\s*")


def _md_title_summary(path: Path) -> tuple[str, str]:
    """강의 .md 에서 제목(첫 # 헤딩, 주차접두 제거)과 한 줄 요약(첫 인용블록)을 추출."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", ""
    title, start = "", 0
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# "):
            title = _WEEK_PREFIX.sub("", s[2:].strip()).strip()
            start = idx + 1
            break
    buf: list[str] = []
    started = False
    for ln in lines[start:]:
        s = ln.strip()
        if s.startswith(">"):
            started = True
            c = s.lstrip(">").strip()
            if c:
                buf.append(c)
        elif started:
            break
    summary = _SUMMARY_LABEL.sub("", " ".join(buf)).replace("**", "").strip()
    return title, summary


def _week_meta(d: Path, w: int) -> tuple[str, str]:
    """주차의 제목 + 요약. 강의 우선, 없으면 실습 yaml(title/description) 폴백."""
    lec = d / f"lecture_week{w:02d}.md"
    title, summary = _md_title_summary(lec) if lec.exists() else ("", "")
    if (not title or not summary):
        lab = d / f"lab_week{w:02d}.yaml"
        if lab.exists():
            try:
                y = yaml.safe_load(lab.read_text(encoding="utf-8")) or {}
                title = title or _WEEK_PREFIX.sub("", str(y.get("title", "")).strip()).strip()
                summary = summary or " ".join(str(y.get("description", "")).split())
            except (yaml.YAMLError, OSError):
                pass
    return title, summary[:180]


@router.get("")
async def list_training(user: User = Depends(get_current_user)):
    """트랙별 보유 주차 목록 + 각 주차의 강의/실습 존재 여부."""
    out = []
    if _ROOT.exists():
        for d in sorted(_ROOT.iterdir()):
            if not d.is_dir() or not _SAFE.match(d.name):
                continue
            weeks = []
            for w in _weeks(d):
                title, summary = _week_meta(d, w)
                weeks.append({
                    "week": w,
                    "lecture": (d / f"lecture_week{w:02d}.md").exists(),
                    "lab": (d / f"lab_week{w:02d}.yaml").exists(),
                    "title": title,
                    "summary": summary,
                })
            if weeks:
                out.append({"track": d.name, "label": TRACK_LABEL.get(d.name, d.name), "weeks": weeks})
    return out


@router.get("/{track}/lecture/{week}")
async def get_lecture(track: str, week: int, user: User = Depends(get_current_user)):
    p = _track_dir(track) / f"lecture_week{week:02d}.md"
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lecture not found")
    return {"track": track, "week": week, "markdown": p.read_text(encoding="utf-8")}


@router.get("/{track}/lab/{week}")
async def get_lab(track: str, week: int, user: User = Depends(get_current_user)):
    p = _track_dir(track) / f"lab_week{week:02d}.yaml"
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lab not found")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"lab yaml parse error: {e}")


@router.get("/{track}/lab/{week}/workbook")
async def get_lab_workbook(track: str, week: int, user: User = Depends(get_current_user)):
    """실습(lab)을 학생 워크북(.docx)으로 — step 별 미션 + 붙여넣기 3칸(명령/결과/분석)."""
    p = _track_dir(track) / f"lab_week{week:02d}.yaml"
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lab not found")
    try:
        lab = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"lab yaml parse error: {e}")
    doc = wb.build_lab_doc(lab, track_label=TRACK_LABEL.get(track, track), week=week)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{track}-w{week:02d}-lab.docx"'})
