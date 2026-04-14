import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Running inside a sandbox container: docker_manager._build_env sets
// SESSION_ID + PLAYGROUND_PUBLIC_HOST, and preview traffic is fronted
// by Cloudflare at https://playground.soxai.io. Configure HMR so the
// Vite client opens its WebSocket at the public URL rather than the
// iframe's console.soxai.io origin — otherwise the HMR socket dials
// into the Next.js SPA catch-all and never reaches the sandbox.
const sessionId = process.env.SESSION_ID || ''
const publicHost = process.env.PLAYGROUND_PUBLIC_HOST || 'playground.soxai.io'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    strictPort: true,
    // Allow any Host header — the FastAPI preview proxy strips the
    // public-facing Host on its way in, and whatever docker-proxy
    // rewrites it to doesn't match Vite's default allowlist.
    allowedHosts: true,
    cors: true,
    hmr: sessionId
      ? {
          protocol: 'wss',
          host: publicHost,
          clientPort: 443,
          path: `/preview/${sessionId}/__hmr`,
        }
      : true,
  },
})
