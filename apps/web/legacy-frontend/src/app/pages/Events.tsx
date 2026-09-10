import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Plus, Save } from "lucide-react";

import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "@/app/hooks/useAuthorizedUnit";
import { QRCodeCard } from "@/components/QRCodeCard";
import {
  ApiRequestError,
  createManualEvent,
  fetchFeedbackQr,
  fetchManualEvent,
  fetchUnitEvents,
  publishManualEvent,
  saveFeedbackQr,
  updateManualEvent,
  type ManualEvent,
  type ManualEventInput,
  type ManualEventTimePrecision,
} from "@/lib/api";
import {
  blankEventForm,
  categoryOptions,
  EventFormFields,
  eventWhen,
  formFromManualEvent,
  inputFromEventForm,
  type EventFormState,
} from "./EventsSections";

/**
 * The Speaker Connector's "Events" surface — create, edit, and publish a
 * manually-filed event for the authorized unit, and configure its per-event
 * feedback QR redirect.
 *
 * **Verified fact:** `GET /v1/units/{unit_id}/events` (`fetchUnitEvents`) only
 * ever returns *presentable* events (a resolved date, no quarantined tags —
 * see `routers/events.py`'s `list_events`), regardless of publication status,
 * and every manual event that route can surface carries
 * `provenance.origin === "coordinator_entry"` (confirmed in
 * `python/smartmatch_persistence/smartmatch_persistence/events.py` and
 * `tests/unit/test_manual_events.py`, not the task brief's paraphrase
 * "manual"). A brand-new draft with an unresolved schedule will not appear
 * there at all, and even a published one with a resolved schedule can be
 * excluded if its tags are still quarantined.
 *
 * **Assumption made here:** because there is no dedicated "my drafts" list
 * endpoint, this page keeps its own session-local list of the events it has
 * created or edited (`recent`, seeded from every `createManualEvent` /
 * `updateManualEvent` / `publishManualEvent` response) so a freshly created
 * draft stays visible and selectable immediately, in addition to whatever
 * `fetchUnitEvents` can already show. `recent` is not a substitute catalog —
 * it is only ever populated by this browser tab's own successful writes, is
 * lost on reload, and is merged with (never replaces) the unit's actual
 * catalog for display.
 */
export function Events() {
  const unitId = useAuthorizedUnitId("admin");
  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<ManualEvent | null>(null);
  const [form, setForm] = useState<EventFormState>(blankEventForm);
  const [notice, setNotice] = useState("");
  const [recent, setRecent] = useState<ManualEvent[]>([]);
  const createKey = useRef(crypto.randomUUID());

  const listKey = [principalKey, "unit-events", unitId] as const;
  const listQuery = useQuery({
    queryKey: listKey,
    queryFn: () => fetchUnitEvents(unitId!),
    enabled: Boolean(principalKey && unitId),
  });

  const qrKey = [principalKey, "feedback-qr", unitId, selected?.id] as const;
  const qrQuery = useQuery({
    queryKey: qrKey,
    queryFn: async () => {
      try {
        return await fetchFeedbackQr(unitId!, selected!.id);
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled: Boolean(principalKey && unitId && selected?.id),
  });

  useEffect(() => {
    if (selected) setForm(formFromManualEvent(selected));
  }, [selected]);

  const invalidateList = async () => {
    await queryClient.invalidateQueries({ queryKey: [principalKey, "unit-events", unitId] });
  };
  const invalidateQr = async () => {
    await queryClient.invalidateQueries({ queryKey: [principalKey, "feedback-qr", unitId, selected?.id] });
  };

  const rememberRecent = (event: ManualEvent) => {
    setRecent((current) => [event, ...current.filter((item) => item.id !== event.id)]);
  };

  const saveMutation = useMutation({
    mutationFn: async () =>
      selected
        ? updateManualEvent(unitId!, selected.id, selected.version, inputFromEventForm(form))
        : createManualEvent(unitId!, inputFromEventForm(form) as ManualEventInput, createKey.current),
    onSuccess: async (event) => {
      setSelected(event);
      rememberRecent(event);
      setNotice(selected ? "Event updated." : "Draft saved.");
      await invalidateList();
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishManualEvent(unitId!, selected!.id),
    onSuccess: async (event) => {
      setSelected(event);
      rememberRecent(event);
      setNotice("Event published. Event Hosts can now see it.");
      await invalidateList();
    },
  });

  const qrMutation = useMutation({
    mutationFn: (destinationUrl: string) => saveFeedbackQr(unitId!, selected!.id, destinationUrl),
    onSuccess: async () => {
      await invalidateQr();
    },
  });

  const refreshSelected = async (eventId: string) => {
    if (!unitId) return;
    const event = await fetchManualEvent(unitId, eventId);
    setSelected(event);
    rememberRecent(event);
  };

  const listedEvents = listQuery.data?.events ?? [];
  const listedManualIds = useMemo(
    () =>
      new Set(
        listedEvents
          .filter((event) => event.provenance.origin === "coordinator_entry")
          .map((event) => event.id),
      ),
    [listedEvents],
  );
  const drafts = useMemo(() => recent.filter((event) => event.status === "draft"), [recent]);
  const published = useMemo(
    () => recent.filter((event) => event.status === "published" || listedManualIds.has(event.id)),
    [recent, listedManualIds],
  );

  const mutationError = saveMutation.error ?? publishMutation.error;

  if (!unitId) {
    return (
      <div className="rounded-2xl border border-border bg-card p-8">
        <h1 className="text-2xl font-semibold">Events</h1>
        <p className="mt-2 text-muted-foreground">
          Choose an authorized unit before managing events.
        </p>
      </div>
    );
  }

  const field = (name: keyof EventFormState, value: string) =>
    setForm((current) => ({ ...current, [name]: value }));

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Events</h1>
          <p className="mt-2 text-muted-foreground">
            Create events, publish them for Event Hosts, and prepare an external feedback QR.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setSelected(null);
            setForm(blankEventForm());
            setNotice("");
            createKey.current = crypto.randomUUID();
          }}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Create event
        </button>
      </div>

      {listQuery.error ? (
        <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-destructive">
          {listQuery.error instanceof Error
            ? listQuery.error.message
            : "The unit's event list could not be loaded."}
        </p>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <section className="space-y-4" aria-label="Saved events">
          {listQuery.isLoading ? (
            <p className="rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">
              Loading events…
            </p>
          ) : null}
          {!listQuery.isLoading && drafts.length === 0 && published.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
              No events yet. A saved draft is not listed here from the unit's catalog until it
              is published — created or edited events from this session stay listed below.
            </div>
          ) : null}
          {[
            { title: "Drafts", items: drafts },
            { title: "Published", items: published },
          ].map((group) => (
            <div key={group.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <h2 className="text-lg font-semibold">{group.title}</h2>
              <div className="mt-3 space-y-2">
                {group.items.length ? (
                  group.items.map((event) => (
                    <button
                      key={event.id}
                      type="button"
                      onClick={() => {
                        setSelected(event);
                        setNotice("");
                      }}
                      className={`w-full rounded-xl border p-4 text-left ${
                        selected?.id === event.id
                          ? "border-primary bg-primary/5"
                          : "border-border hover:bg-muted/50"
                      }`}
                    >
                      <p className="font-semibold text-foreground">{event.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{eventWhen(event)}</p>
                    </button>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No {group.title.toLowerCase()} yet.</p>
                )}
              </div>
            </div>
          ))}
        </section>

        <div className="space-y-6">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setNotice("");
              saveMutation.mutate();
            }}
            className="rounded-2xl border border-border bg-card p-6 shadow-sm"
          >
            <h2 className="text-2xl font-semibold">{selected ? "Edit event" : "New event"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Only the title is required for a draft. Complete every field before publishing.
            </p>

            <EventFormFields form={form} onChange={field} categories={categoryOptions} />

            {mutationError ? (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
              >
                {eventErrorMessage(mutationError)}
              </p>
            ) : null}
            {notice ? (
              <p role="status" className="mt-4 rounded-xl bg-primary/5 p-3 text-sm text-primary">
                {notice}
              </p>
            ) : null}

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={saveMutation.isPending}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
              >
                <Save className="h-4 w-4" aria-hidden="true" />
                {saveMutation.isPending ? "Saving…" : "Save draft"}
              </button>
              {selected?.status === "draft" ? (
                <button
                  type="button"
                  disabled={publishMutation.isPending}
                  onClick={() => publishMutation.mutate()}
                  className="rounded-xl border border-primary px-4 py-2.5 text-sm font-semibold text-primary disabled:opacity-60"
                >
                  {publishMutation.isPending ? "Publishing…" : "Publish event"}
                </button>
              ) : null}
              {selected ? (
                <button
                  type="button"
                  onClick={() => void refreshSelected(selected.id)}
                  className="rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted"
                >
                  Refresh
                </button>
              ) : null}
            </div>
          </form>

          {selected ? (
            <QRCodeCard
              variant="feedback"
              asset={qrQuery.data ?? null}
              loading={qrMutation.isPending || qrQuery.isLoading}
              error={qrMutation.error instanceof Error ? qrMutation.error.message : null}
              onSave={async (destinationUrl) => {
                await qrMutation.mutateAsync(destinationUrl);
              }}
            />
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
              <CalendarDays className="mb-2 h-5 w-5" aria-hidden="true" />
              Save or select an event to configure its feedback QR code.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function eventErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const fields = error.details?.fields;
    if (Array.isArray(fields) && fields.every((field) => typeof field === "string")) {
      return `Complete these fields before publishing: ${fields
        .map((field) => String(field).replace(/_/g, " "))
        .join(", ")}.`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "The event could not be saved.";
}

export type { ManualEventTimePrecision };
