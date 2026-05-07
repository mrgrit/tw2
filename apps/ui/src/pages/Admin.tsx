import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

interface Job {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  request: string
  course_ref: string | null
  weeks_spec: string | null
  queued_at: string
  started_at: string | null
  finished_at: string | null
  scenario_id: number | null
  preview: any
  meta: any
  error: string | null
  dry_run_status?: string
  dry_run?: any
}
interface Draft {
  id: number; title: string; description: string; source: string;
  status: string; time_limit_sec: number;
}
interface ScrapPost {
  id: number; source: string; source_url: string; title: string; summary: string;
  relevance: any; status: 'pending' | 'approved' | 'rejected';
  decided_at: string | null; spawned_scenario_id: number | null; created_at: string;
}
interface AdminBattle {
  id: number; scenario_id: number | null; scenario_title: string | null;
  mode: string; status: string; monitor: string;
  started_at: string | null; ended_at: string | null;
  time_limit_sec: number; elapsed_sec: number;
  participant_count: number; event_count: number; monitor_running: boolean;
  created_at: string;
}
interface AdminUser {
  id: number; email: string; name: string; role: string;
  is_active: boolean; created_at: string;
}
interface Stats {
  user_count: number; student_count: number; admin_count: number;
  scenario_total: number; scenario_validated: number; scenario_draft: number;
  scrap_pending: number; battles_total: number; battles_active: number;
  battles_completed: number; events_total: number;
  top_scorers: { user_id: number; name: string; total_score: number }[];
}

const TABS = ['stats', 'generate', 'scrap', 'battles', 'users', 'scenarios'] as const
type Tab = typeof TABS[number]

export default function Admin() {
  const [tab, setTab] = useState<Tab>('stats')
  const [stats, setStats] = useState<Stats | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function refreshStats() {
    try { setStats(await api<Stats>('/admin/stats')) }
    catch (e: any) { setErr(e.message) }
  }
  useEffect(() => { refreshStats() }, [])

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>관리자 대시보드</h1>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}

      <div className="row" style={{ marginBottom: 16, gap: 6, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t}
            className={t === tab ? '' : 'ghost'}
            onClick={() => setTab(t)}>
            {t === 'stats' ? '통계'
             : t === 'generate' ? '시나리오 생성'
             : t === 'scrap' ? 'Bastion 스크랩'
             : t === 'battles' ? '공방전 관리'
             : t === 'users' ? '사용자 관리'
             : '시나리오 관리'}
          </button>
        ))}
      </div>

      {tab === 'stats' && stats && <StatsTab s={stats} reload={refreshStats} />}
      {tab === 'generate' && <GenerateTab onChange={refreshStats} />}
      {tab === 'scrap' && <ScrapTab onChange={refreshStats} />}
      {tab === 'battles' && <BattlesTab onChange={refreshStats} />}
      {tab === 'users' && <UsersTab />}
      {tab === 'scenarios' && <ScenariosTab onChange={refreshStats} />}
    </>
  )
}

function StatsTab({ s, reload }: { s: Stats; reload: () => void }) {
  return (
    <>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <Card title="사용자" big={s.user_count} sub={`student ${s.student_count} · admin ${s.admin_count}`} />
        <Card title="시나리오 (활성)" big={s.scenario_validated} sub={`총 ${s.scenario_total} · draft ${s.scenario_draft}`} />
        <Card title="공방전" big={s.battles_total} sub={`active ${s.battles_active} · completed ${s.battles_completed}`} />
        <Card title="이벤트 누적" big={s.events_total} sub={`스크랩 대기 ${s.scrap_pending}`} />
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Top scorer</h3>
        {s.top_scorers.map((t, i) => (
          <div key={t.user_id} className="row" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <span style={{ width: 40, fontSize: 18 }}>
              {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i+1}`}
            </span>
            <span style={{ flex: 1 }}>{t.name}</span>
            <b>{t.total_score}</b>
          </div>
        ))}
      </div>
      <button className="ghost" onClick={reload}>새로고침</button>
    </>
  )
}

function Card({ title, big, sub }: { title: string; big: number; sub: string }) {
  return (
    <div className="card" style={{ flex: '1 0 220px' }}>
      <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>{title}</div>
      <div style={{ fontSize: 32, fontWeight: 700, marginTop: 6 }}>{big}</div>
      <div style={{ color: 'var(--fg-dim)', fontSize: 12 }}>{sub}</div>
    </div>
  )
}

function GenerateTab({ onChange }: { onChange: () => void }) {
  const [request, setRequest] = useState('')
  const [courseRef, setCourseRef] = useState('course3')
  const [weeksSpec, setWeeksSpec] = useState('1-3')
  const [jobs, setJobs] = useState<Job[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function refresh() {
    try {
      const [j, d] = await Promise.all([
        api<Job[]>('/admin/scenarios/jobs'),
        api<Draft[]>('/admin/scenarios/drafts'),
      ])
      setJobs(j); setDrafts(d)
    } catch (e: any) { setErr(e.message) }
  }
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    const has = jobs.some(j => j.status === 'queued' || j.status === 'running'
                            || (j.dry_run_status === 'running'))
    if (!has) return
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [jobs])

  async function generate(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      await api('/admin/scenarios/generate', { method: 'POST',
        json: { request, course_ref: courseRef || null, weeks_spec: weeksSpec || null }})
      setRequest(''); await refresh(); onChange()
    } catch (e: any) { setErr(e.message) }
    finally { setBusy(false) }
  }
  async function activate(id: number) {
    await api(`/admin/scenarios/${id}/activate`, { method: 'POST', json: { activate: true } })
    await refresh(); onChange()
  }

  return (
    <>
      <form onSubmit={generate} className="card col">
        <h3 style={{ marginTop: 0 }}>Claude Code 로 새 공방전 시나리오</h3>
        <div className="row">
          <label style={{ flex: 1 }}>과목
            <input value={courseRef} onChange={e => setCourseRef(e.target.value)} placeholder="course3" />
          </label>
          <label style={{ width: 160 }}>주차
            <input value={weeksSpec} onChange={e => setWeeksSpec(e.target.value)} placeholder="1-3" />
          </label>
        </div>
        <label>요청
          <textarea value={request} onChange={e => setRequest(e.target.value)}
            rows={3} required placeholder="예: SQL 인젝션 + WAF 우회 1v1 공방전"/>
        </label>
        {err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>}
        <button type="submit" disabled={busy}>{busy ? '...' : '생성'}</button>
      </form>

      <h3>생성 작업</h3>
      {jobs.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
      {jobs.map(j => (
        <div key={j.id} className="card" style={{ padding: 12 }}>
          <div className="row" style={{ alignItems: 'center' }}>
            <span className={`badge ${j.status === 'completed' ? 'green' : j.status === 'failed' ? 'red' : 'yellow'}`}>{j.status}</span>
            {j.dry_run_status && <span className={`badge ${
              j.dry_run_status === 'completed' ? 'green'
              : j.dry_run_status === 'failed' ? 'red'
              : j.dry_run_status === 'running' ? 'yellow' : 'blue'
            }`}>dry_run: {j.dry_run_status}</span>}
            <code style={{ fontSize: 11 }}>{j.id}</code>
            <div style={{ flex: 1 }} />
            {j.scenario_id && <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>→ #{j.scenario_id}</span>}
          </div>
          <div style={{ marginTop: 6, fontSize: 13 }}>{j.request}</div>
          {j.preview && (
            <div style={{ marginTop: 6, padding: 6, background: 'rgba(255,255,255,0.03)', borderRadius: 4, fontSize: 12 }}>
              <b>{j.preview.title}</b> · {j.preview.difficulty} · red {j.preview.red_count}/blue {j.preview.blue_count}
              {j.dry_run?.pass_rate != null && (
                <span style={{ marginLeft: 8 }}>
                  · pass_rate {j.dry_run.pass_rate}
                </span>
              )}
            </div>
          )}
          {j.error && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 4 }}>{j.error}</div>}
        </div>
      ))}

      <h3 style={{ marginTop: 32 }}>승인 대기 draft</h3>
      {drafts.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
      {drafts.map(d => (
        <div key={d.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>#{d.id} {d.title}</b>
            <span className="badge blue">{d.source}</span>
            <div style={{ flex: 1 }} />
            <button onClick={() => activate(d.id)}>승인</button>
          </div>
          <div style={{ marginTop: 6, color: 'var(--fg-dim)', fontSize: 13 }}>
            {d.description.length > 240 ? d.description.slice(0, 240) + '…' : d.description}
          </div>
        </div>
      ))}
    </>
  )
}

function ScrapTab({ onChange }: { onChange: () => void }) {
  const [scrap, setScrap] = useState<ScrapPost[]>([])
  const refresh = async () => setScrap(await api<ScrapPost[]>('/admin/scrap'))
  useEffect(() => { refresh() }, [])
  return (
    <>
      <div className="row">
        <h3 style={{ margin: 0 }}>Bastion 스크랩 게시판</h3>
        <div style={{ flex: 1 }} />
        <button className="ghost" onClick={async () => { await api('/admin/scrap/seed', { method: 'POST' }); refresh() }}>
          스크랩 새로고침
        </button>
      </div>
      {scrap.map(s => (
        <div key={s.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <span className={`badge ${s.status === 'pending' ? 'yellow' : s.status === 'approved' ? 'green' : 'red'}`}>{s.status}</span>
            <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{s.source}</span>
            <a href={s.source_url} target="_blank" style={{ fontSize: 12 }}>↗</a>
            <div style={{ flex: 1 }} />
            {s.status === 'pending' && (
              <>
                <button onClick={async () => { await api(`/admin/scrap/${s.id}/approve`, { method: 'POST' }); refresh(); onChange() }}>
                  승인 → 시나리오 생성
                </button>
                <button className="danger" onClick={async () => { await api(`/admin/scrap/${s.id}/reject`, { method: 'POST' }); refresh() }}>반려</button>
              </>
            )}
            {s.spawned_scenario_id && <span className="badge blue">scenario #{s.spawned_scenario_id}</span>}
          </div>
          <div style={{ marginTop: 8, fontSize: 14 }}><b>{s.title}</b></div>
          <div style={{ marginTop: 4, color: 'var(--fg-dim)', fontSize: 13 }}>
            {s.summary.length > 280 ? s.summary.slice(0, 280) + '…' : s.summary}
          </div>
          {s.relevance?.kg_match && (
            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--fg-dim)' }}>
              KG: {(s.relevance.kg_match as string[]).join(', ')}
              {s.relevance.education_score != null && ` · 가치 ${s.relevance.education_score}`}
            </div>
          )}
        </div>
      ))}
    </>
  )
}

function BattlesTab({ onChange }: { onChange: () => void }) {
  const [battles, setBattles] = useState<AdminBattle[]>([])
  const [filter, setFilter] = useState('')
  const refresh = async () => {
    const url = filter ? `/admin/battles?status_filter=${filter}` : '/admin/battles'
    setBattles(await api<AdminBattle[]>(url))
  }
  useEffect(() => { refresh() }, [filter])

  async function forceEnd(id: number) {
    if (!confirm(`battle #${id} 강제 종료 (cancelled)?`)) return
    await api(`/admin/battles/${id}/force-end`, { method: 'POST' })
    refresh(); onChange()
  }
  async function delBattle(id: number) {
    if (!confirm(`battle #${id} 영구 삭제?`)) return
    await api(`/admin/battles/${id}`, { method: 'DELETE' })
    refresh(); onChange()
  }

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>공방전 관리</h3>
        <div style={{ flex: 1 }} />
        <select value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 160 }}>
          <option value="">all</option>
          <option value="pending">pending</option>
          <option value="active">active</option>
          <option value="completed">completed</option>
          <option value="cancelled">cancelled</option>
        </select>
      </div>
      {battles.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
      {battles.map(b => (
        <div key={b.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>#{b.id}</b>
            <span className="badge blue">{b.mode}</span>
            <span className={`badge ${b.status === 'active' ? 'green' : b.status === 'completed' ? 'blue' : 'yellow'}`}>{b.status}</span>
            <span className="badge yellow" style={{ visibility: b.monitor_running ? 'visible' : 'hidden' }}>
              monitor●
            </span>
            <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>
              {b.scenario_title || '(no scenario)'} · {b.participant_count} 명 · {b.event_count} 이벤트
            </span>
            <div style={{ flex: 1 }} />
            {(b.status === 'active' || b.status === 'pending') && (
              <button className="danger" onClick={() => forceEnd(b.id)}>강제 종료</button>
            )}
            <button className="ghost" onClick={() => delBattle(b.id)}>삭제</button>
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--fg-dim)' }}>
            elapsed {Math.round(b.elapsed_sec)}s / limit {Math.round(b.time_limit_sec / 60)}분 · monitor: {b.monitor}
          </div>
        </div>
      ))}
    </>
  )
}

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const refresh = async () => setUsers(await api<AdminUser[]>('/admin/users'))
  useEffect(() => { refresh() }, [])

  async function patch(id: number, body: any) {
    await api(`/admin/users/${id}`, { method: 'PATCH', json: body })
    refresh()
  }
  return (
    <>
      <h3>사용자 관리</h3>
      <div className="card" style={{ padding: 0 }}>
        <table style={{ width: '100%', fontSize: 14, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
              <th align="left" style={{ padding: 12 }}>id</th>
              <th align="left" style={{ padding: 12 }}>email</th>
              <th align="left" style={{ padding: 12 }}>name</th>
              <th align="left" style={{ padding: 12 }}>role</th>
              <th align="left" style={{ padding: 12 }}>active</th>
              <th align="left" style={{ padding: 12 }}>actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: 12 }}>{u.id}</td>
                <td style={{ padding: 12 }}>{u.email}</td>
                <td style={{ padding: 12 }}>{u.name}</td>
                <td style={{ padding: 12 }}>
                  <span className={`badge ${u.role === 'admin' ? 'blue' : 'yellow'}`}>{u.role}</span>
                </td>
                <td style={{ padding: 12 }}>
                  <span className={`badge ${u.is_active ? 'green' : 'red'}`}>{u.is_active ? 'on' : 'off'}</span>
                </td>
                <td style={{ padding: 12 }}>
                  {u.role === 'student' ? (
                    <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }}
                      onClick={() => patch(u.id, { role: 'admin' })}>→ admin</button>
                  ) : (
                    <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }}
                      onClick={() => patch(u.id, { role: 'student' })}>→ student</button>
                  )}
                  {' '}
                  <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }}
                    onClick={() => patch(u.id, { is_active: !u.is_active })}>
                    {u.is_active ? '비활성화' : '활성화'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function ScenariosTab({ onChange }: { onChange: () => void }) {
  const [scenarios, setScenarios] = useState<Draft[]>([])
  const refresh = async () => {
    const all = await api<Draft[]>('/scenarios')
    const drafts = await api<Draft[]>('/admin/scenarios/drafts')
    const seen = new Set(all.map(s => s.id))
    setScenarios([...all, ...drafts.filter(d => !seen.has(d.id))])
  }
  useEffect(() => { refresh() }, [])

  async function patch(id: number, body: any) {
    await api(`/admin/scenarios/${id}`, { method: 'PATCH', json: body })
    refresh(); onChange()
  }
  async function del(id: number) {
    if (!confirm(`scenario #${id} 삭제?`)) return
    await api(`/admin/scenarios/${id}`, { method: 'DELETE' })
    refresh(); onChange()
  }

  return (
    <>
      <h3>시나리오 관리</h3>
      {scenarios.map(s => (
        <div key={s.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>#{s.id} {s.title}</b>
            <span className={`badge ${s.status === 'validated' ? 'green' : s.status === 'archived' ? 'red' : 'yellow'}`}>{s.status}</span>
            <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{s.source}</span>
            <div style={{ flex: 1 }} />
            {s.status !== 'archived' && (
              <button className="ghost" onClick={() => patch(s.id, { status: 'archived' })}>archive</button>
            )}
            {s.status === 'archived' && (
              <button className="ghost" onClick={() => patch(s.id, { status: 'validated' })}>복원</button>
            )}
            <button className="danger" onClick={() => del(s.id)}>삭제</button>
          </div>
        </div>
      ))}
    </>
  )
}
