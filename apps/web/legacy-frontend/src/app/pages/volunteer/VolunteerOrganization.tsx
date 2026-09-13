/**
 * Your organization — Event Host portal (migration `0036`, owner decision 4).
 *
 * What an Event Host files a Speaker Request *on behalf of*. The page reads
 * and writes one resource — the caller's own organization in this unit — over
 * the two routes `routers/host_organizations.py` grants to `volunteer` alone:
 *
 *  - `GET  /v1/units/{unit_id}/host/organization`
 *  - `PUT  /v1/units/{unit_id}/host/organization`
 *
 * The Connector's directory (`GET .../host-organizations`) is deliberately
 * absent: it is `admin`/`coordinator` server-side because it carries every
 * host's record, and this page is a host's own surface.
 *
 * ## A 404 here is a state, not a failure
 *
 * A host who has described no organization gets `host_organization_not_found`.
 * That is the honest answer to "what is my organization in this department" —
 * and it is also the answer a host whose organization files into a *different*
 * unit gets, on purpose, so neither is a reason to show an error. The page
 * opens the same form both ways.
 *
 * ## Membership is asserted, never granted
 *
 * Every member row in this release is self-asserted: `granted_by_user_id` is
 * `NULL` and nothing can write it otherwise. Two consequences are rendered
 * rather than hidden. The `self_asserted` flag is shown for what it is — "you
 * described this; nobody approved it" — never as a confirmation. And the two
 * `409`s are shown in the server's own words, because both are things a person
 * has to resolve rather than retry: `host_organization_name_taken` means a
 * different host already created the name in this unit and joining it is a
 * grant nobody can make yet; `host_organization_unit_conflict` means the
 * caller's one organization files into another department and moving it would
 * move every other member.
 *
 * ## Nothing here reports what it did not observe
 *
 * The read-back card is rendered from the `PUT`/`GET` response — the row the
 * server committed — never from the form. A failed save keeps every field
 * exactly as typed and clears nothing.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which unit
 * the grant covers, and that is the only unit read or written. The body
 * carries no tenant, unit, user or organization id and never gains one: the
 * server takes all of them off the verified principal and the authorized path.
 */

import { useMemo, useState } from "react";
import { Building2, ShieldAlert } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchOwnHostOrganization,
  upsertOwnHostOrganization,
  type HostOrganizationUpsertPayload,
  type HostOwnOrganization,
} from "../../../lib/api";
import { scopedQueryKey } from "../../../lib/queryClient";
import { grantedPortal } from "../../components/PortalGate";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { useScopedQuery } from "../../hooks/useScopedQuery";

/**
 * The load's four outcomes, kept distinct so none of them borrows another's
 * screen. `none` is the 404 — "you have not described one" — and is a
 * renderable state with a form, not an error. `denied-or-failed` is every
 * other refusal, rendered in the server's words.
 */
type OrganizationState =
  | { status: "loading" }
  | { status: "ready"; own: HostOwnOrganization }
  | { status: "none" }
  | { status: "failed"; message: string };

/** The stored description, rendered from the response and nothing else. */
function OrganizationCard({ own }: { own: HostOwnOrganization }) {
  const organization = own.organization;
  return (
    <section
      className="space-y-3 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
      aria-label="Your organization on record"
    >
      <div className="flex items-start gap-3">
        <Building2 className="mt-1 h-5 w-5 text-primary" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-foreground">{organization.name}</h2>
          <p className="text-sm text-muted-foreground">
            {organization.department ?? "No department on record"}
          </p>
        </div>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[12rem_1fr]">
        <dt className="text-muted-foreground">Usual location</dt>
        <dd className="text-foreground">{organization.default_location ?? "Not stated"}</dd>
        <dt className="text-muted-foreground">Day-of logistics contact</dt>
        <dd className="text-foreground">{organization.logistics_contact ?? "Not stated"}</dd>
        <dt className="text-muted-foreground">Accounts belonging</dt>
        <dd className="text-foreground">
          {organization.member_count === 1
            ? "1 account — yours"
            : `${organization.member_count} accounts`}
        </dd>
        <dt className="text-muted-foreground">Your membership</dt>
        <dd className="text-foreground">
          Since {new Date(own.member_since).toLocaleDateString()}
          {own.self_asserted
            ? " · described by you — no Speaker Connector has approved it, and nothing can grant one yet"
            : " · granted by a Speaker Connector"}
        </dd>
        <dt className="text-muted-foreground">Last updated</dt>
        <dd className="text-foreground">
          {new Date(organization.updated_at).toLocaleString()}
        </dd>
      </dl>
      <p className="text-xs leading-5 text-muted-foreground">
        New requests you file are stamped with this organization; who belongs to it is a count,
        never a list — no route publishes the members.
      </p>
    </section>
  );
}

export function VolunteerOrganization() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // including the unit id this page reads and writes under.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");
  const unitId = grant?.default_unit_id ?? null;

  const [editing, setEditing] = useState(false);

  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [defaultLocation, setDefaultLocation] = useState("");
  const [logisticsContact, setLogisticsContact] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  // The same cache slot `VolunteerHome`'s organization card reads — the home
  // page's read is this page's warm-up. The 404 is the "none" state — the
  // honest answer to the question this URL asks — resolved inside the query
  // so the cache holds `"none"` rather than an error, and branched on the
  // error's code, never its text.
  const ownQuery = useScopedQuery({
    resource: "own-host-organization",
    params: [unitId],
    queryFn: async (): Promise<HostOwnOrganization | "none"> => {
      try {
        return await fetchOwnHostOrganization(unitId as string);
      } catch (cause) {
        if (cause instanceof ApiRequestError && cause.code === "host_organization_not_found") {
          return "none";
        }
        throw cause;
      }
    },
    enabled: unitId !== null,
  });

  const state: OrganizationState =
    unitId === null || ownQuery.isPending
      ? { status: "loading" }
      : ownQuery.isError
        ? {
            status: "failed",
            message:
              ownQuery.error instanceof ApiRequestError
                ? ownQuery.error.message
                : "Your organization could not be read and the server gave no reason.",
          }
        : ownQuery.data === "none"
          ? { status: "none" }
          : { status: "ready", own: ownQuery.data };

  // Opening the editor copies the stored values in — an edit starts from what
  // the server holds, and creating starts from blank. Both are the same form;
  // which of the two it is follows from the state, not from a second page.
  function openEditor() {
    if (state.status === "ready") {
      const organization = state.own.organization;
      setName(organization.name);
      setDepartment(organization.department ?? "");
      setDefaultLocation(organization.default_location ?? "");
      setLogisticsContact(organization.logistics_contact ?? "");
    }
    setSaveError(null);
    setEditing(true);
  }

  // Why the button is disabled, in the words the server would use. A courtesy,
  // not a validation: the blank-name refusal is a 422 server-side, and every
  // other rule is enforced there too.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit to describe an organization under.";
    }
    if (name.trim().length === 0) return "Give the organization a name.";
    return null;
  }, [unitId, name]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || blockingReason !== null || saving) {
      return;
    }

    const payload: HostOrganizationUpsertPayload = { name: name.trim() };
    // Optional fields are sent only when stated — an omitted key and an empty
    // string both store "they did not say", and sending the trimmed value
    // keeps a stray space from standing in for an answer.
    if (department.trim().length > 0) payload.department = department.trim();
    if (defaultLocation.trim().length > 0) payload.default_location = defaultLocation.trim();
    if (logisticsContact.trim().length > 0) payload.logistics_contact = logisticsContact.trim();

    setSaving(true);
    setSaveError(null);
    try {
      // The response is the stored row, read back — never the form. `201`
      // created and `200` updated, and the body is the same shape either way,
      // so the card does not claim which of the two the call was. Written into
      // the cache slot the read came from, so `VolunteerHome`'s card shows the
      // saved answer without a second fetch.
      queryClient.setQueryData(
        scopedQueryKey(principalKey ?? "unresolved-principal", "own-host-organization", unitId),
        await upsertOwnHostOrganization(unitId, payload),
      );
      setEditing(false);
    } catch (cause) {
      // The two 409s — `host_organization_name_taken` and
      // `host_organization_unit_conflict` — and every other refusal are the
      // server's own message, rendered as given. Nothing typed is cleared.
      setSaveError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The organization could not be saved and the server gave no reason. Nothing was stored.",
      );
    } finally {
      setSaving(false);
    }
  }

  // `VolunteerPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving. Render nothing rather than a form about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Your organization</h1>
        <p className="text-sm text-muted-foreground">
          The group you file speaker requests on behalf of — your club, society, or class. Requests
          you file after describing one are stamped with it, so the Speaker Connector can see which
          organizations are asking.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {unitId === null ? (
        <div className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground">
          The server granted this portal but named no org unit for it, so there is nowhere an
          organization can belong. Unit assignment is an administrator&apos;s decision and is not
          made here.
        </div>
      ) : null}

      {state.status === "loading" ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading your organization…
        </p>
      ) : null}

      {state.status === "failed" ? (
        <p
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{state.message}</span>
        </p>
      ) : null}

      {state.status === "ready" && !editing ? (
        <>
          <OrganizationCard own={state.own} />
          <button
            type="button"
            onClick={openEditor}
            className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
          >
            Edit this description
          </button>
        </>
      ) : null}

      {state.status === "none" && !editing ? (
        <section
          className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
          aria-label="No organization described yet"
        >
          <h2 className="font-semibold text-foreground">You have not described an organization</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            You can file speaker requests without one. Describing your organization stamps each new
            request with the group behind it, so the Speaker Connector can tell a club&apos;s fifth
            event from five different groups&apos; first.
          </p>
          <button
            type="button"
            onClick={openEditor}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
          >
            Describe your organization
          </button>
        </section>
      ) : null}

      {editing ? (
        <form
          className="space-y-5 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
          onSubmit={handleSubmit}
          aria-label={state.status === "ready" ? "Edit your organization" : "Describe your organization"}
        >
          <h2 className="font-semibold text-foreground">
            {state.status === "ready" ? "Edit your organization" : "Describe your organization"}
          </h2>

          <div className="space-y-2">
            <label htmlFor="organization-name" className="text-sm font-semibold text-foreground">
              Organization name
            </label>
            <input
              id="organization-name"
              className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={200}
            />
            <p className="text-xs text-muted-foreground">
              Must be unique in this department. If another host has already created the name, the
              server says so — joining theirs is a membership grant a Speaker Connector makes, and
              nothing can make one yet.
            </p>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="organization-department"
              className="text-sm font-semibold text-foreground"
            >
              Department <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              id="organization-department"
              className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
              value={department}
              onChange={(event) => setDepartment(event.target.value)}
              maxLength={200}
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="organization-location"
              className="text-sm font-semibold text-foreground"
            >
              Where your events usually happen{" "}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              id="organization-location"
              className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
              value={defaultLocation}
              onChange={(event) => setDefaultLocation(event.target.value)}
              maxLength={500}
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="organization-logistics"
              className="text-sm font-semibold text-foreground"
            >
              Who to reach about logistics on the day{" "}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              id="organization-logistics"
              className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
              value={logisticsContact}
              onChange={(event) => setLogisticsContact(event.target.value)}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground">
              Free text for the Connector to read — nothing sends to it, and it is not a contact
              channel.
            </p>
          </div>

          {blockingReason !== null ? (
            <p className="text-sm text-muted-foreground">{blockingReason}</p>
          ) : null}

          {saveError !== null ? (
            <p
              className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
              role="alert"
            >
              {saveError}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              disabled={saving || blockingReason !== null}
            >
              {saving ? "Saving…" : "Save your organization"}
            </button>
            {state.status === "ready" ? (
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setSaveError(null);
                }}
                className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}
