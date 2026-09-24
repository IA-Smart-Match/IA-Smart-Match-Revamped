/**
 * The Speaker Portal's reads and writes (B26 T6b-4 §4). The only module that
 * builds a `my-*` cache key.
 *
 * Every key is `[principalKey, resource, ...params]` through `useScopedQuery`
 * or `scopedQueryKey`, so two principals in one browser never share an entry,
 * and nothing is read while the principal key is unresolved. No key carries a
 * professional, unit or user id: the Speaker is the bearer token's bound
 * profile, resolved server-side (MM-A01).
 *
 * ## Writes re-read; they never splice
 *
 * A channel's `send_eligible`, `last_set_by` and `can_opt_*` are computed by
 * the server, so after a choice the one owning list is invalidated **exactly**
 * and re-read (ADR-0011 rule 3). The invalidation promise is returned from
 * `onSuccess`, so `isPending` stays true until the re-read has landed and the
 * page's buttons stay blocked until the row shows its new state. No
 * `onMutate`, no optimistic update, no automatic retry.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchMyContactChannels,
  optInMyContactChannel,
  optOutMyContactChannel,
  type MyContactChannelChange,
} from "@/lib/api";
import { scopedQueryKey } from "@/lib/queryClient";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { speakerPortalError } from "@/app/pages/speaker/speakerPortalErrors";

import { useScopedQuery } from "./useScopedQuery";

/** The four resource names. Pages and the nav prefetch key through these. */
export const SPEAKER_SELF_RESOURCE = {
  invitations: "my-invitations",
  engagements: "my-engagements",
  availability: "my-availability",
  contactChannels: "my-contact-channels",
} as const;

/** `GET /v1/me/contact-channels`. */
export function useMyContactChannels() {
  return useScopedQuery({
    resource: SPEAKER_SELF_RESOURCE.contactChannels,
    queryFn: fetchMyContactChannels,
  });
}

export type ChannelChoice = "opt_in" | "opt_out";

export interface ChannelChoiceVariables {
  readonly channelId: string;
  readonly choice: ChannelChoice;
}

/**
 * Opt in or out of one channel. Success and the "list is stale" failures
 * invalidate exactly `[principal, "my-contact-channels"]`; nothing else.
 */
export function useMyChannelChoice() {
  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  function rereadChannels(): Promise<void> | undefined {
    if (principalKey === null) return undefined;
    return queryClient.invalidateQueries({
      queryKey: scopedQueryKey(principalKey, SPEAKER_SELF_RESOURCE.contactChannels),
      exact: true,
    });
  }

  return useMutation<MyContactChannelChange, unknown, ChannelChoiceVariables>({
    mutationFn: ({ channelId, choice }) =>
      choice === "opt_in" ? optInMyContactChannel(channelId) : optOutMyContactChannel(channelId),
    onSuccess: () => rereadChannels(),
    onError: (cause) =>
      speakerPortalError("channel", cause).refetch ? rereadChannels() : undefined,
  });
}
