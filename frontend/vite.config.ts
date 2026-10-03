import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const controllerUrl = env.VITE_CONTROLLER_URL || 'http://127.0.0.1:8003'
  const coordinatorUrl = env.VITE_COORDINATOR_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api/controller': {
          target: controllerUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/controller/, '/api/controller')
        },
        '/api/experiments': {
          target: controllerUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/experiments/, '/api/experiments')
        },
        '/api/risk': {
          target: controllerUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/risk/, '/api/risk')
        },
        '/api/demo': {
          target: controllerUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/demo/, '/api/demo')
        },
        '/api': {
          target: coordinatorUrl,
          changeOrigin: true
        }
      }
    }
  }
})
