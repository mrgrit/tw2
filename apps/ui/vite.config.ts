import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// API 대상 — 배포 시 VITE_API_TARGET 으로 override 가능 (기본: 로컬 9200).
const API = process.env.VITE_API_TARGET || 'http://127.0.0.1:9200'

// 외부 노출(Cloudflare Tunnel 등) 시 vite 는 알 수 없는 Host 헤더를 차단하므로
// 허용 호스트를 명시한다. 기본은 quick tunnel 도메인(.trycloudflare.com).
// 커스텀 도메인 붙일 땐 TW2_ALLOWED_HOSTS=tw2.example.com,.other.com 로 추가.
const allowedHosts = [
  '.trycloudflare.com',
  ...(process.env.TW2_ALLOWED_HOSTS || '').split(',').map(h => h.trim()).filter(Boolean),
]

// 클라이언트 라우트(/initiative, /leaderboard 등)와 API 경로가 겹친다. 브라우저 페이지
// 새로고침/네비게이션(Accept: text/html)은 SPA 라우트이므로 API 로 넘기면 안 되고(넘기면
// 인증 없는 GET → {"detail":"missing token"} 원문 노출) index.html 을 서빙해야 한다.
// fetch/XHR(Accept: */* | application/json)만 API 로 프록시.
const bypass = (req: { method?: string; headers: Record<string, any> }) => {
  if ((req.method === 'GET' || req.method === 'HEAD') &&
      String(req.headers.accept || '').includes('text/html')) {
    return '/index.html'
  }
  return undefined
}
const to = (extra: Record<string, unknown> = {}) => ({ target: API, changeOrigin: false, bypass, ...extra })

// dev(server) 와 prod 미리보기(preview) 가 동일하게 API 로 프록시하도록 공유한다.
const proxy = {
  '/auth':        to(),
  '/infras':      to(),
  '/scenarios':   to(),
  '/leaderboard': to(),
  '/admin':       to(),
  '/users':       to(),
  '/cohorts':     to(),
  '/feedback':    to(),
  '/monitoring':  to(),
  '/me':          to(),   // 내 워크북/제출
  '/llm':         to(),   // 드래그-질문 AI 튜터(모델/설정/ask)
  '/training':    to(),   // 트레이닝(강의/실습/워크북)
  '/battles':     to({ ws: false }),
  '/initiative':  to(),   // 이니셔티브 게시판
  '/health':      to(),
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy,
    allowedHosts,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    proxy,
    allowedHosts,
  },
})
