import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Vite配置 - 包含TailwindCSS和API代理
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 代理后端API，避免CORS问题
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err, req) => {
            if (req.url === '/api/heartbeat') return
            console.warn('[vite] api proxy error:', req.url, err.message)
          })
        },
      },
    },
  },
})
