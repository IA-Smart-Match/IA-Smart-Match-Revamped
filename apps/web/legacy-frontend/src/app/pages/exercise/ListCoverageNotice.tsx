/**
 * One line: which majors or years among the whole set have nobody on the list.
 *
 * Requirements row "Who is on the list" — the notice that sits beside the
 * counts table. The table itself belongs to the exercise's matching screen,
 * which does not exist yet; this component is built so that screen can drop
 * it in, which is why it takes the uncovered groups as props and fetches
 * nothing. The server side of the same decision is
 * `smartmatch_domain/exercise_list_coverage.py`.
 *
 * Renders nothing when no group is missing. A notice that appears only when
 * there is something to notice is the point of the row; an empty
 * "all groups represented" line would be one more thing on a projector.
 *
 * Type is sized for the back of Dr. Lin's classroom (design spec §16). It
 * wraps itself in no portal shell and behind no session gate, because the
 * exercise has no login at all (ADR-0025 D1).
 */
import * as React from "react";
import { UsersRound } from "lucide-react";

import { cn } from "../../components/ui/utils";
import { coverageNoticeLine, type ListCoverageGaps } from "./listCoverageNotice";

export interface ListCoverageNoticeProps extends ListCoverageGaps {
  className?: string;
}

export function ListCoverageNotice({
  missingMajors,
  missingClassYears,
  className,
}: ListCoverageNoticeProps): React.JSX.Element | null {
  const line = coverageNoticeLine({ missingMajors, missingClassYears });
  if (line === null) {
    return null;
  }
  return (
    <p
      role="status"
      data-slot="exercise-list-coverage-notice"
      className={cn(
        "flex items-start gap-3 rounded-lg border-2 border-slate-300 bg-slate-50 px-5 py-4 text-xl leading-snug font-medium text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-50",
        className,
      )}
    >
      <UsersRound aria-hidden="true" className="mt-1 size-6 shrink-0" />
      <span>{line}</span>
    </p>
  );
}
