/**
 * Notice (DESIGN.md §6.20): a calm refusal, a transport problem, or a done
 * state, as a composed card.
 *
 * - `message` is the server's sentence, rendered verbatim: never re-cased,
 *   truncated or prefixed with "Error" (§9).
 * - Every tone is `role="status"` (§8.6: refusals are status, not alert;
 *   `alert` is for field errors only).
 * - Calm: surface card with shadow, `Info` in primary. Problem: surface card
 *   with a 2px danger outline and no shadow (a card has one or the other,
 *   §3.7), `TriangleAlert`. Done: avocado-tint wash, `CircleCheck`.
 * - No left-border stripe. Enters with `ce-notice-in`.
 */
import * as React from "react";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "../../../components/ui/utils";
import { ceMotion, usePrefersReducedMotion } from "./motion";

export type NoticeTone = "calm" | "problem" | "done";

export interface NoticeProps {
  readonly message: string;
  readonly tone?: NoticeTone;
  /** At most one action, e.g. "Try again" or "Check again". */
  readonly action?: React.ReactNode;
  /** Anything else the notice must carry, under the sentence. */
  readonly children?: React.ReactNode;
  /** Lets another element point at this notice with `aria-describedby`. */
  readonly id?: string;
  readonly className?: string;
}

const TONE_CLASSES: Readonly<Record<NoticeTone, string>> = {
  calm: "bg-ce-surface shadow-ce-1",
  problem: "bg-ce-surface border-2 border-ce-danger",
  done: "bg-ce-avocado-tint",
};

function ToneIcon({ tone }: { readonly tone: NoticeTone }): React.JSX.Element {
  const className = "mt-[3px] size-6 shrink-0";
  if (tone === "problem") {
    return <TriangleAlert aria-hidden="true" className={cn(className, "text-ce-danger")} />;
  }
  if (tone === "done") {
    return <CircleCheck aria-hidden="true" className={cn(className, "text-ce-primary")} />;
  }
  return <Info aria-hidden="true" className={cn(className, "text-ce-primary")} />;
}

export function Notice({
  message,
  tone = "calm",
  action,
  children,
  id,
  className,
}: NoticeProps): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  return (
    <motion.div
      {...ceMotion("notice-in", reduced)}
      id={id}
      role="status"
      data-slot="exercise-notice"
      data-tone={tone}
      data-reduced-motion={reduced ? "true" : "false"}
      className={cn(
        "flex items-start gap-ce-3 rounded-ce-card p-ce-4 text-ce-ink md:p-ce-5",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <ToneIcon tone={tone} />
      <div className="flex min-w-0 flex-col gap-ce-3">
        <p className="ce-type-body ce-measure">{message}</p>
        {children === undefined ? null : <div>{children}</div>}
        {action === undefined ? null : <div className="flex flex-wrap gap-ce-3">{action}</div>}
      </div>
    </motion.div>
  );
}
