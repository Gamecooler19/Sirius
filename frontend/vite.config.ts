import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fixed port so it matches the CORS_ORIGINS entries added to
    // deploy/.env (http://localhost:5173, http://127.0.0.1:5173) --
    // genuinely cross-origin against the backend on 127.0.0.1:38210,
    // no dev-server proxy standing in for CORS. `host: true` binds all
    // interfaces (not just `localhost`) so the app is actually reachable
    // at the `127.0.0.1:5173` origin too -- required because the session
    // cookie is `SameSite=Strict` and `localhost`/`127.0.0.1` are
    // different sites under the SameSite algorithm even though CORS
    // treats them as distinct-but-allowed origins; only the 127.0.0.1
    // origin can actually receive and resend a cookie the 127.0.0.1
    // backend sets (see reports/module-06-frontend-foundation.md Defect 1).
    host: true,
    port: 5173,
    strictPort: true,
  },
})
