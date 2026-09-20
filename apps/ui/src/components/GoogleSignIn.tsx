import React, { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.ts'
import { login } from '../auth.ts'
import { useAuthProviders } from '../authProviders.ts'

// GIS(Google Identity Services) 전역 — index.html 의 gsi/client 스크립트가 주입.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; hd?: string; callback: (r: { credential: string }) => void }) => void
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void
        }
      }
    }
  }
}

/**
 * 구글 로그인 버튼. 백엔드 /auth/providers 로 활성 여부+client_id 를 받아,
 * GOOGLE_CLIENT_ID 가 설정된 경우에만 버튼을 렌더한다(미설정 시 아무것도 안 보임).
 * divider=false 는 구글 전용 모드(비밀번호 폼 없음) — "또는" 구분선을 뺀다.
 */
export default function GoogleSignIn({ onError, divider = true }: {
  onError?: (msg: string) => void
  divider?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const nav = useNavigate()
  const google = useAuthProviders()?.google
  const clientId = google?.enabled ? google.client_id : null
  const hd = google?.allowed_domain || undefined

  // GIS 스크립트 로드 대기 → 버튼 렌더 + 콜백 연결
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
        hd, // 계정 선택창을 조직 도메인으로 좁히는 힌트일 뿐 — 실제 제한은 백엔드(hd 클레임 검증)
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
  }, [clientId, hd, nav, onError])

  if (!clientId) return null
  return (
    <div className="col" style={{ alignItems: 'center', gap: 8, marginTop: 8 }}>
      {divider && <div style={{ fontSize: 12, color: 'var(--fg-dim)' }}>— 또는 —</div>}
      <div ref={ref} />
    </div>
  )
}
