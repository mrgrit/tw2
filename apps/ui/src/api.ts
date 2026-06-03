import { getToken } from './auth'

export type ApiOpts = RequestInit & { json?: unknown }

export async function api<T = any>(path: string, opts: ApiOpts = {}): Promise<T> {
  const headers = new Headers(opts.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let body = opts.body
  if (opts.json !== undefined) {
    headers.set('content-type', 'application/json')
    body = JSON.stringify(opts.json)
  }
  // 사용자별 데이터가 브라우저 캐시로 다른 계정에 새지 않도록 항상 no-store.
  const res = await fetch(path, { ...opts, headers, body, cache: 'no-store' })
  const text = await res.text()
  let parsed: any = null
  try { parsed = text ? JSON.parse(text) : null } catch { parsed = text }
  if (!res.ok) {
    const msg = parsed?.detail ?? parsed ?? `HTTP ${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return parsed as T
}
