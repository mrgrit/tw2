import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { fmtTime } from '../time.ts'

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
  status: string; time_limit_sec: number; grader_profile_id?: number | null;
  category?: string | null;
}

// 교과목 카테고리 라벨/색 — 시나리오 그룹핑·필터·뱃지에 공용 사용
const CATEGORY_LABEL: Record<string, string> = {
  'secuops-easy': '보안운영 입문', 'secuops': '보안운영', 'soc': 'SOC 관제', 'attack': '공격기법',
}
const CATEGORY_COLOR: Record<string, string> = {
  'secuops-easy': 'green', 'secuops': 'blue', 'soc': 'yellow', 'attack': 'red',
}
const catLabel = (c?: string | null) => (c ? (CATEGORY_LABEL[c] || c) : '미분류')
const catColor = (c?: string | null) => (c ? (CATEGORY_COLOR[c] || 'blue') : '')
interface Grader {
  id: number; name: string; provider: 'cc' | 'bastion'; model: string;
  base_url: string | null; has_api_key: boolean; enabled: boolean; is_default: boolean; created_at: string;
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

const TABS = ['stats', 'cohorts', 'infras', 'monitoring', 'siem', 'feedback', 'generate', 'scrap', 'battles', 'users', 'scenarios', 'graders'] as const
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
             : t === 'siem' ? '중앙 SIEM'
             : t === 'feedback' ? '피드백'
             : t === 'generate' ? '시나리오 생성'
             : t === 'scrap' ? 'Bastion 스크랩'
             : t === 'battles' ? '공방전 관리'
             : t === 'users' ? '사용자 관리'
             : t === 'scenarios' ? '시나리오 관리'
             : 'AI 채점기'}
          </button>
        ))}
      </div>

      {tab === 'stats' && stats && <StatsTab s={stats} reload={refreshStats} />}
      {tab === 'cohorts' && <CohortsTab />}
      {tab === 'infras' && <InfrasTab />}
      {tab === 'monitoring' && <MonitoringTab />}
      {tab === 'siem' && <SiemTab />}
      {tab === 'feedback' && <FeedbackTab />}
      {tab === 'generate' && <GenerateTab onChange={refreshStats} />}
      {tab === 'scrap' && <ScrapTab onChange={refreshStats} />}
      {tab === 'battles' && <BattlesTab onChange={refreshStats} />}
      {tab === 'users' && <UsersTab />}
      {tab === 'scenarios' && <ScenariosTab onChange={refreshStats} />}
      {tab === 'graders' && <GradersTab />}
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
  const [graders, setGraders] = useState<Grader[]>([])
  const [catFilter, setCatFilter] = useState('')
  const refresh = async () => {
    const all = await api<Draft[]>('/scenarios')
    const drafts = await api<Draft[]>('/admin/scenarios/drafts')
    const seen = new Set(all.map(s => s.id))
    setScenarios([...all, ...drafts.filter(d => !seen.has(d.id))])
  }
  useEffect(() => { refresh(); api<Grader[]>('/admin/graders').then(setGraders).catch(() => {}) }, [])

  async function patch(id: number, body: any) {
    await api(`/admin/scenarios/${id}`, { method: 'PATCH', json: body })
    refresh(); onChange()
  }
  async function del(id: number) {
    if (!confirm(`scenario #${id} 삭제?`)) return
    await api(`/admin/scenarios/${id}`, { method: 'DELETE' })
    refresh(); onChange()
  }

  // 카테고리별 그룹핑 (알려진 카테고리 우선순서 → 기타 → 미분류)
  const order = ['secuops-easy', 'secuops', 'soc', 'attack']
  const cats = Array.from(new Set(scenarios.map(s => s.category || ''))).sort((a, b) => {
    const ia = a ? (order.indexOf(a) < 0 ? 98 : order.indexOf(a)) : 99
    const ib = b ? (order.indexOf(b) < 0 ? 98 : order.indexOf(b)) : 99
    return ia - ib
  })
  const counts: Record<string, number> = {}
  scenarios.forEach(s => { const k = s.category || ''; counts[k] = (counts[k] || 0) + 1 })
  const shown = catFilter ? cats.filter(c => c === catFilter) : cats

  function card(s: Draft) {
    return (
      <div key={s.id} className="card">
        <div className="row" style={{ alignItems: 'center' }}>
          <b>#{s.id} {s.title}</b>
          {s.category && <span className={`badge ${catColor(s.category)}`}>{catLabel(s.category)}</span>}
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
        <div className="row" style={{ alignItems: 'center', marginTop: 6, fontSize: 13 }}>
          <span style={{ color: 'var(--fg-dim)' }}>채점 AI:</span>
          <select value={s.grader_profile_id ?? ''}
            onChange={e => patch(s.id, { grader_profile_id: e.target.value ? Number(e.target.value) : 0 })}
            style={{ width: 280 }}>
            <option value="">기본 ({graders.find(g => g.is_default)?.name || 'CC(claude-haiku)'})</option>
            {graders.filter(g => g.enabled).map(g => (
              <option key={g.id} value={g.id}>{g.name} — {g.provider}:{g.model}</option>
            ))}
          </select>
          {graders.length === 0 && <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>(채점기 미등록 — "AI 채점기" 탭에서 등록)</span>}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="row" style={{ alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>시나리오 관리</h3>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>카테고리</span>
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}>
          <option value="">전체 ({scenarios.length})</option>
          {cats.map(c => <option key={c} value={c}>{catLabel(c)} ({counts[c]})</option>)}
        </select>
      </div>
      {/* 카테고리 칩 줄 — 클릭 시 필터 */}
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {cats.map(c => (
          <span key={c} className={`badge ${catColor(c)}`} style={{ cursor: 'pointer', opacity: catFilter && catFilter !== c ? 0.4 : 1 }}
            onClick={() => setCatFilter(catFilter === c ? '' : c)}>
            {catLabel(c)} <b>{counts[c]}</b>
          </span>
        ))}
      </div>
      {shown.map(c => (
        <div key={c || 'none'} style={{ marginBottom: 18 }}>
          <div style={{ borderBottom: '2px solid var(--border)', paddingBottom: 4, marginBottom: 10, fontWeight: 700 }}>
            {catLabel(c)} <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>· {counts[c]}개</span>
          </div>
          {scenarios.filter(s => (s.category || '') === c).sort((a, b) => a.id - b.id).map(card)}
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
                  {r.last_smoke_at ? `${fmtTime(r.last_smoke_at)} (${r.last_smoke_ok ? 'ok' : 'fail'})` : '—'}
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

function GradersTab() {
  const [rows, setRows] = useState<Grader[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [f, setF] = useState<{ name: string; provider: 'cc' | 'bastion'; model: string; base_url: string; api_key: string; is_default: boolean }>(
    { name: '', provider: 'cc', model: 'claude-haiku-4-5', base_url: '', api_key: '', is_default: false })

  const refresh = async () => { try { setRows(await api<Grader[]>('/admin/graders')) } catch (e: any) { setErr(e.message) } }
  useEffect(() => { refresh() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null)
    try {
      await api('/admin/graders', { method: 'POST', json: {
        name: f.name, provider: f.provider, model: f.model,
        base_url: f.provider === 'bastion' ? f.base_url : null,
        api_key: f.provider === 'bastion' ? (f.api_key || null) : null,
        is_default: f.is_default,
      }})
      setF({ ...f, name: '', api_key: '' }); await refresh()
    } catch (e: any) { setErr(e.message) }
  }
  async function patch(id: number, body: any) { try { await api(`/admin/graders/${id}`, { method: 'PATCH', json: body }); refresh() } catch (e: any) { setErr(e.message) } }
  async function del(id: number, name: string) { if (!confirm(`채점기 '${name}' 삭제?`)) return; try { await api(`/admin/graders/${id}`, { method: 'DELETE' }); refresh() } catch (e: any) { setErr(e.message) } }

  return (
    <>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      <form onSubmit={create} className="card col">
        <h3 style={{ marginTop: 0 }}>AI 채점기 등록</h3>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <label>이름<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required placeholder="예: CC-haiku / Bastion-gptoss" /></label>
          <label>제공자
            <select value={f.provider} onChange={e => {
              const provider = e.target.value as 'cc' | 'bastion'
              setF({ ...f, provider, model: provider === 'cc' ? 'claude-haiku-4-5' : 'gpt-oss:120b' })
            }}>
              <option value="cc">CC (Claude Code)</option>
              <option value="bastion">Bastion (6v6 LLM)</option>
            </select>
          </label>
          <label style={{ flex: 1 }}>모델
            <input value={f.model} onChange={e => setF({ ...f, model: e.target.value })} required
              placeholder={f.provider === 'cc' ? 'claude-haiku-4-5 / claude-opus-4-8' : 'gpt-oss:120b / gemma3:4b'} />
          </label>
        </div>
        {f.provider === 'bastion' && (
          <div className="row">
            <label style={{ flex: 1 }}>base_url<input value={f.base_url} onChange={e => setF({ ...f, base_url: e.target.value })} required placeholder="http://10.0.0.80:9100" /></label>
            <label style={{ flex: 1 }}>API key (X-API-Key)<input value={f.api_key} onChange={e => setF({ ...f, api_key: e.target.value })} placeholder="ccc-api-key-2026" /></label>
          </div>
        )}
        <label style={{ fontSize: 13 }}>
          <input type="checkbox" checked={f.is_default} onChange={e => setF({ ...f, is_default: e.target.checked })} style={{ width: 'auto', marginRight: 6 }} />
          기본 채점기로 설정 (시나리오가 따로 지정 안 하면 이걸 사용)
        </label>
        <button type="submit">등록</button>
      </form>

      <h3>등록된 채점기 ({rows.length})</h3>
      {rows.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음 — CC 기본(claude-haiku)로 채점됩니다.</div>}
      {rows.map(g => (
        <div key={g.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>{g.name}</b>
            <span className={`badge ${g.provider === 'cc' ? 'blue' : 'yellow'}`}>{g.provider}</span>
            <code>{g.model}</code>
            {g.base_url && <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{g.base_url}{g.has_api_key ? ' 🔑' : ''}</span>}
            {g.is_default && <span className="badge green">기본</span>}
            {!g.enabled && <span className="badge red">비활성</span>}
            <div style={{ flex: 1 }} />
            {!g.is_default && <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => patch(g.id, { is_default: true })}>기본으로</button>}{' '}
            <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => patch(g.id, { enabled: !g.enabled })}>{g.enabled ? '비활성화' : '활성화'}</button>{' '}
            <button className="danger" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => del(g.id, g.name)}>삭제</button>
          </div>
        </div>
      ))}
    </>
  )
}

interface SiemDoc {
  student: number | null; student_name?: string | null; infra: number | null;
  ts: string | null; kind: string | null;
  cohort_path: string | null; cohort_id: number | null; payload: any;
  battle_id: number | null; scenario_id?: number | null; scenario_step?: number | null
}
interface SiemSearch {
  enabled: boolean; index: string | null; cohort_path: string | null;
  dashboards_deeplink: string | null; docs: SiemDoc[]; note: string | null
}
interface SiemStats {
  enabled: boolean; index: string | null; total: number; note?: string | null;
  by_kind: { key: string; count: number }[];
  by_student: { student: number; name: string | null; count: number }[];
  by_scenario: { scenario_id: number; title: string | null; count: number }[];
  by_day: { date: string; count: number }[];
  pivot: { student: number; name: string | null; total: number; kinds: Record<string, number> }[];
}
interface SiemMission { side: string; order: number | null; instruction: string; points: number | null }
interface SiemScenario { scenario_id: number; title: string; battle_ids: number[]; missions: SiemMission[] }
interface ClearRow {
  student: number; name: string | null; cleared: number; steps_total: number;
  battles: number; stuck: number; completion: number
}
interface AskOut { answer: string; model: string; used_logs: number; used_clears: number; cost_usd: number }

const KIND_COLOR: Record<string, string> = { command: 'blue', alert: 'red', fim: 'yellow', service: 'green' }

function SiemTab() {
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [cohortId, setCohortId] = useState('')
  const [scenarios, setScenarios] = useState<SiemScenario[]>([])
  const [scenarioId, setScenarioId] = useState('')
  const [range, setRange] = useState('now-7d')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [studentFilter, setStudentFilter] = useState('')

  const [stats, setStats] = useState<SiemStats | null>(null)
  const [search, setSearch] = useState<SiemSearch | null>(null)
  const [clears, setClears] = useState<ClearRow[]>([])
  const [selDoc, setSelDoc] = useState<SiemDoc | null>(null)
  const [showDash, setShowDash] = useState(false)
  const [dashLink, setDashLink] = useState<string | null>(null)

  const [graders, setGraders] = useState<Grader[]>([])
  const [graderId, setGraderId] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskOut | null>(null)
  const [missionSel, setMissionSel] = useState<{ side: string; order: number | null } | null>(null)
  const [missionRes, setMissionRes] = useState<any | null>(null)

  async function openMission(side: string, order: number | null) {
    if (!cohortId || order == null || !scenarioId) return
    if (missionSel?.side === side && missionSel?.order === order) { setMissionSel(null); setMissionRes(null); return }
    setMissionSel({ side, order }); setMissionRes(null)
    try {
      const r = await api<any>(`/monitoring/siem/mission?cohort_id=${cohortId}&scenario_id=${scenarioId}&side=${side}&order=${order}`)
      setMissionRes(r)
    } catch (e: any) { setMissionRes({ results: [], error: e.message }) }
  }
  const [asking, setAsking] = useState(false)

  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Cohort[]>('/cohorts').then(setCohorts).catch(() => {})
    api<Grader[]>('/admin/graders').then(g => setGraders(g.filter(x => x.enabled))).catch(() => {})
  }, [])

  function timeVals(): { time_from?: string; time_to?: string } {
    if (dateFrom || dateTo) return {
      time_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
      time_to: dateTo ? `${dateTo}T23:59:59` : undefined,
    }
    return range ? { time_from: range } : {}
  }
  function filterQS(): string {
    const t = timeVals()
    const p = new URLSearchParams()
    if (cohortId) p.set('cohort_id', cohortId)
    if (scenarioId) p.set('scenario_id', scenarioId)
    if (kindFilter) p.set('kind', kindFilter)
    if (studentFilter) p.set('student', studentFilter)
    if (t.time_from) p.set('time_from', t.time_from)
    if (t.time_to) p.set('time_to', t.time_to)
    return p.toString()
  }

  async function load() {
    setBusy(true); setErr(null)
    try {
      const qs = filterQS()
      const [st, se] = await Promise.all([
        api<SiemStats>(`/monitoring/siem/stats?${qs}`),
        api<SiemSearch>(`/monitoring/siem/search?limit=300&${qs}`),
      ])
      setStats(st); setSearch(se)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  // 코호트 변경 → 시나리오/클리어 재로딩 + 시나리오 선택 초기화
  useEffect(() => {
    setScenarioId(''); setShowDash(false); setDashLink(null)
    if (!cohortId) { setScenarios([]); setClears([]); return }
    api<{ scenarios: SiemScenario[] }>(`/monitoring/siem/scenarios?cohort_id=${cohortId}`)
      .then(r => setScenarios(r.scenarios)).catch(() => setScenarios([]))
    // 코호트 선택 시 OSD 데이터뷰/저장검색/대시보드를 멱등 생성하고 딥링크 확보 → 바로 펼침
    api<{ deeplink: string | null; enabled: boolean }>(`/monitoring/cohorts/${cohortId}/siem`)
      .then(r => { setDashLink(r.deeplink); if (r.deeplink) setShowDash(true) })
      .catch(() => setDashLink(null))
  }, [cohortId])
  useEffect(() => {
    if (!cohortId) { setClears([]); return }
    const q = scenarioId ? `&scenario_id=${scenarioId}` : ''
    api<{ students: ClearRow[] }>(`/monitoring/siem/clears?cohort_id=${cohortId}${q}`)
      .then(r => setClears(r.students)).catch(() => setClears([]))
  }, [cohortId, scenarioId])
  // 필터 변경 → 통계+로그 재로딩
  useEffect(() => { load() }, [cohortId, scenarioId, range, dateFrom, dateTo, kindFilter, studentFilter])

  async function ask() {
    if (!question.trim()) return
    setAsking(true); setAnswer(null); setErr(null)
    try {
      const t = timeVals()
      const r = await api<AskOut>('/monitoring/siem/ask', {
        method: 'POST', json: {
          question, cohort_id: cohortId ? Number(cohortId) : null,
          scenario_id: scenarioId ? Number(scenarioId) : null,
          student: studentFilter ? Number(studentFilter) : null,
          kind: kindFilter || null, ...t,
          grader_profile_id: graderId ? Number(graderId) : null,
        },
      })
      setAnswer(r)
    } catch (e: any) { setErr(e.message) } finally { setAsking(false) }
  }

  const selScn = scenarios.find(s => String(s.scenario_id) === scenarioId)
  const studentName = (id: number | null) =>
    stats?.by_student.find(s => s.student === id)?.name
    || clears.find(c => c.student === id)?.name || `#${id}`

  return (
    <div style={{ fontSize: '1.05em' }}>
      {/* ── 필터 바 ── */}
      <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>중앙 SIEM · 활동 분석</h3>
        <div style={{ flex: 1 }} />
        <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ minWidth: 200 }}>
          <option value="">전체 코호트</option>
          {cohorts.map(c => <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>)}
        </select>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          disabled={!cohortId} title="시나리오 드릴다운" style={{ minWidth: 180 }}>
          <option value="">{cohortId ? '전체 시나리오' : '코호트 먼저 선택'}</option>
          {scenarios.map(s => <option key={s.scenario_id} value={s.scenario_id}>#{s.scenario_id} {s.title}</option>)}
        </select>
        <select value={range} onChange={e => { setRange(e.target.value); setDateFrom(''); setDateTo('') }} title="기간">
          <option value="now-1d">최근 1일</option>
          <option value="now-7d">최근 7일</option>
          <option value="now-30d">최근 30일</option>
          <option value="now-365d">최근 1년</option>
          <option value="">전체</option>
        </select>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} title="시작일(범위 지정)" />
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} title="종료일" />
        <button className="ghost" onClick={load} disabled={busy}>{busy ? '…' : '새로고침'}</button>
        {dashLink && (
          <>
            <button className="ghost" onClick={() => setShowDash(v => !v)}>{showDash ? 'Dashboards 숨기기' : 'Dashboards 펼치기'}</button>
            <a href={dashLink} target="_blank" rel="noreferrer"><button className="ghost">↗ 새 탭</button></a>
          </>
        )}
      </div>

      {/* 활성 필터 칩 */}
      {(kindFilter || studentFilter) && (
        <div className="row" style={{ gap: 6, marginBottom: 10, alignItems: 'center' }}>
          <span style={{ color: 'var(--fg-dim)', fontSize: 13 }}>필터:</span>
          {kindFilter && <span className="badge blue" style={{ cursor: 'pointer' }} onClick={() => setKindFilter('')}>kind={kindFilter} ✕</span>}
          {studentFilter && <span className="badge yellow" style={{ cursor: 'pointer' }} onClick={() => setStudentFilter('')}>학생 {studentName(Number(studentFilter))} ✕</span>}
        </div>
      )}

      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}
      {stats && !stats.enabled && (
        <div className="card" style={{ color: 'var(--fg-dim)' }}>
          중앙 SIEM 비활성. {stats.note}
          <div style={{ marginTop: 6, fontSize: 12 }}>서버 env <code>OPENSEARCH_URL</code> 설정 시 활성화됩니다.</div>
        </div>
      )}

      {/* ── 주요 통계 (테이블 위) ── */}
      {stats?.enabled && (
        <div className="row" style={{ flexWrap: 'wrap', marginBottom: 12, alignItems: 'stretch' }}>
          <div className="card" style={{ minWidth: 130 }}>
            <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>총 이벤트</div>
            <div style={{ fontSize: 30, fontWeight: 700, color: 'var(--primary)' }}>{stats.total}</div>
            <div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>{stats.by_day.length}일 · {stats.by_student.length}명</div>
          </div>
          <div className="card" style={{ flex: 1, minWidth: 200 }}>
            <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 6 }}>종류별 (클릭하면 필터)</div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {stats.by_kind.length === 0 && <span style={{ color: 'var(--fg-dim)' }}>—</span>}
              {stats.by_kind.map(k => (
                <span key={k.key} className={`badge ${KIND_COLOR[k.key] || 'blue'}`}
                  style={{ cursor: 'pointer', opacity: kindFilter && kindFilter !== k.key ? 0.4 : 1 }}
                  onClick={() => setKindFilter(kindFilter === k.key ? '' : k.key)}>
                  {k.key} <b>{k.count}</b>
                </span>
              ))}
            </div>
          </div>
          <div className="card" style={{ flex: 1, minWidth: 220 }}>
            <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 6 }}>활동 많은 학생 (클릭하면 필터)</div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {stats.by_student.length === 0 && <span style={{ color: 'var(--fg-dim)' }}>—</span>}
              {stats.by_student.slice(0, 8).map(s => (
                <span key={s.student} className="badge"
                  style={{ cursor: 'pointer', opacity: studentFilter && studentFilter !== String(s.student) ? 0.4 : 1 }}
                  onClick={() => setStudentFilter(studentFilter === String(s.student) ? '' : String(s.student))}>
                  {s.name || `#${s.student}`} <b>{s.count}</b>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── 시나리오 미션 레벨 (드릴다운 시) ── */}
      {selScn && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>#{selScn.scenario_id} {selScn.title} · 미션 {selScn.missions.length}개 · 공방전 {selScn.battle_ids.length}건</div>
          <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginBottom: 6 }}>미션 클릭 → 학생별 채점결과 드릴다운</div>
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            {selScn.missions.map((m, i) => {
              const sel = missionSel?.side === m.side && missionSel?.order === m.order
              return (
                <span key={i} className={`badge ${m.side === 'red' ? 'red' : 'blue'}`} title={m.instruction}
                  onClick={() => openMission(m.side, m.order)}
                  style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', outline: sel ? '2px solid var(--primary)' : 'none' }}>
                  {m.side} #{m.order} · {m.points}점 · {m.instruction}
                </span>
              )
            })}
          </div>

          {/* 미션 → 학생별 채점결과 (마지막 레벨) */}
          {missionSel && (
            <div style={{ marginTop: 10, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                {missionSel.side} #{missionSel.order} — 학생별 결과 {missionRes ? `(${missionRes.results.length}명)` : '…'}
              </div>
              {missionRes && missionRes.results.length === 0 && (
                <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>이 미션에 대한 학생 제출 기록 없음.</div>
              )}
              {missionRes?.results.map((r: any) => {
                const vColor: Record<string, string> = { pass: 'green', partial: 'yellow', fail: 'red', review: 'yellow' }
                const vLabel: Record<string, string> = { pass: 'AI 통과', partial: 'AI 부분', fail: 'AI 불인정', review: '검토대기' }
                return (
                  <div key={r.student} className="card" style={{ marginBottom: 6, padding: 10 }}>
                    <div className="row" style={{ alignItems: 'center', gap: 8 }}>
                      <b>{r.name || `#${r.student}`}</b>
                      {r.verdict && <span className={`badge ${vColor[r.verdict] || 'yellow'}`}>{vLabel[r.verdict] || r.verdict}</span>}
                      <span className={`badge ${r.points > 0 ? 'green' : 'red'}`}>{r.points}점</span>
                      {r.claimed != null && r.claimed !== r.points && <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>(신청 {r.claimed}→AI {r.awarded})</span>}
                      <span style={{ fontSize: 11, color: 'var(--fg-dim)' }}>battle #{r.battle_id}</span>
                    </div>
                    {r.reasoning && <div style={{ marginTop: 6, fontSize: 12, whiteSpace: 'pre-wrap', color: 'var(--fg-dim)' }}>{r.reasoning.slice(0, 600)}</div>}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── AI 분석 Q&A ── */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row" style={{ alignItems: 'center', marginBottom: 8 }}>
          <b>AI 로그 분석</b>
          <span style={{ color: 'var(--fg-dim)', fontSize: 12 }}>현재 필터(코호트/시나리오/기간/학생)의 로그·통계·클리어를 근거로 답변</span>
          <div style={{ flex: 1 }} />
          <select value={graderId} onChange={e => setGraderId(e.target.value)} title="AI/모델 선택">
            <option value="">기본 채점기</option>
            {graders.map(g => <option key={g.id} value={g.id}>{g.provider}: {g.name} ({g.model})</option>)}
          </select>
        </div>
        <textarea value={question} onChange={e => setQuestion(e.target.value)} rows={2}
          placeholder="예: 어떤 학생이 막혀 있고 왜? 가장 의심스러운 공격 활동은? 방어가 약한 지점은?"
          style={{ width: '100%', boxSizing: 'border-box', background: 'var(--bg)', color: 'var(--fg)', border: '1px solid var(--border)', borderRadius: 6, padding: 8 }} />
        <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
          <button onClick={ask} disabled={asking || !question.trim()}>{asking ? 'AI 분석 중… (최대 ~2분)' : 'AI에게 질문'}</button>
          {answer && <span style={{ color: 'var(--fg-dim)', fontSize: 12 }}>모델 {answer.model} · 로그 {answer.used_logs}건 · 클리어 {answer.used_clears}명{answer.cost_usd ? ` · $${answer.cost_usd.toFixed(4)}` : ''}</span>}
        </div>
        {answer && (
          <div style={{ marginTop: 10, padding: 12, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
            {answer.answer}
          </div>
        )}
      </div>

      {/* ── 학생별 클리어 ── */}
      {cohortId && (
        <div className="card" style={{ padding: 0, marginBottom: 12, overflowX: 'auto' }}>
          <div style={{ padding: '8px 12px', fontSize: 13, color: 'var(--fg-dim)' }}>
            학생별 클리어 (완수 미션){scenarioId ? ' · 선택 시나리오 한정' : ''} — {clears.length}명
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead><tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
              <th align="left" style={{ padding: 8 }}>학생</th>
              <th align="left" style={{ padding: 8 }}>클리어</th>
              <th align="left" style={{ padding: 8 }}>완성도</th>
              <th align="left" style={{ padding: 8 }}>공방전</th>
              <th align="left" style={{ padding: 8 }}>상태</th>
            </tr></thead>
            <tbody>
              {clears.length === 0 && <tr><td colSpan={5} style={{ padding: 14, color: 'var(--fg-dim)' }}>이 코호트의 공방전 진도 데이터 없음.</td></tr>}
              {clears.map(c => (
                <tr key={c.student} style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                  onClick={() => setStudentFilter(studentFilter === String(c.student) ? '' : String(c.student))}>
                  <td style={{ padding: 8 }}>{c.name || `#${c.student}`}</td>
                  <td style={{ padding: 8 }}><b>{c.cleared}</b> / {c.steps_total}</td>
                  <td style={{ padding: 8 }}>
                    <div style={{ background: 'var(--border)', borderRadius: 4, height: 8, width: 90, overflow: 'hidden' }}>
                      <div style={{ width: `${c.completion}%`, height: '100%', background: c.completion >= 70 ? 'var(--green)' : c.completion >= 30 ? 'var(--yellow)' : 'var(--red)' }} />
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--fg-dim)' }}>{c.completion}%</span>
                  </td>
                  <td style={{ padding: 8 }}>{c.battles}</td>
                  <td style={{ padding: 8 }}>{c.stuck > 0 ? <span className="badge red">막힘 {c.stuck}</span> : <span className="badge green">정상</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 피벗 분석 (raw 로그 나열 대신 의미있는 집계) ── */}
      {stats?.enabled && (() => {
        const kindCols = stats.by_kind.map(k => k.key)
        const maxScn = Math.max(1, ...stats.by_scenario.map(s => s.count))
        const maxDay = Math.max(1, ...stats.by_day.map(d => d.count))
        return (
          <div className="col" style={{ gap: 12 }}>
            {/* 학생 × 종류 피벗 매트릭스 */}
            <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
              <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--fg-dim)' }}>
                피벗: 학생 × 활동종류 (셀 클릭 시 해당 학생 필터)
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead><tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
                  <th align="left" style={{ padding: 8 }}>학생</th>
                  {kindCols.map(k => <th key={k} align="right" style={{ padding: 8 }}><span className={`badge ${KIND_COLOR[k] || 'blue'}`}>{k}</span></th>)}
                  <th align="right" style={{ padding: 8 }}>합계</th>
                </tr></thead>
                <tbody>
                  {stats.pivot.length === 0 && <tr><td colSpan={kindCols.length + 2} style={{ padding: 14, color: 'var(--fg-dim)' }}>활동 데이터 없음.</td></tr>}
                  {stats.pivot.map(r => (
                    <tr key={r.student} style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                      onClick={() => setStudentFilter(studentFilter === String(r.student) ? '' : String(r.student))}>
                      <td style={{ padding: 8, fontWeight: 600 }}>{r.name || `#${r.student}`}</td>
                      {kindCols.map(k => <td key={k} align="right" style={{ padding: 8, color: r.kinds[k] ? 'var(--fg)' : 'var(--fg-dim)' }}>{r.kinds[k] || 0}</td>)}
                      <td align="right" style={{ padding: 8, fontWeight: 700, color: 'var(--primary)' }}>{r.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="row" style={{ flexWrap: 'wrap', alignItems: 'stretch' }}>
              {/* 시나리오별 */}
              <div className="card" style={{ flex: 1, minWidth: 280 }}>
                <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 8 }}>시나리오별 활동량 (클릭 시 드릴다운)</div>
                {stats.by_scenario.length === 0 && <span style={{ color: 'var(--fg-dim)' }}>—</span>}
                {stats.by_scenario.map(s => (
                  <div key={s.scenario_id} className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 4, cursor: 'pointer' }}
                    onClick={() => setScenarioId(scenarioId === String(s.scenario_id) ? '' : String(s.scenario_id))}>
                    <div style={{ width: 200, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={s.title || `#${s.scenario_id}`}>{s.title || `#${s.scenario_id}`}</div>
                    <div style={{ flex: 1, background: 'var(--border)', borderRadius: 4, height: 14, overflow: 'hidden' }}>
                      <div style={{ width: `${(s.count / maxScn) * 100}%`, height: '100%', background: 'var(--primary)' }} />
                    </div>
                    <b style={{ width: 44, textAlign: 'right' }}>{s.count}</b>
                  </div>
                ))}
              </div>
              {/* 일자별 */}
              <div className="card" style={{ flex: 1, minWidth: 240 }}>
                <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 8 }}>일자별 추이</div>
                {stats.by_day.length === 0 && <span style={{ color: 'var(--fg-dim)' }}>—</span>}
                {stats.by_day.map(d => (
                  <div key={d.date} className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ width: 90, fontSize: 12, color: 'var(--fg-dim)' }}>{String(d.date).slice(0, 10)}</div>
                    <div style={{ flex: 1, background: 'var(--border)', borderRadius: 4, height: 14, overflow: 'hidden' }}>
                      <div style={{ width: `${(d.count / maxDay) * 100}%`, height: '100%', background: 'var(--green)' }} />
                    </div>
                    <b style={{ width: 44, textAlign: 'right' }}>{d.count}</b>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )
      })()}

      {/* ── Dashboards iframe (펼침 시) ── */}
      {dashLink && showDash && (
        <div className="card" style={{ padding: 0, marginTop: 12, overflow: 'hidden' }}>
          <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--fg-dim)' }}>
            OpenSearch Dashboards (이 코호트 전용) — 막대/시계열·필드 탐색. 아래 임베드:
          </div>
          <iframe title="siem-dashboard" src={dashLink}
            style={{ width: '100%', height: 600, border: 0 }} />
        </div>
      )}
      {cohortId && !dashLink && (
        <div className="card" style={{ marginTop: 12, color: 'var(--fg-dim)', fontSize: 13 }}>
          Dashboards iframe 비활성 — 서버 env <code>OPENSEARCH_DASHBOARDS_URL</code> 가 설정돼야 표시됩니다.
          (네이티브 통계·로그·AI 분석은 위에서 그대로 사용 가능)
        </div>
      )}

      {/* ── 풀 로그 모달 ── */}
      {selDoc && (
        <div onClick={() => setSelDoc(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" onClick={e => e.stopPropagation()} style={{ maxWidth: 760, width: '90%', maxHeight: '85vh', overflow: 'auto' }}>
            <div className="row" style={{ alignItems: 'center', marginBottom: 8 }}>
              <b>전체 로그</b>
              <span className={`badge ${KIND_COLOR[selDoc.kind || ''] || 'blue'}`}>{selDoc.kind}</span>
              <span style={{ color: 'var(--fg-dim)', fontSize: 12 }}>{fmtTime(selDoc.ts, true)} · {selDoc.student_name || studentName(selDoc.student)}</span>
              <div style={{ flex: 1 }} />
              <button className="ghost" onClick={() => setSelDoc(null)}>닫기 ✕</button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginBottom: 8 }}>
              {selDoc.cohort_path} {selDoc.scenario_id ? `· 시나리오 #${selDoc.scenario_id}` : ''} {selDoc.battle_id ? `· 공방전 #${selDoc.battle_id}` : ''}
            </div>
            <pre style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: 12, overflow: 'auto', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {JSON.stringify(selDoc.payload, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
