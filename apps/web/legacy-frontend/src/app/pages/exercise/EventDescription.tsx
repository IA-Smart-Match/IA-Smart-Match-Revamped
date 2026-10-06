/**
 * An event's short description, as the data file wrote it (#318).
 *
 * Ann, 2026-10-02: "Show a short description at the top of the Northline and
 * Harbor pages, above the sliders, and next to each event on the instructor
 * page. The text is in the new event_description column of the attached Excel
 * file. Take it from the file, so I can change it later by uploading a new
 * file."
 *
 * Three rules, all hers:
 *
 * - **The text is the file's.** It arrives on the server's response and is
 *   printed as it is. No description is written in the frontend, so uploading
 *   a new file and moving the teams to it is the whole of changing one.
 * - **No description, nothing shown.** The ten past events have none, and
 *   neither does any file from before that date; there is no placeholder.
 * - **Readable on the projector**: "no smaller than the list text" (checklist
 *   §3a). The ranked list sets its names in `ce-type-body`, and so does this.
 */
import * as React from "react";

import { cn } from "../../components/ui/utils";

export function EventDescription({
  text,
  id,
  className,
}: {
  /** The server's `description`; `null` when the data file gives none. */
  readonly text: string | null | undefined;
  /** Lets a card point at the paragraph with `aria-describedby`. */
  readonly id?: string;
  readonly className?: string;
}): React.JSX.Element | null {
  if (!hasDescription(text)) {
    return null;
  }
  return (
    <p
      id={id}
      data-slot="exercise-event-description"
      className={cn("ce-type-body ce-measure break-words whitespace-pre-line text-ce-ink", className)}
    >
      {text}
    </p>
  );
}

/** Whether there is anything to show: not absent, and not only spaces. */
export function hasDescription(text: string | null | undefined): text is string {
  return typeof text === "string" && text.trim() !== "";
}
