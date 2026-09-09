/**
 * Run a match — Speaker Connector portal (customer §§12-13, §19).
 *
 * This is card B24 from `docs/plans/frontend-broken-buttons.md` finally being
 * answered. That control said "Request Match" and deep-linked to the admin
 * scoreboard; nothing was ever submitted. This page submits the real command:
 * `POST /v1/units/{unit_id}/match-runs`, naming a filed Speaker Request and a
 * pool drawn from the unit's own §13 roster.
 *
 * ## Three things it does not do, each for a stated reason
 *
 * **It shows no score.** OQ-CBA-005 and the ratified G1 presentation rule.
 * Scores live on `AIMatching.tsx`, which reads a persisted run; there is
 * nothing to preview here because at submission time nothing has been scored.
 * `tests/unit/test_frontend_match_run_contract.py` forbids the percent sign in
 * this file as a *character*, so a copy tweak cannot reintroduce one.
 *
 * **It ranks nothing.** The server ranks and the UI displays. There is no
 * sort, no threshold, no arithmetic on anything the API returned, and there is
 * no factor weight anywhere in this file — weights live in `factor_registry`
 * and the persisted matching-weights row, and a literal here would be a weight
 * nobody could change without a frontend deploy.
 *
 * **It does not decide who is eligible.** `match_eligible` and
 * `match_ineligibility_reason` are the server's answers to customer §19's
 * review requirement, read and rendered as given. Re-deriving eligibility from
 * a null classification code would be a second copy of that rule, and it could
 * not tell "a classifier proposed Finance and nobody has checked" from "we have
 * no idea where this person works" — two states that call for different actions
 * and would otherwise be one greyed-out row.
 *
 * ## A 202 is queued work, not a shortlist
 *
 * `POST /match-runs` returns `202` and **no `match_run` row exists** when it
 * does. So the panel below says "Queued", names the job the command became, and
 * then follows that job — `GET /v1/jobs/{job_id}` until it settles, then the
 * job's own terminal `job.completed` summary. The run id lives on that summary
 * and nowhere else: no route maps a job to its run, and
 * `tests/e2e/test_pilot_clickthrough.py` recovers it the same way. Only once the
 * server has handed over a real id does this page open
 * `/ai-matching?run={match_run_id}`.
 *
 * Redirecting at `202` would mean composing that id in the browser, which is a
 * fabricated result wearing a URL — the B17 defect with a router in front of it.
 * A job that fails says so, and stays on this page.
 *
 * ## Paging is a window, and it is not the server's truncation
 *
 * Both lists render through `PagedList`, which slices the array this page has
 * already fetched and draws its controls above *and* below the rows, so the
 * submit button under a full roster is reachable without scrolling past every
 * contact. Two things follow and both are load-bearing. Selection is unaffected
 * — `selectedRequestId` and `selectedSubjectIds` are ids in this component's
 * state, so a page turn cannot clear a checked candidate and the submission
 * still carries all of them. And the pager's range line is a statement about
 * what is *drawn*, which is not the statement `requestsTruncated` and
 * `contactsTruncated` make: those say the server stopped sending before it ran
 * out of rows. Letting one notice stand in for the other would hide a real
 * truncation behind a paging control, so both are worded to say which is which.
 *
 * ## No identifier here is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which unit the
 * server granted them, and that is the only unit read or written. Request ids
 * and `professional_id`s come from rows the server returned. A Connector label
 * in this shell is not permission: `/v1` stays deny-by-default and tenant-scoped
 * and re-authorizes every one of these calls.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { AlertCircle, CalendarDays, CheckCircle2, ListChecks, ShieldAlert } from "lucide-react";

import {
  ApiRequestError,
  createMatchRun,
  fetchJobCompletionSummary,
  fetchJobStatus,
  fetchSpeakerContacts,
  fetchSpeakerRequests,
  isTerminalJobState,
  readMatchRunIdFromSummary,
  type JobState,
  type MatchRunAccepted,
  type SpeakerContact,
  type SpeakerRequest,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * The ratified portfolio bounds, as integers, because they are counts of
 * speakers and not a tuning parameter. The server enforces the same range on
 * the submission and refuses anything outside it, so this select is a courtesy
 * rather than a validation.
 */
const PORTFOLIO_SIZES = [2, 3] as const;

/** How often the queued job is asked what it is doing, in milliseconds. */
const JOB_POLL_INTERVAL_MS = 2000;

/**
 * Plain-language wording for the ineligibility tokens the server sends today.
 *
 * The vocabulary grows server-side, so an unrecognised token is rendered as
 * itself rather than folded into a friendly catch-all: a catch-all would report
 * the wrong cause the first time a new reason appeared, and a Connector acting
 * on it would fix the wrong thing.
 */
const MATCH_INELIGIBILITY_EXPLANATIONS: Readonly<Record<string, string>> = {
  speaker_profile_not_found: "No speaker profile is on file for this contact yet.",
  industry_classification_awaiting_review:
    "An industry was proposed for this contact and nobody has reviewed it yet (§19).",
  role_classification_awaiting_review:
    "A role category was proposed for this contact and nobody has reviewed it yet (§19).",
  industry_classification_missing: "No industry is recorded for this contact.",
  role_classification_missing: "No role category is recorded for this contact.",
  industry_classification_provenance_unknown:
    "The recorded industry cannot be attributed to a review, so it is not usable for matching.",
  role_classification_provenance_unknown:
    "The recorded role category cannot be attributed to a review, so it is not usable for matching.",
  industry_taxonomy_version_superseded:
    "The industry was classified under a superseded taxonomy version and needs re-checking.",
  role_taxonomy_version_superseded:
    "The role category was classified under a superseded taxonomy version and needs re-checking.",
  industry_code_unrecognised: "The recorded industry code is not in the released taxonomy.",
  role_code_unrecognised: "The recorded role code is not in the released taxonomy.",
};

/** The server's reason, in words when we have them and verbatim when we do not. */
function explainIneligibility(reason: string | null): string {
  if (reason === null) {
    return "This contact is not available for matching, and the server named no reason.";
  }
  return MATCH_INELIGIBILITY_EXPLANATIONS[reason] ?? reason;
}

/** The request's date at whatever precision the host actually stated. */
function describeRequestTime(request: SpeakerRequest): string {
  const time = request.time;
  if (time.starts_at !== null) {
    return new Date(time.starts_at).toLocaleString();
  }
  if (time.on_date !== null) {
    return `${time.on_date} (date only — the hour is not settled)`;
  }
  return "No date recorded on this request.";
}

/** One row of the incoming queue. Selected by the server's own `request_id`. */
function RequestRow({
  request,
  selected,
  onSelect,
}: {
  request: SpeakerRequest;
  selected: boolean;
  onSelect: (requestId: string) => void;
}) {
  const targets = [
    ...request.industries.map((entry) => entry.display_name),
    ...request.roles.map((entry) => entry.display_name),
  ];

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="radio"
          name="speaker-request"
          className="mt-1"
          checked={selected}
          onChange={() => onSelect(request.request_id)}
        />
        <span className="space-y-1">
          <span className="block font-semibold text-foreground">{request.title}</span>
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
            {describeRequestTime(request)}
          </span>
          <span className="block text-sm text-muted-foreground">
            {request.is_virtual
              ? "Virtual event"
              : `In person${request.location_city !== null ? ` — ${request.location_city}` : ""}`}
          </span>
          <span className="block text-sm text-muted-foreground">
            {targets.length > 0
              ? targets.join(" · ")
              : "No industry or role targets recorded on this request."}
          </span>
        </span>
      </label>
    </li>
  );
}

/** One roster row. Ineligible contacts are shown, disabled, with the reason. */
function ContactRow({
  contact,
  selected,
  onToggle,
}: {
  contact: SpeakerContact;
  selected: boolean;
  onToggle: (professionalId: string) => void;
}) {
  const eligible = contact.match_eligible;
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <label className={eligible ? "flex items-start gap-3" : "flex items-start gap-3 opacity-70"}>
        <input
          type="checkbox"
          className="mt-1"
          checked={selected}
          disabled={!eligible}
          onChange={() => onToggle(contact.professional_id)}
        />
        <span className="space-y-1">
          <span className="block font-semibold text-foreground">{contact.full_name}</span>
          {contact.company !== null || contact.title !== null ? (
            <span className="block text-sm text-muted-foreground">
              {[contact.title, contact.company].filter(Boolean).join(" · ")}
            </span>
          ) : null}
          {eligible ? null : (
            <span className="flex items-start gap-2 text-sm text-amber-700">
              <ShieldAlert className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
              {explainIneligibility(contact.match_ineligibility_reason)}
            </span>
          )}
        </span>
      </label>
    </li>
  );
}

/**
 * What the server said when it took the command, and what it has said since.
 *
 * Every figure here is a server figure. "Queued" is the strongest claim this
 * panel makes on its own — the shortlist does not exist until the job says it
 * does, and this panel then opens it rather than describing it.
 */
function QueuedRunPanel({
  accepted,
  jobState,
  followError,
}: {
  accepted: MatchRunAccepted;
  jobState: JobState | null;
  followError: string | null;
}) {
  return (
    <section className="space-y-3 rounded-xl border border-border/70 p-5">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
        <ListChecks className="h-4 w-4" aria-hidden="true" />
        Queued
      </h2>
      <p className="text-sm text-muted-foreground">
        The server accepted the command and recorded it as a job. No shortlist exists yet — this
        page will open it once the job reports one.
      </p>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="inline text-muted-foreground">Job&nbsp;</dt>
          <dd className="inline font-mono">{accepted.job_id}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Events&nbsp;</dt>
          <dd className="inline font-mono">{accepted.events_url}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Job state&nbsp;</dt>
          <dd className="inline">{jobState ?? "not yet reported"}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Factor registry&nbsp;</dt>
          <dd className="inline">{accepted.registry_version}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Scoring mode&nbsp;</dt>
          <dd className="inline">
            {accepted.scoring_mode} ({accepted.scoring_mode_version})
          </dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">In the pool&nbsp;</dt>
          <dd className="inline">{accepted.scored_candidates}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Evidence missing&nbsp;</dt>
          <dd className="inline">{accepted.unscorable_candidates}</dd>
        </div>
      </dl>
      <p className="text-xs text-muted-foreground">
        Candidates with missing evidence were reported rather than entered at zero — an absence is
        not a low value (ADR-0011).
      </p>

      {accepted.excluded_candidates.length > 0 ? (
        <div className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
          <p className="text-sm font-medium text-foreground">
            Never evaluated ({accepted.excluded_candidates.length})
          </p>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {accepted.excluded_candidates.map((excluded) => (
              <li key={excluded.subject_id}>
                <span className="font-mono">{excluded.subject_id}</span> —{" "}
                {explainIneligibility(excluded.reason)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {followError !== null ? (
        <p className="flex items-start gap-2 rounded-lg border border-destructive/40 p-3 text-sm text-destructive">
          <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
          {followError}
        </p>
      ) : null}
    </section>
  );
}

export function CoordinatorMatchRuns() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit this page reads and
  // writes. Never composed in the browser.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;
  const navigate = useNavigate();

  const [requests, setRequests] = useState<SpeakerRequest[]>([]);
  const [requestsTruncated, setRequestsTruncated] = useState(false);
  const [contacts, setContacts] = useState<SpeakerContact[]>([]);
  const [contactsTruncated, setContactsTruncated] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<readonly string[]>([]);
  const [portfolioSize, setPortfolioSize] = useState<number>(PORTFOLIO_SIZES[0]);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<MatchRunAccepted | null>(null);
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [followError, setFollowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const [queue, roster] = await Promise.all([
        fetchSpeakerRequests(unitId),
        fetchSpeakerContacts(unitId),
      ]);
      setRequests(queue.requests);
      setRequestsTruncated(queue.truncated);
      setContacts(roster.contacts);
      setContactsTruncated(roster.truncated);
      setLoadError(null);
    } catch (cause) {
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The request queue and roster could not be loaded, and the server gave no reason.",
      );
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Follow the accepted command's job. Nothing here infers progress from
  // elapsed time: each tick asks the server, and the loop stops the moment the
  // server reports a state the job never leaves.
  useEffect(() => {
    if (accepted === null) {
      return;
    }
    const jobId = accepted.job_id;
    let cancelled = false;

    async function poll() {
      try {
        const status = await fetchJobStatus(jobId);
        if (cancelled) return;
        setJobState(status.status);
        if (!isTerminalJobState(status.status)) {
          return;
        }
        if (status.status !== "succeeded") {
          setFollowError(
            `The match run finished in state "${status.status}". No shortlist was produced. ` +
              "Read the job's event stream for what the worker recorded.",
          );
          return;
        }
        const summary = await fetchJobCompletionSummary(jobId);
        if (cancelled) return;
        const matchRunId = readMatchRunIdFromSummary(summary);
        if (matchRunId === null) {
          setFollowError(
            "The job settled but its completion summary named no match run, so there is " +
              "nothing to open. Nothing has been discarded — read the job's event stream.",
          );
          return;
        }
        navigate(`/ai-matching?run=${encodeURIComponent(matchRunId)}`);
      } catch (cause) {
        if (cancelled) return;
        setFollowError(
          cause instanceof ApiRequestError
            ? cause.message
            : "The job could not be read, so this page cannot say what became of the command.",
        );
      }
    }

    void poll();
    const timer = setInterval(() => {
      void poll();
    }, JOB_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [accepted, navigate]);

  const eligibleCount = useMemo(
    () => contacts.filter((contact) => contact.match_eligible).length,
    [contacts],
  );

  // Why the button is disabled, in the words the server would use. A courtesy
  // and not a validation — every rule here is enforced server-side.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit to run matching under.";
    }
    if (selectedRequestId === null) {
      return "Choose the Speaker Request this run answers.";
    }
    if (selectedSubjectIds.length === 0) {
      return "Choose at least one contact to consider.";
    }
    if (selectedSubjectIds.length < portfolioSize) {
      return `A shortlist of ${portfolioSize} needs at least ${portfolioSize} candidates in the pool.`;
    }
    return null;
  }, [unitId, selectedRequestId, selectedSubjectIds, portfolioSize]);

  function toggleSubject(professionalId: string) {
    setSelectedSubjectIds((previous) =>
      previous.includes(professionalId)
        ? previous.filter((entry) => entry !== professionalId)
        : [...previous, professionalId],
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || selectedRequestId === null || blockingReason !== null || submitting) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    setFollowError(null);
    setJobState(null);
    try {
      // The response, not the payload. Every figure the panel shows is one the
      // server answered with.
      const acknowledgement = await createMatchRun(unitId, {
        speaker_request_id: selectedRequestId,
        candidate_subject_ids: [...selectedSubjectIds],
        portfolio_size: portfolioSize,
      });
      setAccepted(acknowledgement);
    } catch (cause) {
      setAccepted(null);
      // The server's own refusal — an over-large pool, a duplicate subject, a
      // pool too small to fill the shortlist. Not a message this page made up,
      // and no selection is cleared.
      setSubmitError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The match run could not be submitted and the server gave no reason. Nothing was queued.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-8 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Run a match</h1>
        <p className="text-sm text-muted-foreground">
          Choose an incoming Speaker Request, choose who to consider from your unit&rsquo;s roster,
          and submit the run. The server ranks; this page only submits and then opens the result
          where it appears. No scores are shown here.
        </p>
      </header>

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is nothing to match.
        </p>
      ) : (
        <>
          {loadError !== null ? (
            <p className="flex items-start gap-2 rounded-xl border border-destructive/40 p-4 text-sm text-destructive">
              <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
              {loadError}
            </p>
          ) : null}

          <form onSubmit={handleSubmit} className="space-y-8">
            <section className="space-y-3">
              <h2 className="text-lg font-semibold text-foreground">Incoming Speaker Requests</h2>
              <p className="text-sm text-muted-foreground">
                What Event Hosts filed under this unit (customer §§12-13), soonest first. Only
                filed requests appear here.
              </p>
              {requests.length === 0 ? (
                <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                  No Speaker Requests are filed under this unit yet.
                </p>
              ) : (
                // A window over the requests already in hand, not a server
                // page: the read above fetched this array once and the pager
                // only chooses which of its rows are drawn. The chosen request
                // is an id held in this component's state, so it survives a
                // page turn — there is nothing on a row for paging to lose.
                <PagedList items={requests} label="Speaker Requests" idPrefix="match-run-requests">
                  {(visibleRequests) => (
                    <ul className="space-y-3">
                      {visibleRequests.map((request) => (
                        <RequestRow
                          key={request.request_id}
                          request={request}
                          selected={selectedRequestId === request.request_id}
                          onSelect={setSelectedRequestId}
                        />
                      ))}
                    </ul>
                  )}
                </PagedList>
              )}
              {requestsTruncated ? (
                <p className="text-sm text-amber-700">
                  The server stopped sending at its own limit, so more requests are filed under this
                  unit than ever reached this browser. That is a different shortfall from the pager
                  above, which speaks only about how much of what did arrive is currently drawn.
                </p>
              ) : null}
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-semibold text-foreground">Who to consider</h2>
              <p className="text-sm text-muted-foreground">
                Your unit&rsquo;s §13 roster. {eligibleCount} of {contacts.length} may enter
                matching; the rest are listed with the server&rsquo;s reason rather than hidden,
                because the reason is what tells you what to do next.
              </p>
              {contacts.length === 0 ? (
                <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                  This unit has no recorded contacts yet.
                </p>
              ) : (
                // The roster is paged the same way, and this is the list where
                // it matters most: `selectedSubjectIds` is a list of ids, not a
                // property of a drawn row, so candidates checked on one page
                // stay checked and stay submitted after a Connector moves to
                // another page and back. The count below the submit button
                // keeps counting all of them for the same reason.
                <PagedList items={contacts} label="Roster contacts" idPrefix="match-run-roster">
                  {(visibleContacts) => (
                    <ul className="space-y-3">
                      {visibleContacts.map((contact) => (
                        <ContactRow
                          key={contact.professional_id}
                          contact={contact}
                          selected={selectedSubjectIds.includes(contact.professional_id)}
                          onToggle={toggleSubject}
                        />
                      ))}
                    </ul>
                  )}
                </PagedList>
              )}
              {contactsTruncated ? (
                <p className="text-sm text-amber-700">
                  The server stopped sending at its own limit, so this unit&rsquo;s roster holds
                  more contacts than ever reached this browser. That is a different shortfall from
                  the pager above, which speaks only about how much of what did arrive is currently
                  drawn.
                </p>
              ) : null}
            </section>

            <section className="space-y-3">
              <h2 className="text-lg font-semibold text-foreground">Shortlist size</h2>
              <div className="space-y-1">
                <label htmlFor="portfolio-size" className="text-sm font-medium text-foreground">
                  How many speakers to shortlist
                </label>
                <select
                  id="portfolio-size"
                  value={portfolioSize}
                  onChange={(event) => setPortfolioSize(Number(event.target.value))}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm sm:w-48"
                >
                  {PORTFOLIO_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  Two or three, and the server refuses anything else — the bound is enforced on the
                  submission rather than trimmed at render time.
                </p>
              </div>
            </section>

            <div className="space-y-2">
              <button
                type="submit"
                disabled={submitting || blockingReason !== null}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              >
                {submitting ? "Submitting…" : "Submit match run"}
              </button>
              {blockingReason !== null ? (
                <p className="text-xs text-muted-foreground">{blockingReason}</p>
              ) : (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                  {selectedSubjectIds.length} candidates will be submitted for scoring.
                </p>
              )}
              {submitError !== null ? (
                <p className="flex items-start gap-2 rounded-lg border border-destructive/40 p-3 text-sm text-destructive">
                  <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
                  {submitError}
                </p>
              ) : null}
            </div>
          </form>

          {accepted !== null ? (
            <QueuedRunPanel accepted={accepted} jobState={jobState} followError={followError} />
          ) : null}
        </>
      )}
    </div>
  );
}
