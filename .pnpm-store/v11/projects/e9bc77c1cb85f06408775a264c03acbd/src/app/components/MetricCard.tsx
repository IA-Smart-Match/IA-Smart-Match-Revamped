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
  iconColor = "bg-[#EEE9FB] text-[#2F036C]",
  href,
}: MetricCardProps) {
  const changeColors = {
    positive: "bg-[#efe6fb] text-[#2f036c]",
    negative: "bg-[#fceff5] text-[#b42318]",
    neutral: "bg-[#f4ecff] text-[#2f036c]",
  };

  const inner = (
    <>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-600">
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
          <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[#DFD6F1] ${iconColor}`}>
            <Icon className="w-6 h-6" />
          </div>
          {href && (
            <ArrowRight className="h-4 w-4 text-[#2F036C] opacity-0 transition-opacity group-hover:opacity-100" />
          )}
        </div>
      </div>
    </>
  );

  if (href) {
    return (
      <Link
        to={href}
        className="group relative block overflow-hidden rounded-2xl border border-[#D8CDED] bg-white p-6 shadow-[0_1px_2px_rgba(47,3,108,0.04)] transition-shadow hover:shadow-md"
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-[#D8CDED] bg-white p-6 shadow-[0_1px_2px_rgba(47,3,108,0.04)] transition-shadow hover:shadow-md">
      {inner}
    </div>
  );
}
