import { AlertCircle } from "lucide-react";

import { AccountableValue } from "@/app/components/provenance";
import {
  OPPORTUNITIES_UNKNOWN_REASON,
  unavailableOpportunitiesMetric,
} from "@/lib/metrics";

const opportunitiesMetric = unavailableOpportunitiesMetric();

export function Opportunities() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">Opportunities</h1>
        <p className="mt-1 text-gray-600">
          The canonical opportunities list and count are not available until S12 persistence and a
          registered metric definition are approved.
        </p>
      </div>

      <div
        className="rounded-2xl border border-[#d5e0f7] bg-white p-8 shadow-sm"
        aria-labelledby="opportunities-unavailable-heading"
      >
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#eef4ff] text-[#005394]">
            <AlertCircle className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#005394]/70">
                Registered metric pending
              </p>
              <h2
                id="opportunities-unavailable-heading"
                className="mt-2 text-2xl font-semibold text-gray-900"
              >
                Opportunities count and list
              </h2>
            </div>
            <p className="text-3xl font-semibold tracking-tight text-gray-900">
              <AccountableValue metric={opportunitiesMetric} />
            </p>
            <p className="text-sm leading-6 text-gray-600">{OPPORTUNITIES_UNKNOWN_REASON}</p>
            <p className="text-sm leading-6 text-gray-600">
              This page does not merge legacy CSV or crawler rows, fabricate dates or roles, or show
              match scores. Matching remains unavailable until gate G1 approves the factor registry.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
