import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', 'VITE_')
  return {
    envDir: '..',
    plugins: [react()],
    server: { port: 5173, proxy: { '/api': { target: env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } } },
    test: { environment: 'jsdom', setupFiles: './src/testSetup.ts' },
  }
})
