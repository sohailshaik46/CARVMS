import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    // Vite rejects requests whose Host header it doesn't recognize (DNS
    // rebinding protection). "np.vigilance.com" is a LOCAL-ONLY nickname --
    // it only resolves at all once you add it to the Windows hosts file
    // (127.0.0.1 np.vigilance.com) -- it is never registered/public, so
    // this stays local to this machine regardless.
    allowedHosts: ['localhost', 'np.vigilance.com'],
  },
})
