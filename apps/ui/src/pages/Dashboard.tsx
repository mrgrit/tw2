import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.ts'
import { getUser } from '../auth.ts'
import { fmtTime } from '../time.ts'
import Markdown from '../components/Markdown.tsx'

// ── 학생 개인 대시보드 — 진도·통계·통합 피드백·건건 피드백·AI 추천 직무·학습 히스토리.
//    데이터: /feedback/me(통합=periodic 의 basis.stats 로 진도), /me/recommendations, /me/submissions.

interface Feedback {
  id: number; scope: string; trigger: string; content_md: string
  created_at: string; battle_id: number | null; basis?: any
}
interface Job { id: string; title: string; desc: string; match: number; why: string[] }
interface Submission {
  id: number; scenario_id: number | null; battle_id: number | null
  mission_side: string | null; mission_order: number | null
  verdict: string | null; awarded_points: number | null; max_points: number | null
  mission_snapshot: any; submitted_at: string; grade_status: string
}

function levelColor(pct: number): string {
  if (pct >= 100) return 'var(--green)'
  if (pct >= 50) return 'var(--yellow)'
  return 'var(--red)'
}
function Ring({ pct, size = 88 }: { pct: number; size?: number }) {
  const col = levelColor(pct)
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: `conic-gradient(${col} ${pct * 3.6}deg, var(--bg) 0deg)`,
      display: 'grid', placeItems: 'center', flexShrink: 0,
    }}>
      <div style={{
        width: size - 18, height: size - 18, borderRadius: '50%', background: 'var(--bg-2)',
        display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: size * 0.26, color: col,
      }}>{Math.round(pct)}%</div>
    </div>
  )
}
function verdictBadge(v: string | null): { bg: string; fg: string; label: string } {
  switch ((v || '').toLowerCase()) {
    case 'pass': return { bg: 'var(--green)', fg: '#04210f', label: '통과' }
    case 'partial': return { bg: 'var(--yellow)', fg: '#221a02', label: '부분' }
    case 'fail': return { bg: 'var(--red)', fg: '#fff', label: '실패' }
    default: return { bg: 'var(--fg-dim)', fg: '#fff', label: v || '-' }
  }
}

export default function Dashboard() {
  const user = getUser()!
  const [fbs, setFbs] = useState<Feedback[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [subs, setSubs] = useState<Submission[]>([])

  useEffect(() => {
    api<Feedback[]>('/feedback/me').then(setFbs).catch(() => setFbs([]))
    api<Job[]>('/me/recommendations').then(setJobs).catch(() => setJobs([]))
    api<Submission[]>('/me/submissions?limit=50').then(setSubs).catch(() => setSubs([]))
  }, [])

  const periodic = fbs.find(f => f.scope === 'periodic') || null
  const labs = fbs.filter(f => f.scope !== 'periodic')
  const stats = periodic?.basis?.stats as
    | { completion: number; done: number; total: number; passed: number; graded: number; pass_rate: number; points: number; bottleneck: string[] }
    | undefined
  const graded = useMemo(() => subs.filter(s => s.grade_status === 'graded'), [subs])
  const hasData = !!periodic || jobs.length > 0 || graded.length > 0

  if (!hasData) {
    // 데이터 없음(신규 학생/관리자) — 온보딩 안내.
    return (
      <>
        <h1 style={{ color: 'var(--primary)' }}>대시보드</h1>
        <p style={{ color: 'var(--fg-dim)' }}>환영합니다, <b>{user.name}</b>.</p>
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>시작하기</h3>
          <ol style={{ color: 'var(--fg-dim)', lineHeight: 1.9 }}>
            <li><Link to="/myinfra">내 인프라</Link>에서 타깃(el34)·외부 공격자 2개 등록.</li>
            <li>smoke 테스트로 Assessor 헬스 검증.</li>
            <li><Link to="/battle">공방전</Link> 참가 → 실습이 쌓이면 이 화면에 <b>진도·피드백·추천 직무</b>가 나타납니다.</li>
          </ol>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1 style={{ color: 'var(--primary)', margin: 0 }}>{user.name} 님의 학습 현황</h1>
        <Link to="/mywork" style={{ fontSize: 13 }}>내 워크북 →</Link>
      </div>

      {/* 종합 진도 + 통계 */}
      {stats && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
            <Ring pct={stats.completion} />
            <div className="row" style={{ gap: 24, flex: 1, flexWrap: 'wrap' }}>
              {[
                { k: '완료 미션', v: `${stats.done}/${stats.total}` },
                { k: '통과율', v: `${stats.pass_rate}%` },
                { k: '획득 점수', v: `${stats.points}점` },
              ].map(x => (
                <div key={x.k}>
                  <div style={{ fontSize: 26, fontWeight: 800 }}>{x.v}</div>
                  <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>{x.k}</div>
                </div>
              ))}
            </div>
            {stats.bottleneck?.length > 0 && (
              <span className="badge" style={{ background: 'var(--red)', color: '#fff' }}>
                병목: {stats.bottleneck.join(', ')}
              </span>
            )}
          </div>
        </div>
      )}

      {/* AI 추천 직무 */}
      {jobs.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3>🎯 AI 추천 직무</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 12 }}>
            {jobs.map((j, i) => (
              <div key={j.id} className="card" style={{ borderColor: i === 0 ? 'var(--accent)' : 'var(--border)' }}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <b style={{ fontSize: 15 }}>{i === 0 ? '⭐ ' : ''}{j.title}</b>
                  <span style={{ color: levelColor(j.match), fontWeight: 700 }}>{j.match}%</span>
                </div>
                <div style={{ background: 'var(--bg)', borderRadius: 4, height: 6, margin: '6px 0', overflow: 'hidden' }}>
                  <div style={{ width: `${j.match}%`, height: '100%', background: levelColor(j.match) }} />
                </div>
                <div style={{ color: 'var(--fg-dim)', fontSize: 12, marginBottom: 6 }}>{j.desc}</div>
                <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                  {j.why.map(w => <span key={w} className="badge" style={{ fontSize: 11 }}>{w}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 통합 피드백 */}
      {periodic && (
        <div className="card" style={{ marginTop: 20, borderColor: 'var(--accent)' }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>📋 통합 피드백</h3>
            <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{fmtTime(periodic.created_at)}</span>
          </div>
          <Markdown text={periodic.content_md} />
        </div>
      )}

      {/* 건건 피드백 */}
      {labs.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>🗒 세부 피드백 ({labs.length})</summary>
          {labs.map(f => (
            <div key={f.id} className="card" style={{ marginTop: 8, background: 'var(--bg)' }}>
              <div style={{ fontSize: 11, color: 'var(--fg-dim)', marginBottom: 4 }}>
                <span className="badge" style={{ background: f.trigger === 'bottleneck' ? 'var(--red)' : 'var(--bg-2)', color: f.trigger === 'bottleneck' ? '#fff' : 'var(--fg)' }}>{f.trigger}</span>
                {' '}{fmtTime(f.created_at)}
              </div>
              <Markdown text={f.content_md} />
            </div>
          ))}
        </details>
      )}

      {/* 학습 히스토리 */}
      {graded.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3>📚 학습 히스토리 ({graded.length})</h3>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {graded.slice(0, 12).map(s => {
              const vb = verdictBadge(s.verdict)
              const title = s.mission_snapshot?.title || `미션 ${s.mission_order ?? ''}`
              return (
                <div key={s.id} className="row" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '9px 14px', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                    <span className="badge" style={{ background: s.mission_side === 'red' ? 'var(--red)' : '#1f6feb', color: '#fff', fontSize: 10 }}>{(s.mission_side || '-').toUpperCase()}</span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 420 }}>{String(title).replace(/[#*`]/g, '')}</span>
                  </span>
                  <span style={{ display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ color: 'var(--fg-dim)', fontSize: 12 }}>{s.awarded_points ?? 0}/{s.max_points ?? 0}점</span>
                    <span className="badge" style={{ background: vb.bg, color: vb.fg }}>{vb.label}</span>
                    <span style={{ color: 'var(--fg-dim)', fontSize: 11 }}>{fmtTime(s.submitted_at)}</span>
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </>
  )
}
