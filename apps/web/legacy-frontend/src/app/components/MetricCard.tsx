import { Link } from "react-router";
import { ArrowRight, LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  value: string | number | ReactNode;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  icon: LucideIcon;
  iconColor?: string;
  href?: string;
}

export function MetricCard({
  title,
  value,
  change,
  changeType = "neutral",
  icon: Icon,
  iconColor = "bg-primary/10 text-primary",
  href,
}: MetricCardProps) {
  const changeColors = {
    positive: "bg-accent text-accent-foreground",
    negative: "bg-destructive/10 text-destructive",
    neutral: "bg-accent text-primary",
  };

  const inner = (
    <>
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-primary/70 to-secondary" />
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/70">
            {title}
          </p>
          <p className="mt-2 text-4xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
          {change ? (
            <p className={`mt-4 inline-flex rounded-full px-3 py-1 text-xs font-medium ${changeColors[changeType]}`}>
              {change}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-border ${iconColor}`}>
            <Icon className="w-6 h-6" />
          </div>
          {href && (
            <ArrowRight className="h-4 w-4 text-primary opacity-0 transition-opacity group-hover:opacity-100" />
          )}
        </div>
      </div>
    </>
  );

  if (href) {
    return (
      <Link
        to={href}
        className="group relative overflow-hidden rounded-2xl border border-border bg-card p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-md block"
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-border bg-card p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-md">
      {inner}
    </div>
  );
}
