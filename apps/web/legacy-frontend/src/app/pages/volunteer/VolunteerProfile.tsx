import { useQuery } from "@tanstack/react-query";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "../../hooks/useAuthorizedUnit";
import { fetchMySpeakerProfile } from "../../../lib/api";

export function VolunteerProfile() {
  const unitId = useAuthorizedUnitId("volunteer"); const principalKey = usePrincipalKey();
  const query = useQuery({ queryKey: [principalKey, "speaker-portal", unitId, "profile"], queryFn: () => fetchMySpeakerProfile(unitId!), enabled: Boolean(principalKey && unitId) });
  if (query.isLoading) return <div className="h-48 animate-pulse rounded-2xl bg-muted" />;
  if (query.error) return <section className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8"><h1 className="text-3xl font-semibold">Profile</h1><p role="alert" className="mt-2 text-destructive">{query.error instanceof Error ? query.error.message : "Your profile could not be loaded."}</p></section>;
  const profile = query.data;
  if (!profile) return null;
  return <div className="space-y-6"><header><h1 className="text-3xl font-semibold">Profile</h1><p className="mt-2 text-muted-foreground">The information the Speaker Connector has shared for your engagements.</p></header><section className="rounded-2xl border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-2xl font-semibold">{profile.name}</h2><p className="mt-1 text-muted-foreground">{[profile.title, profile.company].filter(Boolean).join(" · ") || "Professional details not provided"}</p></div><span className="rounded-full bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">{profile.available ? "Available" : "Availability paused"}</span></div><dl className="mt-6 grid gap-5 sm:grid-cols-2"><div><dt className="text-sm font-semibold">Expertise</dt><dd className="mt-1 text-sm text-muted-foreground">{profile.expertise_topics.length ? profile.expertise_topics.join(", ") : "No topics listed"}</dd></div><div><dt className="text-sm font-semibold">Service regions</dt><dd className="mt-1 text-sm text-muted-foreground">{profile.service_regions.length ? profile.service_regions.join(", ") : profile.home_region ?? "No regions listed"}</dd></div><div><dt className="text-sm font-semibold">Email</dt><dd className="mt-1 text-sm text-muted-foreground">{profile.contact_email ?? "Not provided"}</dd></div><div><dt className="text-sm font-semibold">Phone</dt><dd className="mt-1 text-sm text-muted-foreground">{profile.contact_phone ?? "Not provided"}</dd></div></dl></section></div>;
}
