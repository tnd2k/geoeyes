import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Production: `npm run build` writes the app into the Python package, served by `geoeyes serve` (port 8765).
// Development: `npm run dev` on port 8766 (never Vite's default 5173), API proxied to `geoeyes serve`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../src/geoeyes/api/static", emptyOutDir: true, chunkSizeWarningLimit: 2500 },
  server: {
    host: "127.0.0.1",
    port: 8766,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  preview: { host: "127.0.0.1", port: 8767, strictPort: true },
});
