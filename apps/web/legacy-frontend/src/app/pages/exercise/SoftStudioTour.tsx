import * as React from "react";

const STORAGE_KEY = "smartmatch-exercise-tour-v1";

const TOUR_STEPS = [
  ["Team", "Pick your team's number so your work stays together."],
  ["Event", "Start with Round 1, Northline. Round 2, Harbor, opens after your Round 1 results."],
  ["Your list", "Move the four slider numbers and see who your list picks."],
  ["Results", "Use your one results run after your instructor opens results."],
  ["Ask for more", "In Round 2, your team picks how CBACH asks students to fill in their card."],
  ["Try it together", "Use the status line to keep your whole team in sync."],
  ["You're ready", "Replay this tour any time from the Tour button."],
] as const;

function canUseStorage(): boolean {
  try {
    return typeof window !== "undefined" && window.localStorage !== undefined;
  } catch {
    return false;
  }
}

export function SoftStudioTour(): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState(0);
  const [dontShow, setDontShow] = React.useState(false);
  const launcher = React.useRef<HTMLButtonElement>(null);
  const dialog = React.useRef<HTMLDivElement>(null);
  const title = React.useRef<HTMLHeadingElement>(null);

  const close = React.useCallback(() => {
    setOpen(false);
    if (canUseStorage() && dontShow) window.localStorage.setItem(STORAGE_KEY, "hidden");
    requestAnimationFrame(() => launcher.current?.focus());
  }, [dontShow]);

  const openTour = React.useCallback(() => {
    setStep(0);
    setOpen(true);
  }, []);

  React.useEffect(() => {
    if (import.meta.env.MODE === "test" || !canUseStorage()) return;
    if (window.localStorage.getItem(STORAGE_KEY) === null) {
      const timer = window.setTimeout(() => setOpen(true), 700);
      return () => window.clearTimeout(timer);
    }
  }, []);

  React.useEffect(() => {
    if (!open) return;
    title.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setStep((value) => Math.min(TOUR_STEPS.length - 1, value + 1));
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setStep((value) => Math.max(0, value - 1));
      } else if (event.key === "Tab" && dialog.current) {
        const focusable = dialog.current.querySelectorAll<HTMLElement>(
          'button, input[type="checkbox"]',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [close, open]);

  const [label, copy] = TOUR_STEPS[step];
  return (
    <>
      <button
        ref={launcher}
        type="button"
        className="soft-studio-tour-launcher"
        onClick={openTour}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Replay the exercise tour"
      >
        <img src="/exercise/mascot/face5-calm.webp" alt="" aria-hidden="true" />
        <span>Tour</span>
      </button>
      {open ? (
        <div className="soft-studio-tour-scrim" data-tour-layer>
          <div
            ref={dialog}
            className="soft-studio-tour-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="soft-studio-tour-title"
          >
            <img
              className="soft-studio-tour-mascot"
              src="/exercise/mascot/pose1-guide.webp"
              alt=""
              aria-hidden="true"
            />
            <div className="soft-studio-tour-copy">
              <p className="soft-studio-tour-count">{step + 1} of {TOUR_STEPS.length}</p>
              <h2 id="soft-studio-tour-title" ref={title} tabIndex={-1}>{label}</h2>
              <p aria-live="polite">{copy}</p>
              <div className="soft-studio-tour-dots" aria-label="Tour progress">
                {TOUR_STEPS.map((item, index) => (
                  <span key={item[0]} className={index === step ? "is-current" : index < step ? "is-done" : ""} />
                ))}
              </div>
              <label className="soft-studio-tour-check">
                <input type="checkbox" checked={dontShow} onChange={(event) => setDontShow(event.target.checked)} />
                Don't show this again
              </label>
              <div className="soft-studio-tour-actions">
                <button type="button" className="soft-studio-button soft-studio-button--quiet" onClick={close}>Skip</button>
                <button
                  type="button"
                  className="soft-studio-button soft-studio-button--primary"
                  onClick={() => (step === TOUR_STEPS.length - 1 ? close() : setStep((value) => value + 1))}
                >
                  {step === TOUR_STEPS.length - 1 ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
