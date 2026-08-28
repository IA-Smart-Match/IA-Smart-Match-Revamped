import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router";
import {
  Activity,
  BarChart3,
  BookOpen,
  Calendar,
  Clock,
  Mail,
  MapPin,
  MessageSquareHeart,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

import {
  emptyFeedbackStatsSummary,
  fetchCalendarAssignments,
  fetchCourses,
  fetchEvents,
  fetchFeedbackStats,
  fetchPipeline,
  initiateWorkflow,
  rankSpeakers,
  rankSpeakersForCourse,
  splitTags,
  type CalendarAssignmentSummary,
  type CppCourse,
  type CppEvent,
  type FeedbackStatsSummary,
  type PipelineRecord,
  type RankedMatch,
  type WorkflowResponse,
} from "@/lib/api";
import { MOCK_EVENTS, MOCK_RANKED_MATCHES } from "@/lib/mockData";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { FeedbackForm } from "@/components/FeedbackForm";
import { OutreachWorkflowModal } from "@/components/OutreachWorkflowModal";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/app/components/ui/dialog";

const factorLabels: Record<string, string> = {
  topic_relevance: "Topic Relevance",
  role_fit: "Role Fit",
  geographic_proximity: "Geographic Proximity",
  calendar_fit: "Calendar Fit",
  historical_conversion: "Historical Conversion",
  student_interest: "Student Interest",
  volunteer_fatigue: "Recovery Readiness",
};

const factorOrder = [
  "topic_relevance",
  "role_fit",
  "geographic_proximity",
  "calendar_fit",
  "historical_conversion",
  "student_interest",
  "volunteer_fatigue",
] as const;


const workloadWeights: Record<string, number> = {
  Matched: 1,
  Contacted: 2,
  Confirmed: 3,
  Attended: 4,
  "Member Inquiry": 5,
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function formatPercent(value: number) {
  return `${Math.round(clamp(value, 0, 100))}%`;
}

function normalizeName(value: string) {
  return value.trim().toLowerCase();
}

function recoveryState(score: number) {
  if (score >= 0.75) {
    return {
      label: "Rest Recommended",
      tone: "bg-rose-50 text-rose-700 border-rose-200",
    };
  }
  if (score >= 0.4) {
    return {
      label: "Needs Rest",
      tone: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  return {
    label: "Available",
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
}

function summarizeLoad(
  name: string,
  pipeline: PipelineRecord[],
  assignments: CalendarAssignmentSummary[],
) {
  const rows = pipeline.filter(
    (row) => normalizeName(row.speaker_name) === normalizeName(name),
  );
  const recoveryRows = assignments.filter(
    (assignment) => normalizeName(assignment.volunteer_name) === normalizeName(name),
  );

  const stageCounts = {
    Matched: 0,
    Contacted: 0,
    Confirmed: 0,
    Attended: 0,
    "Member Inquiry": 0,
  };

  let weightedLoad = 0;
  for (const row of rows) {
    stageCounts[row.stage as keyof typeof stageCounts] =
      (stageCounts[row.stage as keyof typeof stageCounts] ?? 0) + 1;
    weightedLoad += workloadWeights[row.stage] ?? 1;
  }

  const matchedCount = rows.length;
  const lateStageCount = stageCounts.Attended + stageCounts["Member Inquiry"];
  const backendFatigue =
    recoveryRows.length > 0
      ? recoveryRows.reduce((sum, row) => sum + row.volunteer_fatigue, 0) / recoveryRows.length
      : null;
  const fallbackFatigue = clamp(
    (10 + matchedCount * 7 + weightedLoad * 8 + lateStageCount * 10) / 100,
    0,
    1,
  );
  const volunteerFatigue = backendFatigue ?? fallbackFatigue;
  const fatigueScore = Math.round(volunteerFatigue * 100);
  const recovery =
    recoveryRows[0] ?? null;
  const avgMatchScore =
    matchedCount > 0
      ? rows.reduce((sum, row) => sum + Number(row.match_score || 0), 0) / matchedCount
      : 0;

  return {
    rows,
    recoveryRows,
    stageCounts,
    matchedCount,
    lateStageCount,
    volunteerFatigue,
    fatigueScore,
    avgMatchScore,
    recoveryStatus: recovery?.recovery_status ?? recoveryState(volunteerFatigue).label,
    recoveryLabel: recovery?.recovery_label ?? recoveryState(volunteerFatigue).label,
  };
}

function buildMatchReasoning(match: RankedMatch): string {
  const strongestFactors = Object.entries(match.factor_scores)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([key]) => factorLabels[key] || key);

  if (strongestFactors.length === 0) {
    return "This ranking is ready once factor data is available.";
  }

  return `${match.name} stands out on ${strongestFactors.join(" and ")} for ${match.event_name}.`;
}

function formatFactorName(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function ScoreRing({ score }: { score: number }) {
  const clamped = clamp(score, 0, 100);
  return (
    <div
      className="relative h-24 w-24 rounded-full"
      style={{
        background: `conic-gradient(#2563eb ${clamped * 3.6}deg, #dbeafe 0deg)`,
      }}
    >
      <div className="absolute inset-2 flex flex-col items-center justify-center rounded-full bg-white">
        <span className="text-2xl font-semibold text-blue-700">{Math.round(clamped)}%</span>
        <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
          match
        </span>
      </div>
    </div>
  );
}

function FactorRadar({ factors }: { factors: Record<string, number> }) {
  const ordered = factorOrder.map((key) => ({
    key,
    label: factorLabels[key],
    value: clamp((factors[key] ?? 0) * 100, 0, 100),
  }));

  const cx = 110;
  const cy = 110;
  const radius = 74;

  const rings = [0.25, 0.5, 0.75, 1];
  const points = ordered
    .map((factor, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ordered.length;
      const distance = radius * (factor.value / 100);
      return `${cx + Math.cos(angle) * distance},${cy + Math.sin(angle) * distance}`;
    })
    .join(" ");

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-slate-600">Comparative factor radar</p>
          <p className="text-lg font-semibold text-slate-900">Blue-only balance view</p>
        </div>
        <BarChart3 className="h-5 w-5 text-blue-600" />
      </div>

      <svg viewBox="0 0 220 220" className="h-[220px] w-full">
        {rings.map((ring) => (
          <polygon
            key={ring}
            points={ordered
              .map((_, index) => {
                const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ordered.length;
                return `${cx + Math.cos(angle) * radius * ring},${cy + Math.sin(angle) * radius * ring}`;
              })
              .join(" ")}
            fill="none"
            stroke="#dbeafe"
            strokeWidth="1"
          />
        ))}

        {ordered.map((factor, index) => {
          const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ordered.length;
          const x = cx + Math.cos(angle) * radius;
          const y = cy + Math.sin(angle) * radius;
          const labelX = cx + Math.cos(angle) * (radius + 18);
          const labelY = cy + Math.sin(angle) * (radius + 18);
          return (
            <g key={factor.key}>
              <line x1={cx} y1={cy} x2={x} y2={y} stroke="#bfdbfe" strokeWidth="1.25" />
              <circle cx={x} cy={y} r="2.5" fill="#93c5fd" />
              <text
                x={labelX}
                y={labelY}
                textAnchor={Math.abs(Math.cos(angle)) < 0.35 ? "middle" : Math.cos(angle) > 0 ? "start" : "end"}
                dominantBaseline="middle"
                className="fill-slate-600 text-[10px] font-medium"
              >
                {factor.label}
              </text>
            </g>
          );
        })}

        <polygon points={points} fill="rgba(37, 99, 235, 0.18)" stroke="#2563eb" strokeWidth="2.5" />
        {ordered.map((factor, index) => {
          const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ordered.length;
          const x = cx + Math.cos(angle) * radius * (factor.value / 100);
          const y = cy + Math.sin(angle) * radius * (factor.value / 100);
          return <circle key={factor.key} cx={x} cy={y} r="3.5" fill="#2563eb" />;
        })}
      </svg>

      <div className="mt-4 grid grid-cols-2 gap-2">
        {ordered.map((factor) => (
          <div key={factor.key} className="rounded-xl bg-white px-3 py-2 shadow-sm">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">{factor.label}</span>
              <span className="font-semibold text-slate-900">{formatPercent(factor.value)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


export function AIMatching() {
  const location = useLocation();
  const preselectedEventName = (location.state as { eventName?: string } | null)?.eventName ?? "";

  const [matchMode, setMatchMode] = useState<"events" | "courses">("events");
  const [events, setEvents] = useState<CppEvent[]>([]);
  const [courses, setCourses] = useState<CppCourse[]>([]);
  const [pipeline, setPipeline] = useState<PipelineRecord[]>([]);
  const [assignments, setAssignments] = useState<CalendarAssignmentSummary[]>([]);
  const [selectedEventName, setSelectedEventName] = useState(preselectedEventName);
  const [selectedCourseKey, setSelectedCourseKey] = useState("");
  const [matches, setMatches] = useState<RankedMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [ranking, setRanking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contextWarning, setContextWarning] = useState<string | null>(null);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [selectedVolunteer, setSelectedVolunteer] = useState<RankedMatch | null>(null);
  const [workflowResult, setWorkflowResult] = useState<WorkflowResponse | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsSummary>(
    emptyFeedbackStatsSummary(),
  );
  const [isMockData, setIsMockData] = useState(false);
  const [feedbackTarget, setFeedbackTarget] = useState<RankedMatch | null>(null);

  useEffect(() => {
    let active = true;

    fetchEvents()
      .then((result) => {
        if (!active) {
          return;
        }
        const data = result.data;
        setEvents(data);
        // Honour router state pre-selection from Opportunities page; fall back to first event only when no state was passed.
        const hasMatch = preselectedEventName && data.some((e) => e["Event / Program"] === preselectedEventName);
        if (!hasMatch) {
          setSelectedEventName(data[0]?.["Event / Program"] ?? "");
        }
        if (result.isMockData) {
          setIsMockData(true);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          // Backend unreachable — use Layer-3 mock constants
          setEvents(MOCK_EVENTS);
          if (!preselectedEventName) {
            setSelectedEventName(MOCK_EVENTS[0]?.["Event / Program"] ?? "");
          }
          setMatches(MOCK_RANKED_MATCHES);
          setIsMockData(true);
          setError(err instanceof Error ? err.message : "Failed to load events.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    fetchCourses()
      .then((data) => {
        if (active) {
          setCourses(data);
          if (data.length > 0 && !selectedCourseKey) {
            setSelectedCourseKey(data[0].course_key);
          }
        }
      })
      .catch(() => {
        // Courses unavailable — mode will show empty selector gracefully
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    fetchFeedbackStats()
      .then((result) => {
        if (active) {
          setFeedbackStats(result.data);
          if (result.isMockData) {
            setIsMockData(true);
          }
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setContextWarning(
            err instanceof Error
              ? `Feedback optimizer stats are unavailable: ${err.message}`
              : "Feedback optimizer stats are unavailable.",
          );
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    Promise.allSettled([fetchPipeline(), fetchCalendarAssignments()]).then((results) => {
      if (!active) {
        return;
      }

      const [pipelineResult, assignmentResult] = results;
      if (pipelineResult.status === "fulfilled") {
        setPipeline(pipelineResult.value.data);
        if (pipelineResult.value.isMockData) {
          setIsMockData(true);
        }
      } else {
        setContextWarning((current) =>
          current
            ? `${current} Pipeline context is unavailable: ${pipelineResult.reason instanceof Error ? pipelineResult.reason.message : "Request failed."}`
            : `Pipeline context is unavailable: ${pipelineResult.reason instanceof Error ? pipelineResult.reason.message : "Request failed."}`,
        );
      }

      if (assignmentResult.status === "fulfilled") {
        setAssignments(assignmentResult.value.data);
        if (assignmentResult.value.isMockData) {
          setIsMockData(true);
        }
      } else {
        setContextWarning((current) =>
          current
            ? `${current} Assignment overlays are unavailable: ${assignmentResult.reason instanceof Error ? assignmentResult.reason.message : "Request failed."}`
            : `Assignment overlays are unavailable: ${assignmentResult.reason instanceof Error ? assignmentResult.reason.message : "Request failed."}`,
        );
      }
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const targetKey = matchMode === "events" ? selectedEventName : selectedCourseKey;
    if (!targetKey) {
      return;
    }

    let active = true;
    setRanking(true);
    setError(null);
    setMatches([]);

    const weights =
      Object.keys(feedbackStats.current_weights).length > 0
        ? feedbackStats.current_weights
        : undefined;

    const rankPromise =
      matchMode === "events"
        ? rankSpeakers(selectedEventName, 5, weights)
        : rankSpeakersForCourse(selectedCourseKey, 5, weights);

    rankPromise
      .then((data) => {
        if (active) {
          setMatches(data);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to rank speakers.");
          if (matchMode === "events") {
            setMatches(isMockData ? MOCK_RANKED_MATCHES : []);
          }
        }
      })
      .finally(() => {
        if (active) {
          setRanking(false);
        }
      });

    return () => {
      active = false;
    };
  }, [matchMode, selectedEventName, selectedCourseKey, feedbackStats.current_weights]);

  const selectedEvent =
    events.find((event) => event["Event / Program"] === selectedEventName) ?? null;
  const selectedCourse =
    courses.find((course) => course.course_key === selectedCourseKey) ?? null;

  const openWorkflowModal = async (match: RankedMatch) => {
    if (!selectedEventName) {
      return;
    }

    setSelectedVolunteer(match);
    setShowWorkflowModal(true);
    setWorkflowLoading(true);
    setWorkflowError(null);
    setWorkflowResult(null);

    try {
      const result = await initiateWorkflow(match.name, selectedEventName);
      setWorkflowResult(result);
    } catch (err: unknown) {
      setWorkflowError(err instanceof Error ? err.message : "Workflow failed.");
    } finally {
      setWorkflowLoading(false);
    }
  };

  const topFiveContext = useMemo(
    () =>
      matches.map((match) => ({
        ...match,
        load: summarizeLoad(match.name, pipeline, assignments),
      })),
    [matches, pipeline, assignments],
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
          AI matching
        </p>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-3xl font-semibold text-slate-900">
            AI Matching Engine{isMockData && <DemoModeBadge />}
          </h1>
        </div>
        <p className="text-slate-600">
          {matchMode === "events"
            ? "Rank specialists against live CPP opportunities and review the top-five picture with score, factor, and fatigue context."
            : "Rank specialists as guest lecturers for CPP course sections, weighted by Guest Lecture Fit and topic alignment."}
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setMatchMode("events")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
            matchMode === "events"
              ? "bg-blue-600 text-white shadow-sm"
              : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Target className="h-4 w-4" />
          Events
        </button>
        <button
          onClick={() => setMatchMode("courses")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
            matchMode === "courses"
              ? "bg-blue-600 text-white shadow-sm"
              : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          <BookOpen className="h-4 w-4" />
          Courses
        </button>
      </div>

      {matchMode === "events" ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Select event</label>
          <select
            value={selectedEventName}
            onChange={(event) => setSelectedEventName(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            {events.map((event) => (
              <option key={event["Event / Program"]} value={event["Event / Program"]}>
                {event["Event / Program"]}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Select course</label>
          <select
            value={selectedCourseKey}
            onChange={(e) => setSelectedCourseKey(e.target.value)}
            className="w-full rounded-xl border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            {courses.map((course) => (
              <option key={course.course_key} value={course.course_key}>
                {course.display_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {matchMode === "events" && selectedEvent ? (
        <div className="rounded-3xl border border-blue-100 bg-gradient-to-r from-blue-50 via-white to-slate-50 p-6 shadow-sm">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                {selectedEvent["Event / Program"]}
              </h2>
              <p className="mt-1 max-w-3xl text-slate-700">
                {selectedEvent["Primary Audience"] || "Audience details not provided"}
              </p>
            </div>
            <span className="rounded-full bg-blue-600 px-3 py-1 text-sm font-medium text-white">
              Selected
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Target className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Host:</span>{" "}
                {selectedEvent["Host / Unit"] || "CPP partner"}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Calendar className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Cadence:</span>{" "}
                {selectedEvent["Recurrence (typical)"] || "TBD"}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <MapPin className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Contact:</span>{" "}
                {selectedEvent["Point(s) of Contact (published)"] || "Not listed"}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Users className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Role:</span>{" "}
                {splitTags(selectedEvent["Volunteer Roles (fit)"] || "")[0] || "Volunteer"}
              </span>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {[selectedEvent.Category, ...splitTags(selectedEvent["Volunteer Roles (fit)"] || "").slice(0, 3)]
              .filter(Boolean)
              .map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-blue-600 px-3 py-1 text-sm font-medium text-white"
                >
                  {tag}
                </span>
              ))}
          </div>
        </div>
      ) : matchMode === "courses" && selectedCourse ? (
        <div className="rounded-3xl border border-blue-100 bg-gradient-to-r from-blue-50 via-white to-slate-50 p-6 shadow-sm">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                {selectedCourse.display_name}
              </h2>
              <p className="mt-1 max-w-3xl text-slate-700">
                Instructor: {selectedCourse.Instructor}
              </p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-sm font-medium text-white ${
                selectedCourse["Guest Lecture Fit"] === "High"
                  ? "bg-emerald-600"
                  : selectedCourse["Guest Lecture Fit"] === "Medium"
                    ? "bg-amber-500"
                    : "bg-slate-500"
              }`}
            >
              {selectedCourse["Guest Lecture Fit"]} Fit
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Calendar className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Days:</span> {selectedCourse.Days}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Clock className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Time:</span>{" "}
                {selectedCourse["Start Time"]}–{selectedCourse["End Time"]}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <MapPin className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Mode:</span> {selectedCourse.Mode}
              </span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
              <Users className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-slate-700">
                <span className="font-medium">Cap:</span> {selectedCourse["Enrl Cap"]} students
              </span>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {["Guest Lecture", selectedCourse.Mode, `${selectedCourse["Enrl Cap"]} seats`]
              .filter(Boolean)
              .map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-blue-600 px-3 py-1 text-sm font-medium text-white"
                >
                  {tag}
                </span>
              ))}
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
          {error}
        </div>
      ) : null}

      {contextWarning ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {contextWarning}
        </div>
      ) : null}

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-blue-600" />
            <h2 className="text-xl font-semibold text-slate-900">Top Recommended Volunteers</h2>
          </div>
          <span className="text-sm text-slate-600">
            {ranking ? "Refreshing rankings..." : "Top-five contract active"}
          </span>
        </div>

        {loading || ranking ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-600 shadow-sm">
            Loading ranking results...
          </div>
        ) : topFiveContext.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-600 shadow-sm">
            No match results are available for the selected event yet.
          </div>
        ) : (
          <div className="space-y-6">
            {topFiveContext.map((volunteer) => {
              const scorePercent = clamp(volunteer.score * 100, 0, 100);
              const recoveryBadge = recoveryState(volunteer.load.volunteerFatigue);

              return (
                <div
                  key={`${volunteer.event_name}-${volunteer.name}`}
                  className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
                >
                  <div className="grid gap-6 lg:grid-cols-[1.12fr_0.88fr]">
                    <div>
                      <div className="flex items-start gap-4">
                        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-600 to-sky-500 text-xl font-semibold text-white">
                          {volunteer.name
                            .split(" ")
                            .map((part) => part[0])
                            .join("")
                            .slice(0, 3)}
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="rounded-full bg-blue-600 px-3 py-1 text-sm font-semibold text-white">
                                  #{volunteer.rank || 1}
                                </span>
                                <h3 className="text-xl font-semibold text-slate-900">
                                  {volunteer.name}
                                </h3>
                              </div>
                              <p className="mt-1 text-slate-600">
                                {volunteer.title || "IA West volunteer"} at{" "}
                                {volunteer.company || "IA West"}
                              </p>
                              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-slate-600">
                                <span className="inline-flex items-center gap-1">
                                  <MapPin className="h-4 w-4 text-blue-600" />
                                  {volunteer.metro_region || "Region not listed"}
                                </span>
                                <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                                  {splitTags(volunteer.expertise_tags)[0] ||
                                    volunteer.board_role ||
                                    "Specialist"}
                                </span>
                                <span
                                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${recoveryBadge.tone}`}
                                >
                                  <Activity className="mr-1 inline h-3.5 w-3.5" />
                                  {volunteer.load.recoveryLabel} load
                                </span>
                              </div>
                            </div>

                            <ScoreRing score={scorePercent} />
                          </div>

                          <div className="mt-4 rounded-2xl bg-slate-50 p-4">
                            <p className="text-sm text-slate-700 italic">
                              {buildMatchReasoning(volunteer)}
                            </p>
                          </div>

                          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                            <div className="rounded-2xl border border-slate-200 bg-white p-4">
                              <p className="text-xs uppercase tracking-wide text-slate-500">
                                Match depth
                              </p>
                              <p className="mt-1 text-2xl font-semibold text-slate-900">
                                {volunteer.load.matchedCount}
                              </p>
                            </div>
                            <div className="rounded-2xl border border-slate-200 bg-white p-4">
                              <p className="text-xs uppercase tracking-wide text-slate-500">
                                Fatigue index
                              </p>
                              <p className="mt-1 text-2xl font-semibold text-blue-700">
                                {formatPercent(volunteer.load.fatigueScore)}
                              </p>
                            </div>
                            <div className="rounded-2xl border border-slate-200 bg-white p-4">
                              <p className="text-xs uppercase tracking-wide text-slate-500">
                                Avg score
                              </p>
                              <p className="mt-1 text-2xl font-semibold text-slate-900">
                                {formatPercent(volunteer.load.avgMatchScore * 100)}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="mt-5 flex flex-wrap gap-2">
                        {[volunteer.board_role, ...splitTags(volunteer.expertise_tags).slice(0, 3)]
                          .filter(Boolean)
                          .map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700"
                            >
                              {tag}
                            </span>
                          ))}
                      </div>

                      <div className="mt-6 grid gap-3 sm:grid-cols-2">
                        <button
                          onClick={() => void openWorkflowModal(volunteer)}
                          disabled={workflowLoading}
                          className={`inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50`}
                        >
                          <Mail className="h-5 w-5" />
                          Initiate Outreach
                        </button>
                        <button
                          onClick={() => setFeedbackTarget(volunteer)}
                          className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 px-4 py-3 font-medium text-slate-700 transition hover:bg-slate-50"
                        >
                          <MessageSquareHeart className="h-5 w-5 text-blue-600" />
                          Record Feedback
                        </button>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <FactorRadar factors={volunteer.factor_scores} />

                      <div className="rounded-2xl border border-blue-100 bg-blue-50/70 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-blue-700">
                          Recovery summary
                        </p>
                        <p className="mt-1 text-sm font-semibold text-slate-900">
                          {volunteer.load.recoveryLabel}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {volunteer.load.recoveryRows.length
                            ? `${volunteer.load.recoveryRows.length} assignment overlay rows pulled from the backend contract.`
                            : "Recovery falls back to the live pipeline load until assignment overlays are available."}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-blue-100 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <MessageSquareHeart className="h-5 w-5 text-blue-600" />
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-700">
                Continuous improvement
              </p>
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-900">
              Feedback-informed ranking is active
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Current rankings use the latest effective weights from the feedback optimizer when data is available.
            </p>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">
            {feedbackStats.total_feedback} feedback rows
          </span>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Acceptance rate</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">
              {Math.round(feedbackStats.acceptance_rate * 100)}%
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {feedbackStats.accepted} accepted / {feedbackStats.declined} declined
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Pain score</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">
              {Math.round(feedbackStats.pain_score)}
            </p>
            <p className="mt-1 text-sm text-slate-600">Lower is healthier for the current matcher.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Membership signal</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">
              {Math.round(feedbackStats.membership_interest_rate * 100)}%
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {feedbackStats.membership_interest_count} feedback entries marked as interest.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Lead weight shift</p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {feedbackStats.recommended_adjustments[0]
                ? formatFactorName(feedbackStats.recommended_adjustments[0].factor)
                : "No shift yet"}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {feedbackStats.recommended_adjustments[0]
                ? `${feedbackStats.recommended_adjustments[0].delta > 0 ? "+" : ""}${(
                    feedbackStats.recommended_adjustments[0].delta * 100
                  ).toFixed(1)} pts`
                : "Needs more coordinator decisions."}
            </p>
          </div>
        </div>
      </div>

      {showWorkflowModal && selectedVolunteer ? (
        <OutreachWorkflowModal
          volunteer={selectedVolunteer}
          result={workflowResult}
          loading={workflowLoading}
          error={workflowError}
          onClose={() => setShowWorkflowModal(false)}
        />
      ) : null}

      <Dialog
        open={Boolean(feedbackTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setFeedbackTarget(null);
          }
        }}
      >
        {feedbackTarget ? (
          <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto border-0 bg-transparent p-0 shadow-none [&>button]:hidden">
            <DialogTitle className="sr-only">Capture Match Outcome</DialogTitle>
            <DialogDescription className="sr-only">
              Record what happened with this match so the weight optimizer can learn from it.
            </DialogDescription>
            <FeedbackForm
              eventName={selectedEventName}
              speakerName={feedbackTarget.name}
              matchScore={feedbackTarget.score}
              factorScores={feedbackTarget.factor_scores}
              weightsUsed={
                Object.keys(feedbackStats.current_weights).length > 0
                  ? feedbackStats.current_weights
                  : undefined
              }
              currentStats={feedbackStats}
              onSubmitted={(stats) => {
                setFeedbackStats(stats);
                setFeedbackTarget(null);
              }}
              onCancel={() => setFeedbackTarget(null)}
              title="Capture Match Outcome"
              description="Record what happened with this match so the weight optimizer can learn from it."
            />
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}
