/**
 * Component-test configuration, kept separate from `vite.config.ts`.
 *
 * The frontend's existing suite (`tests/*.test.ts`, `npm test`) runs on
 * `node --test` and asserts over pure modules and file contents. That harness
 * cannot mount a component: Node strips TypeScript types but does not compile
 * JSX. So a component whose whole job is what it renders — the class
 * exercise's projector chart and points counter — needs a runner that does,
 * and this config is the smallest one that works: jsdom, and the `src` tree's
 * own `*.test.tsx` files. The `node --test` suite is untouched and still runs
 * under `npm test`.
 *
 * Deliberately not `mergeConfig`-ed with the dev-server config: nothing here
 * needs the proxy, the tunnel host list, or the manual chunking, and importing
 * them would couple the test run to dev-server settings that change for
 * unrelated reasons.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.tsx"],
  },
});
