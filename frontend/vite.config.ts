import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const nodeProcess = (globalThis as { process?: { env?: Record<string, string | undefined>; platform?: string } }).process
const cacheDir =
  nodeProcess?.env?.VITE_CACHE_DIR ||
  (nodeProcess?.platform === 'win32' ? 'node_modules/.vite' : '/tmp/cloudbridge-vite-cache')

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  cacheDir,
  server: {
    host: '0.0.0.0',
    allowedHosts: [
      'cloud-bridge-frontend-himalay-testing.bobathon-us-south-1-bx2-1-eed9cf6127dd1cc2309a78aba5f4061d-0000.us-south.containers.appdomain.cloud',
    ],
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
