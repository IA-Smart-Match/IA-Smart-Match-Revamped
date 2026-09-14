import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Briefcase,
  Check,
  MapPin,
  RefreshCw,
  Search,
  Users,
} from "lucide-react";

import {
  emptyQrStatsSummary,
  fetchCalendarAssignments,
  fetchPipeline,
  fetchQrStats,
  fetchSpecialists,
  splitTags,
  type CalendarAssignmentSummary,
  type PipelineRecord,
  type QrStatsSummary,
  type Specialist,
} from "@/lib/api";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { Button } from "@/app/components/ui/button";
import { AccountableValue } from "@/app/components/provenance";
import { unavailableMatchingMetric } from "@/lib/metrics";
import {
  normalizeName,
  percentage,
  summarizeVolunteer,
  VolunteerDetailModal,
} from "./VolunteersSections";

/**
 * Gate G1 fail-closed placeholder for every match-score slot on this page.
 * `REGISTRY_STATUS` is `proposed`, so no score, rank, or factor value may be
 * rendered here; the slots show an accountable unknown with the reason
 * instead of a fabricated average.
 */
const matchingMetric = unavailableMatchingMetric();

/**
 * Reads a human message off a thrown value without assuming a specific error
 * shape. Tolerates plain Error instances, the API layer's ApiRequestError,
 * and anything else that merely looks like an error.
 */
function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === "object") {
    const maybeMessage = (err as { message?: unknown }).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim().length > 0) {
      return maybeMessage;
    }
  }
  if (typeof err === "string" && err.trim().length > 0) {
    return err;
  }
  return fallback;
}

function FailureState({
  title = "We couldn't load this data",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
        <AlertTriangle className="h-5 w-5 text-red-600" />
      </div>
      <p className="mt-3 text-sm font-semibold text-red-800">{title}</p>
      <p className="mt-1 text-sm text-red-700">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function VolunteerSkeleton() {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm animate-pulse">
      <div className="flex items-start gap-4">
        <div className="h-16 w-16 rounded-full bg-muted" />
        <div className="flex-1 space-y-3">
          <div className="h-4 w-2/3 rounded bg-muted" />
          <div className="h-3 w-1/2 rounded bg-muted" />
          <div className="h-5 w-24 rounded-full bg-muted" />
        </div>
      </div>
      <div className="mt-5 space-y-2">
        <div className="h-3 rounded bg-muted" />
        <div className="h-3 rounded bg-muted" />
      </div>
      <div className="mt-6 flex gap-2">
        <div className="h-10 flex-1 rounded-xl bg-muted" />
        <div className="h-10 flex-1 rounded-xl bg-muted" />
        <div className="h-10 flex-1 rounded-xl bg-muted" />
      </div>
    </div>
  );
}

const stageWeights: Record<string, number> = {
  Matched: 1,
  Contacted: 2,
  Confirmed: 3,
  Attended: 4,
  "Member Inquiry": 5,
};

export function Volunteers() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVolunteer, setSelectedVolunteer] = useState<string | null>(null);
  const [volunteers, setVolunteers] = useState<Specialist[]>([]);
  const [pipeline, setPipeline] = useState<PipelineRecord[]>([]);
  const [assignments, setAssignments] = useState<CalendarAssignmentSummary[]>([]);
  const [qrStats, setQrStats] = useState<QrStatsSummary>(emptyQrStatsSummary());
  const [isMockData, setIsMockData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setError(null);

    Promise.allSettled([
      fetchSpecialists(),
      fetchPipeline(),
      fetchCalendarAssignments(),
      fetchQrStats(),
    ])
      .then(([specialistResult, pipelineResult, assignmentResult, qrResult]) => {
        if (!active) {
          return;
        }
        // The volunteer roster and pipeline are the core data this page
        // shows. If either failed to load, report the failure instead of
        // substituting fixture volunteers.
        if (specialistResult.status !== "fulfilled" || pipelineResult.status !== "fulfilled") {
          const reason =
            specialistResult.status === "rejected"
              ? specialistResult.reason
              : (pipelineResult as PromiseRejectedResult).reason;
          setVolunteers([]);
          setPipeline([]);
          setAssignments([]);
          setQrStats(emptyQrStatsSummary());
          setIsMockData(false);
          setLoadFailed(true);
          setError(getErrorMessage(reason, "Failed to load volunteers."));
          return;
        }

        let anyMock = false;

        setVolunteers(specialistResult.value.data);
        if (specialistResult.value.isMockData) anyMock = true;

        setPipeline(pipelineResult.value.data);
        if (pipelineResult.value.isMockData) anyMock = true;

        if (assignmentResult.status === "fulfilled") {
          setAssignments(assignmentResult.value.data);
          if (assignmentResult.value.isMockData) anyMock = true;
        } else {
          // Assignment overlays are supplementary — keep the real roster
          // and surface a warning instead of fabricating overlay rows.
          setAssignments([]);
        }

        if (qrResult.status === "fulfilled") {
          setQrStats(qrResult.value.data);
          if (qrResult.value.isMockData) anyMock = true;
        } else {
          setQrStats(emptyQrStatsSummary());
        }

        setIsMockData(anyMock);

        const warnings = [];
        if (assignmentResult.status === "rejected") {
          warnings.push(
            `Assignment overlays are unavailable: ${getErrorMessage(assignmentResult.reason, "Request failed.")}`,
          );
        }
        if (qrResult.status === "rejected") {
          warnings.push(
            `QR analytics are unavailable: ${getErrorMessage(qrResult.reason, "Request failed.")}`,
          );
        }
        setError(warnings.length ? warnings.join(" ") : null);
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        // Unexpected failure — report it honestly rather than substituting
        // fixture data.
        setVolunteers([]);
        setPipeline([]);
        setAssignments([]);
        setQrStats(emptyQrStatsSummary());
        setIsMockData(false);
        setLoadFailed(true);
        setError(getErrorMessage(err, "Failed to load volunteers."));
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [reloadToken]);

  const filteredVolunteers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return volunteers.filter((volunteer) => {
      const expertise = splitTags(volunteer.expertise_tags);
      if (!query) {
        return true;
      }

      return (
        volunteer.name.toLowerCase().includes(query) ||
        volunteer.company.toLowerCase().includes(query) ||
        volunteer.metro_region.toLowerCase().includes(query) ||
        expertise.some((tag) => tag.toLowerCase().includes(query))
      );
    });
  }, [searchQuery, volunteers]);

  const selectedVol =
    volunteers.find((volunteer) => volunteer.name === selectedVolunteer) ?? null;
  const selectedInsights = selectedVol
    ? summarizeVolunteer(selectedVol, pipeline, assignments)
    : null;
  const selectedQrHistory = useMemo(() => {
    if (!selectedVol) {
      return [];
    }

    const selectedName = normalizeName(selectedVol.name);
    return [...qrStats.entries]
      .filter((entry) => normalizeName(entry.speaker_name) === selectedName)
      .sort((left, right) => {
        const leftTime = Date.parse(left.last_scanned_at || left.generated_at || "");
        const rightTime = Date.parse(right.last_scanned_at || right.generated_at || "");
        return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
      });
  }, [qrStats.entries, selectedVol]);
  const selectedQrAsset = selectedQrHistory[0] ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold text-foreground">
          Volunteer Profiles{isMockData && <DemoModeBadge />}
        </h1>
        <p className="text-muted-foreground">
          Browse the live roster, inspect assignment load, and open a dashboard-style detail view
          for any volunteer.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by name, company, region, or expertise..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="w-full rounded-xl border border-border py-3 pl-10 pr-4 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>

      {!loadFailed && error ? (
        <FailureState
          title="Some volunteer data is unavailable"
          message={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : null}

      {loadFailed ? (
        <FailureState
          title="Volunteer profiles could not be loaded"
          message={error ?? "Failed to load volunteers."}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {loading ? (
            Array.from({ length: 6 }, (_, index) => <VolunteerSkeleton key={index} />)
          ) : filteredVolunteers.length === 0 ? (
            <div className="col-span-full rounded-2xl border border-border bg-card p-10 text-center text-muted-foreground shadow-sm">
              {searchQuery
                ? "No volunteers match your search."
                : "No volunteer profiles are available yet."}
            </div>
          ) : (
            filteredVolunteers.map((volunteer) => {
              const expertise = splitTags(volunteer.expertise_tags);
              const profile = summarizeVolunteer(volunteer, pipeline, assignments);

              return (
                <button
                  key={volunteer.name}
                  type="button"
                  onClick={() => setSelectedVolunteer(volunteer.name)}
                  className="rounded-2xl border border-border bg-card p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
                >
                  <div className="mb-4 flex items-start gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/70 text-xl font-semibold text-white">
                      {volunteer.initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="truncate font-semibold text-foreground">{volunteer.name}</h3>
                          <p className="text-sm text-muted-foreground">
                            {volunteer.title || "Board volunteer"}
                          </p>
                        </div>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${profile.recovery.tone}`}
                        >
                          <Activity className="h-3.5 w-3.5" />
                          {profile.recovery.label}
                        </span>
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-primary">
                          <Check className="h-3 w-3" />
                          {volunteer.board_role || "Available"}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                          <Users className="h-3 w-3" />
                          {profile.matchedCount} live matches
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Briefcase className="h-4 w-4 text-primary" />
                      <span>{volunteer.company || "Independent"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-primary" />
                      <span>{volunteer.metro_region || "Region not listed"}</span>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground">
                      <span>Recovery / load</span>
                      <span>{percentage(profile.fatigueScore)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      {profile.fatigueScore === null ? (
                        <div
                          className="h-2 rounded-full bg-[repeating-linear-gradient(45deg,theme(colors.slate.300),theme(colors.slate.300)_4px,transparent_4px,transparent_8px)]"
                          style={{ width: "100%" }}
                          aria-label="Fatigue unknown"
                        />
                      ) : (
                        <div
                          className={`h-2 rounded-full ${
                            profile.fatigueScore >= 75
                              ? "bg-red-500"
                              : profile.fatigueScore >= 50
                                ? "bg-amber-500"
                                : profile.fatigueScore >= 25
                                  ? "bg-primary"
                                  : "bg-emerald-500"
                          }`}
                          style={{ width: `${profile.fatigueScore}%` }}
                        />
                      )}
                    </div>
                  </div>

                  <div className="mt-5 flex items-center justify-between rounded-xl bg-muted px-4 py-3">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Match depth</p>
                      <p className="text-lg font-semibold text-foreground">{profile.matchedCount}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Coverage</p>
                      <p className="text-lg font-semibold text-primary">
                        {percentage(profile.utilizationRate)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Avg score</p>
                      <p className="text-lg font-semibold text-foreground">
                        <AccountableValue metric={matchingMetric} />
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-primary/20 bg-accent/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-primary">Recovery badge</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {profile.recovery.label}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {profile.recoveryRows.length
                        ? `${profile.recoveryRows.length} assignment overlay rows from the backend contract`
                        : "Recovery is falling back to the live pipeline footprint."}
                    </p>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {expertise.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-primary"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}

      {selectedVol && selectedInsights ? (
        <VolunteerDetailModal
          selectedVol={selectedVol}
          selectedInsights={selectedInsights}
          selectedQrHistory={selectedQrHistory}
          selectedQrAsset={selectedQrAsset}
          matchingMetric={matchingMetric}
          onClose={() => setSelectedVolunteer(null)}
        />
      ) : null}
    </div>
  );
}
