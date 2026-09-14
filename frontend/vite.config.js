import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The common .env lives at the repo root (shared with the backend — see
  // backend/core/config.py's _ROOT_ENV_FILE), not inside frontend/.
  // Only VITE_-prefixed vars from it are ever exposed to client-side code.
  envDir: resolve(__dirname, ".."),
  server: {
    // Proxies /api/* to the backend so the dev server (localhost:5173) and the
    // API appear same-origin to the browser — required for the httpOnly auth
    // cookie to work without cross-origin SameSite=None/Secure (HTTPS) locally.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});