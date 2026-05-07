import React, { useEffect, useMemo, useState } from 'react'
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
  reasoning: string | null
  points: number
}

interface BattleSummary {
  id: number
  scenario_id: number | null
  mode: string
  status: string
  monitor: string
  target_apps: string[]
  hint_enabled: boolean
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

interface HintOut {
  text: string
  model: string
  cache_hit: boolean
  cost_usd: number
  cooldown_remaining_sec: number
}

const eventTypePalette: Record<string, string> = {
  attack: 'red', exploit: 'red',
  defend: 'green', detect: 'green', block: 'green',
  alert: 'yellow', score: 'blue', system: 'blue',
}

const TARGET_APPS_CATALOG = [
  { id: 'juiceshop',    label: 'Juice Shop (web vuln 메인)' },
  { id: 'dvwa',         label: 'DVWA (legacy web vuln)' },
  { id: 'neobank',      label: 'NeoBank (FinTech)' },
  { id: 'mediforum',    label: 'MediForum (의료 포럼)' },
  { id: 'govportal',    label: 'GovPortal (정부 포털)' },
  { id: 'aicompanion',  label: 'AICompanion (AI 챗)' },
  { id: 'adminconsole', label: 'AdminConsole (관리)' },
  { id: 'web',          label: 'Web 랜딩 / Reverse Proxy' },
] as const

type Mode = 'solo' | 'duel' | 'ffa'

interface InvitedPlayer {
  user: UserLookup
  role: 'red' | 'blue' | 'free'
  infra_id: number | null
}

interface BattleOptions {
  monitor: 'bastion' | 'claude'
  hint_enabled: boolean
  target_apps: string[]   // [] | ['random'] | ['juiceshop', ...]
  use_random: boolean
}

const defaultOpts: BattleOptions = {
  monitor: 'bastion',
  hint_enabled: false,
  target_apps: [],
  use_random: false,
}

export default function Battle() {
  const user = getUser()!
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [battles, setBattles] = useState<BattleSummary[]>([])
  const [activeBattle, setActiveBattle] = useState<BattleDetail | null>(null)
  const [myInfras, setMyInfras] = useState<Infra[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // 시나리오에서 모드 시작하기 전 옵션
  const [pendingScenario, setPendingScenario] = useState<Scenario | null>(null)
  const [pendingMode, setPendingMode] = useState<Mode>('solo')
  const [pendingOpts, setPendingOpts] = useState<BattleOptions>(defaultOpts)

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

  function startCreate(s: Scenario, mode: Mode) {
    setErr(null)
    if (myInfras.length === 0) {
      setErr('먼저 /myinfra 에서 6v6 인프라를 등록하세요.')
      return
    }
    setPendingScenario(s)
    setPendingMode(mode)
    setPendingOpts({ ...defaultOpts })
  }

  async function createSolo() {
    if (!pendingScenario) return
    const apps = pendingOpts.use_random ? ['random'] : pendingOpts.target_apps
    try {
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: pendingScenario.id, mode: 'solo',
          monitor: pendingOpts.monitor,
          hint_enabled: pendingOpts.hint_enabled,
          target_apps: apps,
          participants: [{ user_id: user.id, role: 'solo', infra_id: myInfras[0].id }],
        },
      })
      setPendingScenario(null)
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

      {pendingScenario && pendingMode === 'solo' && (
        <SoloOptionsDialog
          scenario={pendingScenario}
          opts={pendingOpts} setOpts={setPendingOpts}
          onCancel={() => setPendingScenario(null)}
          onConfirm={createSolo}
        />
      )}

      {pendingScenario && pendingMode !== 'solo' && (
        <CreateMultiBattleDialog
          scenario={pendingScenario}
          mode={pendingMode}
          me={user}
          myInfras={myInfras}
          opts={pendingOpts} setOpts={setPendingOpts}
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

          <h3 style={{ marginTop: 32 }}>내 최근 + 진행 중인 공방전 (관전 가능)</h3>
          {battles.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
          {battles.map(b => (
            <div key={b.id} className="card">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <b>#{b.id}</b> · <span className="badge blue">{b.mode}</span> ·
                  monitor: <span className={`badge ${b.monitor === 'claude' ? 'red' : 'green'}`}>{b.monitor}</span>
                  {b.hint_enabled && <span className="badge yellow" style={{ marginLeft: 6 }}>hint</span>}
                  {b.target_apps?.length > 0 && (
                    <span style={{ marginLeft: 8, color: 'var(--fg-dim)', fontSize: 12 }}>
                      targets: {b.target_apps.join(', ')}
                    </span>
                  )}
                </div>
                <span className={`badge ${b.status === 'active' ? 'green' : b.status === 'completed' ? 'blue' : 'yellow'}`}>
                  {b.status}
                </span>
                <button className="ghost" onClick={() => loadBattle(b.id)}>
                  {b.status === 'active' ? '관전/참여' : '열기'}
                </button>
              </div>
            </div>
          ))}
        </>
      )}

      {activeBattle && <BattleView b={activeBattle}
        meId={user.id}
        onClose={() => { setActiveBattle(null); refresh() }}
        onStart={startBattle} onEnd={endBattle}
        onRefresh={() => loadBattle(activeBattle.battle.id)}
        onErr={setErr} />}
    </>
  )
}

// ──────────────────────────────────────────────────────
// 공통 옵션 패널
// ──────────────────────────────────────────────────────
function OptionsPanel({ opts, setOpts }: { opts: BattleOptions; setOpts: (o: BattleOptions) => void }) {
  function toggleApp(app: string) {
    if (opts.use_random) return
    if (opts.target_apps.includes(app)) {
      setOpts({ ...opts, target_apps: opts.target_apps.filter(a => a !== app) })
    } else if (opts.target_apps.length < 5) {
      setOpts({ ...opts, target_apps: [...opts.target_apps, app] })
    }
  }
  return (
    <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16, marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>채점 / 힌트 / 타겟 옵션</h3>

      <div className="row" style={{ alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>채점 모델</div>
          <label style={{ marginRight: 12 }}>
            <input type="radio" checked={opts.monitor === 'bastion'}
              onChange={() => setOpts({ ...opts, monitor: 'bastion' })} />
            CCC Bastion (heuristic, 무료)
          </label>
          <label>
            <input type="radio" checked={opts.monitor === 'claude'}
              onChange={() => setOpts({ ...opts, monitor: 'claude' })} />
            Claude Code (LLM, 자연어 보고)
          </label>
        </div>

        <label>
          <input type="checkbox" checked={opts.hint_enabled}
            onChange={e => setOpts({ ...opts, hint_enabled: e.target.checked })} />
          힌트 허용 (학생이 명시 요청 시, 60초 cooldown)
        </label>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
          취약 웹 타겟 — 1~5개 선택 또는 랜덤. 비워두면 default 4 종 (web/juiceshop/siem).
        </div>
        <label style={{ marginTop: 4, display: 'block' }}>
          <input type="checkbox" checked={opts.use_random}
            onChange={e => setOpts({
              ...opts, use_random: e.target.checked,
              target_apps: e.target.checked ? [] : opts.target_apps,
            })} />
          🎲 랜덤 (서버가 2~4개 자동 선택)
        </label>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
          {TARGET_APPS_CATALOG.map(a => {
            const on = opts.target_apps.includes(a.id)
            return (
              <button key={a.id} type="button"
                className={on ? '' : 'ghost'}
                style={{
                  fontSize: 12, padding: '4px 10px',
                  opacity: opts.use_random ? 0.4 : 1,
                  cursor: opts.use_random ? 'not-allowed' : 'pointer',
                }}
                disabled={opts.use_random || (!on && opts.target_apps.length >= 5)}
                onClick={() => toggleApp(a.id)}>
                {on ? '✓ ' : ''}{a.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// solo 옵션 다이얼로그
// ──────────────────────────────────────────────────────
function SoloOptionsDialog({ scenario, opts, setOpts, onCancel, onConfirm }: {
  scenario: Scenario
  opts: BattleOptions
  setOpts: (o: BattleOptions) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="card" style={{ borderColor: 'var(--primary)' }}>
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, flex: 1 }}>solo 공방전 옵션</h2>
        <button className="ghost" onClick={onCancel}>닫기</button>
      </div>
      <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 12 }}>
        시나리오: <b>{scenario.title}</b> · 제한 {Math.round(scenario.time_limit_sec / 60)}분
      </div>
      <OptionsPanel opts={opts} setOpts={setOpts} />
      <div className="row" style={{ marginTop: 16 }}>
        <button onClick={onConfirm}>solo 시작</button>
        <button className="ghost" onClick={onCancel}>취소</button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// duel / ffa 다이얼로그
// ──────────────────────────────────────────────────────
function CreateMultiBattleDialog({
  scenario, mode, me, myInfras, opts, setOpts, onCancel, onCreated, onErr,
}: {
  scenario: Scenario
  mode: Mode
  me: { id: number; email: string }
  myInfras: Infra[]
  opts: BattleOptions
  setOpts: (o: BattleOptions) => void
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
    const participants = [
      { user_id: me.id, role: meRole, infra_id: meInfraId },
      ...invited.map(i => ({ user_id: i.user.id, role: i.role, infra_id: i.infra_id })),
    ]
    setBusy(true)
    try {
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: scenario.id, mode,
          monitor: opts.monitor,
          hint_enabled: opts.hint_enabled,
          target_apps: opts.use_random ? ['random'] : opts.target_apps,
          participants,
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
              onChange={e => {
                const next = [...invited]
                next[idx] = { ...next[idx], infra_id: e.target.value ? parseInt(e.target.value) : null }
                setInvited(next)
              }}
            />
            <button className="ghost" onClick={() => setInvited(invited.filter((_, i) => i !== idx))}>×</button>
          </div>
        </div>
      ))}

      <OptionsPanel opts={opts} setOpts={setOpts} />

      <div className="row" style={{ marginTop: 16 }}>
        <button onClick={submit} disabled={busy}>공방전 생성</button>
        <button className="ghost" onClick={onCancel} disabled={busy}>취소</button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 이벤트 row — reasoning + detail JSON 함께 보기
// ──────────────────────────────────────────────────────
function EventRow({ e }: { e: BattleEvent }) {
  const [open, setOpen] = useState(false)
  const hasDetail = (e.detail && Object.keys(e.detail).length > 0) || !!e.reasoning
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
      {open && (
        <div style={{ marginTop: 8, padding: 10, background: 'rgba(255,255,255,0.04)',
                      borderRadius: 6, fontSize: 13 }}>
          {e.reasoning && (
            <div style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>
              {e.reasoning}
            </div>
          )}
          {hasDetail && Object.keys(e.detail || {}).length > 0 && (
            <details>
              <summary style={{ cursor: 'pointer', color: 'var(--fg-dim)', fontSize: 12 }}>
                raw detail (JSON)
              </summary>
              <pre style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 11 }}>
                {JSON.stringify(e.detail, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// BattleView — 참가자 모드 + 관전 모드 통합
// ──────────────────────────────────────────────────────
function BattleView({
  b, meId, onClose, onStart, onEnd, onRefresh, onErr,
}: {
  b: BattleDetail
  meId: number
  onClose: () => void
  onStart: () => void
  onEnd: () => void
  onRefresh: () => void
  onErr: (m: string) => void
}) {
  const isParticipant = b.participants.some(p => p.user_id === meId)
  const isAdmin = getUser()?.role === 'admin'
  const canControl = isParticipant || isAdmin

  const [eventForm, setEventForm] = useState({
    event_type: 'attack', target: '', description: '', points: 0,
  })
  const [hint, setHint] = useState<HintOut | null>(null)
  const [hintBusy, setHintBusy] = useState(false)
  const [hintCool, setHintCool] = useState(0)
  const [hintSide, setHintSide] = useState<'red' | 'blue' | 'any'>('any')
  const [hintNote, setHintNote] = useState('')

  // hint cooldown 카운트다운
  useEffect(() => {
    if (hintCool <= 0) return
    const t = setTimeout(() => setHintCool(c => Math.max(0, c - 1)), 1000)
    return () => clearTimeout(t)
  }, [hintCool])

  async function submitEvent(e: React.FormEvent) {
    e.preventDefault()
    await api(`/battles/${b.battle.id}/events`, { method: 'POST', json: eventForm })
    setEventForm({ ...eventForm, description: '' })
    onRefresh()
  }

  async function requestHint() {
    setHintBusy(true)
    try {
      const r = await api<HintOut>(`/battles/${b.battle.id}/hint`, {
        method: 'POST',
        json: { mission_side: hintSide, note: hintNote },
      })
      setHint(r)
      setHintCool(60)
    } catch (e: any) {
      onErr(`힌트 요청 실패: ${e.message}`)
    } finally {
      setHintBusy(false)
    }
  }

  // 모드별 정렬: duel = red→blue 그룹별, ffa/solo = 점수 내림차순
  const sortedParts = b.battle.mode === 'duel'
    ? [...b.participants].sort((a, b) => (a.role === 'red' ? -1 : 1) - (b.role === 'red' ? -1 : 1) || b.score - a.score)
    : [...b.participants].sort((a, b) => b.score - a.score)
  const teamSums: Record<string, number> = {}
  for (const p of b.participants) teamSums[p.role] = (teamSums[p.role] || 0) + p.score

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 16 }}>
        <button className="ghost" onClick={onClose}>← 목록</button>
        <h2 style={{ margin: 0, flex: 1 }}>
          #{b.battle.id} · {b.scenario_title || '(no scenario)'}
        </h2>
        <span className="badge blue">{b.battle.mode}</span>
        {!isParticipant && <span className="badge yellow">관전</span>}
        <span className={`badge ${b.battle.status === 'active' ? 'green' : 'blue'}`}>{b.battle.status}</span>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>모드 / 참가</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{b.battle.mode}</div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>참가 {b.participants.length}명</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>채점 / 힌트</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            {b.battle.monitor === 'claude' ? 'Claude' : 'Bastion'}
            {b.battle.hint_enabled && <span style={{ color: 'var(--yellow)', fontSize: 12, marginLeft: 6 }}>+ hint</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
            targets: {(b.battle.target_apps || []).join(', ') || '(default)'}
          </div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>경과</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{Math.round(b.elapsed_sec)}s</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>잔여</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{Math.round(b.remaining_sec)}s</div>
        </div>
      </div>

      {b.battle.mode === 'duel' && (
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
              <tr key={p.id} style={{ borderBottom: '1px solid var(--border)',
                                       background: p.user_id === meId ? 'rgba(255,180,80,0.06)' : undefined }}>
                <td style={{ padding: '8px 4px' }}>
                  <span className={`badge ${p.role === 'red' ? 'red' : p.role === 'blue' ? 'blue' : 'yellow'}`}>{p.role}</span>
                </td>
                <td style={{ padding: '8px 4px' }}>#{p.user_id}{p.user_id === meId ? ' (나)' : ''}</td>
                <td style={{ padding: '8px 4px' }}>{p.infra_id ?? '—'}</td>
                <td style={{ padding: '8px 4px', fontWeight: 700, textAlign: 'right' }}>{p.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canControl && (
        <div className="row" style={{ marginTop: 16 }}>
          {b.battle.status === 'pending' && <button onClick={onStart}>시작</button>}
          {b.battle.status === 'active' && <button className="danger" onClick={onEnd}>강제 종료</button>}
          <button className="ghost" onClick={onRefresh}>새로고침</button>
        </div>
      )}
      {!canControl && (
        <div className="card" style={{ color: 'var(--fg-dim)', fontSize: 13 }}>
          🔍 관전 모드 — 이 공방전의 참가자가 아니므로 read-only 입니다. 이벤트 / 강제종료 / 힌트 요청 불가.
        </div>
      )}

      {/* 힌트 패널 — 참가자 + hint_enabled + active */}
      {b.battle.hint_enabled && isParticipant && b.battle.status === 'active' && (
        <div className="card col" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>💡 힌트 요청</h3>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
            토큰 절약을 위해 동일 상태에선 동일 힌트가 캐시됩니다. 60초 cooldown.
          </div>
          <div className="row">
            <select value={hintSide} onChange={e => setHintSide(e.target.value as any)}>
              <option value="any">any (전체)</option>
              <option value="red">red (공격)</option>
              <option value="blue">blue (방어)</option>
            </select>
            <input style={{ flex: 1 }} placeholder="막힌 곳 (선택, 짧게)"
              value={hintNote} onChange={e => setHintNote(e.target.value)} />
            <button onClick={requestHint} disabled={hintBusy || hintCool > 0}>
              {hintCool > 0 ? `${hintCool}s 대기` : (hintBusy ? '요청 중...' : '힌트 받기')}
            </button>
          </div>
          {hint && (
            <div style={{ marginTop: 8, padding: 10, background: 'rgba(255,200,50,0.06)',
                          borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap' }}>
              <div style={{ fontSize: 11, color: 'var(--fg-dim)', marginBottom: 6 }}>
                model: {hint.model} {hint.cache_hit && '· (캐시)'} · cost: ${hint.cost_usd.toFixed(4)}
              </div>
              {hint.text}
            </div>
          )}
        </div>
      )}

      {canControl && b.battle.status === 'active' && (
        <form onSubmit={submitEvent} className="card col" style={{ marginTop: 16 }}>
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
