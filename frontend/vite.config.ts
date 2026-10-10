import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // A first lazy worker import must not trigger dependency discovery/reload
  // halfway through clip preparation in development.
  optimizeDeps: { include: ['mediabunny'] },
  server: { watch: { ignored: ['**/test-results/**', '**/playwright-report/**'] } },
})
