"""training 콘텐츠 서빙 — 강의(lecture_weekNN.md) + 실습(lab_weekNN.yaml).

DB 없이 `contents/training/<track>/` 파일을 읽어 제공한다(시나리오 카탈로그와 동일 발상).
공방전(battle)은 RED/BLUE 적대 채점, training 은 단계별 가이드 실습/강의 — 별개 메뉴.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, status

from ..models import User
from ..security import get_current_user

router = APIRouter(prefix="/training", tags=["training"])

_ROOT = Path(__file__).resolve().parents[4] / "contents" / "training"
_SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")  # 경로 traversal 방지(트랙명)

# 트랙 표시명(공방전과 동일 매핑 재사용 + training 전용)
TRACK_LABEL = {
    "secuops": "보안운영", "secuops-easy": "보안운영 입문", "soc": "SOC 관제",
    "soc-adv": "SOC 관제 심화", "attack": "공격기법", "attack-adv": "공격기법 심화",
    "web-vuln": "웹 취약점", "cloud-container": "클라우드·컨테이너", "compliance": "컴플라이언스",
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
                weeks.append({
                    "week": w,
                    "lecture": (d / f"lecture_week{w:02d}.md").exists(),
                    "lab": (d / f"lab_week{w:02d}.yaml").exists(),
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
