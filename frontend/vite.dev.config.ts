import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Solo desarrollo: proxy hacia una API local de desarrollo (puerto 8001) con cookies sin Secure
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: { '/api': { target: 'http://127.0.0.1:8001', xfwd: true } },
  },
})
