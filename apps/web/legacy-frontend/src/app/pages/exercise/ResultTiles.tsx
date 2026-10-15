/**
 * The numbers side by side (issue #327, Ann's revisions §3): the team's four
 * numbers always sit next to the result of emailing all 300, and on Harbor the
 * team's own Northline result as a third. Numbers only (ADR-0025 D8). Labels
 * are the screen's existing ones: the chart's "Invited / Signed up / Attended"
 * and the figures band's "Still open".
 */
import * as React from "react";

import type { ResultsView } from "../../../lib/exerciseClient";

interface Tile {
  readonly title: string;
  readonly invited: number;
  readonly signedUp: number;
  readonly attended: number;
  readonly open: number | null;
}

export function resultTiles(results: ResultsView): Tile[] {
  const tiles: Tile[] = [
    tile("Your team's 30", results.team, results.seats_empty),
    tile("Email everyone (all 300)", results.email_everyone, results.email_everyone.seats_empty),
  ];
  if (results.round_one !== null) {
    tiles.push(
      tile("Your team's Northline result", results.round_one.team, results.round_one.seats_empty),
    );
  }
  return tiles;
}

function tile(title: string, panel: ResultsView["team"], open: number | null | undefined): Tile {
  return {
    title,
    invited: panel.invited_count,
    signedUp: panel.signed_up_count,
    attended: panel.attended_count,
    open: open ?? null,
  };
}

export function ResultTiles({ results }: { readonly results: ResultsView }): React.JSX.Element {
  const tiles = resultTiles(results);
  return (
    <div
      data-slot="exercise-result-tiles"
      className={`grid gap-ce-4 ${tiles.length === 3 ? "md:grid-cols-3" : "md:grid-cols-2"}`}
    >
      {tiles.map((t) => (
        <section key={t.title} className="ce-card flex min-w-0 flex-col gap-ce-4 p-ce-4 md:p-ce-5">
          <h2 className="ce-type-h2 text-ce-ink">{t.title}</h2>
          <dl className="grid grid-cols-2 gap-ce-4">
            <Figure label="Invited" value={t.invited} />
            <Figure label="Signed up" value={t.signedUp} />
            <Figure label="Attended" value={t.attended} />
            {t.open === null ? null : <Figure label="Still open" value={t.open} />}
          </dl>
        </section>
      ))}
    </div>
  );
}

function Figure({ label, value }: { readonly label: string; readonly value: number }) {
  return (
    <div className="flex min-w-0 flex-col gap-ce-1">
      <dt className="ce-type-label text-ce-ink">{label}</dt>
      <dd className="ce-type-value ce-tabular text-ce-ink">{value}</dd>
    </div>
  );
}
