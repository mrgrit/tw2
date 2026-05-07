import React, { useState } from 'react'
import { api } from '../api.ts'
import { getToken, getUser, login as saveAuth } from '../auth.ts'

interface UserOut {
  id: number
  email: string
  name: string
  role: string
  is_active: boolean
  created_at: string
}

export default function Profile() {
  const me = getUser()!
  const [name, setName] = useState(me.name)
  const [pwForm, setPwForm] = useState({ current: '', next: '', confirm: '' })
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState<'profile' | 'pw' | null>(null)

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault()
    setProfileMsg(null)
    setBusy('profile')
    try {
      const u = await api<UserOut>('/auth/me', { method: 'PATCH', json: { name } })
      // localStorage 의 user 갱신 — 토큰은 재발급 안 함 (이름은 토큰 payload 와 무관)
      saveAuth(getToken() || '', u as any)
      setProfileMsg({ ok: true, text: '프로필 저장 완료.' })
    } catch (err: any) {
      setProfileMsg({ ok: false, text: err.message })
    } finally {
      setBusy(null)
    }
  }

  async function changePw(e: React.FormEvent) {
    e.preventDefault()
    setPwMsg(null)
    if (pwForm.next !== pwForm.confirm) {
      setPwMsg({ ok: false, text: '새 비밀번호 확인이 일치하지 않습니다.' })
      return
    }
    if (pwForm.next.length < 8) {
      setPwMsg({ ok: false, text: '새 비밀번호는 8자 이상.' })
      return
    }
    setBusy('pw')
    try {
      await api('/auth/me/password', {
        method: 'POST',
        json: { current_password: pwForm.current, new_password: pwForm.next },
      })
      setPwForm({ current: '', next: '', confirm: '' })
      setPwMsg({ ok: true, text: '비밀번호 변경 완료. 다음 로그인부터 새 비밀번호 사용.' })
    } catch (err: any) {
      setPwMsg({ ok: false, text: err.message })
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>내 프로필</h1>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>계정 정보</h3>
        <table style={{ fontSize: 14 }}>
          <tbody>
            <tr><td style={{ color: 'var(--fg-dim)', paddingRight: 24 }}>이메일</td><td><b>{me.email}</b></td></tr>
            <tr><td style={{ color: 'var(--fg-dim)' }}>역할</td><td>
              <span className={`badge ${me.role === 'admin' ? 'red' : 'blue'}`}>{me.role}</span>
            </td></tr>
            <tr><td style={{ color: 'var(--fg-dim)' }}>user_id</td><td>#{me.id}</td></tr>
          </tbody>
        </table>
      </div>

      <form onSubmit={saveProfile} className="card col">
        <h3 style={{ marginTop: 0 }}>표시 이름 변경</h3>
        <input value={name} onChange={e => setName(e.target.value)} required maxLength={120} />
        {profileMsg && (
          <div style={{ color: profileMsg.ok ? 'var(--green)' : 'var(--red)', fontSize: 13 }}>
            {profileMsg.text}
          </div>
        )}
        <button type="submit" disabled={busy !== null || name.trim() === me.name}>저장</button>
      </form>

      <form onSubmit={changePw} className="card col">
        <h3 style={{ marginTop: 0 }}>비밀번호 변경</h3>
        <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>현재 비밀번호</label>
        <input type="password" autoComplete="current-password" required
          value={pwForm.current}
          onChange={e => setPwForm({ ...pwForm, current: e.target.value })} />
        <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>새 비밀번호 (8자 이상)</label>
        <input type="password" autoComplete="new-password" required minLength={8}
          value={pwForm.next}
          onChange={e => setPwForm({ ...pwForm, next: e.target.value })} />
        <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>새 비밀번호 확인</label>
        <input type="password" autoComplete="new-password" required minLength={8}
          value={pwForm.confirm}
          onChange={e => setPwForm({ ...pwForm, confirm: e.target.value })} />
        {pwMsg && (
          <div style={{ color: pwMsg.ok ? 'var(--green)' : 'var(--red)', fontSize: 13 }}>
            {pwMsg.text}
          </div>
        )}
        <button type="submit" disabled={busy !== null}>비밀번호 변경</button>
      </form>
    </>
  )
}
