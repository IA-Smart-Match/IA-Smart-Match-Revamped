import { useMemo, useState, useEffect } from "react";
import { AlertTriangle, MessageCircle, SendHorizonal, UserPlus } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import { Button } from "../../components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../../components/ui/sheet";
import {
  fetchPipeline,
  fetchSpecialists,
  fetchStudentConnectionSuggestions,
  type StudentConnectionSuggestionsResponse,
  type StudentConnectionSuggestion,
  type PipelineRecord,
  type Specialist,
  type StudentSpeakerSuggestion,
} from "../../../lib/api";
import { getInitials, getMockProfilePhoto } from "../../../lib/mockProfilePhotos";

function getSharedInterests(a: string, b: string): string[] {
  const setA = new Set(a.split(",").map((s) => s.trim().toLowerCase()));
  return b
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && setA.has(s.toLowerCase()));
}

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

export function StudentConnect() {
  const session = getSession();
  const rawId = (session.user as Record<string, unknown> | undefined)?.student_id;
  const studentId =
    rawId !== undefined && rawId !== null && String(rawId).trim() !== "" && String(rawId) !== "undefined"
      ? String(rawId).trim()
      : "stu-001";

  const [payload, setPayload] = useState<StudentConnectionSuggestionsResponse | null>(null);
  const [speakerSuggestions, setSpeakerSuggestions] = useState<StudentSpeakerSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState<Set<string>>(new Set());
  const [speakerRequested, setSpeakerRequested] = useState<Set<string>>(new Set());
  const [inboxOpen, setInboxOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [draftMessage, setDraftMessage] = useState("");

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [data, pipelineRes, specialistsRes] = await Promise.all([
          fetchStudentConnectionSuggestions(studentId),
          fetchPipeline(),
          fetchSpecialists(),
        ]);
        if (!mounted) return;
        setPayload(data);
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

  const connectedPeers = useMemo(() => {
    return suggestions.filter((s) => isAlreadyConnected(studentId, s.peer_student_id));
  }, [studentId, suggestions]);

  const inboxThreads = useMemo(() => {
    const studentThreads = connectedPeers.map((peer) => {
      const threadId = `peer:${peer.peer_student_id}`;
      return {
        threadId,
        name: peer.name,
        subtitle: peer.school,
        avatarSeed: peer.peer_student_id || peer.name,
        sharedEvents: peer.shared_events.map((e) => e.event_name),
        messages: makeMockThreadMessages({
          currentStudentId: studentId,
          otherName: peer.name,
          sharedEvent: peer.shared_events[0]?.event_name ?? "an IA West event",
        }),
      };
    });

    const speakerThreads = speakerSuggestions
      .filter((s) => isAlreadyConnected(studentId, s.speaker_name))
      .slice(0, 2)
      .map((speaker) => {
        const threadId = `speaker:${speaker.speaker_name}`;
        return {
          threadId,
          name: speaker.speaker_name,
          subtitle: `${speaker.speaker_title} · ${speaker.speaker_company}`,
          avatarSeed: `${speaker.speaker_name}-${speaker.speaker_company}`,
          sharedEvents: speaker.shared_events.map((e) => e.event_name),
          messages: makeMockThreadMessages({
            currentStudentId: studentId,
            otherName: speaker.speaker_name,
            sharedEvent: speaker.shared_events[0]?.event_name ?? "a chapter event",
          }),
        };
      });

    return [...studentThreads, ...speakerThreads];
  }, [connectedPeers, speakerSuggestions, studentId]);

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
  const focusInterests = String((session.user as Record<string, unknown> | undefined)?.interests ?? "");

  const activeThread = inboxThreads.find((t) => t.threadId === activeThreadId) ?? inboxThreads[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">Connect</h1>
          {payload.source === "demo" && <DemoModeBadge />}
        </div>

        <button
          type="button"
          onClick={() => {
            setInboxOpen(true);
            setActiveThreadId((prev) => prev ?? inboxThreads[0]?.threadId ?? null);
          }}
          className="relative inline-flex items-center justify-center rounded-xl border border-border/70 bg-card px-3 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-accent"
          title="Open chats"
          aria-label="Open chats"
        >
          <MessageCircle className="h-4 w-4" aria-hidden />
          {inboxThreads.length > 0 && (
            <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-bold text-primary-foreground">
              {Math.min(inboxThreads.length, 9)}
            </span>
          )}
        </button>
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
            const threadId = `peer:${conn.peer_student_id}`;

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

                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!isConnected}
                      onClick={() => {
                        setInboxOpen(true);
                        setActiveThreadId(threadId);
                      }}
                      title={isConnected ? "Open chat" : "Connect first to chat"}
                    >
                      <MessageCircle className="h-4 w-4" aria-hidden />
                      Chat
                    </Button>
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
              const threadId = `speaker:${speaker.speaker_name}`;
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
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!isConnected}
                        onClick={() => {
                          setInboxOpen(true);
                          setActiveThreadId(threadId);
                        }}
                        title={isConnected ? "Open chat" : "Connect first to chat"}
                      >
                        <MessageCircle className="h-4 w-4" aria-hidden />
                        Chat
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Sheet open={inboxOpen} onOpenChange={setInboxOpen}>
        <SheetContent className="min-h-0 overflow-hidden p-0 gap-0 h-dvh max-h-dvh w-full max-w-full border-l sm:max-w-xl md:max-w-2xl lg:max-w-4xl xl:max-w-[min(56rem,92vw)] 2xl:max-w-[min(64rem,88vw)]">
          <SheetHeader className="border-b">
            <SheetTitle className="px-4 pt-4">Chats</SheetTitle>
            <p className="px-4 pb-4 text-sm text-muted-foreground">
              Mock messages about shared events and professional topics.
            </p>
          </SheetHeader>

          {inboxThreads.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">
              No chats yet. Some connections will appear here after you connect.
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 border-b sm:grid-cols-[minmax(12rem,18rem)_1fr] md:grid-cols-[minmax(14rem,20rem)_1fr] sm:min-h-0">
                <div className="max-h-[min(40vh,18rem)] shrink-0 overflow-auto border-b sm:max-h-none sm:h-full sm:border-b-0 sm:border-r">
                  {inboxThreads.map((t) => {
                    const isActive = (activeThread?.threadId ?? "") === t.threadId;
                    return (
                      <button
                        key={t.threadId}
                        type="button"
                        onClick={() => setActiveThreadId(t.threadId)}
                        className={`flex w-full items-center gap-3 px-4 py-3 text-left transition ${
                          isActive ? "bg-accent" : "hover:bg-accent/50"
                        }`}
                      >
                        <div className="h-10 w-10 overflow-hidden rounded-full border border-border/70 bg-primary/5">
                          <img
                            src={getMockProfilePhoto(t.avatarSeed)}
                            alt={`${t.name} profile`}
                            className="h-full w-full object-cover"
                            loading="lazy"
                            referrerPolicy="no-referrer"
                          />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <div className="truncate text-sm font-semibold text-foreground">{t.name}</div>
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700">
                              Connected
                            </span>
                          </div>
                          <div className="truncate text-xs text-muted-foreground">{t.subtitle}</div>
                          <div className="truncate text-[11px] text-muted-foreground">
                            {t.messages[t.messages.length - 1]?.text ?? ""}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="flex min-h-[min(52dvh,28rem)] min-w-0 flex-1 flex-col sm:min-h-0">
                  <div className="border-b px-4 py-3">
                    <div className="text-sm font-semibold text-foreground">
                      {activeThread?.name ?? "Chat"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {activeThread?.sharedEvents?.[0] ? `About: ${activeThread.sharedEvents[0]}` : "Shared event"}
                    </div>
                  </div>

                  <div className="flex-1 space-y-2 overflow-auto px-4 py-3">
                    {(activeThread?.messages ?? []).map((m, idx) => (
                      <div
                        key={`${m.at}-${idx}`}
                        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                          m.from === "me"
                            ? "ml-auto bg-primary text-primary-foreground"
                            : "bg-muted text-foreground"
                        }`}
                      >
                        <div className="text-[11px] opacity-80">{m.at}</div>
                        <div>{m.text}</div>
                      </div>
                    ))}
                  </div>

                  <div className="border-t p-4">
                    <div className="flex items-center gap-2">
                      <input
                        value={draftMessage}
                        onChange={(e) => setDraftMessage(e.target.value)}
                        placeholder="Type a message (mock)"
                        className="h-10 flex-1 rounded-xl border border-border/70 bg-background px-3 text-sm text-foreground shadow-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
                      />
                      <Button
                        onClick={() => setDraftMessage("")}
                        disabled={!draftMessage.trim()}
                        className="rounded-xl"
                      >
                        <SendHorizonal className="h-4 w-4" aria-hidden />
                        Send
                      </Button>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      Demo-only: messages are not persisted.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
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

function makeMockThreadMessages(input: {
  currentStudentId: string;
  otherName: string;
  sharedEvent: string;
}): Array<{ from: "me" | "them"; text: string; at: string }> {
  const seed = stableHash(`${input.currentStudentId}:${input.otherName}:${input.sharedEvent}`);
  const topicVariants = [
    "career paths in analytics",
    "how to break into product research",
    "AI ethics in student projects",
    "how to prepare for a case competition",
    "what makes a great networking follow-up",
  ];
  const topic = topicVariants[seed % topicVariants.length] ?? "professional growth";
  return [
    {
      from: "them",
      at: "Yesterday",
      text: `Hey! Great seeing you at ${input.sharedEvent}. What did you think of the panel?`,
    },
    {
      from: "me",
      at: "Yesterday",
      text: `Same — it was super useful. I’m especially thinking about ${topic}.`,
    },
    {
      from: "them",
      at: "Today",
      text: `Totally. If you want, I can share a couple resources and how I approached it.`,
    },
  ];
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
