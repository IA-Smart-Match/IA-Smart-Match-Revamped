/**
 * The two things every portal page in this deployment can honestly render.
 *
 * `PortalIdentityCard` — real content, entirely server-derived: who the caller
 * is (`GET /v1/me`), which portal the server granted them, the role that
 * granted it, and the org unit that role covers (`GET /v1/me/portals`). Every
 * value is a fact one of those two routes returned. There is no display name,
 * no school, and no avatar invented here.
 *
 * `PortalDatasetUnavailable` — the honest absence. The legacy portal pages
 * used to fill themselves from `/api/portals/*`: coordinator profiles, hosted
 * events, outreach threads, meeting bookings, student registrations,
 * connection suggestions, retention nudges, volunteer assignments. **That
 * backend is not part of this repository.** It is not gated, not deferred
 * behind a flag, and not coming back on with configuration — the routes do not
 * exist here at all.
 *
 * So the pages say so, per section, naming the dataset. What they must not do
 * is any of the three things that would be easier:
 *
 *  - render placeholder rows, which is fabricated content (Fix #15);
 *  - render an empty list, which claims the true answer is "none" when the
 *    real answer is "not known here" (ADR-0011: unknown is never zero);
 *  - render a red failure banner, which blames an outage for a capability
 *    that was never present.
 *
 * The panel is deliberately calm rather than alarming: nothing is broken, and
 * a reader should be able to tell "this deployment does not carry that data"
 * apart from "something went wrong just now".
 */
import { Database } from "lucide-react";

import type { MeResponse, PortalDescriptor } from "@/lib/api";
import { principalDisplayName, principalInitials } from "@/lib/principal";

export function PortalIdentityCard({ me, grant }: { me: MeResponse; grant: PortalDescriptor }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {principalInitials(me)}
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold text-foreground">
            {principalDisplayName(me)}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{grant.display_name}</p>
        </div>
      </div>

      <dl className="mt-6 grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-border/60 bg-background/60 p-4">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Role assigned by the server
          </dt>
          <dd className="mt-1 font-medium text-foreground">{grant.role}</dd>
        </div>
        <div className="rounded-xl border border-border/60 bg-background/60 p-4">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Org unit
          </dt>
          <dd className="mt-1 font-medium text-foreground">{grant.org_unit_path}</dd>
        </div>
      </dl>

      <p className="mt-4 text-xs leading-5 text-muted-foreground">
        Your role comes from a membership record an administrator wrote. It is reported by{" "}
        <code className="rounded bg-muted px-1.5 py-0.5">GET /v1/me/portals</code> and cannot be
        chosen, changed, or asserted from this browser.
      </p>
    </div>
  );
}

export function PortalDatasetUnavailable({
  dataset,
  endpoints,
}: {
  /** What the section would have shown, in the reader's terms. */
  dataset: string;
  /** The legacy routes that would have served it, named rather than hidden. */
  endpoints: string[];
}) {
  return (
    <section
      className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
      aria-label={`${dataset} unavailable`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <Database className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="space-y-2">
          <h2 className="font-semibold text-foreground">{dataset} is not available here</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            This deployment does not carry that data. It was served by the legacy{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/api/portals/*</code> backend,
            which is not part of this repository, so there is nothing to show and nothing to
            retry. Your sign-in and your portal assignment are unaffected — both are answered by{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/v1</code>.
          </p>
          {endpoints.length > 0 && (
            <p className="text-xs leading-5 text-muted-foreground">
              Would come from:{" "}
              {endpoints.map((endpoint, index) => (
                <span key={endpoint}>
                  {index > 0 && ", "}
                  <code className="rounded bg-muted px-1.5 py-0.5">{endpoint}</code>
                </span>
              ))}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
