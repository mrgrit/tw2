import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.ts'
import { getToken, getUser } from '../auth.ts'

interface Scenario {
  id: number
  title: string
  description: string
  source: string
  status: string
  time_limit_sec: number
}

interface Participant {
  id: number
  user_id: number
  infra_id: number | null
  role: string
  score: number
}

interface BattleEvent {
  id: number
  ts: string
  actor_user_id: number | null
  event_type: string
  target: string
  description: string
  detail: any
  points: number
}

interface BattleSummary {
  id: number
  scenario_id: number | null
  mode: string
  status: string
  monitor: string
  started_at: string | null
  ended_at: string | null
  time_limit_sec: number
  created_at: string
}

interface BattleDetail {
  battle: BattleSummary
  scenario_title: string | null
  participants: Participant[]
  events: BattleEvent[]
  elapsed_sec: number
  remaining_sec: number
}

const eventTypePalette: Record<string, string> = {
  attack: 'red', exploit: 'red',
  defend: 'green', detect: 'green', block: 'green',
  alert: 'yellow', score: 'blue', system: 'blue',
}

export default function Battle() {
  const user = getUser()!
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [battles, setBattles] = useState<BattleSummary[]>([])
  const [activeBattle, setActiveBattle] = useState<BattleDetail | null>(null)
  const [myInfraId, setMyInfraId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // 시나리오/배틀 목록 + 내 인프라 ID 로드
  async function refresh() {
    try {
      const [scns, bts, infras] = await Promise.all([
        api<Scenario[]>('/scenarios'),
        api<BattleSummary[]>('/battles'),
        api<any[]>('/infras'),
      ])
      setScenarios(scns)
      setBattles(bts)
      setMyInfraId(infras[0]?.id ?? null)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { refresh() }, [])

  async function loadBattle(id: number) {
    setErr(null)
    try {
      const b = await api<BattleDetail>(`/battles/${id}`)
      setActiveBattle(b)
    } catch (e: any) { setErr(e.message) }
  }

  async function createSolo(scenarioId: number) {
    if (!myInfraId) {
      setErr('먼저 /myinfra 에서 6v6 인프라를 등록하세요.')
      return
    }
    try {
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: scenarioId,
          mode: 'solo',
          monitor: 'bastion',
          participants: [{ user_id: user.id, role: 'solo', infra_id: myInfraId }],
        },
      })
      setActiveBattle(b)
      await refresh()
    } catch (e: any) { setErr(e.message) }
  }

  async function startBattle() {
    if (!activeBattle) return
    try {
      const b = await api<BattleDetail>(`/battles/${activeBattle.battle.id}/start`, { method: 'POST' })
      setActiveBattle(b)
    } catch (e: any) { setErr(e.message) }
  }

  async function endBattle() {
    if (!activeBattle) return
    try {
      const b = await api<BattleDetail>(`/battles/${activeBattle.battle.id}/end`, { method: 'POST' })
      setActiveBattle(b)
    } catch (e: any) { setErr(e.message) }
  }

  // SSE 라이브 스트림
  useEffect(() => {
    if (!activeBattle || activeBattle.battle.status !== 'active') return
    const id = activeBattle.battle.id
    // EventSource 는 헤더 못 붙이므로 token query string. 백엔드에서 query token 지원은 별도 — 일단 폴링 fallback.
    let cancelled = false
    const tick = async () => {
      while (!cancelled) {
        await new Promise(r => setTimeout(r, 1500))
        if (cancelled) break
        try {
          const b = await api<BattleDetail>(`/battles/${id}`)
          setActiveBattle(b)
          if (b.battle.status !== 'active') break
        } catch { break }
      }
    }
    tick()
    return () => { cancelled = true }
  }, [activeBattle?.battle.id, activeBattle?.battle.status])

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>공방전</h1>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}

      {!activeBattle && (
        <>
          <h3>시나리오 카탈로그</h3>
          {loading && <div className="card">로딩 중...</div>}
          {!loading && scenarios.length === 0 && (
            <div className="card" style={{ color: 'var(--fg-dim)' }}>
              아직 시나리오 없음. API 가 처음 시작될 때 contents/battle-scenarios/ 를 자동 import 합니다.
            </div>
          )}
          {scenarios.map(s => (
            <div key={s.id} className="card">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <b>{s.title}</b> <span className="badge blue">{s.source}</span>
                  <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginTop: 4 }}>
                    {s.description.length > 200 ? s.description.slice(0, 200) + '…' : s.description}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
                    제한 {Math.round(s.time_limit_sec / 60)}분 · status: {s.status}
                  </div>
                </div>
                <button onClick={() => createSolo(s.id)} disabled={!myInfraId}>
                  solo 시작
                </button>
              </div>
            </div>
          ))}

          <h3 style={{ marginTop: 32 }}>내 최근 공방전</h3>
          {battles.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
          {battles.map(b => (
            <div key={b.id} className="card">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <b>#{b.id}</b> · {b.mode} · monitor: {b.monitor}
                </div>
                <span className={`badge ${b.status === 'active' ? 'green' : b.status === 'completed' ? 'blue' : 'yellow'}`}>
                  {b.status}
                </span>
                <button className="ghost" onClick={() => loadBattle(b.id)}>열기</button>
              </div>
            </div>
          ))}
        </>
      )}

      {activeBattle && <BattleView b={activeBattle} onClose={() => { setActiveBattle(null); refresh() }}
        onStart={startBattle} onEnd={endBattle} onRefresh={() => loadBattle(activeBattle.battle.id)} />}
    </>
  )
}

function EventRow({ e }: { e: BattleEvent }) {
  const [open, setOpen] = useState(false)
  const hasDetail = e.detail && Object.keys(e.detail).length > 0
  return (
    <div className="card" style={{ padding: 12 }}>
      <div className="row" style={{ alignItems: 'center', fontSize: 13 }}>
        <span className={`badge ${eventTypePalette[e.event_type] || 'yellow'}`}>{e.event_type}</span>
        <span style={{ color: 'var(--fg-dim)' }}>{new Date(e.ts).toLocaleTimeString()}</span>
        {e.target && <span style={{ color: 'var(--fg-dim)' }}>target: <code>{e.target}</code></span>}
        {e.actor_user_id && <span style={{ color: 'var(--fg-dim)' }}>by user #{e.actor_user_id}</span>}
        {e.points !== 0 && <span className={`badge ${e.points > 0 ? 'green' : 'red'}`}>
          {e.points > 0 ? '+' : ''}{e.points}
        </span>}
        <div style={{ flex: 1 }} />
        {hasDetail && (
          <button className="ghost" style={{ padding: '2px 8px', fontSize: 12 }}
            onClick={() => setOpen(o => !o)}>
            {open ? '채점 근거 ▲' : '채점 근거 ▼'}
          </button>
        )}
      </div>
      {e.description && <div style={{ marginTop: 4 }}>{e.description}</div>}
      {open && hasDetail && (
        <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,255,255,0.04)',
                      borderRadius: 6, fontSize: 12 }}>
          {(e.detail.source === 'auto_monitor') && (
            <div style={{ color: 'var(--green)', marginBottom: 6 }}>
              자동 모니터: probe 응답이 blue 미션 #{e.detail.blue_mission_order} 의
              expect <code>{String(e.detail.matched_expect)}</code> 와 일치
            </div>
          )}
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(e.detail, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function BattleView({
  b, onClose, onStart, onEnd, onRefresh,
}: {
  b: BattleDetail
  onClose: () => void
  onStart: () => void
  onEnd: () => void
  onRefresh: () => void
}) {
  const [eventForm, setEventForm] = useState({
    event_type: 'attack', target: '', description: '', points: 0,
  })

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    await api(`/battles/${b.battle.id}/events`, { method: 'POST', json: eventForm })
    setEventForm({ ...eventForm, description: '' })
    onRefresh()
  }

  const sortedParts = [...b.participants].sort((a, b) => b.score - a.score)

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 16 }}>
        <button className="ghost" onClick={onClose}>← 목록</button>
        <h2 style={{ margin: 0, flex: 1 }}>
          #{b.battle.id} · {b.scenario_title || '(no scenario)'}
        </h2>
        <span className={`badge ${b.battle.status === 'active' ? 'green' : 'blue'}`}>{b.battle.status}</span>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>모드</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{b.battle.mode}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>경과</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{Math.round(b.elapsed_sec)}s</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>잔여</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{Math.round(b.remaining_sec)}s</div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>스코어보드</h3>
        <table style={{ width: '100%', fontSize: 14, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--fg-dim)' }}>
              <th align="left" style={{ padding: '8px 4px' }}>역할</th>
              <th align="left" style={{ padding: '8px 4px' }}>user</th>
              <th align="left" style={{ padding: '8px 4px' }}>infra</th>
              <th align="right" style={{ padding: '8px 4px' }}>점수</th>
            </tr>
          </thead>
          <tbody>
            {sortedParts.map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '8px 4px' }}>
                  <span className={`badge ${p.role === 'red' ? 'red' : p.role === 'blue' ? 'blue' : 'yellow'}`}>{p.role}</span>
                </td>
                <td style={{ padding: '8px 4px' }}>#{p.user_id}</td>
                <td style={{ padding: '8px 4px' }}>{p.infra_id ?? '—'}</td>
                <td style={{ padding: '8px 4px', fontWeight: 700, textAlign: 'right' }}>{p.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        {b.battle.status === 'pending' && <button onClick={onStart}>시작</button>}
        {b.battle.status === 'active' && <button className="danger" onClick={onEnd}>강제 종료</button>}
        <button className="ghost" onClick={onRefresh}>새로고침</button>
      </div>

      {b.battle.status === 'active' && (
        <form onSubmit={submit} className="card col" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>이벤트 추가</h3>
          <div className="row">
            <select value={eventForm.event_type}
              onChange={e => setEventForm({ ...eventForm, event_type: e.target.value })}
              style={{ flex: 1 }}>
              {['attack', 'defend', 'detect', 'block', 'exploit', 'alert', 'score'].map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input style={{ flex: 1 }} placeholder="target (예: web)" value={eventForm.target}
              onChange={e => setEventForm({ ...eventForm, target: e.target.value })} />
            <input type="number" style={{ width: 120 }} placeholder="points"
              value={eventForm.points}
              onChange={e => setEventForm({ ...eventForm, points: parseInt(e.target.value || '0', 10) })} />
          </div>
          <input placeholder="설명" value={eventForm.description}
            onChange={e => setEventForm({ ...eventForm, description: e.target.value })} required />
          <button type="submit">이벤트 push</button>
        </form>
      )}

      <h3>이벤트 타임라인</h3>
      {b.events.slice().reverse().map(e => <EventRow key={e.id} e={e} />)}
    </>
  )
}
