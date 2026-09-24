/**
 * The page-level notice for the three read failures no retry can change
 * (B26 T6b-4 §5): not linked (404 `speaker_profile_not_linked`), denied (any
 * 403) and signed out (401). It replaces the page's content, never sits beside
 * it, and says nothing that would imply a record exists.
 *
 * `role="alert"` because it arrives in place of content the reader asked for.
 */
import { AlertCircle } from "lucide-react";
import { Link } from "react-router";

import {
  DENIED_MESSAGE,
  NOT_LINKED_MESSAGE,
  SIGNED_OUT_MESSAGE,
  type SelfNoticeKind,
} from "./speakerPortalErrors";

const MESSAGE: Record<SelfNoticeKind, string> = {
  not_linked: NOT_LINKED_MESSAGE,
  denied: DENIED_MESSAGE,
  signed_out: SIGNED_OUT_MESSAGE,
};

export function SpeakerSelfNotice({ kind }: { kind: SelfNoticeKind }) {
  return (
    <div role="alert" className="rounded-xl border border-border/70 bg-card p-4 text-sm">
      <p className="flex items-start gap-2 text-foreground">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span>{MESSAGE[kind]}</span>
      </p>
      {kind === "signed_out" ? (
        <Link
          to="/login"
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-border/70 px-4 py-2 font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Go to sign-in
        </Link>
      ) : null}
    </div>
  );
}
