import {
  MOCK_CALENDAR_ASSIGNMENTS,
  MOCK_CALENDAR_EVENTS,
  MOCK_EVENTS,
  MOCK_FEEDBACK_STATS,
  MOCK_PIPELINE,
  MOCK_QR_STATS,
  MOCK_RANKED_MATCHES,
  MOCK_SPECIALISTS,
} from "./mockData";
import type {
  CalendarEventSummary,
  EventCoordinator,
  MeetingBooking,
  OutreachThread,
  RetentionNudge,
  StudentConnectionSuggestionsResponse,
  StudentProfile,
  StudentRegistration,
  VolunteerAssignment,
  VolunteerProfile,
} from "./api";

const LOCAL_SOURCE = "local";

export const localData = {
  specialists: MOCK_SPECIALISTS,
  events: MOCK_EVENTS,
  pipeline: MOCK_PIPELINE,
  calendarEvents: MOCK_CALENDAR_EVENTS,
  calendarAssignments: MOCK_CALENDAR_ASSIGNMENTS,
  qrStats: MOCK_QR_STATS,
  feedbackStats: MOCK_FEEDBACK_STATS,
};

export function localStudentProfile(studentId: string): StudentProfile & { source: string } {
  return {
    student_id: studentId,
    name: "Alex Rivera",
    email: "alex.rivera@cal.edu",
    school: "Cal Poly Pomona",
    major: "Computer Science",
    year: "Junior",
    interests: "Artificial intelligence, product design, startups",
    attendance_streak: 3,
    events_attended: 4,
    churn_risk: "low",
    membership_interest: true,
    suggested_connections: "Students and speakers working in AI, product, and entrepreneurship",
    source: LOCAL_SOURCE,
  };
}

export function localStudentRegistrations(studentId: string): {
  data: StudentRegistration[];
  total: number;
  source: string;
} {
  const data: StudentRegistration[] = [
    {
      registration_id: "reg-001",
      student_id: studentId,
      event_id: "evt-001",
      event_name: "AI for a Better Future Hackathon",
      registered_at: "2026-03-01T10:00:00Z",
      event_date: "2026-04-15",
      status: "registered",
      check_in_time: null,
      check_out_time: null,
      source: LOCAL_SOURCE,
    },
    {
      registration_id: "reg-002",
      student_id: studentId,
      event_id: "evt-004",
      event_name: "IA West Annual Summit",
      registered_at: "2026-01-12T10:00:00Z",
      event_date: "2026-07-20",
      status: "attended",
      check_in_time: "2026-07-20T08:55:00Z",
      check_out_time: "2026-07-20T15:30:00Z",
      source: LOCAL_SOURCE,
    },
  ];
  return { data, total: data.length, source: LOCAL_SOURCE };
}

export function localStudentRecommendations(studentId: string): {
  recommendations: Array<CalendarEventSummary & { is_recommended: boolean }>;
  source: string;
} {
  void studentId;
  return {
    recommendations: localData.calendarEvents.map((event, index) => ({
      ...event,
      is_recommended: index < 3,
    })),
    source: LOCAL_SOURCE,
  };
}

export function localStudentNudge(studentId: string): RetentionNudge & { source: string } {
  return {
    student_id: studentId,
    nudge_type: "next_event",
    message: "The next university event is a strong fit for your interests. Save your spot today.",
    event_id: "evt-001",
    cta_label: "View event",
    points_earned: 120,
    source: LOCAL_SOURCE,
  };
}

export function localStudentConnections(studentId: string): StudentConnectionSuggestionsResponse {
  return {
    student_id: studentId,
    attended_past_events: [{ event_id: "evt-004", event_name: "IA West Annual Summit" }],
    suggestions: [
      {
        peer_student_id: "stu-002",
        name: "Maya Thompson",
        school: "Cal Poly Pomona",
        major: "Business Analytics",
        interests: "Product analytics, community building, and AI",
        shared_events: [{ event_id: "evt-004", event_name: "IA West Annual Summit" }],
        shared_event_count: 1,
      },
      {
        peer_student_id: "stu-003",
        name: "Jordan Kim",
        school: "UC Irvine",
        major: "Informatics",
        interests: "UX research, data visualization, and education",
        shared_events: [{ event_id: "evt-004", event_name: "IA West Annual Summit" }],
        shared_event_count: 1,
      },
    ],
    total: 2,
    source: LOCAL_SOURCE,
  };
}

export function localCoordinatorProfile(coordinatorId: string): EventCoordinator & { source: string } {
  return {
    coordinator_id: coordinatorId,
    name: "Jordan Lee",
    email: "jordan.lee@cpp.edu",
    school: "Cal Poly Pomona",
    department: "Career Services",
    hosted_events: "Technology, entrepreneurship, and career development programs",
    contact_status: "active",
    last_contact_date: "2026-03-18",
    meeting_availability: "Tuesday and Thursday afternoons",
    source: LOCAL_SOURCE,
  };
}

export function localCoordinatorEvents(): {
  data: Array<CalendarEventSummary & { staffing_open: boolean }>;
  total: number;
  source: string;
} {
  const data = localData.calendarEvents.map((event) => ({
    ...event,
    staffing_open: event.open_slots > 0,
  }));
  return { data, total: data.length, source: LOCAL_SOURCE };
}

export function localCoordinatorThreads(coordinatorId: string): { data: OutreachThread[]; total: number; source: string } {
  const data: OutreachThread[] = [
    {
      thread_id: "thread-001",
      coordinator_id: coordinatorId,
      event_id: "evt-001",
      ia_contact: "Priya Nair",
      subject: "Mentor coverage for the April hackathon",
      status: "awaiting_response",
      last_message_at: "2026-03-24T16:00:00Z",
      message_count: 3,
      next_action: "Follow up with the proposed speaker list",
      source: LOCAL_SOURCE,
    },
    {
      thread_id: "thread-002",
      coordinator_id: coordinatorId,
      event_id: "evt-002",
      ia_contact: "Marcus Webb",
      subject: "ITC Conference panel planning",
      status: "confirmed",
      last_message_at: "2026-03-22T11:00:00Z",
      message_count: 6,
      next_action: "Share the final run of show",
      source: LOCAL_SOURCE,
    },
  ];
  return { data, total: data.length, source: LOCAL_SOURCE };
}

export function localCoordinatorMeetings(coordinatorId: string): { data: MeetingBooking[]; total: number; source: string } {
  const data: MeetingBooking[] = [
    {
      booking_id: "meeting-001",
      thread_id: "thread-002",
      coordinator_id: coordinatorId,
      ia_contact: "Marcus Webb",
      event_id: "evt-002",
      title: "ITC Conference panel planning",
      scheduled_at: "2026-04-02T15:00:00Z",
      duration_minutes: 30,
      status: "confirmed",
      meeting_link: "https://meet.google.com/ia-west-planning",
      notes: "Review panel format and speaker availability.",
      source: LOCAL_SOURCE,
    },
  ];
  return { data, total: data.length, source: LOCAL_SOURCE };
}

export function localVolunteerProfile(volunteerId: string): VolunteerProfile & { source: string } {
  return {
    volunteer_id: volunteerId,
    name: "Shana DeMarinis",
    title: "Director of Product Strategy",
    company: "Brightline Labs",
    board_role: "Industry Advisor",
    metro_region: "Los Angeles - West",
    expertise_tags: "Product strategy, research, innovation, mentoring",
    initials: "SD",
    recovery_status: "Available",
    recovery_label: "Available for a new engagement",
    volunteer_fatigue: 0.22,
    source: LOCAL_SOURCE,
  };
}

export function localVolunteerAssignments(): { data: VolunteerAssignment[]; total: number; source: string } {
  const data: VolunteerAssignment[] = [
    {
      assignment_id: "asgn-v-001",
      event_id: "evt-001",
      event_name: "AI for a Better Future Hackathon",
      event_date: "2026-04-15",
      region: "Los Angeles - West",
      stage: "Confirmed",
      match_score: 0.88,
      volunteer_fatigue: 0.22,
      recovery_status: "Available",
      recovery_label: "Available",
      coverage_status: "covered",
    },
    {
      assignment_id: "asgn-v-002",
      event_id: "evt-004",
      event_name: "IA West Annual Summit",
      event_date: "2026-07-20",
      region: "Los Angeles - Central",
      stage: "Attended",
      match_score: 0.81,
      volunteer_fatigue: 0.22,
      recovery_status: "Available",
      recovery_label: "Available",
      coverage_status: "covered",
    },
  ];
  return { data, total: data.length, source: LOCAL_SOURCE };
}

export function localCrawlerResults() {
  return { events: [], count: 0, source: LOCAL_SOURCE };
}

export function localCrawlerStatus() {
  return { state: "idle" as const, started_at: null, finished_at: null, error: null, visited_count: 0, visited_urls: [] };
}

export const localRankedMatches = MOCK_RANKED_MATCHES;
