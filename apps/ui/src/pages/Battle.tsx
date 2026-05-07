import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

interface Battle {
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

export default function Battle() {
  const [battles, setBattles] = useState<Battle[]>([])
  useEffect(() => {
    api<Battle[]>('/battles').then(setBattles).catch(() => setBattles([]))
  }, [])

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>공방전</h1>
      <div className="card" style={{ background: 'rgba(249,115,22,0.08)' }}>
        <b>Phase 2 예정</b> — 현재는 시나리오/배틀 생성·참여 UI placeholder.
        구현 예정 항목:
        <ul style={{ color: 'var(--fg-dim)', margin: '8px 0 0' }}>
          <li>모드: <b>solo</b> (혼자 Red+Blue) / <b>1v1</b> / <b>n인 자율</b></li>
          <li>실시간 점수판 + 이벤트 스트림 (SSE)</li>
          <li>역할별 상세 채점 viewer</li>
          <li>공방전별 리더보드</li>
        </ul>
      </div>

      <h3>최근 공방전</h3>
      {battles.length === 0 && <div className="card" style={{ color: 'var(--fg-dim)' }}>아직 없음.</div>}
      {battles.map(b => (
        <div key={b.id} className="card">
          <div className="row">
            <div style={{ flex: 1 }}>
              <b>#{b.id}</b> · {b.mode} · monitor: {b.monitor}
            </div>
            <span className={`badge ${b.status === 'active' ? 'green' : b.status === 'completed' ? 'blue' : 'yellow'}`}>
              {b.status}
            </span>
          </div>
        </div>
      ))}
    </>
  )
}
