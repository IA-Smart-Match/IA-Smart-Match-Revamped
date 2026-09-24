/**
 * `/speaker-portal` page (B26 T6b-4). Skeleton: the heading and tab title;
 * the content lands with T6b-2's `/v1/me` adapters.
 */
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Invitations";

export function SpeakerInvitations() {
  useSpeakerPageTitle(HEADING);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>
    </div>
  );
}
