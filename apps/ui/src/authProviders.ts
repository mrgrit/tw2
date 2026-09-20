import { useEffect, useState } from 'react'
import { api } from './api.ts'

// 백엔드 /auth/providers — 어떤 로그인 수단이 켜져 있는지(인증 불필요).
export interface AuthProviders {
  google: { enabled: boolean; client_id: string | null; allowed_domain: string | null }
  password: { enabled: boolean }
}

// 로그인 화면의 여러 컴포넌트(Login/GoogleSignIn/Signup)가 같이 쓰므로 요청은 한 번만.
let inflight: Promise<AuthProviders> | null = null

function load(): Promise<AuthProviders> {
  if (!inflight) {
    inflight = api<Partial<AuthProviders>>('/auth/providers')
      // 구버전 API(UI 만 먼저 배포된 경우)는 password/allowed_domain 키가 없다 → 기존 동작(비밀번호 on)으로.
      .then(p => ({
        google: {
          enabled: !!p.google?.enabled,
          client_id: p.google?.client_id ?? null,
          allowed_domain: p.google?.allowed_domain ?? null,
        },
        password: { enabled: p.password?.enabled ?? true },
      }))
      .catch(e => { inflight = null; throw e })
  }
  return inflight
}

/** undefined = 로딩 중, null = 조회 실패(서버 다운 등). */
export function useAuthProviders(): AuthProviders | null | undefined {
  const [p, setP] = useState<AuthProviders | null | undefined>(undefined)
  useEffect(() => {
    let alive = true
    load().then(v => { if (alive) setP(v) }).catch(() => { if (alive) setP(null) })
    return () => { alive = false }
  }, [])
  return p
}
