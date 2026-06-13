import React, { useEffect, useState } from 'react'
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

      <LlmSettingsCard />

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

// ──────────────────────────────────────────────────────
// AI 모델 (GPU 서버) — Ollama 연결 → 모델 선택 → 저장.
// 저장하면 드래그-질문 AI 튜터가 이 서버/모델로 동작한다.
// ──────────────────────────────────────────────────────
interface LlmSettings { url: string | null; model: string | null }
interface LlmModelsResp { connected: boolean; url: string; models: string[]; error?: string }

// 저장된 url(http://ip:port) → {ip, port} 로 역분해 (입력칸 프리필용)
function splitUrl(url: string | null): { ip: string; port: string } {
  if (!url) return { ip: '', port: '' }
  const m = url.replace(/^https?:\/\//, '').match(/^([^:/]+)(?::(\d+))?/)
  return { ip: m?.[1] || '', port: m?.[2] || '' }
}

function LlmSettingsCard() {
  const [ip, setIp] = useState('')
  const [port, setPort] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [savedModel, setSavedModel] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // 기존 설정 프리필
  useEffect(() => {
    api<LlmSettings>('/llm/settings').then(s => {
      const { ip, port } = splitUrl(s.url)
      setIp(ip); setPort(port)
      if (s.model) { setModel(s.model); setSavedModel(s.model); setModels([s.model]) }
    }).catch(() => {})
  }, [])

  const url = () => `http://${ip.trim()}:${(port || '11434').trim()}`

  async function connect() {
    if (!ip.trim()) { setMsg({ ok: false, text: 'GPU 서버 IP를 입력하세요.' }); return }
    setConnecting(true); setMsg(null)
    try {
      const d = await api<LlmModelsResp>('/llm/models', { method: 'POST', json: { url: url() } })
      if (!d.connected) {
        setModels([])
        setMsg({ ok: false, text: `연결 실패 — ${d.error || '응답 없음'}. (VPN 연결/주소 확인)` })
        return
      }
      setModels(d.models)
      setMsg({ ok: true, text: `연결됨 — 모델 ${d.models.length}개. 모델을 고르고 저장하세요.` })
      if (d.models.length > 0 && !d.models.includes(model)) setModel(d.models[0])
    } catch (e: any) {
      setMsg({ ok: false, text: e.message })
    } finally { setConnecting(false) }
  }

  async function save() {
    if (!ip.trim() || !model) { setMsg({ ok: false, text: '연결 후 모델을 선택하세요.' }); return }
    setSaving(true); setMsg(null)
    try {
      const s = await api<LlmSettings>('/llm/settings', { method: 'POST', json: { url: url(), model } })
      setSavedModel(s.model)
      setMsg({ ok: true, text: `저장 완료 — 이제 어느 페이지에서든 텍스트를 드래그해 "AI에게 질문"할 수 있습니다.` })
    } catch (e: any) {
      setMsg({ ok: false, text: e.message })
    } finally { setSaving(false) }
  }

  return (
    <div className="card col">
      <h3 style={{ marginTop: 0 }}>AI 모델 (GPU 서버) 🤖</h3>
      <div style={{ fontSize: 13, color: 'var(--fg-dim)', lineHeight: 1.5 }}>
        개인 GPU(Ollama) 서버를 연결하면, 어느 페이지에서든 <b>텍스트를 드래그 → "AI에게 질문"</b>으로
        현재 페이지 맥락과 선택한 내용을 근거로 한 답변을 받을 수 있습니다.
        <br />※ 서버가 VPN 너머라면 먼저 VPN을 연결해야 합니다.
      </div>
      <div className="row" style={{ alignItems: 'flex-end', flexWrap: 'wrap', gap: 8 }}>
        <div className="col" style={{ flex: 2, minWidth: 180, gap: 2 }}>
          <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>GPU 서버 IP</label>
          <input placeholder="211.170.162.139" value={ip} onChange={e => setIp(e.target.value)} />
        </div>
        <div className="col" style={{ flex: 1, minWidth: 90, gap: 2 }}>
          <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>포트</label>
          <input placeholder="11434" value={port} onChange={e => setPort(e.target.value)} />
        </div>
        <button type="button" onClick={connect} disabled={connecting}>
          {connecting ? '연결 중…' : '연결'}
        </button>
      </div>

      {models.length > 0 && (
        <div className="row" style={{ alignItems: 'flex-end', gap: 8, marginTop: 4 }}>
          <div className="col" style={{ flex: 1, gap: 2 }}>
            <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>모델 선택 (ollama list)</label>
            <select value={model} onChange={e => setModel(e.target.value)}>
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <button type="button" onClick={save} disabled={saving || !model}>
            {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      )}

      {savedModel && (
        <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
          현재 저장된 모델: <b style={{ color: 'var(--primary)' }}>{savedModel}</b>
        </div>
      )}
      {msg && (
        <div style={{ color: msg.ok ? 'var(--green)' : 'var(--red)', fontSize: 13, lineHeight: 1.5 }}>
          {msg.text}
        </div>
      )}
    </div>
  )
}
