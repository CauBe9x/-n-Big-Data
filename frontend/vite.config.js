import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Khi chạy `npm run dev`, mọi request /api được chuyển tới backend FastAPI (cổng 8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_BACKEND || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
