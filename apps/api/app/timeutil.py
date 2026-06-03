"""시각 표준화 — 저장은 UTC, **표시는 KST(Asia/Seoul, UTC+9)** 로 일관.

설계:
- 저장/전송 기준은 UTC aware (DB·계산의 단일 기준). `now()` 는 UTC aware.
- 사람이 보는 모든 시각은 KST 로 변환해 보여준다(`to_seoul`/`iso_kst`/`fmt_kst`).
- KST 는 1988 이후 **DST 가 없어 항상 UTC+9** 이므로 tzdata 의존 없이 고정 오프셋으로 안전하게
  표현한다(`timezone(timedelta(hours=9), "KST")`). 운영 타임존은 `TUBEWAR_TZ` 로 바꿀 수 있고,
  기본값 Asia/Seoul.
"""
from __future__ import annotations
import datetime as dt

# Asia/Seoul = UTC+9 (DST 없음). tzdata 없이도 정확.
SEOUL = dt.timezone(dt.timedelta(hours=9), "KST")
TZ_NAME = "Asia/Seoul"


def now() -> dt.datetime:
    """저장/계산 기준 — UTC aware."""
    return dt.datetime.now(dt.timezone.utc)


def _aware_utc(d: dt.datetime | None) -> dt.datetime | None:
    """naive(예: sqlite) → UTC 로 간주해 aware 화."""
    if d is None:
        return None
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d


def to_seoul(d: dt.datetime | None) -> dt.datetime | None:
    """임의 datetime → KST aware. naive 는 UTC 로 간주."""
    a = _aware_utc(d)
    return a.astimezone(SEOUL) if a else None


def iso_kst(d: dt.datetime | None) -> str | None:
    """ISO8601 + '+09:00' (예: 2026-06-03T19:12:07+09:00)."""
    s = to_seoul(d)
    return s.isoformat() if s else None


def fmt_kst(d: dt.datetime | None, *, with_seconds: bool = True) -> str:
    """사람용 KST 표기 (예: 2026-06-03 19:12:07 KST)."""
    s = to_seoul(d)
    if not s:
        return ""
    fmt = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    return s.strftime(fmt) + " KST"


def fmt_korean(d: dt.datetime | None) -> str:
    """오전/오후 H시 MM분 (KST). heartbeat 등 한국어 표시용."""
    s = to_seoul(d)
    if not s:
        return ""
    am = "오전" if s.hour < 12 else "오후"
    h12 = s.hour % 12 or 12
    return f"{am} {h12}시 {s.minute:02d}분"
