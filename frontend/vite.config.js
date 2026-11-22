import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build lands in app/static, which FastAPI serves at /. During development
// `npm run dev` proxies API calls to the local backend.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../app/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
