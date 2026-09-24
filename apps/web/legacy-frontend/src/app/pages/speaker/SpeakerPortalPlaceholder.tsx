/**
 * The Speaker Portal's one-screen placeholder (B26 T6b-1, L4/L6 option a).
 *
 * Routed only when `speaker_portal` is on (`speakerPortalRoutes`). The portal
 * itself — invitations, availability, contact preferences — is T6b-2 to T6b-4.
 */
export function SpeakerPortalPlaceholder() {
  return (
    <main className="mx-auto max-w-xl space-y-3 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Speaker Portal</h1>
      <p className="text-sm text-muted-foreground">
        Your account is set up. The pages where you will see your speaking invitations and keep
        your details up to date are not open yet. The person who invited you will let you know
        when they are.
      </p>
    </main>
  );
}
