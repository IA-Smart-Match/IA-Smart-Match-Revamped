import { useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import { fetchStudentRegistrations, type StudentRegistration } from "../../../lib/api";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const STATUS_LABELS: Record<StudentRegistration["status"], string> = {
  registered: "Registered",
  attended: "Attended",
  cancelled: "Cancelled",
};

const STATUS_COLORS: Record<StudentRegistration["status"], string> = {
  registered: "bg-primary/10 text-primary",
  attended: "bg-green-100 text-green-700",
  cancelled: "bg-muted text-muted-foreground",
};

export function StudentEvents() {
  const session = getSession();
  const studentId = String((session.user as Record<string, unknown> | undefined)?.student_id ?? "stu-001");

  const [registrations, setRegistrations] = useState<StudentRegistration[]>([]);
  const [allRegistrations, setAllRegistrations] = useState<StudentRegistration[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [calendarToast, setCalendarToast] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchStudentRegistrations(studentId);
        setAllRegistrations(result.data);
        setRegistrations(result.data.filter((r) => r.status === "registered"));
        setSource(result.source);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load registrations");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [studentId]);

  function handleAddToCalendar(eventName: string) {
    setCalendarToast(`Calendar event added: ${eventName}`);
    setTimeout(() => setCalendarToast(null), 3000);
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
      {calendarToast && (
        <div className="flex items-center gap-3 rounded-2xl border border-green-200 bg-green-50 p-4">
          <AppIcon name="success" className="h-5 w-5 text-green-600" />
          <p className="text-sm font-medium text-green-700">{calendarToast}</p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold text-foreground">My Upcoming Events</h1>
        {source === "demo" && <DemoModeBadge />}
      </div>

      <MockStudentCalendar registrations={allRegistrations} />

      {registrations.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <AppIcon name="events" className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No upcoming events</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Check recommendations on your home page.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {registrations.map((reg) => (
            <div
              key={reg.registration_id}
              className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="font-semibold text-foreground">{reg.event_name}</h2>
                    <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${STATUS_COLORS[reg.status]}`}>
                      {STATUS_LABELS[reg.status]}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                    <AppIcon name="calendar" className="h-4 w-4" />
                    <span>Registered {new Date(reg.registered_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAddToCalendar(reg.event_name)}
                    className="rounded-xl border border-border/70 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent"
                  >
                    Add to Calendar
                  </button>
                  <a
                    href="/api/qr/stats"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                  >
                    <AppIcon name="qr" className="h-4 w-4" />
                    View QR Code
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type CalendarEntry = {
  day: number;
  label: string;
  status: StudentRegistration["status"];
};

function MockStudentCalendar({ registrations }: { registrations: StudentRegistration[] }) {
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  const startWeekday = monthStart.getDay();
  const daysInMonth = monthEnd.getDate();
  const dayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const entriesByDay = new Map<number, CalendarEntry[]>();
  for (const reg of registrations) {
    const dateSource =
      reg.status === "registered"
        ? (reg.event_date ?? reg.registered_at)
        : (reg.check_in_time ?? reg.event_date ?? reg.registered_at);
    const date = new Date(dateSource);
    if (Number.isNaN(date.getTime())) continue;
    if (date.getMonth() !== monthStart.getMonth() || date.getFullYear() !== monthStart.getFullYear()) {
      continue;
    }
    const day = date.getDate();
    const prev = entriesByDay.get(day) ?? [];
    prev.push({
      day,
      label: reg.event_name,
      status: reg.status,
    });
    prev.sort((a, b) => {
      // Registered should never be "behind" attended in the same day cell.
      if (a.status === b.status) return a.label.localeCompare(b.label);
      if (a.status === "registered") return -1;
      if (b.status === "registered") return 1;
      if (a.status === "attended") return -1;
      if (b.status === "attended") return 1;
      return 0;
    });
    entriesByDay.set(day, prev);
  }

  const cells: Array<number | null> = [];
  for (let i = 0; i < startWeekday; i += 1) cells.push(null);
  for (let d = 1; d <= daysInMonth; d += 1) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            Calendar View (Google Calendar Style Mock)
          </h2>
          <p className="text-sm text-muted-foreground">
            Upcoming events are blue, attended events are green.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
            Upcoming
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
            Attended
          </span>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-2 text-xs font-medium text-muted-foreground">
        {dayLabels.map((label) => (
          <div key={label} className="rounded-md px-2 py-1 text-center">
            {label}
          </div>
        ))}
      </div>

      <div className="mt-2 grid grid-cols-7 gap-2">
        {cells.map((day, idx) => {
          if (!day) {
            return <div key={`empty-${idx}`} className="min-h-[88px] rounded-lg bg-muted/40" />;
          }
          const entries = entriesByDay.get(day) ?? [];
          return (
            <div
              key={day}
              className="min-h-[88px] rounded-lg border border-border/60 bg-background p-2"
            >
              <div className="mb-1 text-xs font-semibold text-foreground">{day}</div>
              <div className="space-y-1">
                {entries.slice(0, 3).map((entry, entryIdx) => (
                  <div
                    key={`${day}-${entryIdx}-${entry.label}`}
                    className={`truncate rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      entry.status === "attended"
                        ? "bg-green-100 text-green-700"
                        : entry.status === "registered"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-muted text-muted-foreground"
                    }`}
                    title={entry.label}
                  >
                    {entry.label}
                  </div>
                ))}
                {entries.length > 3 && (
                  <div className="text-[10px] text-muted-foreground">+{entries.length - 3} more</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
