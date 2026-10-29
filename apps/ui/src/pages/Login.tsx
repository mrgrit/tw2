import React, { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.ts'
import { login } from '../auth.ts'
import { useAuthProviders } from '../authProviders.ts'
import GoogleSignIn from '../components/GoogleSignIn.tsx'

export default function Login() {
  const nav = useNavigate()
  const providers = useAuthProviders()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [guestOpen, setGuestOpen] = useState(false)   // 구글 전용 모드의 게스트 폼 펼침

  const domain = providers?.google.allowed_domain
  // 백엔드의 도메인 거부("domain not allowed: gmail.com")를 학생이 알아볼 문구로.
  const onGoogleError = useCallback((msg: string) => {
    setErr(msg.includes('domain not allowed') && domain
      ? `@${domain} 조직 계정으로만 로그인할 수 있습니다.`
      : msg)
  }, [domain])

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

  const errBox = err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>

  let body: React.ReactNode
  if (providers === undefined) {
    body = <div className="card" style={{ color: 'var(--fg-dim)' }}>...</div>
  } else if (providers === null) {
    body = <div className="card" style={{ color: 'var(--red)', fontSize: 13 }}>서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.</div>
  } else if (!providers.password.enabled) {
    // 구글 전용 모드 — 회원가입 없음(첫 구글 로그인 시 계정 자동 생성).
    // 비밀번호 로그인은 관리자가 등록한 게스트 계정만 가능 → 접이식 보조 폼으로.
    body = (
      <div className="card col" style={{ alignItems: 'center' }}>
        {providers.google.enabled ? (
          <>
            <div style={{ fontSize: 13, color: 'var(--fg-dim)', textAlign: 'center' }}>
              {domain ? <><b>@{domain}</b> 구글 계정으로 로그인하세요.</> : '구글 계정으로 로그인하세요.'}
            </div>
            <GoogleSignIn onError={onGoogleError} divider={false} />
          </>
        ) : (
          <div style={{ color: 'var(--red)', fontSize: 13 }}>
            구글 로그인이 설정되지 않았습니다. 관리자에게 문의하세요.
          </div>
        )}
        {!guestOpen ? (
          <button type="button" className="ghost" style={{ fontSize: 12, marginTop: 8 }}
            onClick={() => { setGuestOpen(true); setErr(null) }}>
            게스트 계정으로 로그인
          </button>
        ) : (
          <form onSubmit={submit} className="col" style={{ width: '100%', marginTop: 8, gap: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
              게스트 계정은 관리자가 등록합니다. 받은 ID 와 비밀번호를 입력하세요.
            </div>
            <label>
              게스트 ID
              <input type="text" autoComplete="username" value={email}
                onChange={e => setEmail(e.target.value)} required autoFocus />
            </label>
            <label>
              비밀번호
              <input type="password" autoComplete="current-password" value={password}
                onChange={e => setPassword(e.target.value)} required />
            </label>
            <button type="submit" disabled={busy}>{busy ? '...' : '게스트 로그인'}</button>
          </form>
        )}
        {errBox}
      </div>
    )
  } else {
    body = (
      <form onSubmit={submit} className="card col">
        <label>
          이메일
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          비밀번호
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        </label>
        {errBox}
        <button type="submit" disabled={busy}>{busy ? '...' : '로그인'}</button>
        <GoogleSignIn onError={onGoogleError} />
        <div style={{ fontSize: 13, color: 'var(--fg-dim)', textAlign: 'center', marginTop: 6 }}>
          계정이 없나요? <Link to="/signup">회원가입</Link>
        </div>
      </form>
    )
  }

  return (
    <div style={{ maxWidth: 400, margin: '60px auto' }}>
      <h1 style={{ color: 'var(--primary)' }}>tubewar 로그인</h1>
      {body}
    </div>
  )
}
