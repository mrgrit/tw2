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
  // SPA fallback(index.html)이 돌아오면 = API 라우트가 프록시에 없거나 서버가 죽은 것.
  // 이를 JSON 으로 오인해 HTML 문자열을 데이터처럼 렌더(예: 632글자 → 632건)하지 않도록 명확히 실패.
  const ctype = res.headers.get('content-type') || ''
  if (res.ok && (ctype.includes('text/html') || /^\s*<(!doctype|html)/i.test(text))) {
    throw new Error(`API 응답이 JSON 이 아닙니다(라우트 미연결/프록시 누락 가능): ${path}`)
  }
  let parsed: any = null
  try { parsed = text ? JSON.parse(text) : null } catch { parsed = text }
  if (!res.ok) {
    const msg = parsed?.detail ?? parsed ?? `HTTP ${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return parsed as T
}
