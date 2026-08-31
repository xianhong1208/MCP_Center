import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = 'http://localhost:4568'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../static/web',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts']
        }
      }
    }
  },
  server: {
    // 注意:/tokens、/clients、/consent 是 SPA 路由,不能 proxy
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/oauth': { target: BACKEND, changeOrigin: true },
      '/.well-known': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, changeOrigin: true, ws: true },
    }
  }
})
