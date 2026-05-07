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
}

interface Draft {
  id: number
  title: string
  description: string
  source: string
  status: string
  time_limit_sec: number
}

export default function Admin() {
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
      setJobs(j)
      setDrafts(d)
    } catch (e: any) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [])

  // 진행중 job 있으면 2초마다 폴링
  useEffect(() => {
    const has = jobs.some(j => j.status === 'queued' || j.status === 'running')
    if (!has) return
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [jobs])

  async function generate(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      await api('/admin/scenarios/generate', {
        method: 'POST',
        json: { request, course_ref: courseRef || null, weeks_spec: weeksSpec || null },
      })
      setRequest('')
      await refresh()
    } catch (e: any) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function activate(id: number) {
    await api(`/admin/scenarios/${id}/activate`, { method: 'POST', json: { activate: true } })
    await refresh()
  }

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>관리자 — 시나리오 생성</h1>

      <form onSubmit={generate} className="card col">
        <h3 style={{ marginTop: 0 }}>Claude Code 로 새 공방전 시나리오</h3>
        <div className="row">
          <label style={{ flex: 1 }}>
            과목 (course_ref)
            <input value={courseRef} onChange={e => setCourseRef(e.target.value)}
              placeholder="course3" />
          </label>
          <label style={{ width: 160 }}>
            주차 (weeks_spec)
            <input value={weeksSpec} onChange={e => setWeeksSpec(e.target.value)}
              placeholder="1-3" />
          </label>
        </div>
        <label>
          자연어 요청
          <textarea value={request} onChange={e => setRequest(e.target.value)}
            rows={3} placeholder="예: course3 1~3주차 내용으로 SQL 인젝션과 WAF 우회를 다루는 1v1 공방전 만들어줘. 난이도 중급."
            required />
        </label>
        {err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>}
        <button type="submit" disabled={busy}>{busy ? '...' : '생성 (background)'}</button>
        <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
          Claude CLI subprocess 호출 — 5~30초 소요. 모델 기본 <code>haiku-4-5</code>,
          env <code>TUBEWAR_CLAUDE_MODEL</code> 으로 변경 가능.
        </div>
      </form>

      <h3>생성 작업</h3>
      {jobs.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>아직 없음.</div>}
      {jobs.map(j => (
        <div key={j.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <span className={`badge ${
              j.status === 'completed' ? 'green'
              : j.status === 'failed' ? 'red'
              : j.status === 'running' ? 'yellow' : 'blue'
            }`}>{j.status}</span>
            <code style={{ marginLeft: 4 }}>{j.id}</code>
            <div style={{ flex: 1 }} />
            {j.scenario_id && (
              <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>
                → scenario #{j.scenario_id}
              </span>
            )}
          </div>
          <div style={{ marginTop: 8, fontSize: 14 }}>{j.request}</div>
          {j.course_ref && (
            <div style={{ fontSize: 12, color: 'var(--fg-dim)', marginTop: 4 }}>
              context: {j.course_ref} / weeks {j.weeks_spec}
            </div>
          )}
          {j.preview && (
            <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
              <b>{j.preview.title}</b> · {j.preview.difficulty} · {Math.round(j.preview.time_limit_sec/60)}분 ·
              red {j.preview.red_count} / blue {j.preview.blue_count}
            </div>
          )}
          {j.meta?.cost_usd != null && (
            <div style={{ fontSize: 11, color: 'var(--fg-dim)', marginTop: 4 }}>
              ${(j.meta.cost_usd as number).toFixed(4)} · {j.meta.duration_ms}ms · ctx {j.meta.lecture_chars} chars
            </div>
          )}
          {j.error && <div style={{ marginTop: 8, color: 'var(--red)', fontSize: 13 }}>{j.error}</div>}
        </div>
      ))}

      <h3 style={{ marginTop: 32 }}>승인 대기 중 draft</h3>
      {drafts.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>없음.</div>}
      {drafts.map(d => (
        <div key={d.id} className="card">
          <div className="row" style={{ alignItems: 'center' }}>
            <b>#{d.id} {d.title}</b>
            <span className="badge blue">{d.source}</span>
            <div style={{ flex: 1 }} />
            <button onClick={() => activate(d.id)}>승인 (validated)</button>
          </div>
          <div style={{ marginTop: 6, color: 'var(--fg-dim)', fontSize: 13 }}>
            {d.description.length > 240 ? d.description.slice(0, 240) + '…' : d.description}
          </div>
        </div>
      ))}

      <div className="card" style={{ marginTop: 32, background: 'rgba(88,166,255,0.05)' }}>
        <b>다음 Phase:</b> ScrapPost 게시판 (Bastion 자동 스크랩 → 관리자 승인 → 시나리오 자동 생성)
        은 Phase 5. 진행중 공방전 강제 종료/통계는 Phase 7.
      </div>
    </>
  )
}
