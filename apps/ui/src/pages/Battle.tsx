import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { getUser } from '../auth.ts'

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

interface UserLookup {
  id: number
  email: string
  name: string
  role: string
}

interface Infra {
  id: number
  name: string
  vm_ip: string
}

const eventTypePalette: Record<string, string> = {
  attack: 'red', exploit: 'red',
  defend: 'green', detect: 'green', block: 'green',
  alert: 'yellow', score: 'blue', system: 'blue',
}

type Mode = 'solo' | 'duel' | 'ffa'

interface InvitedPlayer {
  user: UserLookup
  role: 'red' | 'blue' | 'free'
  infra_id: number | null
}

export default function Battle() {
  const user = getUser()!
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [battles, setBattles] = useState<BattleSummary[]>([])
  const [activeBattle, setActiveBattle] = useState<BattleDetail | null>(null)
  const [myInfras, setMyInfras] = useState<Infra[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // 모드 시작 다이얼로그 상태
  const [pendingScenario, setPendingScenario] = useState<Scenario | null>(null)
  const [pendingMode, setPendingMode] = useState<Mode>('solo')

  async function refresh() {
    try {
      const [scns, bts, infras] = await Promise.all([
        api<Scenario[]>('/scenarios'),
        api<BattleSummary[]>('/battles'),
        api<Infra[]>('/infras'),
      ])
      setScenarios(scns)
      setBattles(bts)
      setMyInfras(infras)
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

  async function startCreate(s: Scenario, mode: Mode) {
    setErr(null)
    if (mode === 'solo') {
      // solo 는 즉시 생성
      if (myInfras.length === 0) {
        setErr('먼저 /myinfra 에서 6v6 인프라를 등록하세요.')
        return
      }
      try {
        const b = await api<BattleDetail>('/battles', {
          method: 'POST',
          json: {
            scenario_id: s.id, mode: 'solo', monitor: 'bastion',
            participants: [{ user_id: user.id, role: 'solo', infra_id: myInfras[0].id }],
          },
        })
        setActiveBattle(b)
        await refresh()
      } catch (e: any) { setErr(e.message) }
      return
    }
    // duel / ffa 는 다이얼로그 띄움
    setPendingScenario(s)
    setPendingMode(mode)
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

  // 라이브 스트림 (폴링)
  useEffect(() => {
    if (!activeBattle || activeBattle.battle.status !== 'active') return
    const id = activeBattle.battle.id
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

      {pendingScenario && (
        <CreateMultiBattleDialog
          scenario={pendingScenario}
          mode={pendingMode}
          me={user}
          myInfras={myInfras}
          onCancel={() => setPendingScenario(null)}
          onCreated={async (b) => {
            setPendingScenario(null)
            setActiveBattle(b)
            await refresh()
          }}
          onErr={setErr}
        />
      )}

      {!activeBattle && !pendingScenario && (
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
                <button onClick={() => startCreate(s, 'solo')} disabled={myInfras.length === 0}>
                  solo
                </button>
                <button onClick={() => startCreate(s, 'duel')} disabled={myInfras.length === 0}>
                  duel (1v1)
                </button>
                <button onClick={() => startCreate(s, 'ffa')} disabled={myInfras.length === 0}>
                  ffa (n인)
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
                  <b>#{b.id}</b> · <span className="badge blue">{b.mode}</span> · monitor: {b.monitor}
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

// ──────────────────────────────────────────────────────
// duel / ffa 생성 다이얼로그
// ──────────────────────────────────────────────────────
function CreateMultiBattleDialog({
  scenario, mode, me, myInfras, onCancel, onCreated, onErr,
}: {
  scenario: Scenario
  mode: Mode
  me: { id: number; email: string }
  myInfras: Infra[]
  onCancel: () => void
  onCreated: (b: BattleDetail) => void
  onErr: (m: string) => void
}) {
  const myDefaultRole: 'red' | 'blue' | 'free' = mode === 'duel' ? 'red' : 'free'
  const [meRole, setMeRole] = useState<'red' | 'blue' | 'free'>(myDefaultRole)
  const [meInfraId, setMeInfraId] = useState<number | null>(myInfras[0]?.id ?? null)

  const [invited, setInvited] = useState<InvitedPlayer[]>([])
  const [lookupEmail, setLookupEmail] = useState('')
  const [busy, setBusy] = useState(false)

  async function lookupAndAdd() {
    if (!lookupEmail.trim()) return
    if (lookupEmail.trim().toLowerCase() === me.email.toLowerCase()) {
      onErr('자기 자신은 자동 포함됩니다.')
      return
    }
    if (invited.some(i => i.user.email.toLowerCase() === lookupEmail.trim().toLowerCase())) {
      onErr('이미 추가된 사용자입니다.')
      return
    }
    if (mode === 'duel' && invited.length >= 1) {
      onErr('duel 모드는 상대 1명만 가능합니다.')
      return
    }
    if (mode === 'ffa' && invited.length >= 7) {
      onErr('ffa 모드 최대 8명 (본인 포함).')
      return
    }
    try {
      const u = await api<UserLookup>(`/users/lookup?email=${encodeURIComponent(lookupEmail.trim())}`)
      const otherRole: 'red' | 'blue' | 'free' =
        mode === 'duel' ? (meRole === 'red' ? 'blue' : 'red') : 'free'
      setInvited([...invited, { user: u, role: otherRole, infra_id: null }])
      setLookupEmail('')
    } catch (e: any) {
      onErr(`사용자 찾을 수 없음: ${e.message}`)
    }
  }

  function setInvitedInfra(idx: number, infraId: number | null) {
    const next = [...invited]
    next[idx] = { ...next[idx], infra_id: infraId }
    setInvited(next)
  }

  async function submit() {
    if (mode === 'duel' && invited.length !== 1) {
      onErr('duel 은 상대 1명을 추가하세요.')
      return
    }
    if (mode === 'ffa' && invited.length < 1) {
      onErr('ffa 는 본인 외 최소 1명 추가하세요.')
      return
    }
    if (!meInfraId) {
      onErr('본인 인프라를 선택하세요.')
      return
    }
    // 상대는 자기 인프라가 아직 미등록일 수 있음 → infra_id null 허용
    const participants = [
      { user_id: me.id, role: meRole, infra_id: meInfraId },
      ...invited.map(i => ({ user_id: i.user.id, role: i.role, infra_id: i.infra_id })),
    ]
    setBusy(true)
    try {
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: scenario.id, mode, monitor: 'bastion', participants,
        },
      })
      onCreated(b)
    } catch (e: any) {
      onErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ borderColor: 'var(--primary)' }}>
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, flex: 1 }}>
          {mode === 'duel' ? '1v1 duel' : 'FFA n인전'} 생성
        </h2>
        <button className="ghost" onClick={onCancel}>닫기</button>
      </div>

      <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 12 }}>
        시나리오: <b>{scenario.title}</b> · 제한 {Math.round(scenario.time_limit_sec / 60)}분
      </div>

      <h3>본인 ({me.email})</h3>
      <div className="row">
        {mode === 'duel' && (
          <select value={meRole} onChange={e => {
            const r = e.target.value as 'red' | 'blue'
            setMeRole(r)
            // duel 일 때 자동으로 상대 역할 swap
            setInvited(invited.map(i => ({ ...i, role: r === 'red' ? 'blue' : 'red' })))
          }}>
            <option value="red">red (공격)</option>
            <option value="blue">blue (방어)</option>
          </select>
        )}
        {mode === 'ffa' && (
          <select value={meRole} onChange={e => setMeRole(e.target.value as any)}>
            <option value="free">free</option>
            <option value="red">red</option>
            <option value="blue">blue</option>
          </select>
        )}
        <select value={meInfraId ?? ''} onChange={e => setMeInfraId(e.target.value ? parseInt(e.target.value) : null)}>
          <option value="">— 인프라 선택 —</option>
          {myInfras.map(i => (
            <option key={i.id} value={i.id}>{i.name} ({i.vm_ip})</option>
          ))}
        </select>
      </div>

      <h3 style={{ marginTop: 20 }}>참가자 추가</h3>
      <div className="row">
        <input
          style={{ flex: 1 }}
          placeholder="상대방 이메일"
          value={lookupEmail}
          onChange={e => setLookupEmail(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') lookupAndAdd() }}
        />
        <button onClick={lookupAndAdd} disabled={busy}>+ 추가</button>
      </div>

      {invited.length === 0 && (
        <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginTop: 8 }}>
          {mode === 'duel'
            ? '상대 1명을 추가하세요. 이메일로 검색.'
            : '본인 외 추가할 참가자를 이메일로 검색해 추가하세요. (최대 7명 추가)'}
        </div>
      )}

      {invited.map((p, idx) => (
        <div key={p.user.id} className="card" style={{ padding: 10, margin: '8px 0' }}>
          <div className="row" style={{ alignItems: 'center' }}>
            <div style={{ flex: 1 }}>
              <b>{p.user.name}</b> · <span style={{ color: 'var(--fg-dim)' }}>{p.user.email}</span>
              <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
                role: <span className={`badge ${p.role === 'red' ? 'red' : p.role === 'blue' ? 'blue' : 'yellow'}`}>{p.role}</span>
              </div>
            </div>
            {mode === 'ffa' && (
              <select value={p.role} onChange={e => {
                const next = [...invited]
                next[idx] = { ...next[idx], role: e.target.value as any }
                setInvited(next)
              }}>
                <option value="free">free</option>
                <option value="red">red</option>
                <option value="blue">blue</option>
              </select>
            )}
            <input
              style={{ width: 90 }}
              placeholder="infra_id"
              type="number"
              value={p.infra_id ?? ''}
              onChange={e => setInvitedInfra(idx, e.target.value ? parseInt(e.target.value) : null)}
            />
            <button className="ghost" onClick={() => setInvited(invited.filter((_, i) => i !== idx))}>×</button>
          </div>
        </div>
      ))}

      <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 8 }}>
        💡 상대의 infra_id 가 모르면 비워두세요 — 본인이 admin 이거나 상대가 직접 자기 infra 로 join 하는 흐름은 추후 보강.
        지금은 일단 빈칸 또는 상대가 알려준 ID 를 입력합니다.
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <button onClick={submit} disabled={busy}>공방전 생성</button>
        <button className="ghost" onClick={onCancel} disabled={busy}>취소</button>
      </div>
    </div>
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

  // 모드별 정렬: duel 은 red→blue 그룹별, ffa 는 점수 내림차순, solo 는 단일
  const sortedParts = b.battle.mode === 'duel'
    ? [...b.participants].sort((a, b) => (a.role === 'red' ? -1 : 1) - (b.role === 'red' ? -1 : 1) || b.score - a.score)
    : [...b.participants].sort((a, b) => b.score - a.score)

  // ffa 합계 / duel red·blue 합계
  const teamSums: Record<string, number> = {}
  for (const p of b.participants) {
    teamSums[p.role] = (teamSums[p.role] || 0) + p.score
  }

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 16 }}>
        <button className="ghost" onClick={onClose}>← 목록</button>
        <h2 style={{ margin: 0, flex: 1 }}>
          #{b.battle.id} · {b.scenario_title || '(no scenario)'}
        </h2>
        <span className="badge blue">{b.battle.mode}</span>
        <span className={`badge ${b.battle.status === 'active' ? 'green' : 'blue'}`}>{b.battle.status}</span>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>모드</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{b.battle.mode}</div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
            참가자 {b.participants.length}명
          </div>
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

      {(b.battle.mode === 'duel') && (
        <div className="row">
          <div className="card" style={{ flex: 1, borderColor: 'var(--red)' }}>
            <div style={{ color: 'var(--red)', fontSize: 13 }}>RED 팀 합계</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--red)' }}>{teamSums.red ?? 0}</div>
          </div>
          <div className="card" style={{ flex: 1, borderColor: 'var(--blue)' }}>
            <div style={{ color: 'var(--blue)', fontSize: 13 }}>BLUE 팀 합계</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--blue)' }}>{teamSums.blue ?? 0}</div>
          </div>
        </div>
      )}

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
