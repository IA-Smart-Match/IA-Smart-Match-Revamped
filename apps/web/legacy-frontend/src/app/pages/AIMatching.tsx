/**
 * Coordinator shortlist surface (plan card M10).
 *
 * This page reads one persisted match run from the real API —
 * `GET /v1/units/{unit_id}/match-runs/{match_run_id}` — and renders its
 * shortlist with the per-factor explanation behind every candidate. It holds
 * no ranking logic of its own, computes no score, and has no fallback dataset:
 * when it cannot reach a run it says so and shows nothing, because the failure
 * mode this whole plan exists to prevent is a matching page that looks like it
 * is working.
 *
 * ## Where runs are submitted, and why not here
 *
 * There is no "run the matcher" form on this page, and there is no longer any
 * need for one: `pages/coordinator/CoordinatorMatchRuns.tsx` submits runs from
 * the Connector portal, against a filed Speaker Request and a pool drawn from
 * the unit's own §13 roster. That is the right home for it because the
 * submission is a Connector's decision about their own contacts, and because
 * the pool must be built from `professional_id`s the server returned rather
 * than from anything a coordinator could type. A form here that asked for a
 * roster — or, worse, filled one from the legacy CSV surfaces — would be
 * inventing the evidence the score is computed from.
 *
 * This page stays a pure read: it renders whatever run its `?run=` names.
 *
 * ## ADR-0016's third factor state
 *
 * A factor value is `measured`, `policy_neutral`, or `unknown`. The middle one
 * is a real number that a stated customer policy supplied, and it participates
 * in the composite — so it renders as a number, attributed to the policy behind
 * it, and never as "Unknown". Every factor row is driven by the registry's own
 * `display_label`; this file names no CBA factor key, so a registry that gains
 * a factor renders it without a frontend change.
 *
 * ## Three ratified presentation rules, and where each is enforced
 *
 * From `docs/plans/workshops/g1-workshop-output-worksheet.md` agenda item 1:
 *
 * - **2-3 speakers.** Enforced server-side, on the submission — the API refuses
 *   a `portfolio_size` outside that range and caps the rendered shortlist. This
 *   page renders what it is given rather than slicing, so a violation would be
 *   visible here rather than hidden by a client-side trim.
 * - **No percentage.** `formatScore` prints the value as it is, to two
 *   decimals, in [0, 1]. Nothing here scales a score by a hundred and no
 *   percent sign appears anywhere in this file — both are refused by name in
 *   `tests/unit/test_frontend_matching_contract.py`.
 * - **The registry version accompanies every score.** Rendered on the run
 *   header and again on every candidate card, from the response — never from a
 *   constant compiled into this bundle, which could disagree with the registry
 *   the run was actually produced under.
 *
 * ## ADR-0011 at the last boundary
 *
 * `ScoreValue` and `FactorRow` switch on `state`, never on `value == null`, and
 * no coalescing default turns an absent value into a number anywhere in this
 * file — the source contract refuses those operators by name. A factor with no
 * evidence renders the word
 * "Unknown" and its reason; a factor measured at zero renders `0.00` and the
 * source that measured it. Those are different pixels because they are
 * different facts — which is exactly what the legacy "Topic Relevance 0%"
 * surface got wrong.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { AlertCircle, Info } from "lucide-react";

import { AccountableValue } from "@/app/components/provenance";
import {
  fetchMatchRun,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  type MatchCandidateExplanation,
  type MatchFactorExplanation,
  type MatchRunRead,
} from "@/lib/api";
import { MATCHING_UNAVAILABLE_REASON, unavailableMatchingMetric } from "@/lib/metrics";

/** Query parameter naming which persisted run to read. */
const RUN_ID_PARAM = "run";

/**
 * Reads the run id from the URL. Returns null rather than a default: there is
 * no "the latest run" to fall back to, and picking one would be this page
 * choosing which recommendation a coordinator sees.
 */
function readRunIdFromLocation(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const value = new URLSearchParams(window.location.search).get(RUN_ID_PARAM);
  return value && value.trim().length > 0 ? value.trim() : null;
}

/**
 * Renders a score exactly as the API measured it.
 *
 * Two decimals of a unit-interval number. Not a percentage — see the module
 * docstring — and not rounded to an integer, which would make 0.04 and 0.00
 * indistinguishable.
 */
function formatScore(value: number): string {
  return value.toFixed(2);
}

/** The heuristic score, or an honest "Unknown" with the reason it is unknown. */
function ScoreValue({
  state,
  value,
  unknownReason,
}: {
  state: MatchCandidateExplanation["state"];
  value: number | null;
  unknownReason: string;
}) {
  // Switched on `state`, not on `value === null`. The API sends the
  // discriminator for exactly this reason (ADR-0011).
  if (state === "unknown" || value === null) {
    return (
      <span className="text-gray-500" title={unknownReason}>
        Unknown
      </span>
    );
  }
  return <span className="tabular-nums text-gray-900">{formatScore(value)}</span>;
}

/**
 * One factor, with its weight, its value or its absence, and its basis.
 *
 * Three states, not two. ADR-0016 added `policy_neutral` — a value a stated
 * customer policy supplied rather than a measurement — and it is a real number
 * that participates in the composite. A renderer that knew only `measured` and
 * `unknown` would print "Unknown" beside it, which is the deflated-zero defect
 * with the sign flipped: reporting an absence where a value exists. So the row
 * shows the number and names the policy that produced it.
 *
 * The row is driven entirely by `display_label` and `factor_key` off the
 * response. Nothing here knows the CBA vocabulary by name: a switch on the
 * semantic-topic or industry factor keys would go stale the moment the registry
 * gained a factor, and would render nothing at all for the one it had not been
 * taught.
 */
function FactorRow({ factor }: { factor: MatchFactorExplanation }) {
  // Switched on `state`, never on `value === null` — the API sends the
  // discriminator for exactly this reason (ADR-0011).
  const shownValue = factor.state === "unknown" ? null : factor.value;
  return (
    <li className="flex flex-col gap-1 border-t border-[#eef2f9] py-2 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-gray-800">
          {factor.display_label}
          <span className="ml-2 text-xs font-normal text-gray-500">
            {factor.kind === "penalty" ? "penalty" : "suitability"} · weight{" "}
            {factor.weight.toFixed(2)}
          </span>
        </span>
        <span className="text-sm font-semibold">
          {shownValue === null ? (
            <span className="text-gray-500">Unknown</span>
          ) : (
            <span className="tabular-nums text-gray-900">{formatScore(shownValue)}</span>
          )}
        </span>
      </div>
      <p className="text-xs leading-5 text-gray-600">
        {factor.basis}
        {factor.estimate_label ? ` — ${factor.estimate_label}` : ""}
      </p>
      {factor.state === "policy_neutral" ? (
        <p className="text-xs text-gray-500">
          Stated customer policy, not a measurement
          {factor.policy_id === null
            ? ". The response named no policy id."
            : ` (${factor.policy_id}${
                factor.policy_version === null ? "" : ` ${factor.policy_version}`
              }).`}
        </p>
      ) : null}
      {factor.zero_classification === "measured_zero" ? (
        <p className="text-xs text-gray-500">
          Measured zero: the evidence exists and the value really is zero.
        </p>
      ) : null}
      {factor.zero_classification === "unknown" ? (
        <p className="text-xs text-gray-500">
          No evidence on file. This is not a zero, and it is not counted as one.
        </p>
      ) : null}
    </li>
  );
}

/** One candidate card: the score, its label and registry version, its factors. */
function CandidateCard({
  candidate,
  registryVersion,
}: {
  candidate: MatchCandidateExplanation;
  registryVersion: string;
}) {
  const unknownReason =
    candidate.unknown_factor_keys.length > 0
      ? `No evidence for: ${candidate.unknown_factor_keys.join(", ")}.`
      : "No heuristic score was produced for this candidate.";

  return (
    <li className="rounded-2xl border border-[#d5e0f7] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold text-gray-900">{candidate.subject_id}</h3>
        <p className="text-right">
          <span className="text-2xl font-semibold">
            <ScoreValue
              state={candidate.state}
              value={candidate.heuristic_score}
              unknownReason={unknownReason}
            />
          </span>
          <span className="ml-2 text-xs uppercase tracking-[0.18em] text-[#005394]/70">
            {candidate.score_label}
          </span>
        </p>
      </div>
      {/* ADR-0016 Proposal 8: the approved caption is shown beside the score,
          verbatim. Not paraphrased, not composed here, and not omitted — it is
          the sentence the customer approved for this score, and a surface that
          reworded it would be publishing a different claim. Rendered only when
          the response carried one; there is no local default. */}
      {candidate.caption ? (
        <p className="mt-2 text-sm leading-6 text-gray-700">{candidate.caption}</p>
      ) : null}
      <p className="mt-1 text-xs text-gray-500">
        Factor registry {candidate.registry_version || registryVersion} · formula{" "}
        {candidate.formula_version}
        {candidate.scoring_mode ? ` · mode ${candidate.scoring_mode}` : ""}
      </p>
      <ul className="mt-3 list-none">
        {candidate.factors.map((factor) => (
          <FactorRow key={factor.factor_key} factor={factor} />
        ))}
      </ul>
    </li>
  );
}

/** The honest empty state. Shown whenever a real run cannot be displayed. */
function MatchingUnavailable({ reason }: { reason: string }) {
  const matchingMetric = unavailableMatchingMetric(reason);
  return (
    <div
      className="rounded-2xl border border-[#d5e0f7] bg-white p-8 shadow-sm"
      aria-labelledby="matching-unavailable-heading"
    >
      <div className="flex items-start gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#eef4ff] text-[#005394]">
          <AlertCircle className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="space-y-4">
          <h2 id="matching-unavailable-heading" className="text-2xl font-semibold text-gray-900">
            No shortlist to show
          </h2>
          <p className="text-3xl font-semibold tracking-tight text-gray-900">
            <AccountableValue metric={matchingMetric} />
          </p>
          <p className="text-sm leading-6 text-gray-600">{reason}</p>
          <p className="text-sm leading-6 text-gray-600">
            This page reads persisted match runs from{" "}
            <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">
              /v1/units/&#123;unit_id&#125;/match-runs/&#123;match_run_id&#125;
            </code>
            . It never fabricates ranks, scores, or percentages when it cannot reach one.
          </p>
        </div>
      </div>
    </div>
  );
}

export function AIMatching() {
  const unitId = getConfiguredUnitId();
  const runId = readRunIdFromLocation();
  const authenticated = hasSmartmatchAuth();

  const [run, setRun] = useState<MatchRunRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!unitId || !runId || !authenticated) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchMatchRun(unitId, runId)
      .then((result) => {
        if (!cancelled) {
          setRun(result);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          // Surfaced, never swallowed into an empty shortlist: "no speakers
          // matched" and "the request failed" are different facts.
          setError(err instanceof Error ? err.message : "The match run could not be read.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [unitId, runId, authenticated]);

  let body;
  if (!authenticated) {
    body = (
      <MatchingUnavailable reason="No SmartMatch bearer token is configured in this browser session, so the match-run API cannot be called. Sign in to read a shortlist." />
    );
  } else if (!unitId) {
    body = (
      <MatchingUnavailable reason="No organizational unit is configured (VITE_SMARTMATCH_UNIT_ID), and match runs are unit-scoped. There is no unit to read a shortlist for." />
    );
  } else if (!runId) {
    body = (
      <MatchingUnavailable
        reason={`No match run was named. Open this page with ?${RUN_ID_PARAM}=<match_run_id> to read a persisted run. This page does not pick a run for you: choosing one would be choosing which recommendation you see.`}
      />
    );
  } else if (loading) {
    body = (
      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-8 text-sm text-gray-600 shadow-sm">
        Reading match run {runId}…
      </div>
    );
  } else if (error) {
    body = <MatchingUnavailable reason={error} />;
  } else if (!run) {
    body = <MatchingUnavailable reason={MATCHING_UNAVAILABLE_REASON} />;
  } else {
    body = (
      <div className="space-y-6">
        <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#005394]/70">
            Match run
          </p>
          <h2 className="mt-1 text-xl font-semibold text-gray-900">{run.event_need_id}</h2>
          <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Factor registry</dt>
              <dd className="text-gray-900">{run.registry_version}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Score label</dt>
              <dd className="text-gray-900">{run.score_label}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Solver</dt>
              <dd className="text-gray-900">
                {run.solver_name} {run.solver_version}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Travel estimate</dt>
              <dd className="text-gray-900">
                {run.route_estimate_source} {run.route_estimate_version}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Solver verdict</dt>
              <dd className="text-gray-900">{run.portfolio_status}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-600">Recorded</dt>
              <dd className="text-gray-900">{new Date(run.created_at).toLocaleString()}</dd>
            </div>
          </dl>
        </div>

        {run.shortlist_available ? (
          <ul className="list-none space-y-4">
            {run.shortlist.map((candidate) => (
              <CandidateCard
                key={candidate.subject_id}
                candidate={candidate}
                registryVersion={run.registry_version}
              />
            ))}
          </ul>
        ) : (
          <MatchingUnavailable
            reason={
              run.shortlist_unavailable_reason ??
              "The shortlist could not be reconstructed from this run's recorded inputs, so none is shown."
            }
          />
        )}

        {run.unscorable.length > 0 ? (
          <section className="rounded-2xl border border-[#e5e9f2] bg-[#fafbfe] p-6">
            <div className="flex items-start gap-3">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#005394]" aria-hidden="true" />
              <div>
                <h2 className="text-base font-semibold text-gray-900">
                  Not scored — evidence missing
                </h2>
                <p className="mt-1 text-sm leading-6 text-gray-600">
                  These candidates were considered and could not be scored, because at least one
                  factor had no evidence on file. They are listed rather than dropped, and they are
                  not scored as zero: an absence is not a low score.
                </p>
              </div>
            </div>
            <ul className="mt-4 list-none space-y-4">
              {run.unscorable.map((candidate) => (
                <CandidateCard
                  key={candidate.subject_id}
                  candidate={candidate}
                  registryVersion={run.registry_version}
                />
              ))}
            </ul>
          </section>
        ) : null}

        {run.considered.length > 0 ? (
          <section>
            <h2 className="text-base font-semibold text-gray-900">Considered, not shortlisted</h2>
            <ul className="mt-3 list-none space-y-4">
              {run.considered.map((candidate) => (
                <CandidateCard
                  key={candidate.subject_id}
                  candidate={candidate}
                  registryVersion={run.registry_version}
                />
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">Speaker shortlist</h1>
        <p className="mt-1 text-gray-600">
          Two to three speakers per event need, from the approved factor registry. Scores are
          heuristic and are shown as they were measured — never as a percentage, and never with an
          unknown reported as a zero.
        </p>
        {run !== null && runId ? (
          // The one hand-off out of this page, and it carries the run id rather
          // than asking anybody to retype it. Composing invitations happens in
          // the Connector portal against this run's own shortlist; nothing is
          // sent from there either.
          <p className="mt-2 text-sm">
            <Link
              className="font-medium text-blue-700 underline"
              to={`/coordinator-portal/invitations?run=${encodeURIComponent(runId)}`}
            >
              Compose speaker invitations from this shortlist
            </Link>
          </p>
        ) : null}
      </div>
      {body}
    </div>
  );
}
