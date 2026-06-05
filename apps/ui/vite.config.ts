import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// API 대상 — 배포 시 VITE_API_TARGET 으로 override 가능 (기본: 로컬 9200).
const API = process.env.VITE_API_TARGET || 'http://127.0.0.1:9200'

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
  '/battles':   { target: API, changeOrigin: false, ws: false },
  '/health':      API,
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    proxy,
  },
})
