import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { CalendarDays, UserCircle } from "lucide-react";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "../../hooks/useAuthorizedUnit";
import { fetchMySpeakerEngagements, fetchMySpeakerProfile } from "../../../lib/api";

export function VolunteerHome() {
  const unitId = useAuthorizedUnitId("volunteer"); const principalKey = usePrincipalKey();
  const profile = useQuery({ queryKey: [principalKey, "speaker-portal", unitId, "profile"], queryFn: () => fetchMySpeakerProfile(unitId!), enabled: Boolean(principalKey && unitId) });
  const engagements = useQuery({ queryKey: [principalKey, "speaker-portal", unitId, "engagements"], queryFn: () => fetchMySpeakerEngagements(unitId!), enabled: Boolean(principalKey && unitId) });
  if (profile.isLoading || engagements.isLoading) return <div className="h-48 animate-pulse rounded-2xl bg-muted" />;
  if (profile.error || engagements.error) return <section className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8"><h1 className="text-3xl font-semibold">Speaker home</h1><p role="alert" className="mt-2 text-destructive">Your Speaker information could not be loaded. Check that this account is linked to an active speaker profile.</p></section>;
  return <div className="space-y-6"><header><h1 className="text-3xl font-semibold">Welcome, {profile.data?.name}</h1><p className="mt-2 text-muted-foreground">Review upcoming engagements and the profile Event Hosts use when preparing for your visit.</p></header><div className="grid gap-4 md:grid-cols-2"><Link to="/volunteer-portal/assignments" className="rounded-2xl border bg-card p-6 shadow-sm transition hover:border-primary"><CalendarDays className="h-6 w-6 text-primary" /><h2 className="mt-4 text-xl font-semibold">Engagements</h2><p className="mt-2 text-sm text-muted-foreground">{engagements.data?.length ? `${engagements.data.length} event${engagements.data.length === 1 ? "" : "s"} in your current history.` : "No events have been handed to you yet."}</p></Link><Link to="/volunteer-portal/profile" className="rounded-2xl border bg-card p-6 shadow-sm transition hover:border-primary"><UserCircle className="h-6 w-6 text-primary" /><h2 className="mt-4 text-xl font-semibold">Your profile</h2><p className="mt-2 text-sm text-muted-foreground">{profile.data?.expertise_topics.length ? profile.data.expertise_topics.join(", ") : "Review the expertise and regions on file."}</p></Link></div></div>;
}
