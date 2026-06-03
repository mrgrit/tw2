// 모든 타임스탬프를 KST(Asia/Seoul, UTC+9) 로 표시. 브라우저 로컬 타임존과 무관.
// API 가 offset 없는 ISO(예: sqlite naive)를 주면 UTC 로 간주한다.

function parseUTC(iso: string): Date {
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  return new Date(hasTz ? iso : iso + 'Z')
}

export function fmtTime(iso?: string | null, withSeconds = false): string {
  if (!iso) return '—'
  const d = parseUTC(iso)
  if (isNaN(d.getTime())) return String(iso)
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }
  if (withSeconds) opts.second = '2-digit'
  return d.toLocaleString('ko-KR', opts) + ' KST'
}
