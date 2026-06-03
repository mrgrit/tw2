import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.ts'
import { getUser } from '../auth.ts'

interface Feedback {
  id: number; scope: string; trigger: string; content_md: string;
  created_at: string; battle_id: number | null
}

export default function Dashboard() {
  const user = getUser()!
  const [infraCount, setInfraCount] = useState<number | null>(null)
  const [battleCount, setBattleCount] = useState<number | null>(null)
  const [scenarioCount, setScenarioCount] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<Feedback[]>([])

  useEffect(() => {
    api<any[]>('/infras').then(d => setInfraCount(d.length)).catch(() => setInfraCount(0))
    api<any[]>('/battles').then(d => setBattleCount(d.length)).catch(() => setBattleCount(0))
    api<any[]>('/scenarios').then(d => setScenarioCount(d.length)).catch(() => setScenarioCount(0))
    api<Feedback[]>('/feedback/me').then(setFeedback).catch(() => setFeedback([]))
  }, [])

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>대시보드</h1>
      <p style={{ color: 'var(--fg-dim)' }}>
        환영합니다, <b>{user.name}</b>. 6v6 인프라를 등록하고 공방전에 참가하세요.
      </p>

      <div className="row" style={{ marginTop: 24 }}>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>내 6v6 인프라</div>
          <div style={{ fontSize: 32, fontWeight: 700, marginTop: 6 }}>
            {infraCount ?? '...'}
          </div>
          <Link to="/myinfra">관리하기 →</Link>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>활성 시나리오</div>
          <div style={{ fontSize: 32, fontWeight: 700, marginTop: 6 }}>
            {scenarioCount ?? '...'}
          </div>
          <Link to="/battle">시작하기 →</Link>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>최근 공방전</div>
          <div style={{ fontSize: 32, fontWeight: 700, marginTop: 6 }}>
            {battleCount ?? '...'}
          </div>
          <Link to="/battle">목록 보기 →</Link>
        </div>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3 style={{ marginTop: 0 }}>받은 피드백 ({feedback.length})</h3>
        {feedback.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>아직 받은 피드백이 없습니다.</div>}
        {feedback.map(f => (
          <div key={f.id} style={{ padding: '8px 0', borderTop: '1px solid var(--border)' }}>
            <div className="row" style={{ alignItems: 'center' }}>
              <span className="badge blue">{f.scope}</span>
              <span className="badge yellow">{f.trigger}</span>
              <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{f.created_at?.slice(0, 16).replace('T', ' ')}</span>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginTop: 6, fontFamily: 'inherit' }}>{f.content_md}</pre>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3 style={{ marginTop: 0 }}>시작하기</h3>
        <ol style={{ color: 'var(--fg-dim)', lineHeight: 1.9 }}>
          <li>학생 PC 의 VM 에 <code>6v6</code> 인프라를 배포 (<a href="https://github.com/mrgrit/6v6" target="_blank">github.com/mrgrit/6v6</a>).</li>
          <li><Link to="/myinfra">내 인프라</Link> 페이지에서 VM 의 외부 IP / SSH 자격 / Bastion API key 등록.</li>
          <li>등록 후 <b>smoke 테스트</b> 로 7개 외부 포트 + Bastion API 헬스 검증.</li>
          <li><Link to="/battle">공방전</Link> 메뉴에서 solo / 1v1 / n인 모드로 참가 (Phase 2 예정).</li>
        </ol>
      </div>
    </>
  )
}
