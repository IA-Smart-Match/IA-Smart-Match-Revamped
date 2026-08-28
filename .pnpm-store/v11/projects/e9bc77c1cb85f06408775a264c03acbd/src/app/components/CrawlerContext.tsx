import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchCrawlerStatus, type CrawlerStatusResponse } from "@/lib/api";

interface CrawlerContextValue {
  status: CrawlerStatusResponse | null;
  refresh: () => void;
}

const CrawlerContext = createContext<CrawlerContextValue>({
  status: null,
  refresh: () => {},
});

export function CrawlerProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<CrawlerStatusResponse | null>(null);

  // Stable reference — must not change on re-renders so SSE effects in consumers
  // don't teardown/reconnect every 3 s when this provider re-renders from the poll.
  const refresh = useCallback(() => {
    fetchCrawlerStatus()
      .then(setStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    // Poll every 3 s — stops being meaningful once state=done but cost is negligible
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <CrawlerContext.Provider value={{ status, refresh }}>
      {children}
    </CrawlerContext.Provider>
  );
}

export function useCrawlerStatus(): CrawlerContextValue {
  return useContext(CrawlerContext);
}
