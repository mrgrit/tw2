import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

interface UserRow {
  user_id: number
  name: string
  email: string
  role: string
  battle_count: number
  total_score: number
  win_count: number
  avg_score: number
}

interface BattleSummary { id: number; mode: string; status: string }

interface Cohort {
  id: number; kind: string; name: string; parent_id: number | null;
  course_ref: string | null; created_at: string; member_count: number;
}

interface BattleRankRow {
  user_id: number
  name: string
  role_in_battle: string
  score: number
  rank: number
  events_red: number
  events_blue: number
}

interface BattleBoard {
  battle_id: number
  scenario_title: string | null
  mode: string
  status: string
  rows: BattleRankRow[]
}

export default function Leaderboard() {
  const [users, setUsers] = useState<UserRow[]>([])
  const [battles, setBattles] = useState<BattleSummary[]>([])
  const [board, setBoard] = useState<BattleBoard | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [cohortId, setCohortId] = useState('')

  useEffect(() => {
    Promise.all([
      api<BattleSummary[]>('/battles'),
      api<Cohort[]>('/cohorts'),
    ]).then(([b, c]) => { setBattles(b); setCohorts(c) }).catch(e => setErr(e.message))
  }, [])

  useEffect(() => {
    const url = cohortId ? `/leaderboard/users?cohort_id=${cohortId}` : '/leaderboard/users'
    api<UserRow[]>(url).then(setUsers).catch(e => setErr(e.message))
  }, [cohortId])

  async function loadBoard(bid: number) {
    try {
      setBoard(await api<BattleBoard>(`/leaderboard/battles/${bid}`))
    } catch (e: any) { setErr(e.message) }
  }

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>리더보드</h1>
      {err && <div className="card" style={{ color: 'var(--red)' }}>{err}</div>}

      <div className="row" style={{ alignItems: 'center', marginTop: 8 }}>
        <h3 style={{ margin: 0 }}>사용자 누적</h3>
        <div style={{ flex: 1 }} />
        <label style={{ fontSize: 13, color: 'var(--fg-dim)' }}>코호트</label>
        <select value={cohortId} onChange={e => setCohortId(e.target.value)} style={{ width: 220 }}>
          <option value="">전체 (신원 포함)</option>
          {cohorts.map(c => <option key={c.id} value={c.id}>{c.kind}: {c.name}</option>)}
        </select>
      </div>
      <div className="card" style={{ padding: 0, overflowX: 'auto', marginTop: 8 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ color: 'var(--fg-dim)', borderBottom: '1px solid var(--border)' }}>
              <th align="left" style={{ padding: 12 }}>#</th>
              <th align="left" style={{ padding: 12 }}>사용자</th>
              <th align="right" style={{ padding: 12 }}>총점</th>
              <th align="right" style={{ padding: 12 }}>battle</th>
              <th align="right" style={{ padding: 12 }}>승</th>
              <th align="right" style={{ padding: 12 }}>평균</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.user_id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: 12 }}>{i + 1}</td>
                <td style={{ padding: 12 }}>
                  <b>{u.name}</b>
                  <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--fg-dim)' }}>{u.email}</span>
                  {u.role === 'admin' && <span className="badge blue" style={{ marginLeft: 8 }}>admin</span>}
                </td>
                <td align="right" style={{ padding: 12, fontWeight: 700 }}>{u.total_score}</td>
                <td align="right" style={{ padding: 12 }}>{u.battle_count}</td>
                <td align="right" style={{ padding: 12 }}>{u.win_count}</td>
                <td align="right" style={{ padding: 12 }}>{u.avg_score}</td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 16, color: 'var(--fg-dim)' }}>아직 데이터 없음.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 32 }}>battle 별</h3>
      <div className="row">
        <div style={{ flex: '0 0 240px' }}>
          {battles.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>battle 없음.</div>}
          {battles.map(b => (
            <div key={b.id} className="card"
              onClick={() => loadBoard(b.id)}
              style={{
                padding: 12, cursor: 'pointer',
                borderColor: board?.battle_id === b.id ? 'var(--primary)' : 'var(--border)',
              }}>
              <div className="row">
                <b>#{b.id}</b>
                <span className="badge blue">{b.mode}</span>
                <span style={{ marginLeft: 'auto', fontSize: 12 }}>{b.status}</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }}>
          {!board && <div className="card" style={{ color: 'var(--fg-dim)' }}>← battle 선택</div>}
          {board && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>
                #{board.battle_id} {board.scenario_title || '(no scenario)'}
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ color: 'var(--fg-dim)' }}>
                    <th align="left" style={{ padding: 8 }}>순위</th>
                    <th align="left" style={{ padding: 8 }}>사용자</th>
                    <th align="left" style={{ padding: 8 }}>역할</th>
                    <th align="right" style={{ padding: 8 }}>점수</th>
                    <th align="right" style={{ padding: 8 }}>red 이벤트</th>
                    <th align="right" style={{ padding: 8 }}>blue 이벤트</th>
                  </tr>
                </thead>
                <tbody>
                  {board.rows.map(r => (
                    <tr key={r.user_id} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 8 }}>
                        {r.rank === 1 ? <span style={{ fontSize: 18 }}>🥇</span>
                         : r.rank === 2 ? <span style={{ fontSize: 18 }}>🥈</span>
                         : r.rank === 3 ? <span style={{ fontSize: 18 }}>🥉</span>
                         : `#${r.rank}`}
                      </td>
                      <td style={{ padding: 8 }}>{r.name}</td>
                      <td style={{ padding: 8 }}>
                        <span className={`badge ${r.role_in_battle === 'red' ? 'red'
                          : r.role_in_battle === 'blue' ? 'blue' : 'yellow'}`}>{r.role_in_battle}</span>
                      </td>
                      <td align="right" style={{ padding: 8, fontWeight: 700 }}>{r.score}</td>
                      <td align="right" style={{ padding: 8 }}>{r.events_red}</td>
                      <td align="right" style={{ padding: 8 }}>{r.events_blue}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
