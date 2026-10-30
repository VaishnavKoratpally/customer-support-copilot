import react from '@vitejs/plugin-react'
import process from 'node:process'
import { defineConfig } from 'vite'

export default defineConfig({
  base: '/workbench/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/v1': {
        target: process.env.WORKBENCH_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
