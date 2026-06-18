import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './', 
  server: {
    allowedHosts: true, // 允许所有主机
    host: '0.0.0.0',    // 允许局域网访问
    hmr: {
      clientPort: 443,  // 强制热更新走 HTTPS（解决 Cloudflare 兼容性）
    }
  }
})