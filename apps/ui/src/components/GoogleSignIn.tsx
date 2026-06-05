import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.ts'
import { login } from '../auth.ts'

// GIS(Google Identity Services) 전역 — index.html 의 gsi/client 스크립트가 주입.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; callback: (r: { credential: string }) => void }) => void
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void
        }
      }
    }
  }
}

interface ProvidersOut {
  google: { enabled: boolean; client_id: string | null }
}

/**
 * 구글 로그인 버튼. 백엔드 /auth/providers 로 활성 여부+client_id 를 받아,
 * GOOGLE_CLIENT_ID 가 설정된 경우에만 버튼을 렌더한다(미설정 시 아무것도 안 보임).
 */
export default function GoogleSignIn({ onError }: { onError?: (msg: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const nav = useNavigate()
  const [clientId, setClientId] = useState<string | null>(null)

  // 1) 활성 여부 + client_id 조회
  useEffect(() => {
    let alive = true
    api<ProvidersOut>('/auth/providers')
      .then(p => { if (alive && p.google?.enabled && p.google.client_id) setClientId(p.google.client_id) })
      .catch(() => { /* 구글 미설정 — 버튼 숨김 */ })
    return () => { alive = false }
  }, [])

  // 2) GIS 스크립트 로드 대기 → 버튼 렌더 + 콜백 연결
  useEffect(() => {
    if (!clientId) return
    let tries = 0
    const timer = window.setInterval(() => {
      const gid = window.google?.accounts?.id
      if (!gid) {
        if (++tries > 50) window.clearInterval(timer) // ~5s 후 포기
        return
      }
      window.clearInterval(timer)
      gid.initialize({
        client_id: clientId,
        callback: async (resp: { credential: string }) => {
          try {
            const r = await api<{ access_token: string; user: any }>('/auth/google', {
              method: 'POST',
              json: { credential: resp.credential },
            })
            login(r.access_token, r.user)
            nav('/dashboard')
          } catch (e: any) {
            onError?.(e.message)
          }
        },
      })
      if (ref.current) {
        gid.renderButton(ref.current, {
          theme: 'outline', size: 'large', width: 320,
          text: 'signin_with', shape: 'rectangular', locale: 'ko',
        })
      }
    }, 100)
    return () => window.clearInterval(timer)
  }, [clientId, nav, onError])

  if (!clientId) return null
  return (
    <div className="col" style={{ alignItems: 'center', gap: 8, marginTop: 8 }}>
      <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>— 또는 —</div>
      <div ref={ref} />
    </div>
  )
}
