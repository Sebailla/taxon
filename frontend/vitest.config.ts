import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest runs in JSDOM so React components can render against a real
// DOM. The same React plugin used by Vite keeps JSX semantics in
// sync between tests and the production build.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: false,
  },
});