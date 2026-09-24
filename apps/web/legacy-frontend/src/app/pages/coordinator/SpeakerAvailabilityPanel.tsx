/**
 * A roster contact's stated availability, read and corrected by a Speaker
 * Connector (B26 T5). Mounted by `CoordinatorSpeakerContacts`' row disclosure,
 * so it reads on demand — one `GET` per opened row, none on page load.
 *
 * ## What this file owns
 *
 * The read (`useScopedQuery`, key `[principal, "speaker-availability", unit,
 * professional]`), the write (`useMutation`, no optimistic update), cache
 * upkeep after a save, the stale (409) re-read, and the read-side states:
 * loading, refused (403), not on the roster (404), and failed-with-Retry. The
 * form itself is `components/speakerAvailability/SpeakerAvailabilityForm.tsx`.
 *
 * ## After a save
 *
 * The PATCH response is the committed row read back, so it is written into the
 * availability key (server data, not an optimistic guess) and the form re-seeds
 * from it — a quick second save then carries the new version and cannot 409
 * against the user's own write. The `match-run` and `invitation-compose`
 * prefixes for this unit are invalidated because both compute "changed since
 * this run" from current availability at read time (T4). Nothing else is: the
 * roster does not carry availability.
 *
 * ## After a 409
 *
 * The draft stays exactly as typed, the saved version is re-read with one
 * exact refetch, and the Connector is shown it before "Save my changes over
 * it" sends the draft against that fresh version. Nothing retries a stale
 * PATCH on its own, and no version is ever guessed (T3-C9).
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchSpeakerAvailability,
  updateSpeakerAvailability,
  type SpeakerAvailability,
  type SpeakerAvailabilityUpdatePayload,
} from "@/lib/api";
import { scopedQueryKey } from "@/lib/queryClient";
import {
  COPY,
  availabilityErrorMessage,
  readErrorMessage,
  utcToday,
  type AvailabilityError,
} from "@/lib/speakerAvailabilityDraft";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import {
  SpeakerAvailabilityForm,
  type StaleState,
} from "@/app/components/speakerAvailability/SpeakerAvailabilityForm";
import { useScopedQuery } from "@/app/hooks/useScopedQuery";

const RESOURCE = "speaker-availability";

function hasCode(cause: unknown, code: string): boolean {
  return cause instanceof ApiRequestError && cause.code === code;
}

export function SpeakerAvailabilityPanel({
  unitId,
  professionalId,
  contactName,
}: {
  unitId: string;
  professionalId: string;
  contactName: string;
}) {
  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();
  const today = utcToday();
  const idPrefix = `availability-${professionalId}`;
  const headingId = `availability-heading-${professionalId}`;

  const query = useScopedQuery({
    resource: RESOURCE,
    params: [unitId, professionalId],
    queryFn: () => fetchSpeakerAvailability(unitId, professionalId),
  });

  const [stale, setStale] = useState<StaleState | null>(null);
  const [serverError, setServerError] = useState<AvailabilityError | null>(null);
  const [lastSaved, setLastSaved] = useState<SpeakerAvailability | null>(null);

  // A different principal is a different conversation: nothing carries over.
  useEffect(() => {
    setStale(null);
    setServerError(null);
    setLastSaved(null);
  }, [principalKey]);

  const invalidateRoster = useCallback(() => {
    if (principalKey === null) return;
    void queryClient.invalidateQueries({ queryKey: [principalKey, "speaker-contacts", unitId] });
  }, [principalKey, queryClient, unitId]);

  // The roster row is wrong once the server says the contact is gone.
  const readNotFound = query.isError && hasCode(query.error, "speaker_contact_not_found");
  useEffect(() => {
    if (readNotFound) invalidateRoster();
  }, [readNotFound, invalidateRoster]);

  const reread = useCallback(async () => {
    if (principalKey === null) return;
    const key = scopedQueryKey(principalKey, RESOURCE, unitId, professionalId);
    setStale({ phase: "rereading" });
    await queryClient.refetchQueries({ queryKey: key, exact: true });
    const phase = queryClient.getQueryState(key)?.status === "error" ? "failed" : "fresh";
    // Only if still stale: a discard or a principal switch during the re-read
    // cleared it, and a late answer must not bring the stale view back.
    setStale((previous) => (previous === null ? null : { phase }));
  }, [principalKey, queryClient, unitId, professionalId]);

  const mutation = useMutation({
    mutationFn: (payload: SpeakerAvailabilityUpdatePayload) =>
      updateSpeakerAvailability(unitId, professionalId, payload),
    onMutate: () => {
      setServerError(null);
    },
    onSuccess: (saved) => {
      if (principalKey !== null) {
        queryClient.setQueryData(
          scopedQueryKey(principalKey, RESOURCE, unitId, professionalId),
          saved,
        );
        void queryClient.invalidateQueries({ queryKey: [principalKey, "match-run", unitId] });
        void queryClient.invalidateQueries({
          queryKey: [principalKey, "invitation-compose", unitId],
        });
      }
      setStale(null);
      setLastSaved(saved);
    },
    onError: (cause, payload) => {
      if (hasCode(cause, "speaker_availability_stale")) {
        void reread();
        return;
      }
      if (hasCode(cause, "speaker_contact_not_found")) invalidateRoster();
      setServerError(availabilityErrorMessage(cause, payload.unavailable, today));
    },
  });

  function save(payload: SpeakerAvailabilityUpdatePayload) {
    if (principalKey === null || mutation.isPending) return;
    mutation.mutate(payload);
  }

  function retryRead() {
    if (stale !== null) {
      void reread();
    } else {
      void query.refetch();
    }
  }

  const data = query.data;
  const loading = data === undefined && !query.isError;

  let body: ReactNode;
  if (data !== undefined) {
    body = (
      <SpeakerAvailabilityForm
        idPrefix={idPrefix}
        headingId={headingId}
        availability={data}
        reseedFrom={lastSaved}
        today={today}
        copy={COPY.connector}
        saving={mutation.isPending}
        canSave={principalKey !== null}
        stale={stale}
        readError={query.isError ? readErrorMessage(query.error) : null}
        serverError={serverError}
        onSave={save}
        onDiscardStale={() => setStale(null)}
        onRetryRead={retryRead}
      />
    );
  } else if (query.isError) {
    const status = query.error instanceof ApiRequestError ? query.error.status : null;
    // A refusal and a missing contact are answers; retrying them changes nothing.
    const retryable = status !== 403 && !readNotFound;
    body = (
      <div className="space-y-2">
        <p className="text-sm text-foreground">{readErrorMessage(query.error)}</p>
        {retryable ? (
          <button
            type="button"
            onClick={() => void query.refetch()}
            className="min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  } else {
    body = <p className="text-sm text-muted-foreground">Loading availability…</p>;
  }

  return (
    <section
      id={`availability-panel-${professionalId}`}
      aria-labelledby={headingId}
      aria-busy={loading}
      className="mt-4 space-y-3 border-t border-border/70 pt-4"
    >
      <h3 id={headingId} className="text-base font-semibold text-foreground">
        Availability<span className="sr-only"> for {contactName}</span>
      </h3>
      {body}
    </section>
  );
}
