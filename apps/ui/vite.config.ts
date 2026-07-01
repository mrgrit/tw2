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

// dev(server) 와 prod 미리보기(preview) 가 동일하게 API 로 프록시하도록 공유한다.
const proxy = {
  '/auth':        API,
  '/infras':      API,
  '/scenarios':   API,
  '/leaderboard': API,
  '/admin':       API,
  '/users':       API,
  '/cohorts':     API,
  '/feedback':    API,
  '/monitoring':  API,
  '/me':          API,   // 내 워크북/제출 — 누락 시 SPA fallback(index.html)이 반환돼 깨짐
  '/llm':         API,   // 드래그-질문 AI 튜터(모델/설정/ask)
  '/training':    API,   // 트레이닝(강의/실습/워크북) — 누락 시 SPA fallback 으로 목록이 안 뜸
  '/battles':   { target: API, changeOrigin: false, ws: false },
  '/initiative':  API,   // 이니셔티브 게시판
  '/health':      API,
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
