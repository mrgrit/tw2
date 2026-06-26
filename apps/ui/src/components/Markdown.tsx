import React from 'react'

// 외부 라이브러리 없는 경량 마크다운 렌더러 (교과서 가독성 튜닝판).
// 지원: # 헤딩, **굵게**, `코드`, [링크](url), ``` 코드블록(+mermaid 그래픽), - / 1. 리스트(중첩),
//       > 인용, | 표 |(가로 스크롤·줄무늬), --- 구분선.

const codeStyle: React.CSSProperties = {
  background: 'rgba(130,170,255,0.14)', padding: '1px 6px', borderRadius: 4,
  fontSize: '0.86em', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
}
const preStyle: React.CSSProperties = {
  whiteSpace: 'pre', overflowX: 'auto', background: 'rgba(0,0,0,0.38)',
  padding: '12px 14px', borderRadius: 8, fontSize: 13.5, lineHeight: 1.55, margin: '12px 0',
  border: '1px solid var(--border)',
}
const tableStyle: React.CSSProperties = {
  borderCollapse: 'collapse', margin: 0, fontSize: 14, width: '100%', lineHeight: 1.55,
}
const thStyle: React.CSSProperties = {
  border: '1px solid var(--border)', padding: '7px 11px', textAlign: 'left',
  background: 'var(--bg-2)', fontWeight: 700, whiteSpace: 'nowrap',
}
const tdStyle: React.CSSProperties = {
  border: '1px solid var(--border)', padding: '7px 11px', verticalAlign: 'top',
}
const quoteStyle: React.CSSProperties = {
  borderLeft: '4px solid var(--primary)', padding: '8px 16px', margin: '14px 0',
  color: 'var(--fg)', background: 'rgba(130,170,255,0.08)', borderRadius: '0 6px 6px 0',
}

// mermaid 다이어그램 — index.html 에서 로컬 벤더링된 window.mermaid 로 SVG 렌더.
// 라이브러리 미로딩/문법오류 시 원문을 <pre> 로 폴백(절대 깨지지 않게).
function Mermaid({ code }: { code: string }): React.ReactElement {
  const ref = React.useRef<HTMLDivElement>(null)
  const [failed, setFailed] = React.useState(false)
  React.useEffect(() => {
    let cancelled = false
    const m = (window as unknown as { mermaid?: { render: (id: string, t: string) => Promise<{ svg: string }> } }).mermaid
    if (!m) { setFailed(true); return }
    const id = 'mmd-' + Math.abs(Array.from(code).reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7)).toString(36)
    m.render(id, code)
      .then(({ svg }) => { if (!cancelled && ref.current) ref.current.innerHTML = svg })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [code])
  if (failed) return <pre style={preStyle}><code>{code}</code></pre>
  return (
    <div ref={ref}
      style={{ textAlign: 'center', margin: '16px 0', overflowX: 'auto', maxWidth: '100%' }}
      aria-label="diagram" />
  )
}

// 코드 블록 — 우상단 '복사' 버튼으로 명령을 그대로 클립보드에 담는다(따라하기 핵심).
function CodeBlock({ code }: { code: string }): React.ReactElement {
  const [copied, setCopied] = React.useState(false)
  const copy = (): void => {
    const done = (): void => { setCopied(true); setTimeout(() => setCopied(false), 1200) }
    if (navigator.clipboard?.writeText) void navigator.clipboard.writeText(code).then(done).catch(() => undefined)
  }
  return (
    <div style={{ position: 'relative', margin: '12px 0' }}>
      <button onClick={copy} aria-label="복사" style={{
        position: 'absolute', top: 6, right: 6, fontSize: 12, padding: '2px 9px', lineHeight: 1.6,
        background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6,
        color: copied ? '#3fb950' : 'var(--fg-dim)', cursor: 'pointer', zIndex: 1,
      }}>{copied ? '복사됨 ✓' : '복사'}</button>
      <pre style={{ ...preStyle, margin: 0 }}><code>{code}</code></pre>
    </div>
  )
}

function inline(s: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g
  let last = 0
  let k = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push(s.slice(last, m.index))
    if (m[2] !== undefined) out.push(<strong key={k++} style={{ color: 'var(--fg)' }}>{m[2]}</strong>)
    else if (m[3] !== undefined) out.push(<code key={k++} style={codeStyle}>{m[3]}</code>)
    else if (m[4] !== undefined) {
      out.push(
        <a key={k++} href={m[5]} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>{m[4]}</a>,
      )
    }
    last = m.index + m[0].length
  }
  if (last < s.length) out.push(s.slice(last))
  return out
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
}

const listRe = /^(\s*)([-*]|\d+\.)\s+(.*)$/

// 연속 리스트 줄(중첩 포함)을 들여쓰기 기준으로 <ul>/<ol> 트리로 변환.
function renderList(lines: string[], start: number): [React.ReactNode, number] {
  let i = start
  const baseIndent = (lines[i].match(listRe) as RegExpMatchArray)[1].length
  const ordered = /\d+\./.test((lines[i].match(listRe) as RegExpMatchArray)[2])
  const items: React.ReactNode[] = []
  while (i < lines.length) {
    const m = lines[i].match(listRe)
    if (!m) break
    const indent = m[1].length
    if (indent < baseIndent) break
    if (indent > baseIndent) {
      // 중첩 리스트 — 직전 항목 아래로
      const [sub, next] = renderList(lines, i)
      const lastIdx = items.length - 1
      if (lastIdx >= 0) items[lastIdx] = <li key={lastIdx} style={{ margin: '3px 0', lineHeight: 1.65 }}>{(items[lastIdx] as React.ReactElement).props.children}{sub}</li>
      i = next
      continue
    }
    items.push(<li key={items.length} style={{ margin: '4px 0', lineHeight: 1.7 }}>{inline(m[3])}</li>)
    i++
  }
  const style: React.CSSProperties = { margin: '8px 0', paddingLeft: 26 }
  const node = ordered ? <ol style={style}>{items}</ol> : <ul style={style}>{items}</ul>
  return [node, i]
}

export default function Markdown({ text }: { text: string }): React.ReactElement {
  const lines = (text || '').replace(/\r\n/g, '\n').split('\n')
  const blocks: React.ReactNode[] = []
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]
    // 코드 블록 (```lang) — mermaid 는 그래픽, 그 외는 <pre>
    if (line.trimStart().startsWith('```')) {
      const lang = line.trimStart().slice(3).trim().toLowerCase()
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) { code.push(lines[i]); i++ }
      i++
      if (lang === 'mermaid') blocks.push(<Mermaid key={key++} code={code.join('\n')} />)
      else blocks.push(<CodeBlock key={key++} code={code.join('\n')} />)
      continue
    }
    // 표 (| ... | 다음 줄이 |---| 구분자) — 넓으면 가로 스크롤 + 줄무늬
    if (line.trimStart().startsWith('|') && i + 1 < lines.length && /^\s*\|[-:\s|]+\|\s*$/.test(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].trimStart().startsWith('|')) { rows.push(splitRow(lines[i])); i++ }
      blocks.push(
        <div key={key++} style={{ overflowX: 'auto', margin: '12px 0' }}>
          <table style={tableStyle}>
            <thead><tr>{header.map((h, j) => <th key={j} style={thStyle}>{inline(h)}</th>)}</tr></thead>
            <tbody>{rows.map((r, ri) => (
              <tr key={ri} style={ri % 2 ? { background: 'rgba(255,255,255,0.025)' } : undefined}>
                {r.map((c, ci) => <td key={ci} style={tdStyle}>{inline(c)}</td>)}
              </tr>
            ))}</tbody>
          </table>
        </div>,
      )
      continue
    }
    // 구분선
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key++} style={{ border: 0, borderTop: '1px solid var(--border)', margin: '22px 0' }} />)
      i++
      continue
    }
    // 헤딩 — 레벨별 크기·간격·구분선으로 위계 강조
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      const level = h[1].length
      let st: React.CSSProperties
      if (level <= 1) st = { fontWeight: 800, fontSize: 26, lineHeight: 1.3, margin: '8px 0 16px', paddingBottom: 8, borderBottom: '2px solid var(--border)', color: 'var(--fg)' }
      else if (level === 2) st = { fontWeight: 700, fontSize: 21, lineHeight: 1.35, margin: '28px 0 10px', paddingBottom: 5, borderBottom: '1px solid var(--border)', color: 'var(--fg)' }
      else if (level === 3) st = { fontWeight: 700, fontSize: 17, lineHeight: 1.4, margin: '20px 0 6px', color: 'var(--primary)' }
      else st = { fontWeight: 700, fontSize: 15, lineHeight: 1.4, margin: '14px 0 4px', color: 'var(--fg-dim)' }
      blocks.push(<div key={key++} style={st}>{inline(h[2])}</div>)
      i++
      continue
    }
    // 인용
    if (line.trimStart().startsWith('>')) {
      const quote: string[] = []
      while (i < lines.length && lines[i].trimStart().startsWith('>')) { quote.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      blocks.push(<blockquote key={key++} style={quoteStyle}>{quote.map((q, qi) => <div key={qi} style={{ margin: '3px 0', lineHeight: 1.65 }}>{inline(q)}</div>)}</blockquote>)
      continue
    }
    // 리스트 (- / * / 1.) — 중첩 지원, 순서 목록은 번호 유지
    if (listRe.test(line)) {
      const [node, next] = renderList(lines, i)
      blocks.push(<React.Fragment key={key++}>{node}</React.Fragment>)
      i = next
      continue
    }
    // 빈 줄
    if (line.trim() === '') { i++; continue }
    // 문단
    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,6}\s|\s*```|\s*>|\s*([-*]|\d+\.)\s|\s*\|)/.test(lines[i])) {
      para.push(lines[i]); i++
    }
    blocks.push(<p key={key++} style={{ margin: '10px 0', lineHeight: 1.78 }}>{inline(para.join(' '))}</p>)
  }
  return <div style={{ maxWidth: 920, fontSize: 15.5, color: 'var(--fg)' }}>{blocks}</div>
}
