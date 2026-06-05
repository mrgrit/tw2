import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.ts'
import { login } from '../auth.ts'
import GoogleSignIn from '../components/GoogleSignIn.tsx'

export default function Login() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await api<{ access_token: string; user: any }>('/auth/login', {
        method: 'POST',
        json: { email, password },
      })
      login(r.access_token, r.user)
      nav('/dashboard')
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: '60px auto' }}>
      <h1 style={{ color: 'var(--primary)' }}>tubewar 로그인</h1>
      <form onSubmit={submit} className="card col">
        <label>
          이메일
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          비밀번호
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        </label>
        {err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>}
        <button type="submit" disabled={busy}>{busy ? '...' : '로그인'}</button>
        <GoogleSignIn onError={setErr} />
        <div style={{ fontSize: 13, color: 'var(--fg-dim)', textAlign: 'center', marginTop: 6 }}>
          계정이 없나요? <Link to="/signup">회원가입</Link>
        </div>
      </form>
    </div>
  )
}
