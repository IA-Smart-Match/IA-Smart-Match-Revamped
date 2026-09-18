/**
 * The class exercise's per-profile points counter.
 *
 * The requirements table's "Points" row asks, as a nice-to-have, for "a points
 * counter per profile that rises with attendance and card completion". This
 * component displays such a counter and does nothing else: the arithmetic is
 * `smartmatch_domain.exercise_points.profile_points`, server-side and tested
 * there, and this file adds no formula of its own. A total computed in a
 * browser from two counters is the defect ADR-0013 was written about; the same
 * discipline applies here even though nothing about the CBA rewards ledger is
 * shared with this screen.
 *
 * ## The only numbers here are points
 *
 * ADR-0025 D8: no percentage, rate, match score, or confidence. Points are
 * whole counts of a made-up profile's own events. There is no "top 10%", no
 * progress bar toward a threshold, and no reward catalog, redeeming, or extra
 * credit — those are the requirements row's explicit *not now*.
 *
 * ## Unknown stays unknown
 *
 * `cardCompletion` carries the domain's three states through unchanged. Before
 * a team's refresh has run, a profile's card state is `unknown`, and this
 * component says "not asked yet" rather than "no card" — a profile nobody has
 * asked has not refused.
 *
 * ## Not available is never drawn as zero
 *
 * Any of the three point figures may be `null`, meaning the caller does not
 * have it. It renders as the words "not available". Zero points is a real,
 * earned zero and renders as `0`.
 */

/** A points figure, or `null` when the caller does not have it. */
export type ExercisePointsValue = number | null;

/** The three card states of `smartmatch_domain.exercise_points.CardCompletion`. */
export type ExerciseCardCompletion = "unknown" | "not_completed" | "completed";

export interface ProfilePointsCounterProps {
  /** The made-up profile this counter belongs to, in the words the screen shows. */
  readonly profileName: string;
  /** `ProfilePoints.total`, computed server-side. */
  readonly total: ExercisePointsValue;
  /** `ProfilePoints.attendance_points`. */
  readonly attendancePoints: ExercisePointsValue;
  /** `ProfilePoints.card_points`. */
  readonly cardPoints: ExercisePointsValue;
  /** `ProfilePoints.card_completion`, carried through unchanged. */
  readonly cardCompletion: ExerciseCardCompletion;
}

const NOT_AVAILABLE = "not available";

/**
 * How each card state reads on screen.
 *
 * `unknown` is "not asked yet" on purpose: it is the state of every profile
 * before its team has run the refresh, and phrasing it as a refusal would
 * assert something about 300 profiles that nothing has established.
 */
const CARD_COMPLETION_WORDS: Readonly<Record<ExerciseCardCompletion, string>> = {
  unknown: "Card not asked yet",
  not_completed: "Card not completed",
  completed: "Card completed",
};

/** Renders a points figure: a number as itself, an absent figure in words. */
export function formatPoints(value: ExercisePointsValue): string {
  return typeof value === "number" ? String(value) : NOT_AVAILABLE;
}

/** The screen wording for a card state. */
export function cardCompletionLabel(cardCompletion: ExerciseCardCompletion): string {
  return CARD_COMPLETION_WORDS[cardCompletion];
}

export function ProfilePointsCounter({
  profileName,
  total,
  attendancePoints,
  cardPoints,
  cardCompletion,
}: ProfilePointsCounterProps): JSX.Element {
  const totalText = formatPoints(total);
  const hasTotal = typeof total === "number";

  return (
    <section
      aria-label={`Points for ${profileName}`}
      data-testid="profile-points-counter"
      style={{ fontSize: 22, lineHeight: 1.4 }}
    >
      <h3 style={{ fontSize: 26, margin: "0 0 8px" }}>{profileName}</h3>
      <p
        data-testid="profile-points-total"
        style={{ fontSize: hasTotal ? 56 : 30, fontWeight: 700, margin: "0 0 8px" }}
      >
        {totalText}
        {hasTotal ? <span style={{ fontSize: 26, fontWeight: 400 }}> points</span> : null}
      </p>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        <li data-testid="profile-points-attendance">
          From attending events: {formatPoints(attendancePoints)}
        </li>
        <li data-testid="profile-points-card">
          From completing a card: {formatPoints(cardPoints)}
        </li>
        <li data-testid="profile-points-card-state">{cardCompletionLabel(cardCompletion)}</li>
      </ul>
    </section>
  );
}

export default ProfilePointsCounter;
