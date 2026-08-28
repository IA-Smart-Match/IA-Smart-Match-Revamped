import { Link } from "react-router";
import { ArrowRight, LucideIcon } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
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
  iconColor = "bg-[#e6effb] text-[#005394]",
  href,
}: MetricCardProps) {
  const changeColors = {
    positive: "bg-[#eaf6ef] text-[#1f7a46]",
    negative: "bg-[#fef1f1] text-[#b42318]",
    neutral: "bg-[#eef4ff] text-[#005394]",
  };

  const inner = (
    <>
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#005394] via-[#2b6cb0] to-[#d5e0f7]" />
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#005394]/70">
            {title}
          </p>
          <p className="mt-2 text-4xl font-semibold tracking-tight text-gray-900">
            {value}
          </p>
          {change ? (
            <p className={`mt-4 inline-flex rounded-full px-3 py-1 text-xs font-medium ${changeColors[changeType]}`}>
              {change}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[#d5e0f7] ${iconColor}`}>
            <Icon className="w-6 h-6" />
          </div>
          {href && (
            <ArrowRight className="h-4 w-4 text-[#005394] opacity-0 transition-opacity group-hover:opacity-100" />
          )}
        </div>
      </div>
    </>
  );

  if (href) {
    return (
      <Link
        to={href}
        className="group relative overflow-hidden rounded-2xl border border-[#cfd8e5] bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-md block"
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-[#cfd8e5] bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-md">
      {inner}
    </div>
  );
}
