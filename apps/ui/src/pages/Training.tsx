import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { getToken } from '../auth.ts'
import Markdown from '../components/Markdown.tsx'

interface WeekInfo { week: number; lecture: boolean; lab: boolean; title?: string; summary?: string }
interface TrackInfo { track: string; label: string; weeks: WeekInfo[] }
interface LabStep {
  order: number; instruction?: string
  answer?: string; answer_detail?: string; expected_output?: string; hint?: string
  [k: string]: unknown
}
interface Lab { lab_id?: string; title?: string; description?: string; objectives?: string[]; steps?: LabStep[] }

// ── 트랙 표시 메타데이터(아이콘·한 줄 주제·계열) — 카드를 풍성하게, 반복 정보(주차 수)는 제거 ──
interface TrackMeta { icon: string; blurb: string; group: string; adv?: boolean }
const TRACK_META: Record<string, TrackMeta> = {
  secuops: { icon: '🛡️', blurb: '방화벽·IDS·WAF·SIEM·osquery 5종 보안솔루션 통합 운영', group: '방어·관제' },
  'secuops-easy': { icon: '🎓', blurb: '보안 운영 입문 — 핵심 개념부터 차근차근', group: '방어·관제' },
  soc: { icon: '🖥️', blurb: '로그 수집·탐지·triage·사고 대응 관제 실무', group: '방어·관제' },
  'soc-adv': { icon: '🔬', blurb: '위협 헌팅·포렌식·SOAR·퍼플팀·APT 종합 대응', group: '방어·관제', adv: true },
  attack: { icon: '⚔️', blurb: '정찰·웹 익스플로잇·SQLi/XSS·권한상승·CTF', group: '공격·모의침투' },
  'attack-adv': { icon: '🗡️', blurb: 'APT 킬체인·C2·측면 이동·유출·침투 보고서(PTES)', group: '공격·모의침투', adv: true },
  'physical-pentest': { icon: '🚪', blurb: '물리 보안·물리 침투 킬체인 — 물리적 CIA·위협 분류·조기 탐지', group: '공격·모의침투' },
  'web-vuln': { icon: '🕸️', blurb: 'OWASP·SQLi·XSS·인증·API 보안 (WSTG 방법론)', group: '웹·애플리케이션' },
  'cloud-container': { icon: '☁️', blurb: 'Docker/K8s 보안·CIS·이미지 스캔·런타임 탐지', group: '인프라·거버넌스' },
  compliance: { icon: '📋', blurb: 'ISMS-P·ISO27001·PCI-DSS·CIS·감사·증적', group: '인프라·거버넌스' },
  'iot-security': { icon: '📡', blurb: 'IoT 보안 — 4대 공격 표면·펌웨어/통신·표준 기반 방어', group: '인프라·거버넌스' },
  'autonomous-systems': { icon: '🏭', blurb: 'CPS(사이버물리) 보안 — 사이버→물리 공격 경로·안전 우선 다층 방어', group: '인프라·거버넌스' },
  'wazuh-special': { icon: '🦅', blurb: 'Wazuh Dashboard·KQL·4대 보안시스템·자율 에이전트 로그 분석 (특강)', group: '방어·관제' },
  'ai-agent': { icon: '🤖', blurb: 'LLM 에이전트 구조·툴 사용·RAG·가드레일 (Ollama 실습)', group: 'AI·보안' },
  'ai-safety': { icon: '🛟', blurb: '프롬프트 인젝션·탈옥·모델 레드팀 (취약 모델 공격)', group: 'AI·보안' },
  'ai-safety-adv': { icon: '🧨', blurb: 'AI 안전 심화 — 고급 탈옥·정렬 우회·방어 한계', group: 'AI·보안', adv: true },
  'ai-security': { icon: '🔐', blurb: 'AI 시스템 공급망·데이터·모델 보안 위협과 방어', group: 'AI·보안' },
  'ai-service-pentest': { icon: '🎯', blurb: 'LLM 앱 모의해킹 — OWASP LLM Top 10으로 AICompanion 공격 (인젝션·유출·과잉에이전시)', group: 'AI·보안' },
  aisec: { icon: '🧠', blurb: 'AI 보안 종합 — 공격·방어·거버넌스 통합', group: 'AI·보안' },
  'agent-ir': { icon: '🚨', blurb: 'AI 에이전트 사고대응 — 행위 로그·탐지·격리', group: 'AI·보안' },
  'agent-ir-adv': { icon: '🛰️', blurb: 'AI 에이전트 사고대응 심화 — 자율 위협 헌팅·포렌식', group: 'AI·보안', adv: true },
  'autonomous-security': { icon: '🔁', blurb: '자율보안 — 자율 루프·자율성 수준·가드레일·Purple Team 순환', group: 'AI·보안' },
}
const FALLBACK_META: TrackMeta = { icon: '📚', blurb: 'el34 인프라 기반 보안 트레이닝', group: '기타' }
const metaOf = (slug: string): TrackMeta => TRACK_META[slug] ?? FALLBACK_META
// 계열별 강조색·정렬 순서
const GROUP_ORDER: { name: string; color: string }[] = [
  { name: '방어·관제', color: 'var(--green)' },
  { name: '공격·모의침투', color: 'var(--red)' },
  { name: '웹·애플리케이션', color: 'var(--yellow)' },
  { name: '인프라·거버넌스', color: 'var(--accent)' },
  { name: 'AI·보안', color: 'var(--primary)' },
  { name: '기타', color: 'var(--fg-dim)' },
]

const cardStyle: React.CSSProperties = {
  textAlign: 'left', padding: '12px 14px', background: 'var(--bg-2)',
  border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer', color: 'var(--fg)',
}
// 주차 카드의 학습 개요(한 줄 요약) — 3줄 클램프
const weekSummary: React.CSSProperties = {
  fontSize: 12.5, color: 'var(--fg-dim)', marginTop: 5, lineHeight: 1.5,
  display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
}
// 따라하기 표시용 스타일
const accessBanner: React.CSSProperties = {
  background: 'rgba(130,170,255,0.10)', border: '1px solid var(--border)', borderRadius: 8,
  padding: '8px 12px', margin: '6px 0 14px', fontSize: 13.5, color: 'var(--fg)', lineHeight: 1.6,
}
const expBox: React.CSSProperties = {
  background: 'rgba(63,185,80,0.08)', border: '1px solid rgba(63,185,80,0.35)',
  borderRadius: 8, padding: '8px 12px', margin: '10px 0',
}
const expLabel: React.CSSProperties = { fontWeight: 700, fontSize: 13.5, color: '#3fb950', marginBottom: 4 }
const preMini: React.CSSProperties = {
  whiteSpace: 'pre', overflowX: 'auto', background: 'rgba(0,0,0,0.30)', padding: '8px 10px',
  borderRadius: 6, fontSize: 12.5, lineHeight: 1.5, margin: 0,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
}
const hintLine: React.CSSProperties = { fontSize: 13, color: 'var(--fg-dim)', margin: '8px 0 2px' }
const stepNum: React.CSSProperties = { fontSize: 12, color: 'var(--fg-dim)', fontWeight: 700, marginBottom: 2 }
const gridWrap: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12,
}
const advBadge: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: 'var(--primary)', border: '1px solid var(--primary)',
  borderRadius: 10, padding: '1px 7px', marginLeft: 'auto', whiteSpace: 'nowrap',
}
const w2 = (n: number): string => String(n).padStart(2, '0')

export default function Training(): React.ReactElement {
  const [tracks, setTracks] = useState<TrackInfo[]>([])
  const [track, setTrack] = useState<TrackInfo | null>(null)
  const [week, setWeek] = useState<number | null>(null)
  const [tab, setTab] = useState<'lecture' | 'lab'>('lecture')
  const [lecture, setLecture] = useState('')
  const [lab, setLab] = useState<Lab | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      setLoading(true); setErr('')
      try { setTracks(await api<TrackInfo[]>('/training')) }
      catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
      finally { setLoading(false) }
    })()
  }, [])

  const [dlBusy, setDlBusy] = useState(false)
  async function downloadLabWorkbook(): Promise<void> {
    if (!track || week == null) return
    setDlBusy(true)
    try {
      const token = getToken()
      const res = await fetch(`/training/${track.track}/lab/${week}/workbook`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, cache: 'no-store',
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${track.track}-w${w2(week)}-lab.docx`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(`워크북 다운로드 실패: ${e instanceof Error ? e.message : String(e)}`) }
    finally { setDlBusy(false) }
  }

  async function openWeek(t: TrackInfo, w: WeekInfo): Promise<void> {
    setWeek(w.week); setTab(w.lecture ? 'lecture' : 'lab'); setLecture(''); setLab(null); setErr('')
    try {
      if (w.lecture) setLecture((await api<{ markdown: string }>(`/training/${t.track}/lecture/${w.week}`)).markdown)
      if (w.lab) setLab(await api<Lab>(`/training/${t.track}/lab/${w.week}`))
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }

  // ── 주차 상세 (강의/실습) ──
  if (track && week != null) {
    return (
      <>
        <button className="ghost" onClick={() => { setWeek(null); setLab(null); setLecture('') }} style={{ marginBottom: 12 }}>← {track.label} 주차 목록</button>
        <h1 style={{ color: 'var(--primary)' }}>{metaOf(track.track).icon} {track.label} — Week {w2(week)}</h1>
        <div className="row" style={{ gap: 8, marginBottom: 12 }}>
          {lecture && <button onClick={() => setTab('lecture')} style={{ fontWeight: tab === 'lecture' ? 700 : 400 }}>📖 강의</button>}
          {lab && <button onClick={() => setTab('lab')} style={{ fontWeight: tab === 'lab' ? 700 : 400 }}>🧪 실습</button>}
        </div>
        {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}
        {tab === 'lecture' && lecture && <div className="card"><Markdown text={lecture} /></div>}
        {tab === 'lab' && lab && (
          <div className="card">
            <div className="row" style={{ alignItems: 'center', gap: 10 }}>
              <h2 style={{ marginTop: 0, flex: 1 }}>{lab.title}</h2>
              <button onClick={() => void downloadLabWorkbook()} disabled={dlBusy}>
                {dlBusy ? '내려받는 중…' : '📄 워크북(docx)'}
              </button>
            </div>
            <div style={accessBanner}>
              💻 모든 명령은 el34 호스트에서: <code>ssh ccc@192.168.0.151</code> (비밀번호 <code>1</code>) → <code>docker exec …</code>.
              아래 명령 블록은 우상단 <b>복사</b> 버튼으로 그대로 붙여넣어 실행하고, <b>✅ 이렇게 나오면 정상</b>과 비교하세요.
            </div>
            {lab.description && <Markdown text={lab.description} />}
            {lab.objectives && lab.objectives.length > 0 && (
              <>
                <h4>학습 목표</h4>
                <ul>{lab.objectives.map((o, i) => <li key={i}>{o}</li>)}</ul>
              </>
            )}
            {(lab.steps || []).map((s, i) => (
              <div key={i} style={{ borderTop: '2px solid var(--border)', paddingTop: 12, marginTop: 16 }}>
                <div style={stepNum}>STEP {s.order ?? i + 1} / {(lab.steps || []).length}</div>
                <Markdown text={s.instruction || `(step ${s.order})`} />
                {typeof s.expected_output === 'string' && s.expected_output.trim() !== '' && (
                  <div style={expBox}>
                    <div style={expLabel}>✅ 이렇게 나오면 정상 <span style={{ fontWeight: 400, color: 'var(--fg-dim)' }}>(숫자·시간은 환경마다 다름)</span></div>
                    <pre style={preMini}><code>{s.expected_output}</code></pre>
                  </div>
                )}
                {typeof s.answer_detail === 'string' && s.answer_detail.trim() !== '' && (
                  <details style={{ margin: '8px 0' }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13.5, color: 'var(--primary)' }}>💡 결과 해석 (펼치기)</summary>
                    <div style={{ marginTop: 4 }}><Markdown text={s.answer_detail} /></div>
                  </details>
                )}
                {typeof s.hint === 'string' && s.hint.trim() !== '' && (
                  <div style={hintLine}>🆘 막히면 — 핵심 명령: <code>{s.hint}</code></div>
                )}
              </div>
            ))}
          </div>
        )}
      </>
    )
  }

  // ── 트랙의 주차 목록 ──
  if (track) {
    const m = metaOf(track.track)
    const accent = (GROUP_ORDER.find(g => g.name === m.group) ?? GROUP_ORDER[GROUP_ORDER.length - 1]).color
    return (
      <>
        <button className="ghost" onClick={() => setTrack(null)} style={{ marginBottom: 12 }}>← 트랙 목록</button>
        <h1 style={{ color: 'var(--primary)', marginBottom: 2 }}>{m.icon} {track.label}</h1>
        <p style={{ color: 'var(--fg-dim)', marginTop: 0 }}>{m.blurb} · 총 {track.weeks.length}주차</p>
        <div style={gridWrap}>
          {track.weeks.map(w => (
            <button key={w.week} onClick={() => void openWeek(track, w)}
              style={{ ...cardStyle, borderLeft: `3px solid ${accent}` }}>
              <div style={{ fontWeight: 700, fontSize: 14.5, lineHeight: 1.4 }}>
                <span style={{ color: accent }}>Week {w2(w.week)}</span>
                {w.title ? <span style={{ color: 'var(--fg)' }}> · {w.title}</span> : null}
              </div>
              {w.summary ? <div style={weekSummary}>{w.summary}</div> : null}
              <div className="row" style={{ gap: 6, marginTop: 8 }}>
                {w.lecture && <span className="badge blue" style={{ fontSize: 11 }}>📖 강의</span>}
                {w.lab && <span className="badge green" style={{ fontSize: 11 }}>🧪 실습</span>}
              </div>
            </button>
          ))}
        </div>
      </>
    )
  }

  // ── 트랙 목록 (계열별 섹션 + 풍성한 카드) ──
  // 모든 트랙의 주차 수가 같으면 "각 N주차"를 페이지 상단에 한 번만 표기(카드마다 반복 제거)
  const weekCounts = new Set(tracks.map(t => t.weeks.length))
  const uniformWeeks = weekCounts.size === 1 ? [...weekCounts][0] : null
  return (
    <>
      <h1 style={{ color: 'var(--primary)', marginBottom: 2 }}>Training</h1>
      <p style={{ color: 'var(--fg-dim)', marginTop: 0 }}>
        강의(이론) + 실습(lab) 트레이닝 · el34 인프라 기반
        {tracks.length > 0 && <> · <b>{tracks.length}개 트랙</b>{uniformWeeks != null && <> · 각 {uniformWeeks}주차</>}</>}
      </p>
      {loading && <div>로딩...</div>}
      {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}
      {!loading && tracks.length === 0 && <div style={{ color: 'var(--fg-dim)' }}>아직 등록된 트레이닝 콘텐츠가 없습니다.</div>}
      {GROUP_ORDER.map(g => {
        const inGroup = tracks
          .filter(t => metaOf(t.track).group === g.name)
          .sort((a, b) => Number(metaOf(a.track).adv ?? false) - Number(metaOf(b.track).adv ?? false) || a.label.localeCompare(b.label))
        if (inGroup.length === 0) return null
        return (
          <section key={g.name} style={{ marginTop: 22 }}>
            <div className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{ width: 4, height: 18, background: g.color, borderRadius: 2, display: 'inline-block' }} />
              <h3 style={{ margin: 0 }}>{g.name}</h3>
              <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>{inGroup.length}개 트랙</span>
            </div>
            <div style={gridWrap}>
              {inGroup.map(t => {
                const m = metaOf(t.track)
                return (
                  <button key={t.track} onClick={() => setTrack(t)}
                    style={{ ...cardStyle, padding: '14px 16px', borderLeft: `3px solid ${g.color}` }}>
                    <div className="row" style={{ alignItems: 'center', gap: 9 }}>
                      <span style={{ fontSize: 22, lineHeight: 1 }}>{m.icon}</span>
                      <span style={{ fontWeight: 700, fontSize: 16 }}>{t.label}</span>
                      {m.adv && <span style={advBadge}>심화</span>}
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--fg-dim)', marginTop: 8, lineHeight: 1.5 }}>{m.blurb}</div>
                  </button>
                )
              })}
            </div>
          </section>
        )
      })}
    </>
  )
}
