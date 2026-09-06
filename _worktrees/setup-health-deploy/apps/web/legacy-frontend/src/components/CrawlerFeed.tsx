import { Globe } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";

interface CrawlerFeedProps {
  className?: string;
}

export function CrawlerFeed({ className }: CrawlerFeedProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Globe className="h-4 w-4" />
          Web Crawler Feed
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md bg-gray-50 px-3 py-3 text-sm text-muted-foreground">
          <p className="font-medium text-[#394454]">Web-crawler surface retired</p>
          <p className="mt-1">
            This crawler is archived (MM-A08) and gated behind G3. No crawl data is shown here, and
            none is being collected.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default CrawlerFeed;
