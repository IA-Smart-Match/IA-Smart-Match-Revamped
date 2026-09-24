/**
 * `/speaker-portal/availability` — the Speaker's own availability (B26 T6b-4
 * §5.4), on T5's `SpeakerAvailabilityForm` with the Speaker's words
 * (`COPY.speaker`).
 *
 * Reads `GET /v1/me/availability`; writes `PATCH /v1/me/availability`. Named
 * `Own` so it never collides with T3's `SpeakerAvailability` type.
 *
 * ## What this file owns
 *
 * The read states before the first answer (loading, not linked, denied,
 * signed out, failed with Retry), the save, and the stale (409) re-read. The
 * form owns the draft, so a re-read never overwrites what the Speaker typed.
 * Errors are fixed text (§7): the four `speaker_availability_*` field errors
 * keep T5's field messages; everything else is the Speaker map's.
 *
 * A `load` field the response may carry (T8 adds it) is not read here: the
 * Speaker's load band is T8d's, in the slot marked below, and it is a band
 * word only, never a number (OQ-CBA-005).
 */
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, type SpeakerAvailability, type SpeakerAvailabilityUpdatePayload } from "@/lib/api";
import { scopedQueryKey } from "@/lib/queryClient";
import {
  COPY,
  availabilityErrorMessage,
  utcToday,
  type AvailabilityError,
} from "@/lib/speakerAvailabilityDraft";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import {
  SpeakerAvailabilityForm,
  type StaleState,
} from "@/app/components/speakerAvailability/SpeakerAvailabilityForm";
import {
  SPEAKER_SELF_RESOURCE,
  useMyAvailability,
  useUpdateMyAvailability,
} from "@/app/hooks/useSpeakerSelf";

import { SpeakerReadError, SpeakerSelfNotice } from "./SpeakerSelfNotice";
import { selfNoticeKind, speakerPortalError } from "./speakerPortalErrors";
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Your availability";
const HEADING_ID = "my-availability-heading";
const ID_PREFIX = "my-availability";

/** The field errors T5's form already words; every other failure is the Speaker map's. */
const FIELD_CODES = new Set([
  "speaker_availability_window_invalid",
  "speaker_availability_too_many_windows",
  "speaker_availability_pause_invalid",
  "speaker_availability_capacity_invalid",
]);

function saveError(
  cause: unknown,
  payload: SpeakerAvailabilityUpdatePayload,
  today: string,
): AvailabilityError {
  if (cause instanceof ApiRequestError && FIELD_CODES.has(cause.code)) {
    return availabilityErrorMessage(cause, payload.unavailable, today);
  }
  return { field: "form", message: speakerPortalError("availability", cause).message };
}

export function SpeakerOwnAvailability() {
  useSpeakerPageTitle(HEADING);
  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();
  const today = utcToday();
  const query = useMyAvailability();
  const mutation = useUpdateMyAvailability();

  const [stale, setStale] = useState<StaleState | null>(null);
  const [serverError, setServerError] = useState<AvailabilityError | null>(null);
  const [lastSaved, setLastSaved] = useState<SpeakerAvailability | null>(null);

  // A different principal is a different conversation: nothing carries over.
  useEffect(() => {
    setStale(null);
    setServerError(null);
    setLastSaved(null);
  }, [principalKey]);

  const reread = useCallback(async () => {
    if (principalKey === null) return;
    const key = scopedQueryKey(principalKey, SPEAKER_SELF_RESOURCE.availability);
    setStale({ phase: "rereading" });
    await queryClient.refetchQueries({ queryKey: key, exact: true });
    const phase = queryClient.getQueryState(key)?.status === "error" ? "failed" : "fresh";
    // Only if still stale: a discard during the re-read must stay discarded.
    setStale((previous) => (previous === null ? null : { phase }));
  }, [principalKey, queryClient]);

  function save(payload: SpeakerAvailabilityUpdatePayload): void {
    if (principalKey === null || mutation.isPending) return;
    setServerError(null);
    mutation.mutate(payload, {
      onSuccess: (saved) => {
        setStale(null);
        setLastSaved(saved);
      },
      onError: (cause) => {
        if (cause instanceof ApiRequestError && cause.code === "speaker_availability_stale") {
          void reread();
          return;
        }
        setServerError(saveError(cause, payload, today));
      },
    });
  }

  function retryRead(): void {
    if (stale !== null) {
      void reread();
    } else {
      void query.refetch();
    }
  }

  let body;
  if (query.data !== undefined) {
    body = (
      <SpeakerAvailabilityForm
        idPrefix={ID_PREFIX}
        headingId={HEADING_ID}
        availability={query.data}
        reseedFrom={lastSaved}
        today={today}
        copy={COPY.speaker}
        saving={mutation.isPending}
        canSave={principalKey !== null}
        stale={stale}
        readError={
          query.isError ? speakerPortalError("read-availability", query.error).message : null
        }
        serverError={serverError}
        onSave={save}
        onDiscardStale={() => setStale(null)}
        onRetryRead={retryRead}
      />
    );
  } else if (query.isError) {
    const kind = selfNoticeKind(query.error);
    body =
      kind !== null ? (
        <SpeakerSelfNotice kind={kind} />
      ) : (
        <SpeakerReadError
          message={speakerPortalError("read-availability", query.error).message}
          subject="your availability"
          onRetry={() => void query.refetch()}
        />
      );
  } else {
    body = <p className="text-sm text-muted-foreground">Loading your availability…</p>;
  }

  return (
    <div
      className="mx-auto max-w-3xl space-y-6"
      aria-busy={query.data === undefined && !query.isError ? true : undefined}
    >
      <h1
        id={HEADING_ID}
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>
      {/* SLOT(T8d): the Speaker's own load band — a band word only, never a number (OQ-CBA-005) */}
      {body}
    </div>
  );
}
