import { useState, useEffect } from "react";
import { Video, Plus, AlertTriangle, CheckCircle2, ExternalLink } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { fetchCoordinatorMeetings, type MeetingBooking } from "../../../lib/api";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const STATUS_COLORS: Record<MeetingBooking["status"], string> = {
  confirmed: "bg-primary/10 text-primary",
  pending_confirmation: "bg-muted text-muted-foreground",
};

const STATUS_LABELS: Record<MeetingBooking["status"], string> = {
  confirmed: "Confirmed",
  pending_confirmation: "Pending",
};

export function CoordinatorMeetings() {
  const session = getSession();
  const coordinatorId = String((session.user as Record<string, unknown> | undefined)?.coordinator_id ?? "coord-001");

  const [meetings, setMeetings] = useState<MeetingBooking[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [bookDialog, setBookDialog] = useState(false);
  const [bookDate, setBookDate] = useState("");
  const [bookPurpose, setBookPurpose] = useState("");
  const [bookSuccess, setBookSuccess] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchCoordinatorMeetings(coordinatorId);
        setMeetings(result.data);
        setSource(result.source);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load meetings");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [coordinatorId]);

  function handleBook() {
    console.log("Meeting booking requested:", { date: bookDate, purpose: bookPurpose });
    setBookSuccess(true);
    setTimeout(() => {
      setBookSuccess(false);
      setBookDialog(false);
      setBookDate("");
      setBookPurpose("");
    }, 2500);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">Meetings</h1>
          {source === "demo" && <DemoModeBadge />}
        </div>
        <button
          onClick={() => setBookDialog(true)}
          className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Book New Meeting
        </button>
      </div>

      {meetings.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <Video className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No meetings booked yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {meetings.map((mtg) => (
            <div
              key={mtg.booking_id}
              className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="font-semibold text-foreground">{mtg.title}</h2>
                    <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${STATUS_COLORS[mtg.status]}`}>
                      {STATUS_LABELS[mtg.status]}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-4 text-sm text-muted-foreground">
                    <span>{new Date(mtg.scheduled_at).toLocaleString()}</span>
                    <span>{mtg.duration_minutes} min</span>
                    <span>with <span className="text-foreground">{mtg.ia_contact}</span></span>
                  </div>
                  {mtg.notes && (
                    <p className="mt-2 text-sm text-muted-foreground">{mtg.notes}</p>
                  )}
                </div>
                {mtg.status === "confirmed" && mtg.meeting_link && (
                  <a
                    href={mtg.meeting_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Join
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Book Meeting Dialog */}
      {bookDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <div className="w-full max-w-md rounded-2xl border border-border/70 bg-card p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="book-meeting-title">
            <h3 id="book-meeting-title" className="mb-4 text-lg font-semibold text-foreground">Book a Meeting</h3>
            {bookSuccess ? (
              <div className="flex items-center gap-2 rounded-xl bg-primary/10 border border-primary/20 p-4">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <p className="text-sm font-medium text-primary">Meeting request sent! IA West will confirm shortly.</p>
              </div>
            ) : (
              <>
                <div className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                      Preferred Date & Time
                    </label>
                    <input
                      type="datetime-local"
                      value={bookDate}
                      onChange={(e) => setBookDate(e.target.value)}
                      className="w-full rounded-xl border border-border/70 bg-background px-4 py-3 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                      Purpose
                    </label>
                    <textarea
                      value={bookPurpose}
                      onChange={(e) => setBookPurpose(e.target.value)}
                      placeholder="Briefly describe the meeting purpose..."
                      rows={3}
                      className="w-full rounded-xl border border-border/70 bg-background px-4 py-3 text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                </div>
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={handleBook}
                    disabled={!bookDate}
                    className="flex-1 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
                  >
                    Request Meeting
                  </button>
                  <button
                    onClick={() => setBookDialog(false)}
                    className="flex-1 rounded-xl border border-border/70 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
