import React from 'react'

// 외부 라이브러리 없는 경량 마크다운 렌더러.
// 지원: # 헤딩, **굵게**, `코드`, [링크](url), ``` 코드블록, - 리스트, > 인용, | 표 |, --- 구분선.

const codeStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.3)', padding: '1px 5px', borderRadius: 4, fontSize: '0.88em',
}
const preStyle: React.CSSProperties = {
  whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: 'rgba(0,0,0,0.35)',
  padding: '8px 10px', borderRadius: 6, fontSize: 14, lineHeight: 1.45, margin: '6px 0',
}
const tableStyle: React.CSSProperties = {
  borderCollapse: 'collapse', margin: '8px 0', fontSize: 14, width: '100%',
}
const thStyle: React.CSSProperties = {
  border: '1px solid var(--border)', padding: '5px 9px', textAlign: 'left', background: 'var(--bg-2)',
}
const tdStyle: React.CSSProperties = {
  border: '1px solid var(--border)', padding: '5px 9px', verticalAlign: 'top',
}
const quoteStyle: React.CSSProperties = {
  borderLeft: '3px solid var(--primary)', padding: '4px 12px', margin: '8px 0',
  color: 'var(--fg-dim)', background: 'rgba(0,0,0,0.15)',
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
  return <div ref={ref} style={{ textAlign: 'center', margin: '12px 0', overflowX: 'auto' }} aria-label="diagram" />
}

function inline(s: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g
  let last = 0
  let k = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push(s.slice(last, m.index))
    if (m[2] !== undefined) out.push(<strong key={k++}>{m[2]}</strong>)
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
      else blocks.push(<pre key={key++} style={preStyle}><code>{code.join('\n')}</code></pre>)
      continue
    }
    // 표 (| ... | 다음 줄이 |---| 구분자)
    if (line.trimStart().startsWith('|') && i + 1 < lines.length && /^\s*\|[-:\s|]+\|\s*$/.test(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].trimStart().startsWith('|')) { rows.push(splitRow(lines[i])); i++ }
      blocks.push(
        <table key={key++} style={tableStyle}>
          <thead><tr>{header.map((h, j) => <th key={j} style={thStyle}>{inline(h)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} style={tdStyle}>{inline(c)}</td>)}</tr>)}</tbody>
        </table>,
      )
      continue
    }
    // 구분선
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key++} style={{ border: 0, borderTop: '1px solid var(--border)', margin: '16px 0' }} />)
      i++
      continue
    }
    // 헤딩
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      const level = h[1].length
      const size = level <= 1 ? 24 : level === 2 ? 20 : level === 3 ? 17 : 15
      blocks.push(
        <div key={key++} style={{
          fontWeight: 700, fontSize: size, margin: level <= 2 ? '18px 0 8px' : '12px 0 4px',
          color: level <= 3 ? 'var(--fg)' : 'var(--fg-dim)',
        }}>{inline(h[2])}</div>,
      )
      i++
      continue
    }
    // 인용
    if (line.trimStart().startsWith('>')) {
      const quote: string[] = []
      while (i < lines.length && lines[i].trimStart().startsWith('>')) { quote.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      blocks.push(<blockquote key={key++} style={quoteStyle}>{quote.map((q, qi) => <div key={qi}>{inline(q)}</div>)}</blockquote>)
      continue
    }
    // 리스트
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        items.push(<li key={items.length} style={{ margin: '2px 0' }}>{inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''))}</li>)
        i++
      }
      blocks.push(<ul key={key++} style={{ margin: '6px 0', paddingLeft: 22 }}>{items}</ul>)
      continue
    }
    // 빈 줄
    if (line.trim() === '') { i++; continue }
    // 문단
    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,6}\s|\s*```|\s*>|\s*([-*]|\d+\.)\s|\s*\|)/.test(lines[i])) {
      para.push(lines[i]); i++
    }
    blocks.push(<p key={key++} style={{ margin: '6px 0', lineHeight: 1.6 }}>{inline(para.join(' '))}</p>)
  }
  return <>{blocks}</>
}
