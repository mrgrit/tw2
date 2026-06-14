import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { isAdmin } from '../auth.ts'
import Markdown from '../components/Markdown.tsx'

interface Post {
  id: number
  board: string
  title: string
  body: string
  author_id: number | null
  author_name: string
  pinned: boolean
  created_at: string
  updated_at: string
}

function fmt(iso: string): string {
  try { return new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) } catch { return iso }
}

const cardStyle: React.CSSProperties = {
  textAlign: 'left', padding: '12px 14px', background: 'var(--bg-2)',
  border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer', color: 'var(--fg)',
}

export default function Initiative(): React.ReactElement {
  const [posts, setPosts] = useState<Post[]>([])
  const [sel, setSel] = useState<Post | null>(null)
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  async function load(): Promise<void> {
    setLoading(true)
    setErr('')
    try { setPosts(await api<Post[]>('/initiative')) }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  if (sel) return <PostDetail post={sel} onBack={() => setSel(null)} />
  if (creating) {
    return (
      <PostEditor onDone={(p) => {
        setCreating(false)
        if (p) { void load(); setSel(p) }
      }} />
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <h2 style={{ margin: 0 }}>이니셔티브</h2>
        <span style={{ color: 'var(--fg-dim)', fontSize: 13 }}>운영·연구 이니셔티브 게시판</span>
        <div style={{ flex: 1 }} />
        {isAdmin() && <button onClick={() => setCreating(true)}>+ 새 글</button>}
      </div>
      {loading && <p style={{ color: 'var(--fg-dim)' }}>불러오는 중…</p>}
      {err && <p style={{ color: 'var(--danger, #e66)' }}>오류: {err}</p>}
      {!loading && !err && posts.length === 0 && (
        <p style={{ color: 'var(--fg-dim)' }}>아직 게시물이 없습니다.</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {posts.map((p) => (
          <button key={p.id} onClick={() => setSel(p)} style={cardStyle}>
            <div style={{ fontWeight: 600 }}>{p.pinned ? '📌 ' : ''}{p.title}</div>
            <div style={{ color: 'var(--fg-dim)', fontSize: 12, marginTop: 4 }}>
              {p.author_name || '운영'} · {fmt(p.created_at)}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function PostDetail({ post, onBack }: { post: Post; onBack: () => void }): React.ReactElement {
  return (
    <div>
      <button className="ghost" onClick={onBack}>← 목록</button>
      <h1 style={{ marginTop: 12, marginBottom: 4 }}>{post.pinned ? '📌 ' : ''}{post.title}</h1>
      <div style={{ color: 'var(--fg-dim)', fontSize: 13, marginBottom: 16 }}>
        {post.author_name || '운영'} · {fmt(post.created_at)}
      </div>
      <article><Markdown text={post.body} /></article>
    </div>
  )
}

function PostEditor({ onDone }: { onDone: (p: Post | null) => void }): React.ReactElement {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(): Promise<void> {
    if (!title.trim()) { setErr('제목을 입력하세요'); return }
    setBusy(true)
    setErr('')
    try {
      const p = await api<Post>('/initiative', { method: 'POST', json: { title, body } })
      onDone(p)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <div>
      <button className="ghost" onClick={() => onDone(null)}>← 취소</button>
      <h2>새 이니셔티브 글</h2>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="제목"
        style={{ width: '100%', padding: 8, marginBottom: 8, boxSizing: 'border-box' }}
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="본문 (마크다운)"
        style={{ width: '100%', minHeight: 340, padding: 8, fontFamily: 'monospace', fontSize: 13, boxSizing: 'border-box' }}
      />
      {err && <p style={{ color: 'var(--danger, #e66)' }}>{err}</p>}
      <div style={{ marginTop: 8 }}>
        <button onClick={() => void submit()} disabled={busy}>{busy ? '저장 중…' : '게시'}</button>
      </div>
    </div>
  )
}
