import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { getToken } from '../auth.ts'
import Markdown from '../components/Markdown.tsx'

interface WeekInfo { week: number; lecture: boolean; lab: boolean }
interface TrackInfo { track: string; label: string; weeks: WeekInfo[] }
interface LabStep {
  order: number; instruction?: string
  answer?: string; answer_detail?: string; expected_output?: string; hint?: string
  [k: string]: unknown
}
interface Lab { lab_id?: string; title?: string; description?: string; objectives?: string[]; steps?: LabStep[] }

const cardStyle: React.CSSProperties = {
  textAlign: 'left', padding: '12px 14px', background: 'var(--bg-2)',
  border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer', color: 'var(--fg)',
}
// 따라하기 표시용 스타일
const accessBanner: React.CSSProperties = {
  background: 'rgba(130,170,255,0.10)', border: '1px solid var(--border)', borderRadius: 8,
  padding: '8px 12px', margin: '6px 0 14px', fontSize: 13.5, color: 'var(--fg)', lineHeight: 1.6,
}
const expBox: React.CSSProperties = {
  background: 'rgba(63,185,80,0.08)', border: '1px solid rgba(63,185,80,0.35)',
  borderRadius: 8, padding: '8px 12px', margin: '10px 0',
}
const expLabel: React.CSSProperties = { fontWeight: 700, fontSize: 13.5, color: '#3fb950', marginBottom: 4 }
const preMini: React.CSSProperties = {
  whiteSpace: 'pre', overflowX: 'auto', background: 'rgba(0,0,0,0.30)', padding: '8px 10px',
  borderRadius: 6, fontSize: 12.5, lineHeight: 1.5, margin: 0,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
}
const hintLine: React.CSSProperties = { fontSize: 13, color: 'var(--fg-dim)', margin: '8px 0 2px' }
const stepNum: React.CSSProperties = { fontSize: 12, color: 'var(--fg-dim)', fontWeight: 700, marginBottom: 2 }
const w2 = (n: number): string => String(n).padStart(2, '0')

export default function Training(): React.ReactElement {
  const [tracks, setTracks] = useState<TrackInfo[]>([])
  const [track, setTrack] = useState<TrackInfo | null>(null)
  const [week, setWeek] = useState<number | null>(null)
  const [tab, setTab] = useState<'lecture' | 'lab'>('lecture')
  const [lecture, setLecture] = useState('')
  const [lab, setLab] = useState<Lab | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      setLoading(true); setErr('')
      try { setTracks(await api<TrackInfo[]>('/training')) }
      catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
      finally { setLoading(false) }
    })()
  }, [])

  const [dlBusy, setDlBusy] = useState(false)
  async function downloadLabWorkbook(): Promise<void> {
    if (!track || week == null) return
    setDlBusy(true)
    try {
      const token = getToken()
      const res = await fetch(`/training/${track.track}/lab/${week}/workbook`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, cache: 'no-store',
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${track.track}-w${w2(week)}-lab.docx`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(`워크북 다운로드 실패: ${e instanceof Error ? e.message : String(e)}`) }
    finally { setDlBusy(false) }
  }

  async function openWeek(t: TrackInfo, w: WeekInfo): Promise<void> {
    setWeek(w.week); setTab(w.lecture ? 'lecture' : 'lab'); setLecture(''); setLab(null); setErr('')
    try {
      if (w.lecture) setLecture((await api<{ markdown: string }>(`/training/${t.track}/lecture/${w.week}`)).markdown)
      if (w.lab) setLab(await api<Lab>(`/training/${t.track}/lab/${w.week}`))
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }

  // ── 주차 상세 (강의/실습) ──
  if (track && week != null) {
    return (
      <>
        <button onClick={() => { setWeek(null); setLab(null); setLecture('') }} style={{ marginBottom: 12 }}>← {track.label} 주차 목록</button>
        <h1 style={{ color: 'var(--primary)' }}>{track.label} — Week {w2(week)}</h1>
        <div className="row" style={{ gap: 8, marginBottom: 12 }}>
          {lecture && <button onClick={() => setTab('lecture')} style={{ fontWeight: tab === 'lecture' ? 700 : 400 }}>📖 강의</button>}
          {lab && <button onClick={() => setTab('lab')} style={{ fontWeight: tab === 'lab' ? 700 : 400 }}>🧪 실습</button>}
        </div>
        {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}
        {tab === 'lecture' && lecture && <div className="card"><Markdown text={lecture} /></div>}
        {tab === 'lab' && lab && (
          <div className="card">
            <div className="row" style={{ alignItems: 'center', gap: 10 }}>
              <h2 style={{ marginTop: 0, flex: 1 }}>{lab.title}</h2>
              <button onClick={() => void downloadLabWorkbook()} disabled={dlBusy}>
                {dlBusy ? '내려받는 중…' : '📄 워크북(docx)'}
              </button>
            </div>
            <div style={accessBanner}>
              💻 모든 명령은 el34 호스트에서: <code>ssh ccc@192.168.0.151</code> (비밀번호 <code>1</code>) → <code>docker exec …</code>.
              아래 명령 블록은 우상단 <b>복사</b> 버튼으로 그대로 붙여넣어 실행하고, <b>✅ 이렇게 나오면 정상</b>과 비교하세요.
            </div>
            {lab.description && <Markdown text={lab.description} />}
            {lab.objectives && lab.objectives.length > 0 && (
              <>
                <h4>학습 목표</h4>
                <ul>{lab.objectives.map((o, i) => <li key={i}>{o}</li>)}</ul>
              </>
            )}
            {(lab.steps || []).map((s, i) => (
              <div key={i} style={{ borderTop: '2px solid var(--border)', paddingTop: 12, marginTop: 16 }}>
                <div style={stepNum}>STEP {s.order ?? i + 1} / {(lab.steps || []).length}</div>
                <Markdown text={s.instruction || `(step ${s.order})`} />
                {typeof s.expected_output === 'string' && s.expected_output.trim() !== '' && (
                  <div style={expBox}>
                    <div style={expLabel}>✅ 이렇게 나오면 정상 <span style={{ fontWeight: 400, color: 'var(--fg-dim)' }}>(숫자·시간은 환경마다 다름)</span></div>
                    <pre style={preMini}><code>{s.expected_output}</code></pre>
                  </div>
                )}
                {typeof s.answer_detail === 'string' && s.answer_detail.trim() !== '' && (
                  <details style={{ margin: '8px 0' }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13.5, color: 'var(--primary)' }}>💡 결과 해석 (펼치기)</summary>
                    <div style={{ marginTop: 4 }}><Markdown text={s.answer_detail} /></div>
                  </details>
                )}
                {typeof s.hint === 'string' && s.hint.trim() !== '' && (
                  <div style={hintLine}>🆘 막히면 — 핵심 명령: <code>{s.hint}</code></div>
                )}
              </div>
            ))}
          </div>
        )}
      </>
    )
  }

  // ── 트랙의 주차 목록 ──
  if (track) {
    return (
      <>
        <button onClick={() => setTrack(null)} style={{ marginBottom: 12 }}>← 트랙 목록</button>
        <h1 style={{ color: 'var(--primary)' }}>{track.label} <span style={{ fontSize: 14, color: 'var(--fg-dim)' }}>({track.track})</span></h1>
        <div className="row" style={{ flexWrap: 'wrap', gap: 10 }}>
          {track.weeks.map(w => (
            <button key={w.week} onClick={() => void openWeek(track, w)} style={{ ...cardStyle, minWidth: 150 }}>
              <div style={{ fontWeight: 700 }}>Week {w2(w.week)}</div>
              <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
                {w.lecture ? '📖 강의 ' : ''}{w.lab ? '🧪 실습' : ''}
              </div>
            </button>
          ))}
        </div>
      </>
    )
  }

  // ── 트랙 목록 ──
  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>Training</h1>
      <p style={{ color: 'var(--fg-dim)' }}>강의(이론) + 실습(lab) 트레이닝 콘텐츠. el34 인프라 기반.</p>
      {loading && <div>로딩...</div>}
      {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}
      {!loading && tracks.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>아직 등록된 트레이닝 콘텐츠가 없습니다.</div>}
      <div className="row" style={{ flexWrap: 'wrap', gap: 12, marginTop: 16 }}>
        {tracks.map(t => (
          <button key={t.track} onClick={() => setTrack(t)} style={{ ...cardStyle, minWidth: 200 }}>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{t.label}</div>
            <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 6 }}>{t.weeks.length}개 주차 · {t.track}</div>
          </button>
        ))}
      </div>
    </>
  )
}
