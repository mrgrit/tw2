import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'
import { fmtTime } from '../time.ts'

interface Infra {
  id: number
  name: string
  kind: string
  vm_ip: string
  web_entry_ip: string | null
  ssh_user: string
  bastion_api_key: string
  status: string
  last_smoke_at: string | null
  last_smoke_result: any | null
  created_at: string
}

const PORT_HINTS = [
  { port: 80, label: 'HTTP (vhost)' },
  { port: 443, label: 'HTTPS' },
  { port: 2204, label: 'bastion SSH' },
  { port: 2202, label: 'attacker SSH (insider)' },
  { port: 2203, label: 'attacker-ext SSH (외부 침입자)' },
  { port: 8000, label: 'portal' },
  { port: 5601, label: 'siem-lite' },
  { port: 9100, label: 'bastion API' },
]

const statusColor: Record<string, string> = {
  healthy: 'green', registered: 'yellow', degraded: 'red', error: 'red',
}

export default function MyInfra() {
  const [infras, setInfras] = useState<Infra[]>([])
  const [loading, setLoading] = useState(true)
  const [smokingId, setSmokingId] = useState<number | null>(null)
  const [showPorts, setShowPorts] = useState(false)
  const [form, setForm] = useState<{
    name: string; kind: string; vm_ip: string; web_entry_ip: string;
    ssh_user: string; ssh_password: string;
    bastion_api_key: string; port_map: Record<string, number>;
  }>({
    name: '', kind: 'target', vm_ip: '', web_entry_ip: '',
    ssh_user: 'ccc', ssh_password: 'ccc',
    bastion_api_key: 'ccc-api-key-2026',
    port_map: {},
  })
  const [err, setErr] = useState<string | null>(null)

  async function refresh() {
    try {
      setInfras(await api<Infra[]>('/infras'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  async function register(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      await api('/infras', { method: 'POST', json: form })
      setForm({ ...form, name: '', vm_ip: '', web_entry_ip: '' })
      await refresh()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  async function smoke(id: number) {
    setSmokingId(id)
    try {
      await api(`/infras/${id}/smoke`, { method: 'POST' })
      await refresh()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setSmokingId(null)
    }
  }

  async function remove(id: number) {
    if (!confirm('인프라 등록을 삭제할까요?')) return
    await api(`/infras/${id}`, { method: 'DELETE' })
    await refresh()
  }

  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>내 인프라</h1>
      <p style={{ color: 'var(--fg-dim)' }}>
        공방전 대상이 될 <b>타깃 VM</b>(el34)과 <b>외부 공격자 VM</b> 두 인프라의 외부 IP·자격 증명을 등록합니다.
        미션 지시문 속 IP는 <b>여기 등록한 인프라로 자동 치환</b>됩니다. (타깃엔 Assessor key, 웹 진입 IP가 관리
        IP와 다르면 별도 입력)
      </p>

      {!loading && infras.length < 2 && (
        <form onSubmit={register} className="card col">
          <h3 style={{ marginTop: 0 }}>인프라 등록 {infras.length === 1 && '(나머지 1개 추가)'}</h3>
          <div className="row">
            <label style={{ flex: 1 }}>
              alias
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                placeholder="el34-target / attacker" required />
            </label>
            <label style={{ flex: '0 0 140px' }}>
              역할(kind)
              <select value={form.kind} onChange={e => setForm({...form, kind: e.target.value})}>
                <option value="target">target (el34 타깃)</option>
                <option value="attacker">attacker (외부 공격자)</option>
              </select>
            </label>
            <label style={{ flex: 1 }}>
              VM 외부 IP{form.kind === 'target' ? ' (관리/SSH/Assessor)' : ''}
              <input value={form.vm_ip} onChange={e => setForm({...form, vm_ip: e.target.value})}
                placeholder="192.168.0.123" required />
            </label>
          </div>
          {form.kind === 'target' && (
            <label>
              웹 진입 IP (선택 — 비우면 위 VM IP 사용)
              <input value={form.web_entry_ip} onChange={e => setForm({...form, web_entry_ip: e.target.value})}
                placeholder="공격 인입 IP (관리 IP와 다를 때만)" />
            </label>
          )}
          <div className="row">
            <label style={{ flex: 1 }}>
              SSH user
              <input value={form.ssh_user} onChange={e => setForm({...form, ssh_user: e.target.value})} />
            </label>
            <label style={{ flex: 1 }}>
              SSH password
              <input type="password" value={form.ssh_password}
                onChange={e => setForm({...form, ssh_password: e.target.value})} />
            </label>
          </div>
          <label>
            Bastion API key (header X-API-Key)
            <input value={form.bastion_api_key}
              onChange={e => setForm({...form, bastion_api_key: e.target.value})} />
          </label>

          <label style={{ fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={showPorts}
              onChange={e => setShowPorts(e.target.checked)} style={{ width: 'auto', marginRight: 6 }} />
            el34 의 <code>.env</code> 로 포트를 override 했음
          </label>

          {showPorts && (
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {[
                ['http', 80], ['https', 443],
                ['bastion_ssh', 2204], ['attacker_ssh', 2202], ['attacker_ext_ssh', 2203],
                ['portal', 8000], ['siem_lite', 5601], ['bastion_api', 9100],
              ].map(([key, def]) => (
                <label key={key as string} style={{ flex: '1 0 30%', fontSize: 12 }}>
                  {key}
                  <input type="number" placeholder={String(def)}
                    value={form.port_map[key as string] ?? ''}
                    onChange={e => {
                      const v = e.target.value
                      setForm(f => {
                        const pm = { ...f.port_map }
                        if (v === '') delete pm[key as string]
                        else pm[key as string] = parseInt(v, 10)
                        return { ...f, port_map: pm }
                      })}}
                    style={{ fontSize: 13 }} />
                </label>
              ))}
            </div>
          )}

          <details style={{ color: 'var(--fg-dim)', fontSize: 13 }}>
            <summary>등록 시 검증되는 항목</summary>
            <ul>
              {PORT_HINTS.map(p => (
                <li key={p.port}>TCP <code>{p.port}</code> — {p.label}</li>
              ))}
              <li>Bastion API GET <code>/health</code> with X-API-Key</li>
            </ul>
          </details>
          {err && <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div>}
          <button type="submit">등록</button>
        </form>
      )}

      {infras.map(i => (
        <div key={i.id} className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h3 style={{ margin: 0 }}>{i.name}</h3>
            <span className="badge">{i.kind === 'attacker' ? '공격자' : '타깃'}</span>
            <span className={`badge ${statusColor[i.status] || 'yellow'}`}>{i.status}</span>
            <div style={{ flex: 1 }} />
            <button onClick={() => smoke(i.id)} disabled={smokingId === i.id}>
              {smokingId === i.id ? 'smoke 중...' : 'smoke 테스트'}
            </button>
            <button className="danger" onClick={() => remove(i.id)}>삭제</button>
          </div>
          <div style={{ marginTop: 8, color: 'var(--fg-dim)', fontSize: 13 }}>
            IP <code>{i.vm_ip}</code>{i.web_entry_ip && <> · 웹진입 <code>{i.web_entry_ip}</code></>} · SSH <code>{i.ssh_user}@…</code>
            {i.last_smoke_at && <> · 마지막 검증 {fmtTime(i.last_smoke_at, true)}</>}
          </div>

          {i.last_smoke_result && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, color: 'var(--fg-dim)' }}>
                {i.last_smoke_result.summary}
              </div>
              <table style={{ width: '100%', marginTop: 8, fontSize: 13, borderCollapse: 'collapse' }}>
                <tbody>
                  {(i.last_smoke_result.checks || []).map((c: any, idx: number) => (
                    <tr key={idx} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: '6px 8px' }}>
                        <span className={`badge ${c.ok || c.status_code === 200 ? 'green' : 'red'}`}>
                          {(c.ok ?? (c.status_code === 200)) ? 'PASS' : 'FAIL'}
                        </span>
                      </td>
                      <td style={{ padding: '6px 8px' }}>{c.check}</td>
                      <td style={{ padding: '6px 8px' }}>
                        {c.label ? `${c.label} :${c.port}` : c.url}
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--fg-dim)' }}>
                        {c.error || (c.status_code ? `HTTP ${c.status_code}` : '')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}

      {loading && <div className="card">로딩 중...</div>}
    </>
  )
}
