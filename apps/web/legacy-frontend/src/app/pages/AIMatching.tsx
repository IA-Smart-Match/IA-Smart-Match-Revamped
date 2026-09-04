import { AlertCircle } from "lucide-react";

import { AccountableValue } from "@/app/components/provenance";
import {
  MATCHING_UNAVAILABLE_REASON,
  unavailableMatchingMetric,
} from "@/lib/metrics";

const matchingMetric = unavailableMatchingMetric();

export function AIMatching() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">Find volunteer matches</h1>
        <p className="mt-1 text-gray-600">
          Suggestions will appear here after the matching rules have been reviewed and approved.
        </p>
      </div>

      <div
        className="rounded-2xl border border-[#d9cbc4] bg-white p-8 shadow-sm"
        aria-labelledby="matching-unavailable-heading"
      >
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#edf5f0] text-[#005030]">
            <AlertCircle className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#005030]/70">
                Review still in progress
              </p>
              <h2
                id="matching-unavailable-heading"
                className="mt-2 text-2xl font-semibold text-gray-900"
              >
                Volunteer suggestions are not available yet
              </h2>
            </div>
            <p className="text-3xl font-semibold tracking-tight text-gray-900">
              <AccountableValue metric={matchingMetric} />
            </p>
            <p className="text-sm leading-6 text-gray-600">{MATCHING_UNAVAILABLE_REASON}</p>
            <p className="text-sm leading-6 text-gray-600">
              Smart Match will not suggest volunteers until the matching rules have completed gate G1 review. Technical status:{" "}
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">REGISTRY_STATUS</code> remains{" "}
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">proposed</code>. Match runs
              arrive after the program owner closes gate G1.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
