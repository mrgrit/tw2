#!/usr/bin/env python3
"""공방전 학생 워크북(.docx) 생성기 — YAML 시나리오 → **빈** 워크북 1개씩(사전 배포본).

렌더링은 apps/api/app/services/workbook.py 와 **단일 소스**를 공유한다. 학생 제출이 자동으로
채워진 워크북(사후 복습/제출본)은 API `GET /me/workbook/{scenario_id}` 로 받는다.

사용: .venv/bin/python scripts/gen_workbooks.py
출력: contents/battle-workbook/<id>.docx  (TUBEWAR_WORKBOOK_OUT 로 변경 가능)
"""
import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))
from app.services import workbook as wb  # noqa: E402
from app.services import infra_render  # noqa: E402

# 사전 배포 워크북은 배포 기준 IP(config.ref_*)로 플레이스홀더를 치환.
_REF_VARS = infra_render.build_vars(None, None)

SRC = os.path.join(ROOT, "contents", "battle-scenarios")
OUT = os.environ.get("TUBEWAR_WORKBOOK_OUT") or os.path.join(ROOT, "contents", "battle-workbook")


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC, "*.yaml")))
    n = 0
    for f in files:
        d = yaml.safe_load(open(f, encoding="utf-8"))
        if not isinstance(d, dict) or not (d.get("red_missions") or d.get("blue_missions")):
            continue
        sid = d.get("id") or os.path.splitext(os.path.basename(f))[0]
        d = infra_render.render(d, _REF_VARS)   # IP 플레이스홀더 → 기준 IP
        doc = wb.build_doc(d)          # prefill 없음 → 빈 워크북(사전 배포본)
        doc.save(os.path.join(OUT, f"{sid}.docx"))
        n += 1
        print(f"  ✓ {sid}.docx  (RED {len(d.get('red_missions') or [])} / BLUE {len(d.get('blue_missions') or [])})")
    print(f"\n총 {n}개 워크북 생성 → {OUT}")


if __name__ == "__main__":
    main()
