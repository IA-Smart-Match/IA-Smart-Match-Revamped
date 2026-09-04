import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Where the dev/preview server forwards `/api` and `/v1`.
 *
 * Defaults to a locally-run API (`make run-api`, port 8000). Point it at the
 * compose stack's published API — `http://127.0.0.1:8080` — to click through
 * the portals as the seeded compose principal; INSTALL.md documents that
 * sequence. Read from `process.env` (config time), not `import.meta.env`:
 * it configures the dev server, and is never bundled into the app.
 */
const configuredProxyTarget = process.env.SMARTMATCH_API_PROXY_TARGET?.trim();
const apiProxyTarget =
  configuredProxyTarget && configuredProxyTarget.length > 0
    ? configuredProxyTarget
    : "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        // Use IPv4 literal so Windows + Node do not prefer ::1 when the API binds 127.0.0.1 only.
        target: apiProxyTarget,
        changeOrigin: true,
      },
      // Authenticated job/import routes and the planned domain routes use /v1.
      // Without this the browser gets index.html back and the failure reads as
      // a JSON parse error a long way from its cause.
      "/v1": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/v1": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  assetsInclude: ["**/*.svg", "**/*.csv"],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules")) {
            if (
              id.includes("react-dom") ||
              id.includes("react-router") ||
              (id.includes("/react/") && !id.includes("react-"))
            ) {
              return "vendor-react";
            }
            if (id.includes("recharts") || id.includes("d3-")) {
              return "vendor-charts";
            }
            if (id.includes("@mui/") || id.includes("@radix-ui/")) {
              return "vendor-ui";
            }
            if (id.includes("@emotion/")) {
              return "vendor-emotion";
            }
          }
        },
      },
    },
  },
});
