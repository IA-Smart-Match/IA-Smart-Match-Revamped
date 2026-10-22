// @vitest-environment node
/**
 * The dev and preview servers must forward `/i/{token}` (the Speaker invitation
 * page and its form POST) to the API, and nothing else under `/i…`.
 *
 * The pilot tunnel points at Vite, which proxies only what `vite.config.ts`
 * lists; an unproxied `/i/{token}` gets the SPA's index.html instead of the
 * page. The key is the regex `^/i/`: a plain `"/i"` key is a prefix match and
 * would also catch `/index.html` and `/images/…`. Read off the real config, so
 * a change to either proxy block is caught here.
 */
import { describe, expect, it } from "vitest";

import config from "../vite.config";

type ProxyTable = Record<string, unknown>;

/**
 * A copy of Vite 6.4.3's own proxy matcher, `doesProxyContextMatchUrl` in
 * `node_modules/vite/dist/node/chunks/dep-*.js`:
 * `context[0] === "^" && new RegExp(context).test(url) || url.startsWith(context)`.
 */
function doesProxyContextMatchUrl(context: string, url: string): boolean {
  return (context[0] === "^" && new RegExp(context).test(url)) || url.startsWith(context);
}

function isProxied(proxy: ProxyTable, url: string): boolean {
  return Object.keys(proxy).some((context) => doesProxyContextMatchUrl(context, url));
}

const resolved = config as { server?: { proxy?: ProxyTable }; preview?: { proxy?: ProxyTable } };

const blocks: Array<[string, ProxyTable | undefined]> = [
  ["server.proxy", resolved.server?.proxy],
  ["preview.proxy", resolved.preview?.proxy],
];

describe.each(blocks)("%s", (_name, proxy) => {
  it("exists", () => {
    expect(proxy).toBeDefined();
  });

  it.each(["/i/abc0123456789def", "/i/abc0123456789def?x=1"])("proxies %s", (url) => {
    expect(isProxied(proxy ?? {}, url)).toBe(true);
  });

  it.each(["/index.html", "/images/x.png", "/i", "/inbox"])("does not proxy %s", (url) => {
    expect(isProxied(proxy ?? {}, url)).toBe(false);
  });

  it.each(["/api/health", "/v1/x"])("still proxies %s", (url) => {
    expect(isProxied(proxy ?? {}, url)).toBe(true);
  });
});

/**
 * uvicorn closes an idle keep-alive socket after 5 s (its default). An agent that
 * keeps idle upstream sockets longer can reuse one the API just closed: the request
 * dies with ECONNRESET and the student sees a 500 (load runs of 2026-10-21/22, #413).
 * Idle sockets must be dropped first; a slow request in flight is not affected.
 */
describe("upstream keep-alive agent", () => {
  const UVICORN_KEEP_ALIVE_MS = 5000;
  it.each(["/api", "/v1"])("drops idle %s sockets before uvicorn does", (key) => {
    const entry = (resolved.preview?.proxy ?? {})[key] as {
      agent?: { keepAlive?: boolean; options?: { timeout?: number } };
    };
    expect(entry.agent?.keepAlive).toBe(true);
    const timeout = entry.agent?.options?.timeout ?? Infinity;
    expect(timeout).toBeLessThan(UVICORN_KEEP_ALIVE_MS);
  });
});
