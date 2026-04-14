import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Running inside a sandbox container: docker_manager._build_env sets
// SESSION_ID + PLAYGROUND_PUBLIC_HOST + SOXAI_API_KEY + SOXAI_BASE_URL,
// and preview traffic is fronted by Cloudflare at https://playground.soxai.io.
//
// Two concerns handled here:
//
// 1. HMR: Vite client reads location.host in the browser to build its
//    HMR WebSocket URL. Inside the console-proxied iframe that resolves
//    to console.soxai.io, which has no /@vite/hmr route. We override
//    host/protocol/clientPort/path so the client dials a known URL on
//    playground.soxai.io, where api/preview.py has a WebSocket endpoint
//    that bridges into the container.
//
// 2. SoxAI API access from the in-browser app: the sandbox token is a
//    REAL user-owned API token (created via console POST /api/tokens
//    with the user's JWT) that can spend the user's real balance.
//    Putting it in import.meta.env would leak it to browser JS — any
//    XSS Claude introduces could exfiltrate it. Instead, we expose a
//    /soxai/* reverse proxy here that the Vite dev server handles
//    server-side, injecting the Authorization header at proxy-request
//    time so the token never leaves the Node process env.
const sessionId = process.env.SESSION_ID || ''
const publicHost = process.env.PLAYGROUND_PUBLIC_HOST || 'playground.soxai.io'
const soxaiApiKey = process.env.SOXAI_API_KEY || ''
const soxaiBaseUrl = process.env.SOXAI_BASE_URL || ''

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
    // Browser-facing /soxai/* → Vite dev server → upstream SoxAI API.
    // Authorization is injected here in Node, not in client JS, so
    // the user's API token never lands in browser-accessible memory.
    // Usage from user code:
    //   fetch('/soxai/v1/chat/completions', {
    //     method: 'POST',
    //     headers: { 'Content-Type': 'application/json' },
    //     body: JSON.stringify({ model, messages, stream: false }),
    //   })
    proxy: soxaiApiKey && soxaiBaseUrl
      ? {
          '/soxai': {
            target: soxaiBaseUrl,
            changeOrigin: true,
            secure: true,
            rewrite: (path) => path.replace(/^\/soxai/, ''),
            configure: (proxy) => {
              proxy.on('proxyReq', (proxyReq) => {
                proxyReq.setHeader(
                  'Authorization',
                  `Bearer ${soxaiApiKey}`,
                )
              })
            },
          },
        }
      : undefined,
  },
})
