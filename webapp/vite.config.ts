import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Production: `npm run build` writes the app into the Python package, served by `geoeyes serve` (port 8765).
// Development: `npm run dev` on port 8766 (never Vite's default 5173), API proxied to `geoeyes serve`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/geoeyes/api/static",
    emptyOutDir: true,
    // the map engine (deck.gl + MapLibre) is large on its own: one cached chunk, loaded only by the pages with a map
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Vite's preload and CommonJS helpers: with the always-loaded code, or Rollup puts them in the map chunk and
          // every page preloads 1.9 MB of map engine
          if (id.includes("preload-helper") || id.includes("commonjsHelpers")) return "react";
          if (!id.includes("node_modules")) return;
          if (/[\/](@deck\.gl|@luma\.gl|@loaders\.gl|@math\.gl|@probe\.gl|maplibre-gl|pmtiles|earcut|h3-js|@mapbox)[\/]/.test(id)) return "map";
          if (/[\/]uplot[\/]/.test(id)) return "charts";
          if (/[\/](react|react-dom|scheduler|@tanstack)[\/]/.test(id)) return "react";
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 8766,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  preview: { host: "127.0.0.1", port: 8767, strictPort: true },
});
