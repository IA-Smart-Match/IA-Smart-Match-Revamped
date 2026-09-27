/**
 * Button (DESIGN.md §6.3): primary, secondary, quiet, destructive.
 *
 * - One primary per region; the caller keeps to that.
 * - Pending: the label becomes the in-progress verb (`pendingLabel`), a 16px
 *   spinner leads, `aria-disabled` is set and clicks are ignored.
 * - Disabled: 45% opacity and `not-allowed`, but still focusable (so the
 *   reason is reachable) — `aria-disabled`, not the `disabled` attribute —
 *   with the reason wired through `describedBy`.
 * - 56px tall at ≥768px, 48px below; never under the 44px target.
 * - Motion: `ce-press` on every variant; `ce-lift` on the filled ones.
 */
import * as React from "react";
import { LoaderCircle } from "lucide-react";

import { cn } from "../../../components/ui/utils";

export type ButtonVariant = "primary" | "secondary" | "quiet" | "destructive";

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "disabled"> {
  readonly variant?: ButtonVariant;
  /** Work is in flight: show `pendingLabel` and a spinner, ignore presses. */
  readonly pending?: boolean;
  /** The in-progress verb, e.g. "Opening your team's work…". */
  readonly pendingLabel?: React.ReactNode;
  /** Unavailable. Stays focusable; pair with `describedBy` for the reason. */
  readonly disabled?: boolean;
  /** Id of the element that says why the button is disabled. */
  readonly describedBy?: string;
  /** A lucide icon (20px) before the label. */
  readonly leadingIcon?: React.ReactNode;
}

const VARIANT_CLASSES: Readonly<Record<ButtonVariant, string>> = {
  primary:
    "ce-lift min-h-ce-control px-ce-5 bg-ce-primary text-ce-on-primary hover:bg-[color-mix(in_srgb,var(--ce-primary)_92%,black)]",
  secondary:
    "min-h-ce-control px-ce-5 bg-ce-surface text-ce-ink border-2 border-ce-line-strong hover:border-ce-primary hover:bg-ce-primary-tint",
  quiet:
    "min-h-ce-target px-ce-2 bg-transparent text-ce-primary underline-offset-4 decoration-1 hover:underline hover:decoration-2",
  destructive:
    "ce-lift min-h-ce-control px-ce-5 bg-ce-danger text-ce-on-danger hover:bg-[color-mix(in_srgb,var(--ce-danger)_92%,black)]",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    pending = false,
    pendingLabel,
    disabled = false,
    describedBy,
    leadingIcon,
    type = "button",
    className,
    children,
    onClick,
    ...rest
  },
  ref,
) {
  const inert = pending || disabled;
  const describedByIds =
    [describedBy, rest["aria-describedby"]].filter((id) => id !== undefined && id !== "").join(" ") ||
    undefined;

  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      data-slot="ce-button"
      data-variant={variant}
      data-pending={pending ? "true" : undefined}
      aria-disabled={inert ? true : undefined}
      aria-describedby={describedByIds}
      onClick={(event) => {
        if (inert) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      className={cn(
        "ce-press ce-type-label inline-flex min-w-ce-target items-center justify-center gap-ce-2 rounded-ce-control",
        VARIANT_CLASSES[variant],
        disabled && "cursor-not-allowed opacity-45",
        pending && "cursor-progress",
        className,
      )}
    >
      {pending ? (
        <LoaderCircle
          aria-hidden="true"
          className="ce-spin size-4 shrink-0 animate-spin motion-reduce:animate-none"
        />
      ) : leadingIcon !== undefined ? (
        <span aria-hidden="true" className="inline-flex shrink-0 [&>svg]:size-5">
          {leadingIcon}
        </span>
      ) : null}
      <span>{pending && pendingLabel !== undefined ? pendingLabel : children}</span>
    </button>
  );
});
