import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.ts'
import Markdown from '../components/Markdown.tsx'

// ── 관제 대시보드 — 교수(관리자)가 코호트 실습 현황을 한눈에 보고 학생별로 드릴다운.
//    데이터 소스(로컬 DB): /battles, /monitoring/battles/{id}/progress·activity, /feedback.
//    (중앙 OpenSearch SIEM 은 tw2 기본 OFF → 여기선 쓰지 않는다.)

interface BattleOut {
  id: number
  scenario_id: number | null
  cohort_id: number | null
  mode: string
  status: string
  scenario_title?: string | null
  cohort_name?: string | null
  started_at?: string | null
}
interface StudentProgress {
  user_id: number
  name: string | null
  completion: number
  steps_done: number
  steps_total: number
  bottleneck_flags: Record<string, unknown>
  stuck: boolean
  last_activity_ts?: string | null
}
interface CohortProgress {
  cohort_id: number | null
  battle_id: number | null
  steps_total: number
  students: StudentProgress[]
}
interface ActivityEvent {
  id: number
  kind: string
  scenario_step: number | null
  payload: Record<string, any>
  ts: string
}
interface Feedback {
  id: number
  scope: string
  trigger: string
  content_md: string
  created_at: string
}

const C = {
  ok: 'var(--green)', warn: 'var(--yellow)', bad: 'var(--red)', dim: 'var(--fg-dim)',
  border: 'var(--border)', bg2: 'var(--bg-2)', accent: 'var(--accent)', primary: 'var(--primary)',
}
function levelColor(pct: number): string {
  if (pct >= 100) return C.ok
  if (pct >= 50) return C.warn
  return C.bad
}
function fmt(ts?: string | null): string {
  if (!ts) return '-'
  try { return new Date(ts).toLocaleString('ko-KR', { hour12: false }) } catch { return ts }
}
function kindBadge(kind: string): { bg: string; label: string } {
  switch (kind) {
    case 'command': return { bg: '#1f6feb', label: 'CMD' }
    case 'alert': return { bg: 'var(--red)', label: 'ALERT' }
    case 'log': return { bg: '#8957e5', label: 'LOG' }
    case 'fim': return { bg: 'var(--yellow)', label: 'FIM' }
    default: return { bg: 'var(--fg-dim)', label: kind.toUpperCase() }
  }
}

// 완성도 링 (conic-gradient, 라이브러리 없이)
function Ring({ pct, size = 72 }: { pct: number; size?: number }) {
  const col = levelColor(pct)
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: `conic-gradient(${col} ${pct * 3.6}deg, var(--bg) 0deg)`,
      display: 'grid', placeItems: 'center', flexShrink: 0,
    }}>
      <div style={{
        width: size - 16, height: size - 16, borderRadius: '50%', background: C.bg2,
        display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: size * 0.24, color: col,
      }}>{Math.round(pct)}%</div>
    </div>
  )
}

export default function Monitor() {
  const [battles, setBattles] = useState<BattleOut[]>([])
  const [battleId, setBattleId] = useState<number | null>(null)
  const [prog, setProg] = useState<CohortProgress | null>(null)
  const [sel, setSel] = useState<number | null>(null)
  const [acts, setActs] = useState<ActivityEvent[]>([])
  const [fbs, setFbs] = useState<Feedback[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // 배틀 목록 → 기본값(진행중 우선)
  useEffect(() => {
    api<BattleOut[]>('/battles').then(list => {
      setBattles(list)
      const active = list.find(b => b.status === 'active') || list[0]
      if (active) setBattleId(active.id)
    }).catch(e => setErr(String(e.message || e)))
  }, [])

  // 배틀 선택 → 진도 로드
  useEffect(() => {
    if (battleId == null) return
    setLoading(true); setSel(null); setErr(null)
    api<CohortProgress>(`/monitoring/battles/${battleId}/progress`)
      .then(setProg)
      .catch(e => setErr(String(e.message || e)))
      .finally(() => setLoading(false))
  }, [battleId])

  // 학생 선택 → 활동·피드백
  useEffect(() => {
    if (battleId == null || sel == null) { setActs([]); setFbs([]); return }
    api<ActivityEvent[]>(`/monitoring/battles/${battleId}/activity?user_id=${sel}&limit=20`)
      .then(setActs).catch(() => setActs([]))
    api<Feedback[]>(`/feedback?user_id=${sel}`)
      .then(setFbs).catch(() => setFbs([]))
  }, [battleId, sel])

  const students = prog?.students || []
  const kpi = useMemo(() => {
    const n = students.length
    const avg = n ? Math.round(students.reduce((s, x) => s + x.completion, 0) / n) : 0
    const done = students.filter(x => x.completion >= 100).length
    const stuck = students.filter(x => x.stuck).length
    return { n, avg, done, stuck }
  }, [students])

  // 완성도 분포 버킷
  const buckets = useMemo(() => {
    const b = [
      { label: '0–25%', lo: 0, hi: 25, col: C.bad, n: 0 },
      { label: '26–50%', lo: 26, hi: 50, col: C.bad, n: 0 },
      { label: '51–75%', lo: 51, hi: 75, col: C.warn, n: 0 },
      { label: '76–99%', lo: 76, hi: 99, col: C.warn, n: 0 },
      { label: '100%', lo: 100, hi: 100, col: C.ok, n: 0 },
    ]
    for (const s of students) {
      const hit = b.find(x => s.completion >= x.lo && s.completion <= x.hi)
      if (hit) hit.n++
    }
    return b
  }, [students])

  const stuckRank = useMemo(
    () => students.filter(s => s.stuck).sort((a, b) => a.completion - b.completion), [students])
  const selStudent = students.find(s => s.user_id === sel) || null
  const curBattle = battles.find(b => b.id === battleId) || null

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>🛰️ 관제 대시보드</h1>
        <select value={battleId ?? ''} onChange={e => setBattleId(Number(e.target.value))}
          style={{ padding: '6px 10px', background: C.bg2, color: 'var(--fg)', border: `1px solid ${C.border}`, borderRadius: 6 }}>
          {battles.length === 0 && <option value="">배틀 없음</option>}
          {battles.map(b => (
            <option key={b.id} value={b.id}>
              #{b.id} · {b.cohort_name || '코호트-'} · {b.scenario_title?.slice(0, 30) || '시나리오-'} [{b.status}]
            </option>
          ))}
        </select>
      </div>

      {err && <div className="card" style={{ borderColor: C.bad, color: C.bad }}>⚠ {err}</div>}
      {curBattle && (
        <div style={{ color: C.dim, fontSize: 13, marginBottom: 12 }}>
          코호트 <b style={{ color: 'var(--fg)' }}>{curBattle.cohort_name}</b> · 시나리오 {curBattle.scenario_title} ·
          시작 {fmt(curBattle.started_at)} · steps {prog?.steps_total ?? '-'}
        </div>
      )}

      {/* KPI */}
      <div className="row" style={{ gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { k: '학생', v: kpi.n, col: C.primary },
          { k: '평균 완성도', v: `${kpi.avg}%`, col: levelColor(kpi.avg) },
          { k: '완주(100%)', v: kpi.done, col: C.ok },
          { k: '병목 학생', v: kpi.stuck, col: kpi.stuck ? C.bad : C.dim },
        ].map(x => (
          <div key={x.k} className="card" style={{ flex: 1, minWidth: 150, textAlign: 'center', padding: 16 }}>
            <div style={{ fontSize: 30, fontWeight: 800, color: x.col }}>{x.v}</div>
            <div style={{ color: C.dim, fontSize: 13 }}>{x.k}</div>
          </div>
        ))}
      </div>

      <div className="row" style={{ gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* 완성도 분포 */}
        <div className="card" style={{ flex: 1, minWidth: 260 }}>
          <h3 style={{ marginTop: 0 }}>완성도 분포</h3>
          {buckets.map(b => (
            <div key={b.label} style={{ marginBottom: 8 }}>
              <div className="row" style={{ justifyContent: 'space-between', fontSize: 12, color: C.dim }}>
                <span>{b.label}</span><span>{b.n}명</span>
              </div>
              <div style={{ background: 'var(--bg)', borderRadius: 4, height: 14, overflow: 'hidden' }}>
                <div style={{
                  width: `${kpi.n ? (b.n / kpi.n) * 100 : 0}%`, height: '100%',
                  background: b.col, transition: 'width .3s',
                }} />
              </div>
            </div>
          ))}
        </div>
        {/* 병목 랭킹 */}
        <div className="card" style={{ flex: 1, minWidth: 260 }}>
          <h3 style={{ marginTop: 0 }}>🚧 병목 랭킹</h3>
          {stuckRank.length === 0 && <div style={{ color: C.dim }}>병목 학생 없음 — 순항 중</div>}
          {stuckRank.map(s => (
            <div key={s.user_id} onClick={() => setSel(s.user_id)}
              className="row" style={{
                justifyContent: 'space-between', padding: '7px 8px', cursor: 'pointer',
                borderRadius: 6, borderBottom: `1px solid ${C.border}`,
              }}>
              <span>⚠ <b>{s.name}</b> <span style={{ color: C.dim, fontSize: 12 }}>{s.completion}%</span></span>
              <span style={{ display: 'flex', gap: 4 }}>
                {Object.keys(s.bottleneck_flags || {}).map(f => (
                  <span key={f} className="badge" style={{ background: C.bad, color: '#fff', fontSize: 11 }}>{f}</span>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>

      <h3 style={{ marginBottom: 8 }}>학생 현황 {loading && <span style={{ color: C.dim, fontSize: 13 }}>불러오는 중…</span>}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 12 }}>
        {students.map(s => (
          <div key={s.user_id} onClick={() => setSel(s.user_id)} className="card"
            style={{
              cursor: 'pointer', padding: 14,
              borderColor: sel === s.user_id ? C.accent : (s.stuck ? C.bad : C.border),
              boxShadow: sel === s.user_id ? `0 0 0 1px ${C.accent}` : undefined,
            }}>
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
              <Ring pct={s.completion} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{s.name || `학생 ${s.user_id}`}</div>
                <div style={{ color: C.dim, fontSize: 12 }}>미션 {s.steps_done}/{s.steps_total}</div>
                {s.stuck
                  ? <span className="badge" style={{ background: C.bad, color: '#fff', marginTop: 4 }}>병목</span>
                  : s.completion >= 100
                    ? <span className="badge" style={{ background: C.ok, color: '#04210f', marginTop: 4 }}>완주</span>
                    : <span className="badge" style={{ background: C.warn, color: '#221a02', marginTop: 4 }}>진행중</span>}
              </div>
            </div>
          </div>
        ))}
        {!loading && students.length === 0 && <div style={{ color: C.dim }}>학생 데이터 없음</div>}
      </div>

      {/* 드릴다운 */}
      {selStudent && (
        <div className="card" style={{ marginTop: 16, borderColor: C.accent }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ margin: 0 }}>👤 {selStudent.name} <span style={{ color: C.dim, fontSize: 14, fontWeight: 400 }}>· {selStudent.completion}% ({selStudent.steps_done}/{selStudent.steps_total})</span></h2>
            <button className="ghost" onClick={() => setSel(null)}>닫기 ✕</button>
          </div>
          {Object.keys(selStudent.bottleneck_flags || {}).length > 0 && (
            <div style={{ margin: '8px 0' }}>
              {Object.entries(selStudent.bottleneck_flags).map(([k, v]) => (
                <span key={k} className="badge" style={{ background: C.bad, color: '#fff', marginRight: 6 }}>{k}: {String(v)}</span>
              ))}
            </div>
          )}
          <div className="row" style={{ gap: 16, alignItems: 'flex-start', flexWrap: 'wrap', marginTop: 8 }}>
            {/* 피드백 */}
            <div style={{ flex: 1, minWidth: 280 }}>
              <h3 style={{ marginTop: 0 }}>📝 피드백 ({fbs.length})</h3>
              {fbs.length === 0 && <div style={{ color: C.dim }}>피드백 없음</div>}
              {fbs.map(f => (
                <div key={f.id} className="card" style={{ background: 'var(--bg)', marginBottom: 8 }}>
                  <div style={{ fontSize: 11, color: C.dim, marginBottom: 4 }}>
                    <span className="badge" style={{ background: f.trigger === 'bottleneck' ? C.bad : C.bg2, color: f.trigger === 'bottleneck' ? '#fff' : 'var(--fg)' }}>{f.trigger}</span>
                    {' '}{f.scope} · {fmt(f.created_at)}
                  </div>
                  <Markdown text={f.content_md} />
                </div>
              ))}
            </div>
            {/* 활동 타임라인 */}
            <div style={{ flex: 1, minWidth: 280 }}>
              <h3 style={{ marginTop: 0 }}>📡 활동 타임라인 (최근 {acts.length})</h3>
              <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                {acts.map(a => {
                  const kb = kindBadge(a.kind)
                  const txt = a.payload?.cmd || a.payload?.rule || a.payload?.line || a.payload?.path || JSON.stringify(a.payload).slice(0, 80)
                  const failed = a.kind === 'command' && (a.payload?.rc && a.payload.rc !== 0)
                  return (
                    <div key={a.id} className="row" style={{ gap: 8, padding: '5px 0', borderBottom: `1px solid ${C.border}`, alignItems: 'baseline' }}>
                      <span className="badge" style={{ background: kb.bg, color: '#fff', fontSize: 10, minWidth: 42, textAlign: 'center' }}>{kb.label}</span>
                      <span style={{ fontSize: 12, color: failed ? C.bad : 'var(--fg)', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
                        {failed ? '✗ ' : ''}{String(txt).slice(0, 100)}
                      </span>
                      <span style={{ fontSize: 10, color: C.dim, whiteSpace: 'nowrap' }}>{new Date(a.ts).toLocaleTimeString('ko-KR', { hour12: false })}</span>
                    </div>
                  )
                })}
                {acts.length === 0 && <div style={{ color: C.dim }}>활동 없음</div>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
