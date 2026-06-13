import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { getToken } from '../auth.ts'

// 백엔드 StudentSubmissionOut 와 1:1
interface Submission {
  id: number
  scenario_id: number | null
  battle_id: number | null
  mission_side: 'red' | 'blue' | null
  mission_order: number | null
  what_i_did: string
  what_happened: string
  description: string
  claimed_points: number
  mission_snapshot: { title?: string; instruction?: string; points?: number } | null
  grade_status: 'pending' | 'graded' | 'failed'
  verdict: string | null
  awarded_points: number | null
  max_points: number | null
  feedback: string | null
  criteria_met: string[]
  criteria_missing: string[]
  submitted_at: string
  graded_at: string | null
}

const VERDICT_KO: Record<string, string> = {
  pass: '통과', partial: '부분', fail: '미통과', review: '검토대기',
}

function StatusBadge({ s }: { s: Submission }) {
  if (s.grade_status === 'pending')
    return <span style={{ ...badge, background: '#fff7e6', color: '#ad6800' }}>⏳ 채점 중</span>
  if (s.grade_status === 'failed')
    return <span style={{ ...badge, background: '#fff1f0', color: '#cf1322' }}>⚠ 채점 보류(강사 검토)</span>
  const v = s.verdict || 'review'
  const tone: Record<string, [string, string]> = {
    pass: ['#f6ffed', '#237804'], partial: ['#feffe6', '#7c8500'],
    fail: ['#fff1f0', '#cf1322'], review: ['#f0f5ff', '#1d39c4'],
  }
  const [bg, fg] = tone[v] || tone.review
  return (
    <span style={{ ...badge, background: bg, color: fg }}>
      {VERDICT_KO[v] || v}{s.awarded_points != null ? ` · ${s.awarded_points}/${s.max_points ?? '-'}점` : ''}
    </span>
  )
}

const badge: React.CSSProperties = {
  fontSize: 12, padding: '1px 8px', borderRadius: 10, fontWeight: 600, whiteSpace: 'nowrap',
}

export default function MyWork() {
  const [subs, setSubs] = useState<Submission[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)

  async function load() {
    setErr(null)
    try {
      setSubs(await api<Submission[]>('/me/submissions'))
    } catch (e: any) { setErr(e.message) }
  }
  useEffect(() => { load() }, [])

  async function downloadWorkbook(scenarioId: number) {
    setDownloading(scenarioId)
    try {
      const token = getToken()
      const res = await fetch(`/me/workbook/${scenarioId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, cache: 'no-store',
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `workbook-${scenarioId}.docx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) { setErr(`워크북 다운로드 실패: ${e.message}`) }
    finally { setDownloading(null) }
  }

  if (subs === null && !err) return <div className="card">불러오는 중…</div>

  // 시나리오별 그룹 (scenario_id, 최신 제출이 위로 정렬된 상태로 옴)
  const groups = new Map<number, Submission[]>()
  for (const s of subs || []) {
    const k = s.scenario_id ?? -1
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(s)
  }

  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <h2 style={{ margin: 0 }}>내 워크북 · 복습</h2>
        <span style={{ color: 'var(--fg-dim)', fontSize: 13 }}>
          내가 제출한 명령·결과·분석과 AI 채점을 시나리오별로 — 명령을 다시 내리지 않고 복습.
        </span>
        <button className="ghost" style={{ marginLeft: 'auto' }} onClick={load}>새로고침</button>
      </div>

      {err && <div className="card" style={{ color: '#cf1322' }}>{err}</div>}
      {subs && subs.length === 0 && (
        <div className="card">아직 제출한 기록이 없어요. 공방전에서 미션을 제출하면 여기에 쌓입니다.</div>
      )}

      {[...groups.entries()].map(([sid, list]) => {
        const title = list.find(x => x.mission_snapshot?.title)?.mission_snapshot?.title
        const pending = list.filter(x => x.grade_status === 'pending').length
        return (
          <div key={sid} className="card col" style={{ gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 15 }}>{title || (sid < 0 ? '(시나리오 없음)' : `시나리오 #${sid}`)}</strong>
              <span style={{ color: 'var(--fg-dim)', fontSize: 12 }}>제출 {list.length}건</span>
              {pending > 0 && <span style={{ ...badge, background: '#fff7e6', color: '#ad6800' }}>채점 중 {pending}</span>}
              {sid >= 0 && (
                <button style={{ marginLeft: 'auto' }} disabled={downloading === sid}
                  onClick={() => downloadWorkbook(sid)}>
                  {downloading === sid ? '내려받는 중…' : '📄 워크북(docx) 다운로드'}
                </button>
              )}
            </div>

            {list.map(s => (
              <div key={s.id} style={{ borderTop: '1px solid var(--border, #eee)', paddingTop: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600, color: s.mission_side === 'red' ? '#c0392b' : '#1f4ea0' }}>
                    {s.mission_side ? s.mission_side.toUpperCase() : '기타'}{s.mission_order ? ` #${s.mission_order}` : ''}
                  </span>
                  <StatusBadge s={s} />
                  <span style={{ color: 'var(--fg-dim)', fontSize: 12, marginLeft: 'auto' }}>
                    {new Date(s.submitted_at).toLocaleString()}
                  </span>
                </div>
                {s.what_i_did && <Field label="실행 명령/페이로드" value={s.what_i_did} mono />}
                {s.what_happened && <Field label="실행 결과" value={s.what_happened} mono />}
                {s.description && <Field label="설명/분석" value={s.description} />}
                {s.grade_status === 'graded' && s.feedback && (
                  <Field label="AI 피드백" value={s.feedback} />
                )}
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>{label}</div>
      <div style={{
        whiteSpace: 'pre-wrap', fontSize: 13,
        fontFamily: mono ? 'monospace' : 'inherit',
        background: mono ? 'var(--code-bg, #f6f8fa)' : 'transparent',
        padding: mono ? '6px 8px' : 0, borderRadius: mono ? 6 : 0,
      }}>{value}</div>
    </div>
  )
}
