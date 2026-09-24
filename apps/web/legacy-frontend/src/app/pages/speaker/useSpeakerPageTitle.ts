/**
 * Names the browser tab after the page (B26 T6b-4 §2.4, WCAG 2.4.2).
 *
 * The title is the page's own `h1` constant, never a server value, so it is
 * right while data loads and in every read-failure state. Leaving the page
 * restores the title it found, so another shell never inherits a Speaker one.
 */
import { useEffect } from "react";

const PORTAL_NAME = "Speaker Portal";

export function useSpeakerPageTitle(h1Text: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = `${h1Text} · ${PORTAL_NAME}`;
    return () => {
      document.title = previous;
    };
  }, [h1Text]);
}
