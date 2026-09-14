interface BrandLogoProps {
  label?: string;
  compact?: boolean;
  className?: string;
}

export function BrandLogo({ label, compact = false, className = "" }: BrandLogoProps) {
  return (
    <div className={`min-w-0 ${className}`}>
      <img
        src="/brand/cpp-horizontal-green.png"
        alt="Cal Poly Pomona"
        className={`brand-logo ${compact ? "max-w-[150px]" : "max-w-[205px]"}`}
      />
      {label && (
        <p className="mt-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">
          {label}
        </p>
      )}
    </div>
  );
}
