import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { StudentLayout } from "./components/StudentLayout";
import { CoordinatorPortalLayout } from "./components/CoordinatorPortalLayout";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { Dashboard } from "./pages/Dashboard";
import { Opportunities } from "./pages/Opportunities";
import { Volunteers } from "./pages/Volunteers";
import { Pipeline } from "./pages/Pipeline";
import { Calendar } from "./pages/Calendar";
import { Outreach } from "./pages/Outreach";
import { AIMatching } from "./pages/AIMatching";
import { StudentHome } from "./pages/student/StudentHome";
import { StudentEvents } from "./pages/student/StudentEvents";
import { StudentHistory } from "./pages/student/StudentHistory";
import { StudentConnect } from "./pages/student/StudentConnect";
import { StudentRewards } from "./pages/student/StudentRewards";
import { CoordinatorHome } from "./pages/coordinator/CoordinatorHome";
import { CoordinatorEvents } from "./pages/coordinator/CoordinatorEvents";
import { CoordinatorOutreach } from "./pages/coordinator/CoordinatorOutreach";
import { CoordinatorMeetings } from "./pages/coordinator/CoordinatorMeetings";
import { VolunteerPortalLayout } from "./components/VolunteerPortalLayout";
import { VolunteerHome } from "./pages/volunteer/VolunteerHome";
import { VolunteerAssignments } from "./pages/volunteer/VolunteerAssignments";
import { VolunteerProfile } from "./pages/volunteer/VolunteerProfile";

export const router = createBrowserRouter([
  // Public routes (no sidebar)
  { path: "/", Component: LandingPage },
  { path: "/login", Component: LoginPage },

  // Student portal routes
  {
    path: "student-portal",
    Component: StudentLayout,
    children: [
      { index: true, Component: StudentHome },
      { path: "events", Component: StudentEvents },
      { path: "history", Component: StudentHistory },
      { path: "connect", Component: StudentConnect },
      { path: "rewards", Component: StudentRewards },
    ],
  },

  // Event coordinator portal routes
  {
    path: "coordinator-portal",
    Component: CoordinatorPortalLayout,
    children: [
      { index: true, Component: CoordinatorHome },
      { path: "events", Component: CoordinatorEvents },
      { path: "outreach", Component: CoordinatorOutreach },
      { path: "meetings", Component: CoordinatorMeetings },
    ],
  },

  // Volunteer portal routes
  {
    path: "volunteer-portal",
    Component: VolunteerPortalLayout,
    children: [
      { index: true, Component: VolunteerHome },
      { path: "assignments", Component: VolunteerAssignments },
      { path: "profile", Component: VolunteerProfile },
    ],
  },

  // IA Admin routes (with sidebar layout — pathless layout route)
  {
    Component: Layout,
    children: [
      { path: "dashboard", Component: Dashboard },
      { path: "opportunities", Component: Opportunities },
      { path: "volunteers", Component: Volunteers },
      { path: "ai-matching", Component: AIMatching },
      { path: "pipeline", Component: Pipeline },
      { path: "calendar", Component: Calendar },
      { path: "outreach", Component: Outreach },
    ],
  },
]);
