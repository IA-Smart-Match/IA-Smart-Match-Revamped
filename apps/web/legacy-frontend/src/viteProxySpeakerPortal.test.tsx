// @vitest-environment node
/**
 * The dev and preview servers must forward `/s/{token}` (the Speaker portal
 * activation page and its form POST) to the API, and nothing else under `/s…`
 * (B26 T6b-1 plan §3.5). T6a's `viteProxy.test.tsx` checks `/i/` the same way;
 * the two fold into one when T6a rebases onto this.
 */
import { describe, expect, it } from "vitest";

import config from "../vite.config";

type ProxyTable = Record<string, unknown>;

/** Vite 6.4.3's own `doesProxyContextMatchUrl`, copied (as in T6a's test). */
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
  it.each(["/s/abc", "/s/abc0123456789def?x=1"])("proxies %s", (url) => {
    expect(isProxied(proxy ?? {}, url)).toBe(true);
  });

  it.each(["/speaker-portal", "/settings", "/s", "/search"])("does not proxy %s", (url) => {
    expect(isProxied(proxy ?? {}, url)).toBe(false);
  });
});
