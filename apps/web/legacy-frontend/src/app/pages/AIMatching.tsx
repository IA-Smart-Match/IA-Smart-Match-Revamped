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
 * ## What it deliberately does not do
 *
 * There is no "run the matcher" form here. Submitting a run
 * (`POST /v1/units/{unit_id}/match-runs`) requires a candidate pool carrying
 * each professional's recorded expertise topics and coordinates, and this
 * legacy frontend has no authenticated, unit-scoped roster endpoint to
 * assemble one from. A form that asked a coordinator to type that roster in —
 * or, worse, that filled it from the legacy CSV surfaces — would be inventing
 * the evidence the score is computed from. So a run is submitted elsewhere
 * (API client, seed tooling) and this page reads the result.
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

/** One factor, with its weight, its value or its absence, and its basis. */
function FactorRow({ factor }: { factor: MatchFactorExplanation }) {
  const measuredValue = factor.state === "measured" ? factor.value : null;
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
          {measuredValue === null ? (
            <span className="text-gray-500">Unknown</span>
          ) : (
            <span className="tabular-nums text-gray-900">{formatScore(measuredValue)}</span>
          )}
        </span>
      </div>
      <p className="text-xs leading-5 text-gray-600">
        {factor.basis}
        {factor.estimate_label ? ` — ${factor.estimate_label}` : ""}
      </p>
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
      <p className="mt-1 text-xs text-gray-500">
        Factor registry {candidate.registry_version || registryVersion} · formula{" "}
        {candidate.formula_version}
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
      </div>
      {body}
    </div>
  );
}
