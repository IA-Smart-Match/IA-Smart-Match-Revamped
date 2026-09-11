import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { CalendarDays, MessageSquare } from "lucide-react";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "../../hooks/useAuthorizedUnit";
import { fetchStudentAgenda, fetchStudentEvents } from "../../../lib/api";

export function StudentHome() {
  const unitId = useAuthorizedUnitId("student"); const principalKey = usePrincipalKey();
  const events = useQuery({ queryKey: [principalKey, "student-events", unitId], queryFn: () => fetchStudentEvents(unitId!), enabled: Boolean(principalKey && unitId) });
  const agenda = useQuery({ queryKey: [principalKey, "student-agenda", unitId], queryFn: () => fetchStudentAgenda(unitId!), enabled: Boolean(principalKey && unitId) });
  if (events.isLoading || agenda.isLoading) return <div className="h-44 animate-pulse rounded-2xl bg-muted" />;
  if (events.error || agenda.error) return <section className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8"><h1 className="text-3xl font-semibold">Student home</h1><p role="alert" className="mt-2 text-destructive">Events could not be loaded. Check the API connection and try again.</p></section>;
  return <div className="space-y-6"><header><h1 className="text-3xl font-semibold">Student home</h1><p className="mt-2 text-muted-foreground">Find upcoming events, keep your registrations together, and share feedback after attending.</p></header><div className="grid gap-4 md:grid-cols-2"><Link to="/student-portal/events" className="rounded-2xl border bg-card p-6 shadow-sm transition hover:border-primary"><CalendarDays className="h-6 w-6 text-primary" /><h2 className="mt-4 text-xl font-semibold">Events</h2><p className="mt-2 text-sm text-muted-foreground">{events.data?.events.length ? `${events.data.events.length} published event${events.data.events.length === 1 ? "" : "s"} available. ${agenda.data?.events.length ?? 0} on your agenda.` : "No published events are available yet."}</p></Link><Link to="/student-portal/speaker-feedback" className="rounded-2xl border bg-card p-6 shadow-sm transition hover:border-primary"><MessageSquare className="h-6 w-6 text-primary" /><h2 className="mt-4 text-xl font-semibold">Speaker feedback</h2><p className="mt-2 text-sm text-muted-foreground">Review feedback you have submitted for speakers at attended events.</p></Link></div></div>;
}
