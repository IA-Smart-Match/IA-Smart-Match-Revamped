/**
 * "Invite to portal" for one roster contact (B26 T6b-1 plan §7).
 *
 * Renders nothing unless `speaker_portal` is on, and it is off in every scope
 * today. The server decides everything: who may invite (`{admin,
 * coordinator}`), which address may be written to (`send_eligible`), and the
 * status shown. No optimistic state; the only cache entry touched is this
 * contact's access status.
 *
 * While the worker runs in fixture mode no email is delivered, so this says
 * "Invited" and never "Sent" or "Delivered".
 */
import { useId, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchSpeakerContactChannels,
  fetchSpeakerPortalAccess,
  inviteSpeakerToPortal,
  revokeSpeakerPortalInvitation,
  type SpeakerPortalAccess,
  type SpeakerPortalInvitation,
} from "../../../lib/api";
import { isCapabilityEnabled } from "../../../lib/productScope";
import { scopedQueryKey } from "../../../lib/queryClient";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { useScopedQuery } from "../../hooks/useScopedQuery";

const ACCESS_RESOURCE = "speaker-portal-access";

const ERROR_MESSAGES: Record<string, string> = {
  speaker_portal_already_active: "This Speaker already has portal access",
  speaker_portal_invitation_conflict: "Another invitation was just sent. Refresh and try again",
  speaker_portal_channel_not_eligible: "That address can no longer be emailed",
  speaker_contact_not_found: "This contact is no longer in your roster",
  rate_limited: "Too many requests. Wait a minute and try again",
  forbidden: "You do not have permission to invite this Speaker",
};

function messageFor(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return ERROR_MESSAGES[error.code] ?? "Something went wrong. Try again";
  }
  return "Something went wrong. Try again";
}

function formatDate(iso: string | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const BUTTON =
  "min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-sm font-medium " +
  "disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2";

export function SpeakerPortalInvite({
  unitId,
  professionalId,
}: {
  unitId: string;
  professionalId: string;
}) {
  if (!isCapabilityEnabled("speaker_portal")) return null;
  return <SpeakerPortalInvitePanel unitId={unitId} professionalId={professionalId} />;
}

function SpeakerPortalInvitePanel({
  unitId,
  professionalId,
}: {
  unitId: string;
  professionalId: string;
}) {
  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();
  const errorId = useId();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const access = useScopedQuery<SpeakerPortalAccess>({
    resource: ACCESS_RESOURCE,
    params: [unitId, professionalId],
    queryFn: () => fetchSpeakerPortalAccess(unitId, professionalId),
  });
  const channels = useScopedQuery({
    resource: "speaker-contact-channels",
    params: [unitId, professionalId],
    queryFn: () => fetchSpeakerContactChannels(unitId, professionalId),
    enabled: open,
  });

  const invalidateAccess = () =>
    queryClient.invalidateQueries({
      queryKey: scopedQueryKey(principalKey ?? "", ACCESS_RESOURCE, unitId, professionalId),
    });

  const invite = useMutation<SpeakerPortalInvitation, unknown, string>({
    mutationFn: (channelId) => inviteSpeakerToPortal(unitId, professionalId, channelId),
    onSuccess: () => {
      setOpen(false);
      void invalidateAccess();
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 409) void invalidateAccess();
    },
  });
  const revoke = useMutation({
    mutationFn: () => revokeSpeakerPortalInvitation(unitId, professionalId),
    onSuccess: () => {
      invite.reset();
      void invalidateAccess();
    },
  });

  const eligible = (channels.data?.channels ?? [])
    .map((item) => item.channel)
    .filter((channel) => channel.send_eligible && channel.channel_kind === "email");

  // The invite response is the server's answer, not a guess, so it is shown
  // until the refetched status replaces it.
  const shown: SpeakerPortalAccess | undefined = invite.data
    ? { status: "invited", expires_at: invite.data.expires_at }
    : access.data;
  const error = invite.error ?? revoke.error ?? null;

  const onRevoke = () => {
    if (!window.confirm("Revoke this Speaker's portal link? It will stop working.")) return;
    revoke.mutate();
  };

  let status: string;
  let actions: ReactNode = null;
  if (access.isPending && !invite.data) {
    status = "Checking portal access…";
  } else if (access.isError && !invite.data) {
    status = messageFor(access.error);
  } else if (shown?.status === "active") {
    status = `Portal active since ${formatDate(shown.bound_at)}`;
  } else if (shown?.status === "invited") {
    status = `Invited · link expires ${formatDate(shown.expires_at)}`;
    actions = (
      <>
        <button type="button" className={BUTTON} onClick={() => setOpen(true)}>
          Send a new link
        </button>
        <button
          type="button"
          className={BUTTON}
          onClick={onRevoke}
          disabled={revoke.isPending}
        >
          Revoke
        </button>
      </>
    );
  } else if (shown?.status === "expired") {
    status = "Link expired";
    actions = (
      <button type="button" className={BUTTON} onClick={() => setOpen(true)}>
        Invite again
      </button>
    );
  } else {
    status = "No portal access";
    actions = (
      <button type="button" className={BUTTON} onClick={() => setOpen(true)}>
        Invite to portal
      </button>
    );
  }

  const selected = chosen ?? (eligible.length === 1 ? eligible[0].contact_channel_id : null);

  return (
    <div className="mt-3 space-y-2 border-t border-border/70 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <p role="status" className="text-sm text-muted-foreground">
          {status}
        </p>
        {open ? null : actions}
      </div>

      {open ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (selected !== null && !invite.isPending) invite.mutate(selected);
          }}
        >
          {channels.isPending ? (
            <p className="text-sm text-muted-foreground">Loading addresses…</p>
          ) : (
            <fieldset className="space-y-1">
              <legend className="text-sm font-medium text-foreground">Send the link to</legend>
              {eligible.map((channel) => (
                <label
                  key={channel.contact_channel_id}
                  className="flex min-h-11 items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name={`portal-channel-${professionalId}`}
                    value={channel.contact_channel_id}
                    checked={selected === channel.contact_channel_id}
                    onChange={() => setChosen(channel.contact_channel_id)}
                  />
                  {channel.address}
                </label>
              ))}
              {eligible.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No email address this Speaker agreed to receive
                </p>
              ) : null}
            </fieldset>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              className={BUTTON}
              disabled={selected === null || invite.isPending}
              aria-describedby={error ? errorId : undefined}
            >
              {invite.isPending ? "Sending…" : "Send invitation"}
            </button>
            <button type="button" className={BUTTON} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {error ? (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {messageFor(error)}
        </p>
      ) : null}
    </div>
  );
}
