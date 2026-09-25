/**
 * The wording of the class exercise's "who is on the list" notice.
 *
 * Requirements row "Who is on the list": *"A one-line notice when a major or
 * year that exists among the 300 has nobody on the list."*
 *
 * Which groups are uncovered is decided on the server by
 * `smartmatch_domain/exercise_list_coverage.py`; this module decides only how
 * that reads. Keeping the sentence here rather than inside the component
 * means the promise — one line, plain words, no number — is testable without
 * rendering anything.
 *
 * No vocabulary of majors or class years appears in this file. Labels arrive
 * as data: the vocabularies are closed by Ann's workbook of 2026-09-24, but
 * the server owns them, not this module; even the "a"/"an" choice is made from the label's
 * own first letter rather than from a list this module would have to learn.
 *
 * Unknown never reaches here. A profile with no major on file is not a group
 * (ADR-0011), so the server never names one, and this module has no wording
 * for it — there is no "unspecified" or "other" sentence to fall into.
 */

/** The uncovered groups, exactly as the server reported them. */
export interface ListCoverageGaps {
  /** Majors carried by somebody in the whole set and by nobody on the list. */
  readonly missingMajors: readonly string[];
  /** The same for class years. */
  readonly missingClassYears: readonly string[];
}

/** "a" or "an", by the label's own first letter. */
function article(label: string): string {
  return /^[aeiou]/i.test(label) ? "an" : "a";
}

/** Joins phrases the way a person would speak them: "x", "x or y", "x, y, or z". */
function joinWithOr(phrases: readonly string[]): string {
  if (phrases.length <= 1) {
    return phrases[0] ?? "";
  }
  if (phrases.length === 2) {
    return `${phrases[0]} or ${phrases[1]}`;
  }
  return `${phrases.slice(0, -1).join(", ")}, or ${phrases[phrases.length - 1]}`;
}

/**
 * The single sentence for the notice, or `null` when there is nothing to say.
 *
 * Order is the caller's: majors in the order supplied, then class years. The
 * server supplies them in first-appearance order over the whole set, so once
 * Ann's year vocabulary is settled the reading order follows it with no
 * change here.
 *
 * Carries no count, share, score, or confidence (ADR-0025 D8). It says which
 * kinds of profile are absent, never how many.
 */
export function coverageNoticeLine(gaps: ListCoverageGaps): string | null {
  const phrases = [
    ...gaps.missingMajors.map((major) => `${article(major)} ${major} major`),
    ...gaps.missingClassYears.map((year) => `${article(year)} ${year}`),
  ];
  if (phrases.length === 0) {
    return null;
  }
  return `Nobody on this list is ${joinWithOr(phrases)}.`;
}
