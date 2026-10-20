/**
 * "Before and after asking" — the team's own setting run twice on the same
 * event with the same chance draws, plus a "major first" row for contrast
 * (Ann Wang, Oct 2026). The server computes the rows on read; they do not use
 * up the team's one results run. Renders nothing in round one.
 */
import * as React from "react";

import type { BeforeAfterView } from "../../../lib/exerciseClient";

export function HarborBeforeAfter({
  beforeAfter,
}: {
  readonly beforeAfter?: BeforeAfterView | null;
}): React.JSX.Element | null {
  if (!beforeAfter || beforeAfter.rows.length === 0) return null;
  return (
    <section
      data-slot="exercise-before-after"
      className="flex flex-col gap-ce-3 border-t border-ce-line pt-ce-5"
    >
      <h2 className="ce-type-h2 text-ce-ink">Before and after asking</h2>
      <p className="ce-type-body ce-measure text-ce-ink-muted">
        These rows use the same event and the same chance draws as your run. They do not use up
        your results run.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">
            Sign-ups for the same event: before asking, after asking, and major first
          </caption>
          <thead>
            <tr className="ce-type-meta bg-ce-surface-sunk font-semibold text-ce-ink">
              <th scope="col" className="px-ce-3 py-ce-2">
                Setting
              </th>
              <th scope="col" className="px-ce-3 py-ce-2 text-right">
                Mass email alone
              </th>
              <th scope="col" className="px-ce-3 py-ce-2 text-right">
                With your list
              </th>
              <th scope="col" className="px-ce-3 py-ce-2 text-right">
                Your list added
              </th>
            </tr>
          </thead>
          <tbody className="ce-type-body text-ce-ink">
            {beforeAfter.rows.map((row) => (
              <tr key={row.label} className="border-b border-ce-line last:border-b-0">
                <th scope="row" className="px-ce-3 py-ce-2 font-normal">
                  {row.label}
                </th>
                <td className="ce-tabular px-ce-3 py-ce-2 text-right">{row.mass_email_signups}</td>
                <td className="ce-tabular px-ce-3 py-ce-2 text-right">{row.with_list_signups}</td>
                <td className="ce-tabular px-ce-3 py-ce-2 text-right">
                  {row.list_added} ({row.list_added_came} came)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ce-type-body ce-measure text-ce-ink">
        Same event, same students, same luck. The only difference is what we knew about them.
      </p>
    </section>
  );
}
