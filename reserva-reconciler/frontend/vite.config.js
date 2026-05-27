import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE is set to '/Donor-CRM-Reserva-/' in the GitHub Actions workflow.
// In local dev it is unset, so the base defaults to '/' (normal behaviour).
const base = process.env.VITE_BASE || '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/mapping': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/auth':    { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/classy':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/export':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/donors':  { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
