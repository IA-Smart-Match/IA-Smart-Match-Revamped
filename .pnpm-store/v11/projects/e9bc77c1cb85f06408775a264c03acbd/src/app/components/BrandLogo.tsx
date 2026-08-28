import { Link } from "react-router";
import { cn } from "./ui/utils";

interface BrandLogoProps {
  href?: string;
  caption?: string;
  subcaption?: string;
  direction?: "row" | "column";
  className?: string;
  imageClassName?: string;
  textClassName?: string;
  showBadge?: boolean;
}

export function BrandLogo({
  href = "/",
  caption,
  subcaption,
  direction = "row",
  className,
  imageClassName,
  textClassName,
  showBadge = false,
}: BrandLogoProps) {
  const containerClassName = cn(
    "group inline-flex shrink-0 items-center",
    direction === "column" ? "flex-col items-start gap-2" : "flex-row gap-3",
    className,
  );

  const badgeClassName = cn(
    "flex items-center justify-center transition-transform duration-200 group-hover:scale-[1.01]",
    !showBadge && "border-transparent bg-transparent px-0 py-0 shadow-none",
  );

  const textBlock = caption || subcaption ? (
    <span className={cn("min-w-0", textClassName)}>
      {caption ? <span className="block text-sm font-semibold leading-tight">{caption}</span> : null}
      {subcaption ? (
        <span className="block text-[11px] font-semibold uppercase tracking-[0.22em] opacity-70">
          {subcaption}
        </span>
      ) : null}
    </span>
  ) : null;

  const content = (
    <>
      <span className={badgeClassName}>
        <img
          src="/insights-association-logo.png"
          alt="Insights Association"
          className={cn("block h-8 w-auto object-contain", imageClassName)}
        />
      </span>
      {textBlock}
    </>
  );

  if (href) {
    return (
      <Link to={href} className={containerClassName}>
        {content}
      </Link>
    );
  }

  return <div className={containerClassName}>{content}</div>;
}
