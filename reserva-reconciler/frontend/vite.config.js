import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/mapping': { target: 'https://127.0.0.1:8000', secure: false, changeOrigin: true },
      '/auth':    { target: 'https://127.0.0.1:8000', secure: false, changeOrigin: true },
      '/classy':  { target: 'https://127.0.0.1:8000', secure: false, changeOrigin: true },
      '/health':  { target: 'https://127.0.0.1:8000', secure: false, changeOrigin: true },
    },
  },
})
