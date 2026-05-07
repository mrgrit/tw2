import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.ts'
import { login } from '../auth.ts'

export default function Signup() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await api<{ access_token: string; user: any }>('/auth/signup', {
        method: 'POST',
        json: { email, password, name },
      })
      login(r.access_token, r.user)
      nav('/myinfra')
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: '60px auto' }}>
      <h1 style={{ color: 'var(--primary)' }}>회원가입</h1>
      <form onSubmit={submit} className="card col">
        <label>
          이메일
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          이름
          <input value={name} onChange={e => setName(e.target.value)} required />
        </label>
        <label>
          비밀번호 (8자 이상)
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            minLength={8} required />
        </label>
        {err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>}
        <button type="submit" disabled={busy}>{busy ? '...' : '가입하기'}</button>
        <div style={{ fontSize: 13, color: 'var(--fg-dim)', textAlign: 'center', marginTop: 6 }}>
          이미 계정 있음 — <Link to="/login">로그인</Link>
        </div>
      </form>
    </div>
  )
}
