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
interface Cohort {
  id: number; kind: string; name: string; parent_id: number | null;
  course_ref: string | null; created_at: string; member_count: number;
}
interface CohortMember {
  id: number; cohort_id: number; user_id: number;
  user_name: string | null; user_email: string | null;
  role: string | null; created_at: string;
}
interface AdminBattle {
  id: number; scenario_id: number | null; cohort_id: number | null; scenario_title: string | null;
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

interface StudentProgress {
  user_id: number; name: string | null; completion: number;
  steps_done: number; steps_total: number; bottleneck_flags: Record<string, any>; stuck: boolean
}
interface CohortProgress {
  cohort_id: number | null; battle_id: number | null; steps_total: number; students: StudentProgress[]
}
interface ActivityEvt {
  id: number; user_id: number | null; kind: string; scenario_step: number | null;
  payload: Record<string, any>; ts: string
}
interface AdminFeedback {
  id: number; user_id: number; cohort_id: number | null; battle_id: number | null;
  scope: string; trigger: string; content_md: string; model: string; delivered_to: string; created_at: string
}

interface AdminInfra {
  id: number; owner_id: number; owner_name: string | null; owner_email: string | null;
  name: string; vm_ip: string; ssh_user: string; bastion_api_key: string;
  port_map: Record<string, number>; status: string;
  last_smoke_at: string | null; last_smoke_ok: boolean | null; created_at: string
}

const TABS = ['stats', 'cohorts', 'infras', 'monitoring', 'feedback', 'generate', 'scrap', 'battles', 'users', 'scenarios'] as const
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
             : t === 'cohorts' ? '코호트'
             : t === 'infras' ? '인프라 관리'
             : t === 'monitoring' ? '실습 모니터링'
             : t === 'feedback' ? '피드백'
             : t === 'generate' ? '시나리오 생성'
             : t === 'scrap' ? 'Bastion 스크랩'
             : t === 'battles' ? '공방전 관리'
             : t === 'users' ? '사용자 관리'
             : '시나리오 관리'}
          </button>
        ))}
      </div>

      {tab === 'stats' && stats && <StatsTab s={stats} reload={refreshStats} />}
      {tab === 'cohorts' && <CohortsTab />}
      {tab === 'infras' && <InfrasTab />}
      {tab === 'monitoring' && <MonitoringTab />}
      {tab === 'feedback' && <FeedbackTab />}
      {tab === 'generate' && <GenerateTab onChange={refreshStats} />}
      {tab === 'scrap' && <ScrapTab onChange={refreshStats} />}
      {tab === 'battles' && <BattlesTab onChange={refreshStats} />}
      {tab === 'users' && <UsersTab />}
      {tab === 'scenarios' && <ScenariosTab onChange={refreshStats} />}
    </>
  )
}

function StatsTab({ s, reload }: { s: Stats; reload: () => void }) {
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [cohortId, setCohortId] = useState<string>('')
  const [scoped, setScoped] = useState<Stats | null>(null)

  useEffect(() => { api<Cohort[]>('/cohorts').then(setCohorts).catch(() => {}) }, [])
  useEffect(() => {
    if (!cohortId) { setScoped(null); return }
    api<Stats>(`/admin/stats?cohort_id=${cohortId}`).then(setScoped).catch(() => setScoped(null))
  }, [cohortId])
  const v = scoped ?? s

  return (
    <>
      <div className="row" style={{ marginBottom: 12, alignItems: 'center' }}>
        <label style={{ fontSize: 13, color: 'var(--fg-dim)' }}>코호트 필터</label>
        <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ width: 240 }}>
          <option value="">(전체 — 신원 포함)</option>
          {cohorts.map(c => (
            <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>
          ))}
        </select>
      </div>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <Card title="사용자" big={v.user_count} sub={`student ${v.student_count} · admin ${v.admin_count}`} />
        <Card title="시나리오 (활성)" big={v.scenario_validated} sub={`총 ${v.scenario_total} · draft ${v.scenario_draft}`} />
        <Card title="공방전" big={v.battles_total} sub={`active ${v.battles_active} · completed ${v.battles_completed}`} />
        <Card title="이벤트 누적" big={v.events_total} sub={`스크랩 대기 ${v.scrap_pending}`} />
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Top scorer{scoped ? ' (코호트)' : ''}</h3>
        {v.top_scorers.map((t, i) => (
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
  const [cohortId, setCohortId] = useState('')
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  useEffect(() => { api<Cohort[]>('/cohorts').then(setCohorts).catch(() => {}) }, [])
  const refresh = async () => {
    const qs: string[] = []
    if (filter) qs.push(`status_filter=${filter}`)
    if (cohortId) qs.push(`cohort_id=${cohortId}`)
    const url = qs.length ? `/admin/battles?${qs.join('&')}` : '/admin/battles'
    setBattles(await api<AdminBattle[]>(url))
  }
  useEffect(() => { refresh() }, [filter, cohortId])

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
        <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ width: 200 }}>
          <option value="">코호트: 전체</option>
          {cohorts.map(c => <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>)}
        </select>
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

const COHORT_KINDS = ['department', 'grade', 'course', 'section', 'team'] as const

function CohortsTab() {
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [sel, setSel] = useState<number | null>(null)
  const [members, setMembers] = useState<CohortMember[]>([])
  const [err, setErr] = useState<string | null>(null)

  // 새 노드 폼
  const [kind, setKind] = useState<string>('department')
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState<string>('')
  const [courseRef, setCourseRef] = useState('')
  // 멤버 추가 폼
  const [memUser, setMemUser] = useState<string>('')

  async function refresh() {
    try {
      const [c, u] = await Promise.all([
        api<Cohort[]>('/cohorts'),
        api<AdminUser[]>('/admin/users'),
      ])
      setCohorts(c); setUsers(u)
    } catch (e: any) { setErr(e.message) }
  }
  useEffect(() => { refresh() }, [])

  async function loadMembers(id: number) {
    setSel(id)
    try { setMembers(await api<CohortMember[]>(`/cohorts/${id}/members`)) }
    catch (e: any) { setErr(e.message) }
  }

  async function createNode(e: React.FormEvent) {
    e.preventDefault(); setErr(null)
    try {
      await api('/cohorts', { method: 'POST', json: {
        kind, name, parent_id: parentId ? Number(parentId) : null,
        course_ref: courseRef || null,
      }})
      setName(''); setCourseRef(''); await refresh()
    } catch (e: any) { setErr(e.message) }
  }

  async function delNode(id: number) {
    if (!confirm(`코호트 #${id} 삭제? (하위 노드·멤버십 함께 삭제)`)) return
    try { await api(`/cohorts/${id}`, { method: 'DELETE' }); if (sel === id) setSel(null); await refresh() }
    catch (e: any) { setErr(e.message) }
  }

  async function addMember() {
    if (!sel || !memUser) return
    try {
      await api(`/cohorts/${sel}/members`, { method: 'POST', json: { user_id: Number(memUser) } })
      setMemUser(''); await loadMembers(sel); await refresh()
    } catch (e: any) { setErr(e.message) }
  }

  async function removeMember(uid: number) {
    if (!sel) return
    try { await api(`/cohorts/${sel}/members/${uid}`, { method: 'DELETE' }); await loadMembers(sel); await refresh() }
    catch (e: any) { setErr(e.message) }
  }

  async function moveMember(uid: number, to: string) {
    if (!sel || !to) return
    try {
      await api('/cohorts/members/move', { method: 'POST', json: {
        user_id: uid, from_cohort_id: sel, to_cohort_id: Number(to),
      }})
      await loadMembers(sel); await refresh()
    } catch (e: any) { setErr(e.message) }
  }

  async function openSiem(id: number) {
    try {
      const r = await api<{ deeplink: string | null; enabled: boolean; cohort_path: string }>(
        `/monitoring/cohorts/${id}/siem`)
      if (r.enabled && r.deeplink) window.open(r.deeplink, '_blank')
      else alert(`중앙 SIEM 미설정(disabled). 코호트 경로: ${r.cohort_path}\n(데이터뷰/RBAC 는 OPENSEARCH_URL 설정 시 자동 생성됩니다.)`)
    } catch (e: any) { setErr(e.message) }
  }

  const byParent = (pid: number | null) =>
    cohorts.filter(c => c.parent_id === pid).sort((a, b) => a.name.localeCompare(b.name))

  function renderNode(c: Cohort, depth: number): React.ReactNode {
    return (
      <div key={c.id}>
        <div className="row" style={{
          alignItems: 'center', padding: '6px 8px', marginLeft: depth * 18,
          borderLeft: depth ? '1px solid var(--border)' : undefined,
          background: sel === c.id ? 'rgba(255,255,255,0.04)' : undefined, borderRadius: 4,
        }}>
          <span className="badge blue">{c.kind}</span>
          <b style={{ cursor: 'pointer' }} onClick={() => loadMembers(c.id)}>{c.name}</b>
          {c.course_ref && <code style={{ fontSize: 11 }}>{c.course_ref}</code>}
          <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>멤버 {c.member_count}</span>
          <div style={{ flex: 1 }} />
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => loadMembers(c.id)}>멤버</button>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => openSiem(c.id)}>SIEM</button>
          <button className="danger" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => delNode(c.id)}>삭제</button>
        </div>
        {byParent(c.id).map(ch => renderNode(ch, depth + 1))}
      </div>
    )
  }

  return (
    <>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      <form onSubmit={createNode} className="card col">
        <h3 style={{ marginTop: 0 }}>코호트 노드 추가</h3>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <label>종류
            <select value={kind} onChange={e => setKind(e.target.value)}>
              {COHORT_KINDS.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>
          <label style={{ flex: 1 }}>이름
            <input value={name} onChange={e => setName(e.target.value)} required placeholder="정보보안과 / 2학년 / A분반..." />
          </label>
          <label>상위 노드
            <select value={parentId} onChange={e => setParentId(e.target.value)}>
              <option value="">(루트)</option>
              {cohorts.map(c => <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>)}
            </select>
          </label>
          <label>course_ref
            <input value={courseRef} onChange={e => setCourseRef(e.target.value)} placeholder="course3" style={{ width: 120 }} />
          </label>
        </div>
        <button type="submit">노드 생성</button>
      </form>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>트리</h3>
          {cohorts.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>없음.</div>}
          {byParent(null).map(c => renderNode(c, 0))}
        </div>

        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>멤버 {sel ? `(코호트 #${sel})` : ''}</h3>
          {!sel && <div style={{ color: 'var(--fg-dim)' }}>← 트리에서 노드 선택</div>}
          {sel && (
            <>
              <div className="row" style={{ marginBottom: 8 }}>
                <select value={memUser} onChange={e => setMemUser(e.target.value)} style={{ flex: 1 }}>
                  <option value="">학생 선택…</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
                </select>
                <button onClick={addMember}>배치</button>
              </div>
              {members.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>멤버 없음.</div>}
              {members.map(m => (
                <div key={m.id} className="row" style={{ alignItems: 'center', padding: '4px 0', borderTop: '1px solid var(--border)' }}>
                  <span>{m.user_name}</span>
                  <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{m.user_email}</span>
                  <div style={{ flex: 1 }} />
                  <select defaultValue="" onChange={e => moveMember(m.user_id, e.target.value)} style={{ width: 150, fontSize: 12 }}>
                    <option value="">이동…</option>
                    {cohorts.filter(c => c.id !== sel).map(c => (
                      <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>
                    ))}
                  </select>
                  <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => removeMember(m.user_id)}>제거</button>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </>
  )
}

function MonitoringTab() {
  const [battles, setBattles] = useState<AdminBattle[]>([])
  const [bid, setBid] = useState<number | null>(null)
  const [prog, setProg] = useState<CohortProgress | null>(null)
  const [timeline, setTimeline] = useState<ActivityEvt[]>([])
  const [drillUser, setDrillUser] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api<AdminBattle[]>('/admin/battles').then(setBattles).catch(e => setErr(e.message)) }, [])

  async function loadProgress(id: number) {
    setBid(id); setTimeline([]); setDrillUser(null)
    try { setProg(await api<CohortProgress>(`/monitoring/battles/${id}/progress`)) }
    catch (e: any) { setErr(e.message) }
  }
  async function tick() {
    if (!bid) return
    setBusy(true)
    try {
      await api(`/monitoring/battles/${bid}/lab-tick?with_feedback=true`, { method: 'POST' })
      await loadProgress(bid)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  async function drill(uid: number) {
    if (!bid) return
    setDrillUser(uid)
    try { setTimeline(await api<ActivityEvt[]>(`/monitoring/battles/${bid}/activity?user_id=${uid}`)) }
    catch (e: any) { setErr(e.message) }
  }
  async function makeFeedback(uid: number) {
    if (!bid) return
    try {
      await api(`/feedback/students/${uid}`, { method: 'POST', json: { battle_id: bid, delivered_to: 'both' } })
      alert('피드백 생성됨 (학생 대시보드 + 피드백 탭)')
    } catch (e: any) { setErr(e.message) }
  }

  return (
    <>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>실습 모니터링 (진도·병목)</h3>
        <div style={{ flex: 1 }} />
        <select value={bid ?? ''} onChange={e => e.target.value && loadProgress(Number(e.target.value))} style={{ width: 280 }}>
          <option value="">battle 선택…</option>
          {battles.map(b => <option key={b.id} value={b.id}>#{b.id} {b.scenario_title || ''} [{b.status}]</option>)}
        </select>
        <button onClick={tick} disabled={!bid || busy}>{busy ? '...' : '지금 점검'}</button>
      </div>

      {prog && (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
                <th align="left" style={{ padding: 10 }}>학생</th>
                <th align="left" style={{ padding: 10 }}>진도</th>
                <th align="left" style={{ padding: 10 }}>step</th>
                <th align="left" style={{ padding: 10 }}>병목</th>
                <th align="left" style={{ padding: 10 }}>액션</th>
              </tr>
            </thead>
            <tbody>
              {prog.students.map(s => (
                <tr key={s.user_id} style={{ borderTop: '1px solid var(--border)',
                  background: s.stuck ? 'rgba(255,80,80,0.08)' : undefined }}>
                  <td style={{ padding: 10 }}>{s.name || `user-${s.user_id}`} {s.stuck && <span className="badge red">막힘</span>}</td>
                  <td style={{ padding: 10 }}>{s.completion}%</td>
                  <td style={{ padding: 10 }}>{s.steps_done}/{s.steps_total}</td>
                  <td style={{ padding: 10, fontSize: 12 }}>{Object.keys(s.bottleneck_flags).join(', ') || '-'}</td>
                  <td style={{ padding: 10 }}>
                    <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => drill(s.user_id)}>타임라인</button>{' '}
                    <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => makeFeedback(s.user_id)}>피드백 생성</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {drillUser && (
        <div className="card" style={{ marginTop: 12 }}>
          <h4 style={{ marginTop: 0 }}>활동 타임라인 (user #{drillUser})</h4>
          {timeline.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>활동 없음.</div>}
          {timeline.map(e => (
            <div key={e.id} style={{ fontSize: 12, padding: '3px 0', borderTop: '1px solid var(--border)' }}>
              <span className="badge blue">{e.kind}</span>{' '}
              <code>{JSON.stringify(e.payload).slice(0, 160)}</code>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function FeedbackTab() {
  const [rows, setRows] = useState<AdminFeedback[]>([])
  const [err, setErr] = useState<string | null>(null)
  const refresh = async () => { try { setRows(await api<AdminFeedback[]>('/feedback')) } catch (e: any) { setErr(e.message) } }
  useEffect(() => { refresh() }, [])
  async function regen(id: number) {
    try { await api(`/feedback/${id}/regenerate`, { method: 'POST' }); refresh() }
    catch (e: any) { setErr(e.message) }
  }
  return (
    <>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      <h3>학생 피드백 검토</h3>
      {rows.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>피드백 없음.</div>}
      {rows.map(f => (
        <div key={f.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>user #{f.user_id}</b>
            <span className="badge blue">{f.scope}</span>
            <span className="badge yellow">{f.trigger}</span>
            <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{f.model} · {f.delivered_to}</span>
            <div style={{ flex: 1 }} />
            <button className="ghost" onClick={() => regen(f.id)}>재생성</button>
          </div>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginTop: 6, fontFamily: 'inherit' }}>{f.content_md}</pre>
        </div>
      ))}
    </>
  )
}

function InfrasTab() {
  const [rows, setRows] = useState<AdminInfra[]>([])
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [cohortId, setCohortId] = useState('')
  const [statusF, setStatusF] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  const [msg, setMsg] = useState<Record<number, string>>({})
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api<Cohort[]>('/cohorts').then(setCohorts).catch(() => {}) }, [])
  async function refresh() {
    const qs: string[] = []
    if (cohortId) qs.push(`cohort_id=${cohortId}`)
    if (statusF) qs.push(`status_filter=${statusF}`)
    try { setRows(await api<AdminInfra[]>(`/admin/infras${qs.length ? '?' + qs.join('&') : ''}`)) }
    catch (e: any) { setErr(e.message) }
  }
  useEffect(() => { refresh() }, [cohortId, statusF])

  async function smoke(id: number) {
    setBusy(id); setErr(null)
    try {
      const r = await api<{ ok: boolean; summary: string }>(`/admin/infras/${id}/smoke`, { method: 'POST' })
      setMsg(m => ({ ...m, [id]: `smoke: ${r.ok ? 'OK' : 'DEGRADED'} — ${r.summary}` }))
      await refresh()
    } catch (e: any) { setErr(e.message) } finally { setBusy(null) }
  }
  async function assessCheck(id: number) {
    setBusy(id); setErr(null)
    try {
      const r = await api<{ assessor_ok: boolean; bastion_ok: boolean; evidence: string | null; error: string | null }>(
        `/admin/infras/${id}/assess-check`, { method: 'POST' })
      setMsg(m => ({ ...m, [id]: `채점도달성: assessor=${r.assessor_ok ? '✓' : '✗'} bastion=${r.bastion_ok ? '✓' : '✗'}${r.error ? ' (' + r.error + ')' : ''}${r.evidence ? ' · ' + r.evidence.slice(0, 60) : ''}` }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(null) }
  }
  async function del(id: number, who: string) {
    if (!confirm(`${who} 의 인프라 #${id} 를 삭제할까요?`)) return
    try { await api(`/admin/infras/${id}`, { method: 'DELETE' }); await refresh() }
    catch (e: any) { setErr(e.message) }
  }

  const badge = (s: string) => s === 'healthy' ? 'green' : s === 'degraded' ? 'red' : 'yellow'

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>등록 인프라 관리 ({rows.length})</h3>
        <div style={{ flex: 1 }} />
        <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ width: 190 }}>
          <option value="">코호트: 전체</option>
          {cohorts.map(c => <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>)}
        </select>
        <select value={statusF} onChange={e => setStatusF(e.target.value)} style={{ width: 140 }}>
          <option value="">상태: 전체</option>
          <option value="registered">registered</option>
          <option value="healthy">healthy</option>
          <option value="degraded">degraded</option>
        </select>
        <button className="ghost" onClick={refresh}>새로고침</button>
      </div>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
              <th align="left" style={{ padding: 10 }}>소유자</th>
              <th align="left" style={{ padding: 10 }}>이름</th>
              <th align="left" style={{ padding: 10 }}>vm_ip</th>
              <th align="left" style={{ padding: 10 }}>상태</th>
              <th align="left" style={{ padding: 10 }}>last smoke</th>
              <th align="left" style={{ padding: 10 }}>액션</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} style={{ padding: 14, color: 'var(--fg-dim)' }}>등록된 인프라 없음.</td></tr>}
            {rows.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: 10 }}>{r.owner_name}<div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>{r.owner_email}</div></td>
                <td style={{ padding: 10 }}>{r.name}</td>
                <td style={{ padding: 10 }}><code>{r.vm_ip}</code>{r.port_map?.assessor ? <span style={{ fontSize: 11, color: 'var(--fg-dim)' }}> :assessor={r.port_map.assessor}</span> : null}</td>
                <td style={{ padding: 10 }}><span className={`badge ${badge(r.status)}`}>{r.status}</span></td>
                <td style={{ padding: 10, fontSize: 12, color: 'var(--fg-dim)' }}>
                  {r.last_smoke_at ? `${r.last_smoke_at.slice(0, 16).replace('T', ' ')} (${r.last_smoke_ok ? 'ok' : 'fail'})` : '—'}
                  {msg[r.id] && <div style={{ marginTop: 4, color: 'var(--fg)' }}>{msg[r.id]}</div>}
                </td>
                <td style={{ padding: 10, whiteSpace: 'nowrap' }}>
                  <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} disabled={busy === r.id} onClick={() => smoke(r.id)}>smoke</button>{' '}
                  <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} disabled={busy === r.id} onClick={() => assessCheck(r.id)}>채점확인</button>{' '}
                  <button className="danger" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => del(r.id, r.owner_name || `user-${r.owner_id}`)}>삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
