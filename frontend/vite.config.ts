import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite serves the React SPA in development and produces an optimized
// production build. The dev server proxies API requests to the local
// FastAPI backend (uvicorn on :8000) so the SPA can hit the same
// origin during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});