/**
 * Speaker feedback — student portal (customer §§15-16, OQ-CBA-003).
 *
 * A student rates the speakers they heard, from 1 to 5, with an optional
 * comment, and may amend or take the rating back until seven days after the
 * event. That is the whole decision, and every part of it is enforced on the
 * server: this page holds no rule of its own.
 *
 * ## What this page deliberately does not do
 *
 * It offers no way to rate a speaker for the **first** time, and the reason is
 * a gap rather than a preference. There is no student-visible route that lists
 * the speakers at an event. The roster reads that exist —
 * `GET .../speaker-contacts` and `GET .../cba/confirmed-speakers` — are
 * `admin`/`coordinator` server-side, so calling one from here would earn a
 * `403` and teach a reader that a student surface may be built on a route the
 * server refuses. The only two remaining ways to produce a speaker id in the
 * browser would be to invent a list, or to ask a student to type an identifier
 * — the second being MM-A01's caller-selected identity in a new spelling.
 *
 * So the page says so, in the empty state, in words. A surface that quietly
 * showed nothing would be indistinguishable from a student who has rated
 * nobody, which is the ADR-0011 defect applied to a capability instead of to a
 * number. The amend and withdraw path below is complete and real; first-time
 * submission waits on a student-scoped read of the speakers at an attended
 * event, and this is a deliberate partial delivery rather than an oversight.
 *
 * ## What it does do, and why each part is the server's answer
 *
 * `GET .../student/events/{event_id}/speaker-feedback` returns the caller's own
 * rows and is scoped to them by the session — there is no parameter to aim it
 * with. Withdrawn rows come back too, because "you withdrew this" and "you
 * never rated this speaker" are different facts and this is the surface that
 * has to tell them apart.
 *
 * Whether a rating may still be changed is `edit_window.state`, resolved
 * server-side from the event's own anchor. This page never compares a date. The
 * window has three states and the third is the interesting one: `unknown` means
 * the event carries no resolved date, so no cutoff can be measured — which is
 * neither a cutoff that has not arrived nor one that has, and it is rendered as
 * the third thing it is.
 *
 * Controls stay rendered when the window is closed. A UI gate is not
 * authorization, the server answers `409 student_feedback_window_closed` in
 * words, and hiding the control would tell a student the capability does not
 * exist rather than that it has expired.
 *
 * ## B07 discipline
 *
 * Nothing here reports a result it did not observe. The write returns the
 * stored row and a `changed` flag, and the two are rendered as the different
 * facts they are: a repeat of an identical submission comes back with `changed`
 * false, and saying "saved" to that would claim an edit that did not happen.
 * After every write the list is re-read, so if a write did not persist the page
 * comes back saying so.
 *
 * ## OQ-CBA-053
 *
 * No rating on this page feeds matching. Nothing here mentions scoring, because
 * nothing here is scoring — and the Connector's aggregate surface, which is
 * where a reader might reasonably assume otherwise, says so out loud.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarX2, Info, MessageSquare } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchMySpeakerFeedback,
  fetchStudentAgenda,
  submitSpeakerFeedback,
  withdrawSpeakerFeedback,
  type StudentEvent,
  type StudentSpeakerFeedback as StoredFeedback,
} from "../../../lib/api";
import { scopedQueryKey } from "../../../lib/queryClient";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { useScopedQuery } from "../../hooks/useScopedQuery";

/** The five points on the scale. There is no zero: see the module docstring. */
const RATING_CHOICES = [1, 2, 3, 4, 5] as const;

/** `student_speaker_feedback.status` — the server's two values, mirrored. */
const SUBMITTED = "submitted";

/**
 * What the server's three window states mean to a student, in their words.
 *
 * `unknown` is not a hedge. The event has no resolved date, so there is no
 * cutoff to measure against, and saying "closes soon" or "still open" would
 * both be inventions.
 */
const WINDOW_TEXT: Record<string, string> = {
  open: "You can still change or withdraw this.",
  closed: "The window for changing feedback on this event has closed.",
  unknown:
    "This event has no confirmed date recorded, so there is no cutoff to measure. " +
    "Whether a change is still accepted is the server's answer, not this page's guess.",
};

/** When the event happened, at whatever precision is actually known. */
function whenText(event: StudentEvent): string {
  const { precision, starts_at: startsAt, on_date: onDate, time_zone: zone } = event.time;
  if (precision === "exact" && startsAt !== null) {
    const rendered = new Date(startsAt).toLocaleString("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: zone ?? "UTC",
    });
    return zone === null ? rendered : `${rendered} (${zone})`;
  }
  if (onDate !== null) {
    return `${onDate} · time not yet announced`;
  }
  return "Date not yet announced";
}

/**
 * One stored rating, with the controls to amend or withdraw it.
 *
 * The row is not copied into component state. The draft values below are what
 * this student has typed and not yet sent; they are seeded from the stored row
 * and re-seeded after every reload. Anything the page claims about what is
 * saved comes from `row`, which came from the server.
 */
function FeedbackRow({
  row,
  unitId,
  eventId,
  onChanged,
}: {
  row: StoredFeedback;
  unitId: string;
  eventId: string;
  onChanged: () => Promise<void>;
}) {
  const [draftRating, setDraftRating] = useState<number | null>(row.rating);
  const [draftComment, setDraftComment] = useState(row.comment ?? "");
  const [pending, setPending] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  // The server's own report of what the last write did, or null before one.
  // True and false are different answers, and neither is a success banner.
  const [lastWriteChanged, setLastWriteChanged] = useState<boolean | null>(null);

  // Re-seed the draft whenever the stored row moves under it — after a reload,
  // the server's answer replaces whatever was typed against the old one.
  useEffect(() => {
    setDraftRating(row.rating);
    setDraftComment(row.comment ?? "");
    setLastWriteChanged(null);
  }, [row.rating, row.comment, row.updated_at]);

  const withdrawn = row.status !== SUBMITTED;
  const windowState = row.edit_window.state;

  const save = async () => {
    if (draftRating === null) return;
    setPending(true);
    setWriteError(null);
    setLastWriteChanged(null);
    try {
      const result = await submitSpeakerFeedback(unitId, eventId, row.speaker_professional_id, {
        rating: draftRating,
        // Whitespace is normalized to absent server-side. Sending null for an
        // empty box says "they wrote nothing" rather than storing a blank.
        comment: draftComment.trim().length === 0 ? null : draftComment,
      });
      setLastWriteChanged(result.changed);
      await onChanged();
    } catch (cause) {
      setWriteError(
        cause instanceof ApiRequestError
          ? cause.message
          : "That could not be saved and the server gave no reason.",
      );
    } finally {
      setPending(false);
    }
  };

  const withdraw = async () => {
    setPending(true);
    setWriteError(null);
    setLastWriteChanged(null);
    try {
      const result = await withdrawSpeakerFeedback(unitId, eventId, row.speaker_professional_id);
      setLastWriteChanged(result.changed);
      await onChanged();
    } catch (cause) {
      setWriteError(
        cause instanceof ApiRequestError
          ? cause.message
          : "That could not be withdrawn and the server gave no reason.",
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="space-y-1">
        <h3 className="font-semibold text-foreground">
          {/*
            The speaker is identified by the id the server sent, and nothing is
            derived from it. No student-visible read turns that id into a name,
            and inventing a display name would be worse than showing none: a
            reader would trust it.
          */}
          A speaker you rated at this event
        </h3>
        <p className="text-xs text-muted-foreground">
          {withdrawn
            ? "You withdrew this rating. The number and your words were cleared."
            : `You rated this ${row.rating} out of 5.`}
        </p>
        <p className="text-xs text-muted-foreground">
          Last changed {new Date(row.updated_at).toLocaleString("en-US")}
        </p>
      </div>

      <fieldset className="mt-3 space-y-2" disabled={pending}>
        <legend className="text-xs text-muted-foreground">
          Your rating, 1 to 5. There is no zero — to take a rating back, withdraw it.
        </legend>
        <div className="flex flex-wrap gap-2">
          {RATING_CHOICES.map((choice) => (
            <button
              key={choice}
              type="button"
              onClick={() => setDraftRating(choice)}
              aria-pressed={draftRating === choice}
              className={
                draftRating === choice
                  ? "rounded-lg border border-foreground px-3 py-2 text-sm font-medium text-foreground"
                  : "rounded-lg border border-border/70 px-3 py-2 text-sm text-muted-foreground"
              }
            >
              {choice}
            </button>
          ))}
        </div>

        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">
            Anything you want to add. Optional — leaving it empty stores nothing rather than a
            blank.
          </span>
          <textarea
            value={draftComment}
            onChange={(entry) => setDraftComment(entry.target.value)}
            rows={3}
            className="w-full rounded-lg border border-border/70 bg-transparent p-2 text-sm text-foreground"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          {/*
            Both controls stay rendered when the window is closed. The server
            refuses with `409 student_feedback_window_closed` in words, and a
            hidden control would say the capability does not exist rather than
            that it has expired.
          */}
          <button
            type="button"
            onClick={() => void save()}
            disabled={pending || draftRating === null}
            aria-busy={pending}
            className="rounded-lg border border-border/70 px-3 py-2 text-sm font-medium text-foreground disabled:opacity-60"
          >
            {pending ? "Sending…" : withdrawn ? "Rate again" : "Save changes"}
          </button>
          {withdrawn ? null : (
            <button
              type="button"
              onClick={() => void withdraw()}
              disabled={pending}
              aria-busy={pending}
              className="rounded-lg border border-border/70 px-3 py-2 text-sm text-muted-foreground disabled:opacity-60"
            >
              Withdraw
            </button>
          )}
        </div>
      </fieldset>

      <p className="mt-2 text-xs text-muted-foreground">
        {WINDOW_TEXT[windowState] ?? windowState}
        {row.edit_window.closes_at === null
          ? null
          : ` Closes ${new Date(row.edit_window.closes_at).toLocaleString("en-US")}.`}
      </p>

      {/*
        What the server said the request did, which is not the same as what it
        was asked to do. A false `changed` is the honest answer to re-sending a
        rating that was already exactly this, and reporting it as a save would
        claim an edit that never happened.
      */}
      {lastWriteChanged === null ? null : (
        <p className="mt-2 text-xs text-muted-foreground">
          {lastWriteChanged
            ? "The server recorded that change."
            : "The server had exactly this already, so nothing moved."}
        </p>
      )}

      {writeError === null ? null : (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs text-foreground"
        >
          {writeError}
        </p>
      )}
    </li>
  );
}

/** One event on the student's agenda, and whatever they have already said at it. */
function EventFeedback({
  event,
  unitId,
  rows,
  readError,
  onChanged,
}: {
  event: StudentEvent;
  unitId: string;
  rows: StoredFeedback[];
  readError: string | null;
  onChanged: () => Promise<void>;
}) {
  return (
    <section className="space-y-3 rounded-2xl border border-border/70 p-5">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-foreground">{event.title}</h2>
        <p className="text-sm text-muted-foreground">{whenText(event)}</p>
      </header>

      {readError === null ? null : (
        <p
          role="alert"
          className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs text-foreground"
        >
          {readError}
        </p>
      )}

      {rows.length === 0 ? (
        <p className="flex items-start gap-2 rounded-lg border border-border/70 p-3 text-xs leading-5 text-muted-foreground">
          <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span>
            You have not rated a speaker at this event. SmartMatch cannot yet offer you a first
            rating here: there is no student-facing list of who spoke at an event, so this page has
            nobody to name. Rating one for the first time becomes possible when that list exists.
            Ratings you have already left appear here, and can be changed or withdrawn.
          </span>
        </p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <FeedbackRow
              key={row.speaker_professional_id}
              row={row}
              unitId={unitId}
              eventId={event.id}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

export function StudentSpeakerFeedback() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "student");
  const unitId = grant?.default_unit_id ?? null;

  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  // One cached composite: the agenda (shared with `useStudentPortalData`'s
  // `student-agenda` slot, so Home/Events warm it) plus one read per event.
  // Each per-event read is still allowed to fail on its own — an event whose
  // feedback could not be read is reported against that event rather than
  // collapsing the whole page into a single banner.
  const pageQuery = useScopedQuery({
    resource: "student-feedback-by-event",
    params: [unitId],
    enabled: unitId !== null && principalKey !== null,
    queryFn: async () => {
      const id = unitId as string;
      const agenda = await queryClient.fetchQuery({
        queryKey: scopedQueryKey(principalKey as string, "student-agenda", id),
        queryFn: () => fetchStudentAgenda(id),
      });
      const results = await Promise.all(
        agenda.events.map(async (event) => {
          try {
            const list = await fetchMySpeakerFeedback(id, event.id);
            return { id: event.id, rows: list.feedback, error: null as string | null };
          } catch (cause) {
            return {
              id: event.id,
              rows: [] as StoredFeedback[],
              error:
                cause instanceof ApiRequestError
                  ? cause.message
                  : "Your feedback for this event could not be read and the server gave no reason.",
            };
          }
        }),
      );
      return {
        events: agenda.events,
        byEvent: Object.fromEntries(results.map((result) => [result.id, result.rows])),
        readErrors: Object.fromEntries(
          results
            .filter((result) => result.error !== null)
            .map((result) => [result.id, result.error as string]),
        ),
      };
    },
  });

  const events: StudentEvent[] = pageQuery.data?.events ?? [];
  const byEvent: Record<string, StoredFeedback[]> = pageQuery.data?.byEvent ?? {};
  const readErrors: Record<string, string> = pageQuery.data?.readErrors ?? {};
  const loadError = pageQuery.isError
    ? pageQuery.error instanceof ApiRequestError
      ? pageQuery.error.message
      : "Your events could not be loaded and the server gave no reason."
    : null;
  const loaded = !pageQuery.isPending;

  const load = useCallback(async () => {
    await pageQuery.refetch();
  }, [pageQuery]);

  /** Events carrying at least one stored rating come first: they are the actionable ones. */
  const ordered = useMemo(() => {
    const rated = events.filter((event) => (byEvent[event.id] ?? []).length > 0);
    const unrated = events.filter((event) => (byEvent[event.id] ?? []).length === 0);
    return [...rated, ...unrated];
  }, [events, byEvent]);

  // `StudentLayout` already renders `PortalGate` when the server granted no such
  // portal, so reaching here without a grant means the mapping is still
  // resolving. Render nothing rather than a header about a portal that may turn
  // out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Speaker feedback</h1>
        <p className="text-sm text-muted-foreground">
          What you said about the speakers you heard, and your chance to change your mind.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <p className="flex items-start gap-2 rounded-xl border border-border/70 p-4 text-sm leading-6 text-muted-foreground">
        <MessageSquare className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Your rating is yours until seven days after the event, and you can change or withdraw it
          until then. Your department sees an average across everyone who answered — never your
          name, and never what you wrote.
        </span>
      </p>

      {loadError === null ? null : (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {loadError}
        </p>
      )}

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is nothing to show.
        </p>
      ) : ordered.length === 0 ? (
        <p className="flex items-start gap-2 rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          <CalendarX2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {!loaded
              ? "Loading…"
              : "Nothing is on your agenda in this department yet, so there is no event to give " +
                "feedback on. Events you register for, or that your department records you at, " +
                "appear here."}
          </span>
        </p>
      ) : (
        /* The agenda events this student can give feedback on, a page at a
           time. The pager only windows the rows this browser already holds —
           it issues no read, and its count is of what arrived, not of how
           many events the department has recorded. */
        <PagedList items={ordered} label="agenda events" idPrefix="student-speaker-feedback-events">
          {(visibleEvents) => (
            <div className="space-y-4">
              {visibleEvents.map((event) => (
                <EventFeedback
                  key={event.id}
                  event={event}
                  unitId={unitId}
                  rows={byEvent[event.id] ?? []}
                  readError={readErrors[event.id] ?? null}
                  onChanged={load}
                />
              ))}
            </div>
          )}
        </PagedList>
      )}
    </div>
  );
}
