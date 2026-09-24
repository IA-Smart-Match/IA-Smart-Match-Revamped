/**
 * Bookings — coordinator portal (B26 T8a).
 *
 * The confirmed Speaker bookings in this unit, and the one action on each: a
 * Speaker Connector cancels a booking that will not happen. A booking is a
 * `pipeline_record` that reached Confirmed; cancelling it is a transition on
 * that row (migration `0040`), not a delete.
 *
 * ## What it reads and writes
 *
 * `GET /v1/units/{unit_id}/cba/confirmed-speakers` — the same list the Event
 * Host reads, and the same set the `pipeline_confirmed` metric counts. A
 * cancelled booking is in neither, so after a cancel the row leaves this list.
 * `POST …/pipeline-records/{record_id}/cancellation` is the write. Event titles
 * come from the unit's events read, whose cache key this page reuses.
 *
 * ## What it is careful not to do
 *
 * No optimistic update: the row leaves only when the re-read says so. The
 * Cancel button appears only on bookings that have not been presented, which
 * is a courtesy — the server refuses an attended booking whatever this page
 * draws. A refusal is the server's sentence, rendered in the dialog, and the
 * dialog stays open so the reader sees it.
 *
 * Out of scope: undoing a cancellation (follow-up FU-1), showing cancelled
 * bookings (a later filter).
 */
import { useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";

import {
  ApiRequestError,
  type BookingCancellationResult,
  type ConfirmedSpeaker,
  cancelBooking,
  fetchConfirmedSpeakers,
  fetchUnitEvents,
} from "../../../lib/api";
import { metricsQueryKey, scopedQueryKey } from "../../../lib/queryClient";
import { PagedList } from "../../components/PagedList";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { grantedPortal } from "../../components/PortalGate";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../../components/ui/alert-dialog";
import { Button } from "../../components/ui/button";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useScopedQuery } from "../../hooks/useScopedQuery";

const NOTICE = "rounded-xl border border-border/70 p-4 text-sm text-muted-foreground";
const ALERT = "rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground";
const TRIGGER =
  "min-h-11 rounded-lg border border-destructive/50 px-3 py-1.5 text-xs font-medium " +
  "text-destructive hover:bg-destructive/5 focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2";

/** Fixed copy for the two refusals a coordinator can act on; the rest is verbatim. */
const CANCEL_REFUSALS: Readonly<Record<string, string>> = {
  pipeline_booking_already_attended:
    "This speaker already presented. An attended booking cannot be cancelled.",
  pipeline_booking_confirmed_in_future:
    "This booking's confirmation time is in the future. It can be cancelled after that time.",
};

function cancelErrorMessage(cause: unknown): string {
  if (cause instanceof ApiRequestError) {
    return CANCEL_REFUSALS[cause.code] ?? cause.message;
  }
  return "The booking could not be cancelled and the server gave no reason.";
}

function listErrorMessage(cause: unknown): string {
  if (cause instanceof ApiRequestError) {
    if (cause.status === 403) {
      return (
        `The server refused this request (403). ${cause.message} ` +
        "Reading bookings is granted to unit administrators and Speaker Connectors."
      );
    }
    return cause.message;
  }
  return "The bookings could not be read and the server gave no reason.";
}

function day(value: string): string {
  return new Date(value).toLocaleDateString();
}

function speakerName(speaker: ConfirmedSpeaker): string {
  return speaker.full_name ?? "Name not on file";
}

type Row = {
  speaker: ConfirmedSpeaker;
  name: string;
  event: string;
  booked: boolean;
};

function stateLabel(row: Row): string {
  return row.booked ? "Booked" : `Presented ${day(row.speaker.attended_at as string)}`;
}

export function CoordinatorBookings() {
  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;
  const [searchParams] = useSearchParams();
  const eventFilter = searchParams.get("event_id");

  const bookingsQuery = useScopedQuery({
    resource: "confirmed-speakers",
    params: [unitId, eventFilter ?? "all"],
    queryFn: () => fetchConfirmedSpeakers(unitId as string, eventFilter ?? undefined),
    enabled: unitId !== null,
  });
  const eventsQuery = useScopedQuery({
    resource: "unit-events",
    params: [unitId],
    queryFn: () => fetchUnitEvents(unitId as string),
    enabled: unitId !== null,
  });

  const [target, setTarget] = useState<Row | null>(null);
  const [open, setOpen] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const mutation = useMutation<BookingCancellationResult, unknown, string>({
    mutationFn: (recordId: string) => cancelBooking(unitId as string, recordId),
    onSuccess: async (result) => {
      if (principalKey !== null && unitId !== null) {
        // The prefix covers "all" and every event filter; the metric moved too,
        // and so did the Speaker's load band (B26 T8d): every availability read
        // for this unit carries it.
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: scopedQueryKey(principalKey, "confirmed-speakers", unitId),
          }),
          queryClient.invalidateQueries({ queryKey: metricsQueryKey(principalKey, unitId) }),
          queryClient.invalidateQueries({
            queryKey: scopedQueryKey(principalKey, "speaker-availability", unitId),
          }),
        ]);
      }
      setAnnouncement(
        result.transitioned ? "Booking cancelled." : "Already cancelled — nothing changed.",
      );
      setOpen(false);
    },
    onError: (cause) => {
      setDialogError(cancelErrorMessage(cause));
    },
  });
  const pending = mutation.isPending;

  function openFor(row: Row, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setTarget(row);
    setDialogError("");
    setAnnouncement("");
    mutation.reset();
    setOpen(true);
  }

  function onOpenChange(next: boolean) {
    // While the write is in flight the dialog stays: closing it would hide the
    // answer the reader is waiting for.
    if (!next && pending) return;
    setOpen(next);
  }

  if (grant === null) {
    return null;
  }

  const titles = new Map<string, string>(
    (eventsQuery.data?.events ?? []).map((event) => [event.id, event.title]),
  );
  const bookings: Row[] = (bookingsQuery.data?.speakers ?? []).map((speaker) => ({
    speaker,
    name: speakerName(speaker),
    event: titles.get(speaker.event_id) ?? `Event ${speaker.event_id.slice(0, 8)}`,
    booked: speaker.attended_at === null,
  }));

  function trigger(row: Row) {
    if (!row.booked) return null;
    return (
      <button
        type="button"
        className={TRIGGER}
        aria-label={`Cancel booking for ${row.name} at ${row.event}`}
        onClick={(event) => openFor(row, event.currentTarget)}
      >
        Cancel booking
      </button>
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-2xl font-semibold text-foreground focus-visible:outline-none"
        >
          Bookings
        </h1>
        <p className="text-sm text-muted-foreground">
          Speakers who agreed to present at this unit&apos;s events. Cancel a booking that will not
          happen: the speaker leaves the Event Host&apos;s list and the Confirmed count.
        </p>
      </header>

      <p role="status" aria-live="polite" className={announcement === "" ? "sr-only" : NOTICE}>
        {announcement}
      </p>

      {unitId === null ? (
        <p className={NOTICE}>
          The server has not assigned this account a unit, so there are no bookings to show.
        </p>
      ) : bookingsQuery.isError ? (
        <div className={`${ALERT} space-y-3`} role="alert">
          <p>{listErrorMessage(bookingsQuery.error)}</p>
          <button
            type="button"
            onClick={() => {
              void bookingsQuery.refetch();
            }}
            className="min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Retry
          </button>
        </div>
      ) : bookingsQuery.data === undefined ? (
        <div aria-busy="true" aria-label="Loading bookings" className="space-y-3">
          <div className="h-16 animate-pulse rounded-xl bg-muted" />
          <div className="h-16 animate-pulse rounded-xl bg-muted" />
        </div>
      ) : bookings.length === 0 ? (
        <p className={NOTICE}>No confirmed speakers in this unit.</p>
      ) : (
        <PagedList items={bookings} label="Confirmed speakers" idPrefix="bookings">
          {(visible) => (
            <>
              {/* Cards below `md`, the table above; the hidden one is display:none. */}
              <ul className="space-y-3 md:hidden" aria-label="Confirmed speakers">
                {visible.map((row) => (
                  <li
                    key={row.speaker.record_id}
                    className="space-y-2 rounded-2xl border border-border/70 bg-card p-4"
                  >
                    <p className="flex items-center gap-2 font-semibold text-foreground">
                      <CalendarCheck className="h-4 w-4 text-primary" aria-hidden="true" />
                      {row.name}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {row.speaker.company ?? "No company on record"} · {row.event}
                    </p>
                    <p className="text-sm text-foreground">
                      Agreed {day(row.speaker.confirmed_at)} · {stateLabel(row)}
                    </p>
                    {trigger(row)}
                  </li>
                ))}
              </ul>
              <div className="hidden md:block">
                <table className="w-full border-collapse">
                  <caption className="sr-only">Confirmed speakers, in the order they agreed</caption>
                  <thead>
                    <tr className="text-left text-xs font-medium text-muted-foreground">
                      <th scope="col" className="pb-2 pr-4">
                        Speaker
                      </th>
                      <th scope="col" className="pb-2 pr-4">
                        Company
                      </th>
                      <th scope="col" className="pb-2 pr-4">
                        Event
                      </th>
                      <th scope="col" className="pb-2 pr-4">
                        Agreed
                      </th>
                      <th scope="col" className="pb-2 pr-4">
                        State
                      </th>
                      <th scope="col" className="pb-2">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((row) => (
                      <tr key={row.speaker.record_id} className="border-t border-border/60 text-sm">
                        <td className="py-3 pr-4 font-medium text-foreground">{row.name}</td>
                        <td className="py-3 pr-4 text-muted-foreground">
                          {row.speaker.company ?? "—"}
                        </td>
                        <td className="py-3 pr-4 text-foreground">{row.event}</td>
                        <td className="py-3 pr-4 text-foreground">
                          Agreed {day(row.speaker.confirmed_at)}
                        </td>
                        <td className="py-3 pr-4 text-foreground">{stateLabel(row)}</td>
                        <td className="py-3">{trigger(row)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </PagedList>
      )}

      <AlertDialog open={open} onOpenChange={onOpenChange}>
        {/* An alertdialog never closes on an outside click (Radix omits
            onPointerDownOutside for it); Escape is blocked while pending below. */}
        <AlertDialogContent
          aria-describedby="booking-cancel-desc booking-cancel-error"
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const back = triggerRef.current;
            (back !== null && back.isConnected ? back : headingRef.current)?.focus();
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel this booking?</AlertDialogTitle>
            <AlertDialogDescription id="booking-cancel-desc">
              {target === null
                ? ""
                : `${target.name} will no longer count as booked for ${target.event}, and their ` +
                  "load drops at once. Your name and the time are recorded. This cannot be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <p id="booking-cancel-error" role="alert" className="text-sm text-destructive">
            {dialogError}
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Keep booking</AlertDialogCancel>
            <Button
              type="button"
              variant="destructive"
              disabled={pending || target === null}
              onClick={() => {
                if (target === null || pending) return;
                setDialogError("");
                mutation.mutate(target.speaker.record_id);
              }}
            >
              {pending ? "Cancelling…" : "Cancel booking"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
