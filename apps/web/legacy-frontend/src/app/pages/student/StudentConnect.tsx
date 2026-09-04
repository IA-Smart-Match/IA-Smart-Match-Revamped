import { useState, useEffect } from "react";
import { AlertTriangle, UserPlus } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import {
  fetchPipeline,
  fetchSpecialists,
  fetchStudentConnectionSuggestions,
  fetchStudentProfile,
  type StudentConnectionSuggestionsResponse,
  type StudentConnectionSuggestion,
  type PipelineRecord,
  type Specialist,
  type StudentSpeakerSuggestion,
} from "../../../lib/api";
import { getInitials, getMockProfilePhoto } from "../../../lib/mockProfilePhotos";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { portalSubjectId } from "../../../lib/principal";

function getSharedInterests(a: string, b: string): string[] {
  const setA = new Set(a.split(",").map((s) => s.trim().toLowerCase()));
  return b
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && setA.has(s.toLowerCase()));
}

export function StudentConnect() {
  // `/v1/me` verifies the account but does not provide a legacy student id;
  // the API client rejects the empty value locally instead of guessing one.
  const principal = useAuthenticatedPrincipal();
  const studentId = portalSubjectId(principal, "student") ?? "";

  const [payload, setPayload] = useState<StudentConnectionSuggestionsResponse | null>(null);
  // The viewer's own interests, as the server records them. This used to be
  // read out of the browser-written session blob, which nothing ever wrote —
  // so the overlap chips below were permanently empty. It now comes from the
  // student's server-held profile, or stays empty when the server has none.
  const [viewerInterests, setViewerInterests] = useState("");
  const [speakerSuggestions, setSpeakerSuggestions] = useState<StudentSpeakerSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState<Set<string>>(new Set());
  const [speakerRequested, setSpeakerRequested] = useState<Set<string>>(new Set());

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [data, pipelineRes, specialistsRes, profile] = await Promise.all([
          fetchStudentConnectionSuggestions(studentId),
          fetchPipeline(),
          fetchSpecialists(),
          // Optional: the overlap chips are an enhancement, so a profile the
          // legacy backend cannot serve must not fail the whole page.
          fetchStudentProfile(studentId).catch(() => null),
        ]);
        if (!mounted) return;
        setPayload(data);
        setViewerInterests(profile?.interests ?? "");
        setSpeakerSuggestions(
          buildSpeakerSuggestions(data.attended_past_events, pipelineRes.data, specialistsRes.data),
        );
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load suggestions");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [studentId]);

  const suggestions = payload?.suggestions ?? [];

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-24 w-full rounded-2xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">{error}</p>
      </div>
    );
  }

  if (!payload) return null;

  const { attended_past_events } = payload;
  const serviceUnavailable = payload.source === "unavailable";
  const focusInterests = viewerInterests;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">Connect</h1>
          {payload.source === "demo" && <DemoModeBadge />}
        </div>
      </div>

      <p className="max-w-3xl text-muted-foreground">
        People you may want to meet are ranked by{" "}
        <span className="font-medium text-foreground">events you both attended</span> (same check-in
        history as on Past Events). Shared interests are shown as a secondary signal when they apply.
      </p>
      {serviceUnavailable && (
        <div className="rounded-2xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Connect suggestions are temporarily unavailable. If you just updated backend routes, restart the
          API server and refresh this page.
        </div>
      )}

      <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
            <AppIcon name="attendance" className="h-5 w-5 text-primary" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-foreground">Your attended events</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Connection ideas only use events where your status is{" "}
              <span className="font-medium text-foreground">Attended</span> — matching Past Events.
            </p>
            {attended_past_events.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
                No attended events yet. After you check in at a chapter event, peers from the same room
                will appear here.
              </p>
            ) : (
              <ul className="mt-3 flex flex-wrap gap-2" aria-label="Events you attended">
                {attended_past_events.map((ev) => (
                  <li
                    key={ev.event_id}
                    className="rounded-full border border-primary/25 bg-primary/5 px-3 py-1 text-xs font-medium text-primary"
                  >
                    {ev.event_name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {suggestions.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <AppIcon name="connect" className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No co-attendance matches in the demo roster</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {attended_past_events.length === 0
              ? "Attend at least one event to unlock this list."
              : "No other demo students share your attended events yet. Try another account or re-seed the demo database."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <AppIcon name="sparkles" className="h-4 w-4 text-primary" aria-hidden />
            <span>
              {suggestions.length} suggested connection{suggestions.length === 1 ? "" : "s"} from shared
              attendance
            </span>
          </div>
          {suggestions.map((conn: StudentConnectionSuggestion) => {
            const interestOverlap =
              focusInterests && conn.interests ? getSharedInterests(focusInterests, conn.interests) : [];
            const isRequested = requested.has(conn.peer_student_id);
            const isConnected = isAlreadyConnected(studentId, conn.peer_student_id);

            return (
              <div
                key={conn.peer_student_id}
                className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border/70 bg-primary/5">
                      <img
                        src={getMockProfilePhoto(conn.peer_student_id || conn.name)}
                        alt={`${conn.name} profile`}
                        className="h-full w-full object-cover"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                          const next = e.currentTarget.nextElementSibling as HTMLElement | null;
                          if (next) next.style.display = "flex";
                        }}
                      />
                      <div className="hidden h-full w-full items-center justify-center text-base font-semibold text-primary">
                        {getInitials(conn.name)}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 gap-y-1">
                        <p className="font-semibold text-foreground">{conn.name}</p>
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                          {conn.shared_event_count} shared event{conn.shared_event_count === 1 ? "" : "s"}
                        </span>
                        {isConnected && (
                          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                            Connected
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">{conn.school}</p>
                      <p className="text-sm text-muted-foreground">{conn.major}</p>

                      <div className="mt-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          You both attended
                        </p>
                        <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Shared attended events">
                          {conn.shared_events.map((ev) => (
                            <li
                              key={ev.event_id}
                              className="rounded-full border border-border/80 bg-surface-container-low px-2.5 py-1 text-xs font-medium text-foreground"
                            >
                              {ev.event_name}
                            </li>
                          ))}
                        </ul>
                      </div>

                      {interestOverlap.length > 0 && (
                        <div className="mt-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Shared interests
                          </p>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {interestOverlap.map((interest) => (
                              <span
                                key={interest}
                                className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
                              >
                                {interest}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <button
                      type="button"
                      onClick={() => setRequested((prev) => new Set([...prev, conn.peer_student_id]))}
                      disabled={isRequested || isConnected}
                      className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                        isConnected
                          ? "cursor-default bg-green-100 text-green-700"
                          : isRequested
                            ? "cursor-default bg-green-100 text-green-700"
                            : "bg-primary text-primary-foreground hover:bg-primary/90"
                      }`}
                    >
                      <UserPlus className="h-4 w-4" aria-hidden />
                      {isConnected ? "Connected" : isRequested ? "Request sent!" : "Connect"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="space-y-4 pt-2">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-foreground">
            Connect with IA West Volunteer Speakers
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Speakers are synced to your attended events. If you attended an event where a volunteer
          speaker participated, they show up here.
        </p>

        {speakerSuggestions.length === 0 ? (
          <div className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground shadow-sm">
            No speaker matches yet. Attend more events and this list will auto-populate.
          </div>
        ) : (
          <div className="space-y-4">
            {speakerSuggestions.map((speaker) => {
              const speakerId = `${speaker.speaker_name}-${speaker.speaker_company}`;
              const isRequested = speakerRequested.has(speakerId);
              const isConnected = isAlreadyConnected(studentId, speaker.speaker_name);
              return (
                <div
                  key={speakerId}
                  className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border/70 bg-primary/5">
                        <img
                          src={getMockProfilePhoto(speakerId)}
                          alt={`${speaker.speaker_name} profile`}
                          className="h-full w-full object-cover"
                          loading="lazy"
                          referrerPolicy="no-referrer"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                            const next = e.currentTarget.nextElementSibling as HTMLElement | null;
                            if (next) next.style.display = "flex";
                          }}
                        />
                        <div className="hidden h-full w-full items-center justify-center text-base font-semibold text-primary">
                          {getInitials(speaker.speaker_name)}
                        </div>
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-foreground">{speaker.speaker_name}</p>
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                            {speaker.shared_event_count} shared event{speaker.shared_event_count === 1 ? "" : "s"}
                          </span>
                          {isConnected && (
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                              Connected
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {speaker.speaker_title} · {speaker.speaker_company}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {speaker.board_role} · {speaker.metro_region}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Expertise: {speaker.expertise_tags || "General speaking"}
                        </p>
                        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Shared attended events with speaker">
                          {speaker.shared_events.map((ev) => (
                            <li
                              key={`${speakerId}-${ev.event_id}`}
                              className="rounded-full border border-border/80 bg-surface-container-low px-2.5 py-1 text-xs font-medium text-foreground"
                            >
                              {ev.event_name}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <button
                        type="button"
                        onClick={() => setSpeakerRequested((prev) => new Set([...prev, speakerId]))}
                        disabled={isRequested || isConnected}
                        className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                          isConnected
                            ? "cursor-default bg-green-100 text-green-700"
                            : isRequested
                              ? "cursor-default bg-green-100 text-green-700"
                              : "bg-primary text-primary-foreground hover:bg-primary/90"
                        }`}
                      >
                        <UserPlus className="h-4 w-4" aria-hidden />
                        {isConnected ? "Connected" : isRequested ? "Request sent!" : "Connect with speaker"}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function stableHash(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function isAlreadyConnected(currentStudentId: string, otherId: string): boolean {
  // Deterministic “half already connected” rule for the demo.
  const key = `${currentStudentId}::${otherId}`.toLowerCase();
  return stableHash(key) % 2 === 0;
}

function buildSpeakerSuggestions(
  attendedPastEvents: Array<{ event_id: string; event_name: string }>,
  pipeline: PipelineRecord[],
  specialists: Specialist[],
): StudentSpeakerSuggestion[] {
  if (attendedPastEvents.length === 0) return [];

  const attendedByName = new Map(
    attendedPastEvents.map((ev) => [ev.event_name.trim().toLowerCase(), ev]),
  );
  const specialistByName = new Map(
    specialists.map((s) => [s.name.trim().toLowerCase(), s]),
  );
  const grouped = new Map<string, StudentSpeakerSuggestion>();

  for (const row of pipeline) {
    const eventKey = row.event_name.trim().toLowerCase();
    const sharedEvent = attendedByName.get(eventKey);
    if (!sharedEvent) continue;

    const speakerName = row.speaker_name?.trim();
    if (!speakerName) continue;
    const speakerKey = speakerName.toLowerCase();
    const specialist = specialistByName.get(speakerKey);
    const existing = grouped.get(speakerKey);

    if (existing) {
      if (!existing.shared_events.some((ev) => ev.event_id === sharedEvent.event_id)) {
        existing.shared_events.push(sharedEvent);
        existing.shared_event_count = existing.shared_events.length;
      }
      continue;
    }

    grouped.set(speakerKey, {
      speaker_name: speakerName,
      speaker_title: specialist?.title ?? "IA West Speaker",
      speaker_company: specialist?.company ?? "Insights Association West",
      board_role: specialist?.board_role ?? "Volunteer Speaker",
      metro_region: specialist?.metro_region ?? "West Coast",
      expertise_tags: specialist?.expertise_tags ?? "",
      shared_events: [sharedEvent],
      shared_event_count: 1,
    });
  }

  return Array.from(grouped.values()).sort((a, b) => {
    if (b.shared_event_count !== a.shared_event_count) {
      return b.shared_event_count - a.shared_event_count;
    }
    return a.speaker_name.localeCompare(b.speaker_name);
  });
}
