import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.ts'
import { getUser } from '../auth.ts'
import { fmtTime } from '../time.ts'

interface Scenario {
  id: number
  title: string
  description: string
  source: string
  status: string
  time_limit_sec: number
  category?: string | null
}

// 시나리오 트랙(카테고리) 라벨/순서 — 카탈로그 그룹핑용
const CAT_LABEL: Record<string, string> = {
  'secuops-easy': '보안운영 입문', 'secuops': '보안운영', 'soc': 'SOC 관제', 'attack': '공격기법',
}
const CAT_ORDER = ['secuops-easy', 'secuops', 'soc', 'attack']
function catLabel(c?: string | null) { return c ? (CAT_LABEL[c] || c) : '미분류' }
function catRank(c: string) { const i = CAT_ORDER.indexOf(c); return i < 0 ? 99 : i }

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
  scenario_title: string | null
  cohort_id: number | null
  cohort_name: string | null
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

interface Mission {
  side: 'red' | 'blue'
  order: number
  title: string | null
  instruction: string
  target_vm: string | null
  points: number
  hint: string | null
  verify_expect: string | null
  semantic_intent: string | null
  success_criteria: string[]
  solved: boolean
}

interface BattleDetail {
  battle: BattleSummary
  scenario_title: string | null
  participants: Participant[]
  events: BattleEvent[]
  elapsed_sec: number
  remaining_sec: number
  my_role: string | null
  my_missions: Mission[]
  opponent_missions: Mission[]
}

interface UserLookup { id: number; email: string; name: string; role: string }
interface Cohort { id: number; kind: string; name: string; parent_id: number | null; course_ref: string | null; member_count: number }
interface Infra { id: number; name: string; vm_ip: string }
interface HintOut { text: string; model: string; cache_hit: boolean; cost_usd: number; cooldown_remaining_sec: number }

const eventTypePalette: Record<string, string> = {
  attack: 'red', exploit: 'red',
  defend: 'green', detect: 'green', block: 'green',
  alert: 'yellow', score: 'blue', system: 'blue',
}

const TARGET_APPS_CATALOG = [
  { id: 'juiceshop',    label: 'Juice Shop' },
  { id: 'dvwa',         label: 'DVWA' },
  { id: 'neobank',      label: 'NeoBank' },
  { id: 'mediforum',    label: 'MediForum' },
  { id: 'govportal',    label: 'GovPortal' },
  { id: 'aicompanion',  label: 'AICompanion' },
  { id: 'adminconsole', label: 'AdminConsole' },
  { id: 'web',          label: 'Web 랜딩' },
] as const

type Mode = 'solo' | 'duel' | 'ffa'

interface BattleOptions {
  monitor: 'bastion' | 'claude'
  hint_enabled: boolean
  target_apps: string[]
  use_random: boolean
  mode: Mode
}

const defaultOpts: BattleOptions = {
  monitor: 'bastion', hint_enabled: false,
  target_apps: [], use_random: false, mode: 'duel',
}

function isAdmin() { return getUser()?.role === 'admin' }

export default function Battle() {
  const user = getUser()!
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [battles, setBattles] = useState<BattleSummary[]>([])
  const [activeBattle, setActiveBattle] = useState<BattleDetail | null>(null)
  const [myInfras, setMyInfras] = useState<Infra[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // admin: lobby 개설 다이얼로그 상태
  const [lobbyOpen, setLobbyOpen] = useState(false)
  // 카탈로그 트랙 접기/펼치기 (기본: 모두 접힘 → 스크롤 짧게)
  const [openCats, setOpenCats] = useState<Set<string>>(new Set())
  const [histOpen, setHistOpen] = useState(false)  // 완료된 공방전 이력 접기

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

  // 상단 nav 의 "공방전" 링크 클릭 시: 같은 path 라 router 가 unmount 안 함 →
  // 커스텀 이벤트로 강제 리셋
  useEffect(() => {
    const reset = () => {
      setActiveBattle(null)
      setLobbyOpen(false)
      setErr(null)
      refresh()
    }
    window.addEventListener('tubewar:battle:reset', reset)
    return () => window.removeEventListener('tubewar:battle:reset', reset)
  }, [])

  async function loadBattle(id: number) {
    setErr(null)
    try {
      const b = await api<BattleDetail>(`/battles/${id}`)
      setActiveBattle(b)
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

  // 라이브 폴링
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

  // 로비 = pending + 본인이 참가자 아닌 + (mode duel/ffa)
  const lobbyBattles = battles.filter(b =>
    b.status === 'pending' && b.mode !== 'solo'
  )
  const myActiveBattles = battles.filter(b =>
    b.status === 'active' || b.status === 'completed'
  )

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>공방전</h1>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}

      {lobbyOpen && (
        <LobbyCreateDialog
          scenarios={scenarios}
          onCancel={() => setLobbyOpen(false)}
          onCreated={async (b) => {
            setLobbyOpen(false)
            setActiveBattle(b)
            await refresh()
          }}
          onErr={setErr}
        />
      )}

      {!activeBattle && !lobbyOpen && (
        <>
          {/* 1. 로비 — 학생이 참여하는 곳, admin 이 만드는 곳 */}
          <div className="row" style={{ alignItems: 'center', marginTop: 12 }}>
            <h3 style={{ margin: 0, flex: 1 }}>🎮 로비 (참여 가능한 공방전)</h3>
            {isAdmin() && (
              <button onClick={() => setLobbyOpen(true)}>+ 새 로비 공방전 개설</button>
            )}
          </div>
          {lobbyBattles.length === 0 ? (
            <div className="card" style={{ color: 'var(--fg-dim)' }}>
              현재 모집 중인 공방전 없음.
              {isAdmin() && ' 위 버튼으로 새 로비를 개설하세요.'}
              {!isAdmin() && ' 관리자가 공방전을 개설할 때까지 기다리세요. (또는 직접 solo 시작)'}
            </div>
          ) : (
            lobbyBattles.map(b => (
              <LobbyCard key={b.id} b={b} myInfras={myInfras}
                onJoined={(d) => { setActiveBattle(d); refresh() }}
                onView={() => loadBattle(b.id)}
                onErr={setErr} />
            ))
          )}

          {/* 2. 학생 — solo (혼자 연습) */}
          <h3 style={{ marginTop: 32 }}>📚 시나리오 카탈로그 — solo 연습</h3>
          {loading && <div className="card">로딩 중...</div>}
          {!loading && scenarios.length === 0 && (
            <div className="card" style={{ color: 'var(--fg-dim)' }}>아직 시나리오 없음.</div>
          )}
          {!loading && (() => {
            const cats = Array.from(new Set(scenarios.map(s => s.category || '')))
              .sort((a, b) => catRank(a) - catRank(b))
            return cats.map(c => {
              const items = scenarios.filter(s => (s.category || '') === c)
                .sort((a, b) => a.id - b.id)
              const open = openCats.has(c)
              return (
                <div key={c || 'none'} style={{ marginBottom: 8 }}>
                  <div onClick={() => setOpenCats(p => {
                    const n = new Set(p); n.has(c) ? n.delete(c) : n.add(c); return n
                  })} className="row" style={{
                    cursor: 'pointer', alignItems: 'center', padding: '8px 12px',
                    border: '1px solid var(--border)', borderRadius: 6, fontWeight: 600,
                  }}>
                    <span style={{ marginRight: 8, color: 'var(--primary)' }}>{open ? '▼' : '▶'}</span>
                    {catLabel(c)}
                    <span style={{ fontSize: 12, color: 'var(--fg-dim)', marginLeft: 8 }}>· {items.length}개</span>
                  </div>
                  {open && (
                    <div style={{ marginTop: 6 }}>
                      {items.map(s => (
                        <SoloRow key={s.id} s={s} myInfras={myInfras}
                          onCreated={(b) => { setActiveBattle(b); refresh() }}
                          onErr={setErr} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })
          })()}

          {/* 3. 진행 중·완료 공방전 (관전·이력) — 진행중은 항상, 완료는 접이식 */}
          {(() => {
            const battleCard = (b: BattleSummary) => (
              <div key={b.id} className="card">
                <div className="row">
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, marginBottom: 2 }}>
                      {b.scenario_title || `시나리오 #${b.scenario_id ?? '-'}`}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
                      <span className="badge blue">{b.mode}</span>
                      {b.cohort_name && <span style={{ marginLeft: 6 }}>· {b.cohort_name}</span>}
                      <span style={{ marginLeft: 6 }}>· #{b.id}</span>
                      <span style={{ marginLeft: 6 }}>· 채점 {b.monitor === 'claude' ? 'AI(Claude)' : 'Bastion'}</span>
                      {b.hint_enabled && <span className="badge yellow" style={{ marginLeft: 6 }}>hint</span>}
                      {b.target_apps?.length > 0 && <span style={{ marginLeft: 6 }}>· targets: {b.target_apps.join(', ')}</span>}
                    </div>
                  </div>
                  <span className={`badge ${b.status === 'active' ? 'green' : 'blue'}`}>{b.status}</span>
                  <button className="ghost" onClick={() => loadBattle(b.id)}>
                    {b.status === 'active' ? '관전/참여' : '열기'}
                  </button>
                </div>
              </div>
            )
            const active = myActiveBattles.filter(b => b.status === 'active')
            const completed = myActiveBattles.filter(b => b.status === 'completed')
            return (
              <>
                <h3 style={{ marginTop: 32 }}>📺 진행 중인 공방전 <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>({active.length})</span></h3>
                {active.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>진행 중인 공방전 없음.</div>}
                {active.map(battleCard)}

                <h3 style={{ marginTop: 24, cursor: 'pointer' }} onClick={() => setHistOpen(o => !o)}>
                  <span style={{ color: 'var(--primary)', marginRight: 6 }}>{histOpen ? '▼' : '▶'}</span>
                  ✅ 완료된 공방전 이력 <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>({completed.length})</span>
                </h3>
                {histOpen && (completed.length === 0
                  ? <div className="card" style={{ color: 'var(--fg-dim)' }}>완료된 공방전 없음.</div>
                  : completed.map(battleCard))}
              </>
            )
          })()}
        </>
      )}

      {activeBattle && (
        <BattleView b={activeBattle} meId={user.id}
          onClose={() => { setActiveBattle(null); refresh() }}
          onStart={startBattle} onEnd={endBattle}
          onRefresh={() => loadBattle(activeBattle.battle.id)}
          onErr={setErr}
          myInfras={myInfras} />
      )}
    </>
  )
}

// ──────────────────────────────────────────────────────
// solo 시작 (간단 row, 옵션 없음 — 빠른 연습용)
// ──────────────────────────────────────────────────────
function SoloRow({ s, myInfras, onCreated, onErr }: {
  s: Scenario
  myInfras: Infra[]
  onCreated: (b: BattleDetail) => void
  onErr: (m: string) => void
}) {
  const [busy, setBusy] = useState(false)
  async function start() {
    if (myInfras.length === 0) { onErr('먼저 /myinfra 등록.'); return }
    setBusy(true)
    try {
      const me = getUser()!
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: s.id, mode: 'solo', monitor: 'bastion',
          hint_enabled: true, target_apps: [],
          participants: [{ user_id: me.id, role: 'solo', infra_id: myInfras[0].id }],
        },
      })
      // 자동 시작
      const started = await api<BattleDetail>(`/battles/${b.battle.id}/start`, { method: 'POST' })
      onCreated(started)
    } catch (e: any) { onErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <div className="row">
        <div style={{ flex: 1 }}>
          <b>{s.title}</b> <span className="badge blue">{s.source}</span>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginTop: 4 }}>
            {s.description.slice(0, 200)}{s.description.length > 200 ? '…' : ''}
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
            제한 {Math.round(s.time_limit_sec / 60)}분 · status: {s.status}
          </div>
        </div>
        <button onClick={start} disabled={busy || myInfras.length === 0}>
          solo 즉시 시작
        </button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// admin: 로비 공방전 개설 다이얼로그 (참가자 0명)
// ──────────────────────────────────────────────────────
function LobbyCreateDialog({ scenarios, onCancel, onCreated, onErr }: {
  scenarios: Scenario[]
  onCancel: () => void
  onCreated: (b: BattleDetail) => void
  onErr: (m: string) => void
}) {
  const [scenarioId, setScenarioId] = useState<number | null>(scenarios[0]?.id ?? null)
  const [opts, setOpts] = useState<BattleOptions>({ ...defaultOpts })
  const [busy, setBusy] = useState(false)
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [cohortId, setCohortId] = useState<string>('')
  useEffect(() => { api<Cohort[]>('/cohorts').then(setCohorts).catch(() => {}) }, [])

  function toggleApp(app: string) {
    if (opts.use_random) return
    if (opts.target_apps.includes(app)) {
      setOpts({ ...opts, target_apps: opts.target_apps.filter(a => a !== app) })
    } else if (opts.target_apps.length < 5) {
      setOpts({ ...opts, target_apps: [...opts.target_apps, app] })
    }
  }

  async function submit() {
    if (!scenarioId) { onErr('시나리오 선택'); return }
    setBusy(true)
    try {
      const b = await api<BattleDetail>('/battles', {
        method: 'POST',
        json: {
          scenario_id: scenarioId, mode: opts.mode, monitor: opts.monitor,
          cohort_id: cohortId ? Number(cohortId) : null,   // 수업용이면 지정, 신원-only 면 null
          hint_enabled: opts.hint_enabled,
          target_apps: opts.use_random ? ['random'] : opts.target_apps,
          participants: [],   // 로비 — 학생이 join 함
        },
      })
      onCreated(b)
    } catch (e: any) { onErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ borderColor: 'var(--primary)' }}>
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, flex: 1 }}>🎮 로비 공방전 개설 (admin)</h2>
        <button className="ghost" onClick={onCancel}>닫기</button>
      </div>
      <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 12 }}>
        참가자 없이 로비를 만들어두면 학생들이 직접 "참여" 버튼으로 들어옵니다.
        모드별 최소 인원이 차면 누구든 시작 가능.
      </div>

      <h3 style={{ marginTop: 12 }}>시나리오</h3>
      <select value={scenarioId ?? ''}
        onChange={e => setScenarioId(e.target.value ? parseInt(e.target.value) : null)}
        style={{ width: '100%' }}>
        {scenarios.map(s => (
          <option key={s.id} value={s.id}>
            {s.title} · {Math.round(s.time_limit_sec / 60)}분
          </option>
        ))}
      </select>

      <h3 style={{ marginTop: 16 }}>코호트 (수업용 — 선택)</h3>
      <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ width: '100%' }}>
        <option value="">없음 (신원-only 모드)</option>
        {cohorts.map(c => (
          <option key={c.id} value={c.id}>{c.kind}: {c.name}{c.course_ref ? ` (${c.course_ref})` : ''}</option>
        ))}
      </select>

      <h3 style={{ marginTop: 16 }}>모드</h3>
      <div className="row">
        {(['duel', 'ffa'] as Mode[]).map(m => (
          <label key={m} style={{ marginRight: 16 }}>
            <input type="radio" checked={opts.mode === m}
              onChange={() => setOpts({ ...opts, mode: m })} />
            {m === 'duel' ? '1v1 duel (red vs blue)' : 'FFA n인전'}
          </label>
        ))}
      </div>

      <h3 style={{ marginTop: 16 }}>채점 모델 / 힌트</h3>
      <div className="row" style={{ flexWrap: 'wrap', gap: 16 }}>
        <label><input type="radio" checked={opts.monitor === 'bastion'}
          onChange={() => setOpts({ ...opts, monitor: 'bastion' })} />
          CCC Bastion (heuristic, 무료)</label>
        <label><input type="radio" checked={opts.monitor === 'claude'}
          onChange={() => setOpts({ ...opts, monitor: 'claude' })} />
          Claude Code (LLM, 자연어 보고)</label>
        <label><input type="checkbox" checked={opts.hint_enabled}
          onChange={e => setOpts({ ...opts, hint_enabled: e.target.checked })} />
          힌트 허용 (60초 cooldown)</label>
      </div>

      <h3 style={{ marginTop: 16 }}>취약 웹 타겟 (1~5 또는 랜덤)</h3>
      <label>
        <input type="checkbox" checked={opts.use_random}
          onChange={e => setOpts({ ...opts, use_random: e.target.checked, target_apps: e.target.checked ? [] : opts.target_apps })} />
        🎲 랜덤
      </label>
      <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
        {TARGET_APPS_CATALOG.map(a => {
          const on = opts.target_apps.includes(a.id)
          return (
            <button key={a.id} type="button"
              className={on ? '' : 'ghost'}
              style={{ fontSize: 12, padding: '4px 10px',
                       opacity: opts.use_random ? 0.4 : 1 }}
              disabled={opts.use_random || (!on && opts.target_apps.length >= 5)}
              onClick={() => toggleApp(a.id)}>
              {on ? '✓ ' : ''}{a.label}
            </button>
          )
        })}
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <button onClick={submit} disabled={busy}>로비 개설</button>
        <button className="ghost" onClick={onCancel} disabled={busy}>취소</button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 로비 카드 — 학생 "참여" 또는 관전
// ──────────────────────────────────────────────────────
function LobbyCard({ b, myInfras, onJoined, onView, onErr }: {
  b: BattleSummary
  myInfras: Infra[]
  onJoined: (d: BattleDetail) => void
  onView: () => void
  onErr: (m: string) => void
}) {
  const [joining, setJoining] = useState(false)
  const [role, setRole] = useState<'red' | 'blue' | 'free'>(b.mode === 'duel' ? 'red' : 'free')
  const [infraId, setInfraId] = useState<number | null>(myInfras[0]?.id ?? null)
  const me = getUser()!

  async function join() {
    setJoining(true)
    try {
      const d = await api<BattleDetail>(`/battles/${b.id}/join`, {
        method: 'POST',
        json: { role, infra_id: infraId },
      })
      onJoined(d)
    } catch (e: any) { onErr(e.message) } finally { setJoining(false) }
  }

  return (
    <div className="card">
      <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 300 }}>
          <b>#{b.id}</b> ·
          <span className="badge blue">{b.mode}</span>
          <span className={`badge ${b.monitor === 'claude' ? 'red' : 'green'}`}>{b.monitor}</span>
          {b.hint_enabled && <span className="badge yellow">hint</span>}
          <div style={{ color: 'var(--fg-dim)', fontSize: 12, marginTop: 4 }}>
            제한 {Math.round(b.time_limit_sec / 60)}분 · targets: {b.target_apps?.join(', ') || '(default)'}
          </div>
        </div>
        <select value={role} onChange={e => setRole(e.target.value as any)}>
          {b.mode === 'duel' && <>
            <option value="red">red (공격)</option>
            <option value="blue">blue (방어)</option>
          </>}
          {b.mode === 'ffa' && <>
            <option value="free">free</option>
            <option value="red">red</option>
            <option value="blue">blue</option>
          </>}
        </select>
        <select value={infraId ?? ''} onChange={e => setInfraId(e.target.value ? parseInt(e.target.value) : null)}>
          <option value="">— 인프라 선택 —</option>
          {myInfras.map(i => (
            <option key={i.id} value={i.id}>{i.name} ({i.vm_ip})</option>
          ))}
        </select>
        <button onClick={join} disabled={joining || !infraId}>참여</button>
        <button className="ghost" onClick={onView}>관전</button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 미션 카드 — 학생이 보는 핵심 UI
// ──────────────────────────────────────────────────────
function MissionCard({ m }: { m: Mission }) {
  const [open, setOpen] = useState(false)
  const sideColor = m.side === 'red' ? 'red' : 'blue'
  return (
    <div className="card" style={{ padding: 12,
      borderLeft: `4px solid var(--${sideColor})`,
      opacity: m.solved ? 0.7 : 1,
    }}>
      <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <span className={`badge ${sideColor}`} style={{ fontSize: 16 }}>{m.side === 'red' ? '🔴 RED' : '🔵 BLUE'} #{m.order}</span>
        {m.target_vm && <span style={{ fontSize: 18, color: 'var(--fg-dim)' }}>target: <code>{m.target_vm}</code></span>}
        {m.points > 0 && <span className="badge green" style={{ fontSize: 16 }}>+{m.points}점</span>}
        {m.solved && <span className="badge green" style={{ fontSize: 16 }}>✓ 자동 검증 통과</span>}
        <div style={{ flex: 1 }} />
        {(m.hint || m.semantic_intent || m.success_criteria.length > 0 || m.verify_expect) && (
          <button className="ghost" style={{ fontSize: 15, padding: '4px 12px' }}
            onClick={() => setOpen(o => !o)}>
            {open ? '상세 ▲' : '상세 ▼'}
          </button>
        )}
      </div>
      <div style={{ marginTop: 8, fontSize: 21, lineHeight: 1.5 }}>
        <b>할 일:</b> {m.instruction}
      </div>
      {open && (
        <div style={{ marginTop: 8, padding: 12, background: 'rgba(255,255,255,0.04)',
                      borderRadius: 6, fontSize: 19, lineHeight: 1.5 }}>
          {m.semantic_intent && (
            <div style={{ marginBottom: 8 }}>
              <b>의도/배경:</b> {m.semantic_intent}
            </div>
          )}
          {m.success_criteria.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <b>성공 조건:</b>
              <ul style={{ margin: '4px 0 0 22px', padding: 0 }}>
                {m.success_criteria.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          {m.verify_expect && (
            <div style={{ marginBottom: 8, fontSize: 17 }}>
              <b>검증 패턴:</b> <code>{m.verify_expect}</code>
            </div>
          )}
          {m.hint && (
            <details>
              <summary style={{ cursor: 'pointer', color: 'var(--yellow)' }}>💡 힌트 (스포일러)</summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                            fontSize: 17, margin: '6px 0 0' }}>{m.hint}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 이벤트 row — reasoning 자연어 + raw detail
// ──────────────────────────────────────────────────────
function EventRow({ e }: { e: BattleEvent }) {
  const [open, setOpen] = useState(false)
  const hasContent = !!e.reasoning || (e.detail && Object.keys(e.detail).length > 0)
  const g: any = e.detail?.grading
  const verdictBadge: Record<string, string> = { pass: 'green', partial: 'yellow', fail: 'red', review: 'yellow' }
  const verdictLabel: Record<string, string> = { pass: 'AI 통과', partial: 'AI 부분', fail: 'AI 불인정', review: '검토 대기' }
  return (
    <div className="card" style={{ padding: 12 }}>
      <div className="row" style={{ alignItems: 'center', fontSize: 14, flexWrap: 'wrap' }}>
        <span className={`badge ${eventTypePalette[e.event_type] || 'yellow'}`}>{e.event_type}</span>
        <span style={{ color: 'var(--fg-dim)' }}>{fmtTime(e.ts, true)}</span>
        {e.target && <span style={{ color: 'var(--fg-dim)' }}>target: <code>{e.target}</code></span>}
        {e.actor_user_id && <span style={{ color: 'var(--fg-dim)' }}>by user #{e.actor_user_id}</span>}
        {g?.ai_decided && g?.verdict && (
          <span className={`badge ${verdictBadge[g.verdict] || 'yellow'}`} style={{ fontSize: 13 }}>
            {verdictLabel[g.verdict] || g.verdict}
          </span>
        )}
        {e.points !== 0 && <span className={`badge ${e.points > 0 ? 'green' : 'red'}`} style={{ fontSize: 14 }}>
          {e.points > 0 ? '+' : ''}{e.points}점
        </span>}
        {g?.ai_decided && g?.claimed_points != null && g.claimed_points !== e.points && (
          <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>(신청 {g.claimed_points} → AI {g.awarded_points})</span>
        )}
        <div style={{ flex: 1 }} />
        {hasContent && (
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
            <div style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>{e.reasoning}</div>
          )}
          {e.detail && Object.keys(e.detail).length > 0 && (
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
// BattleView — 미션 패널 + 점수판 + 이벤트 + 힌트
// ──────────────────────────────────────────────────────
function BattleView({ b, meId, onClose, onStart, onEnd, onRefresh, onErr, myInfras }: {
  b: BattleDetail
  meId: number
  onClose: () => void
  onStart: () => void
  onEnd: () => void
  onRefresh: () => void
  onErr: (m: string) => void
  myInfras: Infra[]
}) {
  const isParticipant = b.participants.some(p => p.user_id === meId)
  const admin = isAdmin()
  const canControl = isParticipant || admin
  const canPostEvent = isParticipant
  const isLobby = b.battle.status === 'pending'

  const [eventForm, setEventForm] = useState<{
    event_type: string
    target: string
    description: string
    points: number
    mission_order: number | null
    mission_side: 'red' | 'blue' | null
    what_i_did: string
    what_happened: string
  }>({
    event_type: 'attack', target: '', description: '', points: 0,
    mission_order: null, mission_side: null,
    what_i_did: '', what_happened: '',
  })
  const [hint, setHint] = useState<HintOut | null>(null)
  const [hintBusy, setHintBusy] = useState(false)
  const [hintCool, setHintCool] = useState(0)
  const [hintSide, setHintSide] = useState<'red' | 'blue' | 'any'>('any')
  const [hintNote, setHintNote] = useState('')

  // join 다이얼로그 — 로비에서 BattleView 직접 열린 경우
  const [joinRole, setJoinRole] = useState<'red' | 'blue' | 'free'>(b.battle.mode === 'duel' ? 'red' : 'free')
  const [joinInfra, setJoinInfra] = useState<number | null>(myInfras[0]?.id ?? null)

  useEffect(() => {
    if (hintCool <= 0) return
    const t = setTimeout(() => setHintCool(c => Math.max(0, c - 1)), 1000)
    return () => clearTimeout(t)
  }, [hintCool])

  async function submitEvent(e: React.FormEvent) {
    e.preventDefault()
    // 백엔드 schema 와 일치하는 payload 만 전달 (mission_side null 이면 백엔드가 event_type 으로 추정)
    const payload: any = {
      event_type: eventForm.event_type,
      target: eventForm.target,
      description: eventForm.description,
      points: eventForm.points,
      what_i_did: eventForm.what_i_did,
      what_happened: eventForm.what_happened,
    }
    if (eventForm.mission_order) payload.mission_order = eventForm.mission_order
    if (eventForm.mission_side)  payload.mission_side  = eventForm.mission_side
    await api(`/battles/${b.battle.id}/events`, { method: 'POST', json: payload })
    setEventForm({
      ...eventForm, description: '', what_i_did: '', what_happened: '',
    })
    onRefresh()
  }

  async function joinHere() {
    try {
      await api<BattleDetail>(`/battles/${b.battle.id}/join`, {
        method: 'POST', json: { role: joinRole, infra_id: joinInfra },
      })
      onRefresh()
    } catch (e: any) { onErr(e.message) }
  }

  async function leaveHere() {
    try {
      await api<BattleDetail>(`/battles/${b.battle.id}/leave`, { method: 'POST' })
      onRefresh()
    } catch (e: any) { onErr(e.message) }
  }

  async function requestHint() {
    setHintBusy(true)
    try {
      const r = await api<HintOut>(`/battles/${b.battle.id}/hint`, {
        method: 'POST', json: { mission_side: hintSide, note: hintNote },
      })
      setHint(r)
      setHintCool(60)
    } catch (e: any) { onErr(`힌트 요청 실패: ${e.message}`) }
    finally { setHintBusy(false) }
  }

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
        {isParticipant && b.my_role &&
          <span className={`badge ${b.my_role === 'red' ? 'red' : b.my_role === 'blue' ? 'blue' : 'green'}`}>나: {b.my_role}</span>}
        <span className={`badge ${b.battle.status === 'active' ? 'green' : 'blue'}`}>{b.battle.status}</span>
      </div>

      {/* 로비 join/leave 패널 */}
      {isLobby && b.battle.mode !== 'solo' && (
        <div className="card" style={{ borderColor: 'var(--yellow)' }}>
          <h3 style={{ marginTop: 0 }}>🎮 로비 — 시작 대기 중</h3>
          {!isParticipant ? (
            <div className="row">
              <div style={{ flex: 1, color: 'var(--fg-dim)' }}>
                참여하려면 역할 + 인프라 선택 후 "참여" 클릭.
              </div>
              <select value={joinRole} onChange={e => setJoinRole(e.target.value as any)}>
                {b.battle.mode === 'duel' && <>
                  <option value="red">red (공격)</option>
                  <option value="blue">blue (방어)</option>
                </>}
                {b.battle.mode === 'ffa' && <>
                  <option value="free">free</option>
                  <option value="red">red</option>
                  <option value="blue">blue</option>
                </>}
              </select>
              <select value={joinInfra ?? ''} onChange={e => setJoinInfra(e.target.value ? parseInt(e.target.value) : null)}>
                <option value="">— 인프라 선택 —</option>
                {myInfras.map(i => <option key={i.id} value={i.id}>{i.name} ({i.vm_ip})</option>)}
              </select>
              <button onClick={joinHere} disabled={!joinInfra}>참여</button>
            </div>
          ) : (
            <div className="row">
              <div style={{ flex: 1 }}>
                ✓ 당신은 <b>{b.my_role}</b> 역할로 참여 중. 다른 참가자 대기.
              </div>
              <button className="ghost" onClick={leaveHere}>나가기</button>
            </div>
          )}
        </div>
      )}

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

      {/* 🎯 미션 패널 — 핵심 신규 UI */}
      {b.my_missions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3>🎯 내 미션 ({b.my_role})</h3>
          {b.my_missions.map(m => <MissionCard key={`${m.side}-${m.order}`} m={m} />)}
        </div>
      )}
      {b.opponent_missions.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: 'pointer', fontSize: 16, fontWeight: 600 }}>
            👀 상대편 미션 ({b.opponent_missions.length}개) — {isParticipant ? '관전 시야 (공격 정보)' : '관전 모드'}
          </summary>
          <div style={{ marginTop: 8 }}>
            {b.opponent_missions.map(m => <MissionCard key={`${m.side}-${m.order}`} m={m} />)}
          </div>
        </details>
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
          🔍 관전 모드 — read-only.
        </div>
      )}

      {/* 힌트 패널 */}
      {b.battle.hint_enabled && isParticipant && b.battle.status === 'active' && (
        <div className="card col" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>💡 힌트 요청</h3>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
            토큰 절약을 위해 동일 상태에선 동일 힌트가 캐시. 60초 cooldown.
          </div>
          <div className="row">
            <select value={hintSide} onChange={e => setHintSide(e.target.value as any)}>
              <option value="any">any (전체)</option>
              <option value="red">red (공격)</option>
              <option value="blue">blue (방어)</option>
            </select>
            <input style={{ flex: 1 }} placeholder="막힌 곳 (선택)"
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

      {canPostEvent && b.battle.status === 'active' && (
        <form onSubmit={submitEvent} className="card col" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 22 }}>📝 내가 한 일 보고 → AI 채점 요청</h3>
          <div style={{ fontSize: 15, color: 'var(--fg-dim)', lineHeight: 1.5 }}>
            ① 어느 미션? ② 어떤 명령/페이로드를 썼는가? ③ 결과/응답은 무엇이었는가?<br />
            제출하면 <b>AI 채점기가 너의 인프라를 직접 점검</b>(실제 실행한 명령·상태)해서 success_criteria
            기준으로 채점합니다. <b>점수는 AI 가 결정</b>하며, 아래 점수 칸은 참고용 신청값일 뿐입니다.
            (앰비언트 상태만으로는 통과되지 않으니, 네가 직접 한 명령을 정확히 적어 주세요.)
          </div>

          {/* ① 미션 선택 — my_missions 에서 골라 자동 채움 */}
          <label style={{ fontSize: 15, color: 'var(--fg-dim)', marginTop: 4 }}>
            ① 미션 선택
          </label>
          <select
            value={eventForm.mission_order ? `${eventForm.mission_side}-${eventForm.mission_order}` : ''}
            onChange={e => {
              const v = e.target.value
              if (!v) {
                setEventForm({ ...eventForm, mission_order: null, mission_side: null })
                return
              }
              const [side, orderStr] = v.split('-')
              const order = parseInt(orderStr, 10)
              const m = b.my_missions.find(x => x.side === side && x.order === order)
              if (!m) return
              setEventForm({
                ...eventForm,
                mission_order: order,
                mission_side: side as 'red' | 'blue',
                event_type: side === 'red' ? 'exploit' : 'detect',
                target: m.target_vm || eventForm.target,
                points: m.points,
                description: eventForm.description ||
                  `미션 #${m.order} — ${m.instruction.slice(0, 80)}`,
              })
            }}>
            <option value="">— 일반 보고 (미션 무관) —</option>
            {b.my_missions.map(m => (
              <option key={`${m.side}-${m.order}`} value={`${m.side}-${m.order}`}>
                {m.side === 'red' ? '🔴' : '🔵'} #{m.order} (+{m.points}점, {m.target_vm || '-'})
                {m.solved ? ' ✓' : ''} — {m.instruction.slice(0, 60)}
              </option>
            ))}
          </select>

          <div className="row" style={{ marginTop: 8 }}>
            <select value={eventForm.event_type}
              onChange={e => setEventForm({ ...eventForm, event_type: e.target.value })}
              style={{ flex: 1 }}>
              {['attack', 'exploit', 'defend', 'detect', 'block', 'alert', 'score'].map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input style={{ flex: 1 }} placeholder="target (예: juiceshop)" value={eventForm.target}
              onChange={e => setEventForm({ ...eventForm, target: e.target.value })} />
            <input type="number" style={{ width: 130 }} placeholder="신청점수(참고)"
              title="참고용 신청값 — 실제 점수는 AI 가 결정합니다"
              value={eventForm.points}
              onChange={e => setEventForm({ ...eventForm, points: parseInt(e.target.value || '0', 10) })} />
          </div>

          <input placeholder="한 줄 설명 (요약)"
            value={eventForm.description}
            onChange={e => setEventForm({ ...eventForm, description: e.target.value })} required />

          {/* ② 학생이 한 행위 — 분석의 핵심 입력 */}
          <label style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
            ② 사용한 명령 / 페이로드 (분석의 핵심 — 비워두면 채점 정확도 낮음)
          </label>
          <textarea
            rows={4}
            placeholder="예) hydra -l admin -P rockyou.txt 10.20.30.80 http-get-form '...:H=Cookie: security=low; PHPSESSID=...'"
            value={eventForm.what_i_did}
            onChange={e => setEventForm({ ...eventForm, what_i_did: e.target.value })}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />

          {/* ③ 결과/응답 */}
          <label style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
            ③ 결과 / 응답 발췌 (출력, 로그 라인, 에러 메시지 등)
          </label>
          <textarea
            rows={3}
            placeholder="예) [80][http-get-form] host: 10.20.30.80   login: admin   password: password"
            value={eventForm.what_happened}
            onChange={e => setEventForm({ ...eventForm, what_happened: e.target.value })}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />

          <button type="submit">이벤트 push (채점 분석 자동 생성)</button>
        </form>
      )}

      <h3 style={{ marginTop: 16 }}>이벤트 타임라인</h3>
      {b.events.slice().reverse().map(e => <EventRow key={e.id} e={e} />)}
    </>
  )
}
