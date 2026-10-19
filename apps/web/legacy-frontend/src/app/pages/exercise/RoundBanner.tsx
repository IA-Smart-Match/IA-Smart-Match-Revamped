/** Large "Round N of M: Name" banner at the top of each student event page. */
import * as React from "react";
import { Link } from "react-router";

import { readEvents } from "../../../lib/exerciseClient";
import {
  roundBannerLine,
  roundBannerTitle,
  roundOneDoneLine,
  roundsOf,
  type RoundPage,
} from "./teamStatusWording";
import { useExerciseResource } from "./useExerciseResource";

async function readRounds(signal: AbortSignal) {
  return roundsOf((await readEvents(signal)).events);
}

export function RoundBanner({
  page,
  eventKey,
  revision = 0,
}: {
  readonly page: RoundPage;
  /** Omitted on the asking page, which is round 2's. */
  readonly eventKey?: string;
  readonly revision?: number;
}): React.JSX.Element | null {
  const { state } = useExerciseResource(readRounds, [revision]);
  if (state.status !== "ready") {
    return null;
  }
  const rounds = state.data;
  const round =
    eventKey === undefined ? rounds[1] : rounds.find((r) => r.eventKey === eventKey);
  if (round === undefined) {
    return null;
  }
  const next = rounds[1];
  const done = page === "results" && round.round === 1 && round.run && next !== undefined;
  return (
    <section data-slot="exercise-round-banner" className="ce-card flex flex-col gap-ce-2 p-ce-4 text-ce-ink md:p-ce-5">
      <h2 className="ce-type-h1">{roundBannerTitle(round, rounds.length)}</h2>
      <p className="ce-type-body">{roundBannerLine(page, round)}</p>
      {done ? (
        <p className="ce-type-body font-bold">
          {roundOneDoneLine(next)}{" "}
          <Link to="/exercise/asking">Go to Round 2</Link>
        </p>
      ) : null}
    </section>
  );
}
