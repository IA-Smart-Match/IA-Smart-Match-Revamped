/**
 * "How much we know" — the three markers, in Ann's words.
 *
 * Requirements, "How much we know" row: *"Next to every profile, a simple
 * marker: major only; major plus events attended; completed card."* Those
 * three phrases are the requirements' own, so they are written here rather
 * than derived: the API carries the wire values `major_only`,
 * `major_plus_events` and `completed_card`, and a projector needs the words.
 *
 * This is not an OQ-CE-01 vocabulary. That open row is about the *data file's*
 * columns and values — majors, years, interests — and nothing in this module
 * touches those; they render as whatever strings the file carries.
 *
 * An unrecognised marker renders as itself rather than as "unknown" or as
 * nothing. Design spec §7: absent information is `unknown`, and an empty card
 * is not the same as no card — collapsing a fourth marker into one of these
 * three would be inventing an answer.
 */

/** The three the requirements name, keyed by the value the API sends. */
const MARKER_LABELS: Readonly<Record<string, string>> = {
  major_only: "major only",
  major_plus_events: "major plus events attended",
  completed_card: "completed card",
};

/** Ann's words for a marker, or the marker itself if it is not one of the three. */
export function markerLabel(marker: string): string {
  return MARKER_LABELS[marker] ?? marker;
}

/**
 * The label for one of the three counted dimensions.
 *
 * `GroupCountsView.dimension` is `major`, `class_year` or `marker`. The first
 * needs no translation; the other two are internal spellings of words the
 * requirements write differently.
 */
export function dimensionLabel(dimension: string): string {
  if (dimension === "class_year") {
    return "year";
  }
  if (dimension === "marker") {
    return "how much we know";
  }
  return dimension;
}
