import { useEffect, useRef, useState, useCallback } from "react";
import { CheckCircle2, Globe, Loader2, Trash2, XCircle, RefreshCw } from "lucide-react";

import { Button } from "@/app/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { startCrawl, fetchCrawlerResults, clearCrawlerResults, type CrawlerEvent } from "@/lib/api";
import { useCrawlerStatus } from "@/app/components/CrawlerContext";

interface CrawlerFeedProps {
  className?: string;
}

const SOURCE_LABELS: Record<string, string> = {
  gemini: "Gemini",
  tavily: "Tavily",
  seed: "Seed",
  search: "Search",
};

const SOURCE_COLORS: Record<string, string> = {
  gemini: "bg-blue-50 text-blue-700",
  tavily: "bg-purple-50 text-purple-700",
  seed: "bg-gray-100 text-gray-600",
  search: "bg-amber-50 text-amber-700",
};

function dbRowToEvent(row: Record<string, unknown>): CrawlerEvent {
  return {
    url: String(row["url"] ?? ""),
    title: String(row["title"] ?? ""),
    status: (row["status"] as CrawlerEvent["status"]) ?? "found",
    timestamp: String(row["crawled_at"] ?? new Date().toISOString()),
    source: (row["source"] as CrawlerEvent["source"]) ?? undefined,
  };
}

export function CrawlerFeed({ className }: CrawlerFeedProps) {
  const [events, setEvents] = useState<CrawlerEvent[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [savedLabel, setSavedLabel] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { status, refresh: refreshStatus } = useCrawlerStatus();
  const crawlRunning = status?.state === "running";

  // Keep a stable ref so the SSE effect doesn't close/reopen every 3 s when the
  // provider re-renders from its own poll and refreshStatus's identity changes.
  const refreshStatusRef = useRef(refreshStatus);
  useEffect(() => { refreshStatusRef.current = refreshStatus; });

  // Load saved results from DB (called on mount and after crawl finishes)
  const loadSavedResults = useCallback(() => {
    fetchCrawlerResults()
      .then((res) => {
        if (res.count > 0) {
          const mapped = res.events.map(dbRowToEvent);
          setEvents(mapped);
          setSavedLabel(`Last saved crawl (${res.count} pages)`);
        }
      })
      .catch(() => {});
  }, []);

  // On mount: hydrate from DB, and if a crawl is already running start polling
  useEffect(() => {
    loadSavedResults();
  }, [loadSavedResults]);

  // Poll results while a crawl is running (handles "left page, came back" scenario)
  useEffect(() => {
    if (crawlRunning && !isLive) {
      setSavedLabel(null);
      pollRef.current = setInterval(() => {
        fetchCrawlerResults()
          .then((res) => {
            if (res.count > 0) {
              setEvents(res.events.map(dbRowToEvent));
            }
          })
          .catch(() => {});
      }, 3000);
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      // If crawl just finished (status flipped to done), reload from DB
      if (status?.state === "done" && !isLive) {
        loadSavedResults();
      }
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [crawlRunning, isLive, status?.state, loadSavedResults]);

  // SSE live stream (while user stays on the page)
  useEffect(() => {
    if (!isLive) {
      return;
    }

    const es = new EventSource("/api/crawler/feed");
    esRef.current = es;

    let startRequested = false;
    es.onopen = () => {
      if (startRequested) return;
      startRequested = true;
      void (async () => {
        try {
          await startCrawl();
          refreshStatusRef.current();
        } catch {
          es.close();
          setIsLive(false);
        }
      })();
    };

    es.onmessage = (e: MessageEvent) => {
      let data: Partial<CrawlerEvent> & { status?: string; source?: string };
      try {
        data = JSON.parse(e.data as string) as Partial<CrawlerEvent> & { status?: string; source?: string };
      } catch {
        return;
      }

      if (data.status === "done") {
        setIsDone(true);
        setIsLive(false);
        es.close();
        refreshStatusRef.current();
        loadSavedResults();
        return;
      }

      const event: CrawlerEvent = {
        url: data.url ?? "",
        title: data.title ?? "",
        status: (data.status as CrawlerEvent["status"]) ?? "crawling",
        timestamp: data.timestamp ?? new Date().toISOString(),
        source: (data.source as CrawlerEvent["source"]) ?? undefined,
      };

      setEvents((prev) => [event, ...prev].slice(0, 100));
      setSavedLabel(null);
    };

    es.onerror = () => {
      es.close();
      setIsLive(false);
      // Status poll will still detect when the crawl completes via /api/crawler/status
      refreshStatusRef.current();
    };

    return () => {
      esRef.current?.close();
    };
    // refreshStatusRef is a ref — stable, intentionally omitted from deps.
    // loadSavedResults is memoized with useCallback([]) so it's stable too.
  }, [isLive, loadSavedResults]);

  function handleStartCrawl() {
    setIsLive(true);
    setIsDone(false);
    setEvents([]);
    setSavedLabel(null);
  }

  function handleClearResults() {
    clearCrawlerResults()
      .then(() => {
        setEvents([]);
        setIsDone(false);
        setSavedLabel(null);
      })
      .catch(() => {});
  }

  const foundCount = events.filter((ev) => ev.status === "found").length;
  const isDisabled = isLive || crawlRunning;
  const hasSavedResults = events.length > 0 && !isLive && !crawlRunning;

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Globe className="h-4 w-4" />
            Web Crawler Feed
          </CardTitle>
          <div className="flex items-center gap-2">
            {hasSavedResults && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleClearResults}
                title="Clear all saved crawler results from the database"
                className="text-red-600 hover:text-red-700 hover:border-red-300"
              >
                <Trash2 className="mr-1 h-3 w-3" />
                Clear
              </Button>
            )}
            <Button
              size="sm"
              variant={isDisabled ? "outline" : "default"}
              onClick={handleStartCrawl}
              disabled={isDisabled}
              title={crawlRunning && !isLive ? "Crawl already running" : undefined}
            >
              {isLive ? (
                <>
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  Crawling…
                </>
              ) : crawlRunning ? (
                "Running…"
              ) : (
                "Start Crawl"
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Status indicators */}
        {isDone && (
          <div className="mb-3 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
            <div className="font-medium">Found {foundCount} directed school pages — results saved</div>
            {status?.visited_count != null && status.visited_count > 0 && (
              <div className="mt-0.5 text-green-600 text-xs">
                Visited {status.visited_count} URLs total
                {status.visited_urls && (() => {
                  const bySource = status.visited_urls.reduce<Record<string, number>>((acc, v) => {
                    acc[v.source] = (acc[v.source] ?? 0) + 1;
                    return acc;
                  }, {});
                  return Object.entries(bySource).map(([src, count]) => (
                    <span key={src} className="ml-2">· {count} via {src}</span>
                  ));
                })()}
              </div>
            )}
          </div>
        )}
        {crawlRunning && !isLive && (
          <div className="mb-3 flex items-center gap-2 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Crawl in progress — results updating every 3 s
          </div>
        )}
        {savedLabel && !crawlRunning && !isLive && (
          <div className="mb-3 flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm text-gray-600">
            <span>{savedLabel}</span>
            <button
              onClick={loadSavedResults}
              className="ml-2 text-gray-400 hover:text-gray-600"
              aria-label="Refresh saved results"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <div className="max-h-[280px] overflow-y-auto space-y-1.5">
          {events.length === 0 && !isLive && !crawlRunning && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Click &quot;Start Crawl&quot; to discover IA West directed school pages
            </p>
          )}
          {events.map((event, i) => (
            <div
              key={`${event.timestamp}-${i}`}
              className="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm transition-all duration-300"
            >
              <span className="mt-0.5 shrink-0">
                {event.status === "crawling" && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
                )}
                {event.status === "found" && (
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                )}
                {event.status === "error" && (
                  <XCircle className="h-3.5 w-3.5 text-red-400" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium truncate">
                    {event.title || event.url}
                  </span>
                  {event.source && SOURCE_LABELS[event.source] && (
                    <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${SOURCE_COLORS[event.source] ?? "bg-gray-100 text-gray-600"}`}>
                      {SOURCE_LABELS[event.source]}
                    </span>
                  )}
                </div>
                {event.url && event.title && (
                  <span className="text-xs text-muted-foreground truncate block">
                    {event.url}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default CrawlerFeed;
