/**
 * "You will send: [name]" — what the chosen final setting's list holds, shown
 * before the team commits its one run (Ann Wang 2026-10-16, results item 7).
 *
 * Reads the same ranked list the event page builds (`readRankedList` with the
 * saved setting's name, so the server applies the saved weights) and reuses
 * `ListCompositionTable` for the counts by major, class year and "how much we
 * know". No second ranker. A failed read says so and leaves the run alone.
 */
import * as React from "react";
import { Link } from "react-router-dom";

import { readRankedList, type RankedListView } from "../../../lib/exerciseClient";
import { ListCompositionTable } from "./ListCompositionTable";

export function ChosenListSummary({
  eventKey,
  settingName,
}: {
  readonly eventKey: string;
  /** The chosen final setting, or "" when none is chosen. */
  readonly settingName: string;
}): React.JSX.Element | null {
  const [list, setList] = React.useState<RankedListView | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    setList(null);
    setFailed(false);
    if (settingName === "") {
      return undefined;
    }
    const controller = new AbortController();
    readRankedList(eventKey, { kind: "setting", name: settingName }, controller.signal).then(
      (read) => setList(read),
      () => {
        if (!controller.signal.aborted) {
          setFailed(true);
        }
      },
    );
    return () => controller.abort();
  }, [eventKey, settingName]);

  if (settingName === "") {
    return null;
  }
  return (
    <section data-slot="exercise-chosen-list" className="flex flex-col gap-ce-4">
      <h2 className="ce-type-h2 text-ce-ink">{`You will send: ${settingName}`}</h2>
      {failed ? (
        <p className="ce-type-body ce-measure text-ce-ink-muted">
          This list could not be loaded. You can still read it on the event page.
        </p>
      ) : list === null ? (
        <p className="ce-type-body text-ce-ink-muted" role="status">
          Loading this list…
        </p>
      ) : (
        <>
          <p className="ce-type-body ce-measure text-ce-ink">
            {`This list holds ${list.entries.length} names, by major, by year and by how much we know:`}
          </p>
          <ListCompositionTable
            composition={list.composition}
            unrankableProfileCount={list.unrankable_profile_count}
          />
        </>
      )}
      <p className="ce-type-body">
        <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`}>See the full list on the event page</Link>
      </p>
    </section>
  );
}
