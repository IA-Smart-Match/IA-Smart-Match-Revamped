/**
 * A Speaker's stated availability as an editable form (B26 T5).
 *
 * Presentational: it takes the stored statement as a prop and hands a
 * full-replace payload to `onSave`. The Connector's panel
 * (`pages/coordinator/SpeakerAvailabilityPanel.tsx`) owns the query and the
 * mutation; the Speaker's own page (T6b-4) reuses this form with its own copy.
 *
 * ## The form owns the draft
 *
 * The draft is seeded from `availability` when the form mounts, when
 * `reseedFrom` changes (a save succeeded: the response is the new truth), and
 * when the user discards their changes. A background refetch that brings a new
 * `availability` **never** overwrites what the user typed — that is what keeps
 * input alive through a stale (409) re-read.
 *
 * ## Accessibility (WCAG 2.2 AA)
 *
 * Native inputs with persistent labels; each window is a `<fieldset>` named by
 * its legend; errors are `role="alert"` beside their field and linked through
 * `aria-describedby` with `aria-invalid`; exactly one `role="status"` region
 * carries save results; focus never drops to `<body>` when a row is removed.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertCircle, Plus } from "lucide-react";

import type { SpeakerAvailability, SpeakerAvailabilityUpdatePayload } from "@/lib/api";
import {
  MAX_WINDOWS,
  PAUSE_HORIZON_MONTHS,
  WINDOW_HORIZON_MONTHS,
  addMonths,
  draftFromAvailability,
  failureMessage,
  formatCalendarDate,
  formatTimestamp,
  isDraftEmpty,
  isDraftUnchanged,
  payloadFromDraft,
  readInput,
  validateDraft,
  windowDraft,
  type AvailabilityCopy,
  type AvailabilityDraft,
  type AvailabilityError,
  type WindowDraft,
} from "@/lib/speakerAvailabilityDraft";

/** After a 409: re-reading the saved version, shown it, or failed to re-read it. */
export interface StaleState {
  phase: "rereading" | "fresh" | "failed";
}

export interface SpeakerAvailabilityFormProps {
  /** Prefix for every id in the form, e.g. `availability-{professional_id}`. */
  idPrefix: string;
  /** The panel heading that names the form. */
  headingId: string;
  /** The latest statement read. */
  availability: SpeakerAvailability;
  /** A saved statement to re-seed from; a new object means "a save succeeded". */
  reseedFrom: SpeakerAvailability | null;
  /** The UTC date (T3-C1). */
  today: string;
  copy: AvailabilityCopy;
  saving: boolean;
  /** False while the principal is unresolved: nothing may be sent. */
  canSave: boolean;
  stale: StaleState | null;
  /** A failed read after a good one; the form stays mounted and says so. */
  readError: string | null;
  serverError: AvailabilityError | null;
  onSave: (payload: SpeakerAvailabilityUpdatePayload) => void;
  onDiscardStale: () => void;
  onRetryRead: () => void;
}

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const INPUT_CLASS = `w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm disabled:opacity-50 aria-[invalid=true]:border-destructive ${FOCUS_RING}`;
const BUTTON_CLASS =
  "min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-sm font-medium disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const PRIMARY_CLASS =
  "min-h-11 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const ERROR_CLASS = "flex items-start gap-1.5 text-sm text-destructive";

function describedBy(...ids: (string | false | null | undefined)[]): string {
  return ids.filter(Boolean).join(" ");
}

function FieldError({ id, message }: { id: string; message: string }) {
  return (
    <p id={id} role="alert" className={ERROR_CLASS}>
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

/** The stored statement in words: never "available", never a made-up 0. */
export function StatementSummary({
  availability,
  today,
  copy,
}: {
  availability: SpeakerAvailability;
  today: string;
  copy: AvailabilityCopy;
}) {
  if (!availability.stated) {
    return (
      <p className="text-sm text-foreground">
        <strong>Not stated.</strong> {copy.notStated}
      </p>
    );
  }
  const count = availability.unavailable.length;
  const pause = availability.invitations_paused_until;
  const capacity = availability.declared_capacity_hours_per_90_days;
  const source = availability.updated_source;
  return (
    <div className="space-y-1 text-sm">
      <p className="text-foreground">
        {count === 0 ? (
          <strong>Stated: no dates blocked.</strong>
        ) : (
          <>
            <strong>Stated:</strong> {count} blocked date {count === 1 ? "range" : "ranges"}.
          </>
        )}
        {pause !== null && pause >= today
          ? ` Invitations paused until ${formatCalendarDate(pause)}.`
          : null}
      </p>
      <p className="text-muted-foreground">
        {capacity === null ? "Capacity not stated" : `${capacity} hours per 90 days`}
      </p>
      {availability.updated_at !== null && source !== null ? (
        <p className="text-muted-foreground">
          Last changed {formatTimestamp(availability.updated_at)} {copy.changedBy[source]}
        </p>
      ) : null}
    </div>
  );
}

export function SpeakerAvailabilityForm({
  idPrefix: p,
  headingId,
  availability,
  reseedFrom,
  today,
  copy,
  saving,
  canSave,
  stale,
  readError,
  serverError,
  onSave,
  onDiscardStale,
  onRetryRead,
}: SpeakerAvailabilityFormProps) {
  const nextKey = useRef(availability.unavailable.length + 1);
  const [draft, setDraft] = useState<AvailabilityDraft>(() => draftFromAvailability(availability));
  const [clientError, setClientError] = useState<AvailabilityError | null>(null);
  const [status, setStatus] = useState("");
  const pendingFocus = useRef<string | null>(null);
  const lastSeed = useRef(reseedFrom);

  function reseed(from: SpeakerAvailability) {
    setDraft(draftFromAvailability(from, nextKey.current));
    nextKey.current += from.unavailable.length;
    setClientError(null);
  }

  function focusIdFor(error: AvailabilityError): string | null {
    switch (error.field) {
      case "capacity":
        return `${p}-capacity`;
      case "pause":
        return `${p}-pause`;
      case "add":
        return `${p}-add`;
      case "window": {
        const key = error.index === undefined ? undefined : draft.windows[error.index]?.key;
        return key === undefined ? null : `${p}-${key}-${error.part ?? "from"}`;
      }
      default:
        return null;
    }
  }

  // A save succeeded: the response is the new truth.
  useEffect(() => {
    if (reseedFrom === null || reseedFrom === lastSeed.current) return;
    lastSeed.current = reseedFrom;
    reseed(reseedFrom);
    setStatus(
      reseedFrom.updated_at === null
        ? "Availability saved."
        : `Availability saved ${formatTimestamp(reseedFrom.updated_at)}.`,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new saved object re-seeds
  }, [reseedFrom]);

  // A server field error moves focus to that field — once the save has
  // settled, because a disabled (saving) input cannot take focus.
  const focusedError = useRef<AvailabilityError | null>(null);
  useEffect(() => {
    if (serverError === null || saving || focusedError.current === serverError) return;
    focusedError.current = serverError;
    const id = focusIdFor(serverError);
    if (id !== null) document.getElementById(id)?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new error, not a new draft
  }, [serverError, saving]);

  // Focus requested by the last action, once the DOM it names exists.
  useEffect(() => {
    if (pendingFocus.current === null) return;
    document.getElementById(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  });

  const unchanged = isDraftUnchanged(draft, availability);
  const empty = isDraftEmpty(draft);
  const blockedUnchanged = availability.stated && unchanged && stale === null;
  const staleNotFresh = stale !== null && stale.phase !== "fresh";
  const saveDisabled = saving || !canSave || blockedUnchanged || staleNotFresh;
  const offerEmptySave = !availability.stated && empty && stale === null;
  const saveLabel = saving
    ? "Saving…"
    : stale !== null
      ? "Save my changes over it"
      : offerEmptySave
        ? "Save: no dates blocked"
        : "Save availability";

  const storedPause = availability.invitations_paused_until;
  const expiredPause = storedPause !== null && storedPause < today && draft.pause === storedPause;
  const windowsFull = draft.windows.length >= MAX_WINDOWS;
  const windowHorizon = addMonths(today, WINDOW_HORIZON_MONTHS);

  const active = clientError ?? serverError;
  const activeWindowKey =
    active?.field === "window" && active.index !== undefined
      ? (draft.windows[active.index]?.key ?? null)
      : null;
  const formError =
    active !== null && (active.field === "form" || (active.field === "window" && activeWindowKey === null))
      ? active
      : null;
  const errorOn = (field: AvailabilityError["field"]) => active !== null && active.field === field;

  function update(patch: Partial<AvailabilityDraft>) {
    setDraft((previous) => ({ ...previous, ...patch }));
  }

  function updateWindow(key: string, patch: Partial<WindowDraft>) {
    setDraft((previous) => ({
      ...previous,
      windows: previous.windows.map((w) => (w.key === key ? { ...w, ...patch } : w)),
    }));
  }

  function addWindow() {
    if (windowsFull) return;
    const key = `w${nextKey.current}`;
    nextKey.current += 1;
    update({ windows: [...draft.windows, windowDraft(key)] });
    pendingFocus.current = `${p}-${key}-from`;
  }

  function removeWindow(index: number) {
    const neighbour = draft.windows[index + 1] ?? draft.windows[index - 1];
    update({ windows: draft.windows.filter((_, i) => i !== index) });
    pendingFocus.current = neighbour === undefined ? `${p}-add` : `${p}-${neighbour.key}-from`;
  }

  function discard() {
    if (stale !== null && stale.phase === "rereading") return;
    reseed(availability);
    if (stale !== null) onDiscardStale();
    setStatus("Changes discarded.");
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (saveDisabled) return;
    setStatus("");
    const failure = validateDraft(draft, today, availability);
    if (failure !== null) {
      const error = failureMessage(failure, today);
      setClientError(error);
      pendingFocus.current = focusIdFor(error);
      return;
    }
    setClientError(null);
    // After a 409 the fresh read's version is the one being overwritten.
    onSave(payloadFromDraft(draft, stale !== null ? availability.version : draft.baseVersion));
  }

  function windowSource(w: WindowDraft): string {
    const match = availability.unavailable.find(
      (s) => s.starts_on === w.starts_on && s.ends_on === w.ends_on,
    );
    return match === undefined ? "Not saved yet" : copy.sourceLabel[match.source];
  }

  return (
    <div className="space-y-4">
      <StatementSummary availability={availability} today={today} copy={copy} />

      <form noValidate aria-labelledby={headingId} onSubmit={submit} className="space-y-4">
        {/* One switch for every control while a save is in flight: nothing can
            be edited or discarded under a request that has not answered yet. */}
        <fieldset disabled={saving} className="m-0 min-w-0 space-y-4 border-0 p-0">
          <div className="space-y-1">
            <label htmlFor={`${p}-pause`} className="text-sm font-medium text-foreground">
              Pause invitations until
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <input
                id={`${p}-pause`}
                type="date"
                value={draft.pause}
                min={today}
                max={addMonths(today, PAUSE_HORIZON_MONTHS)}
                aria-invalid={errorOn("pause") ? true : undefined}
                aria-describedby={describedBy(`${p}-pause-hint`, errorOn("pause") && `${p}-pause-error`)}
                onChange={(event) => {
                  const read = readInput(event.target.value, event.target.validity?.badInput ?? false);
                  update({ pause: read.value, pauseBad: read.bad });
                }}
                className={`${INPUT_CLASS} sm:w-auto`}
              />
              <button
                type="button"
                onClick={() => update({ pause: "", pauseBad: false })}
                className={BUTTON_CLASS}
              >
                Clear pause
              </button>
            </div>
            <p id={`${p}-pause-hint`} className="text-xs text-muted-foreground">
              {expiredPause
                ? `This pause ended on ${formatCalendarDate(storedPause)}. Saving clears it.`
                : `Optional. The last day no invitations go out. Latest ${formatCalendarDate(
                    addMonths(today, PAUSE_HORIZON_MONTHS),
                  )}.`}
            </p>
            {errorOn("pause") && active !== null ? (
              <FieldError id={`${p}-pause-error`} message={active.message} />
            ) : null}
          </div>

          <div className="space-y-1">
            <label htmlFor={`${p}-capacity`} className="text-sm font-medium text-foreground">
              Capacity (hours per 90 days)
            </label>
            <input
              id={`${p}-capacity`}
              type="number"
              inputMode="decimal"
              min="0.1"
              max="720"
              step="0.1"
              value={draft.capacity}
              aria-invalid={errorOn("capacity") ? true : undefined}
              aria-describedby={describedBy(
                `${p}-capacity-hint`,
                errorOn("capacity") && `${p}-capacity-error`,
              )}
              onChange={(event) => {
                const read = readInput(event.target.value, event.target.validity?.badInput ?? false);
                update({ capacity: read.value, capacityBad: read.bad });
              }}
              className={`${INPUT_CLASS} sm:max-w-48`}
            />
            <p id={`${p}-capacity-hint`} className="text-xs text-muted-foreground">
              Optional. Leave blank if not stated.
            </p>
            {errorOn("capacity") && active !== null ? (
              <FieldError id={`${p}-capacity-error`} message={active.message} />
            ) : null}
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-foreground">{copy.windowsLegend}</legend>
            <p id={`${p}-windows-hint`} className="text-xs text-muted-foreground">
              Each range includes both dates. Past ranges are fine. The latest end date is{" "}
              {formatCalendarDate(windowHorizon)}.
            </p>
            {draft.windows.length > 0 ? (
              <ol className="space-y-3">
                {draft.windows.map((w, index) => {
                  const n = index + 1;
                  const hasError = activeWindowKey === w.key && active !== null;
                  const errorId = `${p}-${w.key}-error`;
                  const errorPart = hasError ? (active.part ?? "from") : null;
                  const named =
                    w.starts_on !== "" && w.ends_on !== ""
                      ? `${formatCalendarDate(w.starts_on)} to ${formatCalendarDate(w.ends_on)}`
                      : `${n} (no dates yet)`;
                  return (
                    <li key={w.key}>
                      <fieldset className="space-y-2 rounded-lg border border-border/70 p-3">
                        <legend className="px-1 text-sm font-medium text-foreground">
                          Unavailable dates {n}
                        </legend>
                        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                          <div className="space-y-1">
                            <label htmlFor={`${p}-${w.key}-from`} className="text-sm text-foreground">
                              From
                            </label>
                            <input
                              id={`${p}-${w.key}-from`}
                              type="date"
                              value={w.starts_on}
                              aria-invalid={errorPart === "from" ? true : undefined}
                              aria-describedby={describedBy(
                                `${p}-windows-hint`,
                                errorPart === "from" && errorId,
                              )}
                              onChange={(event) => {
                                const read = readInput(
                                  event.target.value,
                                  event.target.validity?.badInput ?? false,
                                );
                                updateWindow(w.key, { starts_on: read.value, startsBad: read.bad });
                              }}
                              className={INPUT_CLASS}
                            />
                          </div>
                          <div className="space-y-1">
                            <label htmlFor={`${p}-${w.key}-to`} className="text-sm text-foreground">
                              To, inclusive
                            </label>
                            <input
                              id={`${p}-${w.key}-to`}
                              type="date"
                              value={w.ends_on}
                              max={windowHorizon}
                              aria-invalid={errorPart === "to" ? true : undefined}
                              aria-describedby={describedBy(
                                `${p}-windows-hint`,
                                errorPart === "to" && errorId,
                              )}
                              onChange={(event) => {
                                const read = readInput(
                                  event.target.value,
                                  event.target.validity?.badInput ?? false,
                                );
                                updateWindow(w.key, { ends_on: read.value, endsBad: read.bad });
                              }}
                              className={INPUT_CLASS}
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => removeWindow(index)}
                            className={BUTTON_CLASS}
                          >
                            Remove<span className="sr-only"> unavailable dates {named}</span>
                          </button>
                        </div>
                        <p className="text-xs text-muted-foreground">{windowSource(w)}</p>
                        {hasError ? <FieldError id={errorId} message={active.message} /> : null}
                      </fieldset>
                    </li>
                  );
                })}
              </ol>
            ) : null}
            <div className="space-y-1">
              <button
                id={`${p}-add`}
                type="button"
                disabled={windowsFull}
                aria-describedby={describedBy(
                  windowsFull && `${p}-add-reason`,
                  errorOn("add") && `${p}-add-error`,
                ) || undefined}
                onClick={addWindow}
                className={`${BUTTON_CLASS} inline-flex items-center gap-1.5`}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add unavailable dates
              </button>
              {windowsFull ? (
                <p id={`${p}-add-reason`} className="text-xs text-muted-foreground">
                  {copy.addReason}
                </p>
              ) : null}
              {errorOn("add") && active !== null ? (
                <FieldError id={`${p}-add-error`} message={active.message} />
              ) : null}
            </div>
        </fieldset>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={saveDisabled}
              aria-describedby={describedBy(
                `${p}-form-error`,
                blockedUnchanged && `${p}-save-reason`,
                staleNotFresh && `${p}-stale-reason`,
                offerEmptySave && `${p}-empty-hint`,
              )}
              className={PRIMARY_CLASS}
            >
              {saveLabel}
            </button>
            {stale !== null ? (
              // Not while the saved version is being re-read: there is nothing
              // fresh to discard to yet.
              <button
                type="button"
                onClick={discard}
                disabled={stale.phase === "rereading"}
                aria-describedby={stale.phase === "rereading" ? `${p}-stale-reason` : undefined}
                className={BUTTON_CLASS}
              >
                Discard my changes
              </button>
            ) : !unchanged ? (
              <button type="button" onClick={discard} className={BUTTON_CLASS}>
                Discard changes
              </button>
            ) : null}
          </div>
          {blockedUnchanged ? (
            <p id={`${p}-save-reason`} className="text-xs text-muted-foreground">
              No changes to save.
            </p>
          ) : null}
          {staleNotFresh ? (
            <p id={`${p}-stale-reason`} className="text-xs text-muted-foreground">
              {stale.phase === "failed"
                ? "The saved version could not be re-read, so there is nothing to save over yet. Retry the read first."
                : "Reading the saved version now."}
            </p>
          ) : null}
          {offerEmptySave ? (
            <p id={`${p}-empty-hint`} className="text-xs text-muted-foreground">
              {copy.emptySaveHint}
            </p>
          ) : null}
        </div>
        </fieldset>

        {/* Always mounted, so the Save button's reference always resolves. */}
        <div id={`${p}-form-error`} role="alert" className="space-y-2 text-sm">
          {stale !== null ? (
            <>
              <p className="text-foreground">
                <strong>Someone changed this</strong> availability since you opened it. Your
                changes are still in the form and were not saved.
              </p>
              {formError !== null ? <p className="text-foreground">{formError.message}</p> : null}
              {readError !== null ? (
                <p className="text-foreground">
                  {readError}{" "}
                  <button type="button" onClick={onRetryRead} className={BUTTON_CLASS}>
                    Retry
                  </button>
                </p>
              ) : null}
            </>
          ) : formError !== null ? (
            <p className="text-foreground">{formError.message}</p>
          ) : readError !== null ? (
            <p className="text-foreground">
              {readError}{" "}
              <button type="button" onClick={onRetryRead} className={BUTTON_CLASS}>
                Retry
              </button>
            </p>
          ) : null}
        </div>

        {stale !== null && stale.phase === "fresh" ? (
          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/40 p-3">
            <p className="text-sm font-semibold text-foreground">Saved now</p>
            <StatementSummary availability={availability} today={today} copy={copy} />
            {/* An active pause is already in the summary line above. */}
            {storedPause !== null && storedPause < today ? (
              <p className="text-sm text-muted-foreground">
                Pause ended on {formatCalendarDate(storedPause)}.
              </p>
            ) : null}
            {availability.unavailable.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {availability.unavailable.map((w) => (
                  <li key={`${w.starts_on}-${w.ends_on}`}>
                    {formatCalendarDate(w.starts_on)} to {formatCalendarDate(w.ends_on)} (
                    {copy.sourceLabel[w.source]})
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </form>

      <p id={`${p}-status`} role="status" className="text-sm text-foreground">
        {status}
      </p>
    </div>
  );
}
