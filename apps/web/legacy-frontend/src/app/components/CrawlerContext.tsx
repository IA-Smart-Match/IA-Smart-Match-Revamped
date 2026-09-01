import { createContext, useContext, type ReactNode } from "react";

/**
 * The legacy web-crawler surface is retired. It is archived under MM-A08 and
 * gated behind G3 (see plan P6) — there is no crawler running, so there is
 * nothing to poll and nothing to report. This is the only truthful state:
 * we do not model a fake "idle" or "done" crawl in its place.
 */
interface CrawlerRetiredStatus {
  availability: "retired";
  reason: string;
}

interface CrawlerContextValue {
  status: CrawlerRetiredStatus;
  /**
   * No-op. Kept only so existing consumers that call `refresh()` still
   * typecheck. There is no crawler to refresh: the surface is retired
   * (MM-A08) and gated (G3), so this never issues network requests.
   */
  refresh: () => void;
}

const RETIRED_STATUS: CrawlerRetiredStatus = {
  availability: "retired",
  reason:
    "The web-crawler surface is archived (MM-A08) and gated behind G3; no crawler runs in this build.",
};

const CrawlerContext = createContext<CrawlerContextValue>({
  status: RETIRED_STATUS,
  refresh: () => {},
});

export function CrawlerProvider({ children }: { children: ReactNode }) {
  return (
    <CrawlerContext.Provider value={{ status: RETIRED_STATUS, refresh: () => {} }}>
      {children}
    </CrawlerContext.Provider>
  );
}

export function useCrawlerStatus(): CrawlerContextValue {
  return useContext(CrawlerContext);
}
