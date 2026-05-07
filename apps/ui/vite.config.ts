import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/auth':      'http://127.0.0.1:9200',
      '/infras':    'http://127.0.0.1:9200',
      '/scenarios':   'http://127.0.0.1:9200',
      '/leaderboard': 'http://127.0.0.1:9200',
      '/admin':       'http://127.0.0.1:9200',
      '/battles':   { target: 'http://127.0.0.1:9200', changeOrigin: false, ws: false },
      '/health':    'http://127.0.0.1:9200',
    },
  },
})
