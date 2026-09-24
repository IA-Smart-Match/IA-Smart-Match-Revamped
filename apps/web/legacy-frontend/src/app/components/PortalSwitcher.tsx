/**
 * The portal switcher (B26 T6b-5 §6.1): one login, two roles.
 *
 * A login that holds both the Event Host and the Speaker role is granted two
 * portals by `GET /v1/me/portals`. This lists them, so the person can move
 * between the two shells without signing out. It renders **nothing** unless
 * the mapping is ready and lists two or more portals.
 *
 * - **Disclosure navigation, not `role="menu"`.** The items are page links; a
 *   menu role would promise arrow-key roving focus they do not need. The
 *   native button toggles with Enter or Space, Tab moves through the links,
 *   Escape closes and returns focus to the button, and focus leaving the
 *   switcher or a pointer-down outside it closes it.
 * - **The server's words.** Each link is the grant's own `display_name` and
 *   points at its own `home_path`, in the server's order. `aria-current="true"`
 *   (not `"page"`) marks the portal this shell is: the link targets that
 *   portal's home, and the person may be on a sub-page.
 * - **Grants nothing, asks nothing.** No request is made on open or select;
 *   choosing a link only remembers the portal id (`lib/portalChoice.ts`) so
 *   `/` lands there next time. Every `/v1` route still authorizes server-side.
 */
import { useEffect, useId, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { ArrowLeftRight } from "lucide-react";

import { rememberPortal } from "@/lib/portalChoice";
import type { PortalKind } from "@/lib/principal";

import { usePortalAccess } from "../hooks/usePortalAccess";

export type PortalSwitcherPlacement = "sidebar" | "header";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar";

export function PortalSwitcher({
  current,
  placement,
}: {
  current: PortalKind;
  placement: PortalSwitcherPlacement;
}) {
  const access = usePortalAccess();
  const [open, setOpen] = useState(false);
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      const root = rootRef.current;
      if (root !== null && event.target instanceof Node && !root.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  if (access.status !== "ready" || access.mapping.portals.length < 2) {
    return null;
  }
  const portals = access.mapping.portals;

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Escape" || !open) return;
    // Handled here, so a shell's own Escape handler (its drawer) is not also run.
    event.stopPropagation();
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onBlur(event: FocusEvent<HTMLDivElement>): void {
    const next = event.relatedTarget;
    if (next instanceof Node && event.currentTarget.contains(next)) return;
    setOpen(false);
  }

  const header = placement === "header";

  return (
    <div
      ref={rootRef}
      className={header ? "relative" : "mb-2"}
      onKeyDown={onKeyDown}
      onBlur={onBlur}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
        className={
          header
            ? `inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent ${FOCUS_RING}`
            : `flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-sidebar-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-sidebar-accent hover:text-sidebar-accent-foreground ${FOCUS_RING}`
        }
      >
        <ArrowLeftRight className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className={header ? "sr-only" : "min-w-0"}>Switch portal</span>
      </button>
      <ul
        id={listId}
        hidden={!open}
        className={
          header
            ? "absolute right-0 top-full z-40 mt-2 w-60 space-y-1 rounded-xl border border-sidebar-border bg-sidebar p-2 shadow-lg"
            : "mt-1 space-y-1"
        }
      >
        {portals.map((portal) => {
          const isCurrent = portal.portal === current;
          return (
            <li key={portal.portal}>
              <Link
                to={portal.home_path}
                aria-current={isCurrent ? "true" : undefined}
                onClick={() => {
                  rememberPortal(portal.portal);
                  setOpen(false);
                }}
                className={`flex min-h-11 items-center rounded-xl px-3 py-2 text-sm transition-colors duration-150 motion-reduce:transition-none ${FOCUS_RING} ${
                  isCurrent
                    ? "border border-primary/30 bg-primary/10 font-medium text-primary"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                }`}
              >
                <span className="min-w-0 truncate">{portal.display_name}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
