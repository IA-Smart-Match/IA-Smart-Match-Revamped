/**
 * The entry screen: a team number, and nothing else.
 *
 * Requirements, "Getting in" row: *"No login. A public web address. … a team
 * enters its team number (1-6) so its saved runs are labeled."* That is the
 * whole of the input. There is no password, no name, no email and no account,
 * because ADR-0025 D1 gives this scope no login at all — a team *is* its
 * number, and entering a number another team has already entered opens that
 * team's workspace, which is the point.
 *
 * The numbers come from `GET /v1/exercise` (`team_numbers`) rather than being
 * written here. The requirements fix them at 1-6 and that route reports them
 * as a constant of the scope, so there is one place they live.
 *
 * **An older data file's label is not a bug.** PR #186's owner ruling of
 * 2026-09-19: a team's entry no longer lands on the newest upload — an
 * existing workspace wins, and only an instructor re-point moves a team. So
 * after the instructor uploads a file, this screen may legitimately show the
 * previous file's label. Nothing here warns about that, deliberately.
 *
 * **The license line is a constant of the exercise, not of a data file.**
 * OQ-CE-09 closed 2026-09-25 (Ann Wang, email reply to the team's question
 * list): {@link EXERCISE_LICENSE_LINE}. It is
 * rendered here, in every state of the screen — loading, refused, unreachable
 * and ready — because this is the opening screen and no team has picked a
 * workspace yet, so no data file is in play. It is not read from
 * `DatasetView.license_line`: that column is per upload, the ingest never
 * fills it, and a team that has not entered a number has no dataset to read
 * it from.
 */
import * as React from "react";
import { useNavigate } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  enterTeamWorkspace,
  readCurrentWorkspace,
  readScopeFacts,
  type ExerciseScopeFacts,
  type TeamWorkspaceView,
} from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { Button, Skeleton, SkeletonRegion } from "./desk";
import { LectureHallArt, TeamBadgeArt } from "./ExerciseEntryArt";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { clearWorkspacePointer, readWorkspacePointer, writeWorkspacePointer } from "./workspacePointer";

/**
 * The opening screen's license line (OQ-CE-09, closed 2026-09-25). Ann's two
 * sentences, verbatim.
 */
export const EXERCISE_LICENSE_LINE =
  "For California State Polytechnic University, Pomona — College of Business Administration instructional use only. All student profiles are fictional.";

/** The room's question and the brief, as the opening title (DESIGN.md §7.1, §11.1). */
export const OPENING_TITLE = "Who should we invite?";
export const OPENING_LEAD =
  "Your team is promoting a campus career event with 60 seats. Choose whom to invite, see what happened, then try again.";

/** Where a team goes once it is in. */
export const EVENT_PICKER_PATH = "/exercise/events";

interface EntryData {
  readonly facts: ExerciseScopeFacts;
  /** `null` when this browser has not entered a number yet. */
  readonly workspace: TeamWorkspaceView | null;
}

/**
 * The scope's facts, plus whichever workspace the cookie points at.
 *
 * A browser that has not entered a number is refused with
 * `exercise_workspace_required`, and that refusal is the *ordinary first
 * visit* rather than a failure — so it is caught here and turned into
 * `workspace: null`. Every other refusal is left to propagate and is shown as
 * the sentence it is.
 */
async function loadEntry(signal: AbortSignal): Promise<EntryData> {
  const facts = await readScopeFacts(signal);
  try {
    return { facts, workspace: await readCurrentWorkspace(signal) };
  } catch (error) {
    if (isRefusal(error) && error.code === "exercise_workspace_required") {
      clearWorkspacePointer();
      return { facts, workspace: null };
    }
    throw error;
  }
}

/** The sentence under "Which team are you?"; also why the open button waits. */
const TEAM_HELPER = "Pick your team's number. Your team's saved work is kept under that number.";
const TEAM_HELPER_ID = "exercise-team-helper";
const TEAM_HEADING_ID = "exercise-team-heading";

/**
 * The opening screen (DESIGN.md §7.1) above the team entry (§7.2).
 *
 * Top zone: the room's question as the one `h1`, the brief as the lead, then
 * the license line in a quiet sunk card beside the lecture-hall shape (the
 * shape is desktop only). Lower zone: "Which team are you?", the tiles, and
 * the one primary button. The license card sits outside the state switch, so
 * it shows while loading, refused, unreachable and ready alike.
 */
export function ExerciseEntry(): React.JSX.Element {
  const { state, reload } = useExerciseResource(loadEntry, []);

  return (
    <ExerciseScreen title={OPENING_TITLE} intro={OPENING_LEAD}>
      <div className="ce-grid items-center gap-y-ce-5">
        <p
          className="ce-type-body col-span-4 rounded-ce-card bg-ce-surface-sunk p-ce-4 text-ce-ink md:col-span-8 md:p-ce-5 lg:col-span-7"
          data-slot="exercise-license-line"
        >
          {EXERCISE_LICENSE_LINE}
        </p>
        <div className="hidden justify-center lg:col-span-5 lg:flex">
          <LectureHallArt className="h-auto w-[160px] text-ce-primary" />
        </div>
      </div>

      <section
        aria-labelledby={TEAM_HEADING_ID}
        className="mt-ce-2 flex flex-col gap-ce-5 border-t border-ce-line pt-ce-6 md:mt-ce-4 md:pt-ce-7"
      >
        <div className="flex flex-col gap-ce-2">
          <h2 id={TEAM_HEADING_ID} className="ce-type-h2 text-ce-ink">
            Which team are you?
          </h2>
          <p id={TEAM_HELPER_ID} className="ce-type-body ce-measure text-ce-ink-muted">
            {TEAM_HELPER}
          </p>
        </div>
        {state.status === "loading" ? <TileSkeletons /> : null}
        {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
        {state.status === "unreachable" ? (
          <ExerciseNotice message={state.message} tone="problem">
            <Button variant="secondary" onClick={reload}>
              Try again
            </Button>
          </ExerciseNotice>
        ) : null}
        {state.status === "ready" ? <EntryForm data={state.data} /> : null}
      </section>
    </ExerciseScreen>
  );
}

/** §6.4 L: six tile-shaped blocks, with the stated loading line. */
function TileSkeletons(): React.JSX.Element {
  return (
    <SkeletonRegion label="Loading the exercise…">
      <div className="grid w-fit grid-cols-3 gap-ce-4 md:flex md:flex-wrap">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} data-slot="exercise-team-tile-skeleton">
            <Skeleton className="size-24 rounded-ce-card lg:size-28" />
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

function EntryForm({ data }: { readonly data: EntryData }): React.JSX.Element {
  const navigate = useNavigate();
  const teamNumbers = data.facts.team_numbers;

  // Pre-select what this browser last entered, when the mirror has it and the
  // server still offers it. The value is never trusted for anything: it seeds
  // a form control, and the server decides on submit.
  const [selected, setSelected] = React.useState<number | null>(
    () => data.workspace?.team_number ?? readWorkspacePointer(teamNumbers),
  );
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (selected === null || pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      const workspace = await enterTeamWorkspace(selected);
      writeWorkspacePointer(workspace.team_number);
      await navigate(EVENT_PICKER_PATH);
    } catch (error) {
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  const chosen = selected !== null;

  return (
    <form onSubmit={submit} className="flex flex-col gap-ce-5 md:w-fit">
      {/* The h2 above is the visible question; the legend keeps the group's
          spoken name as it was. Native radios sharing a name give the arrow
          keys (§8.4) for free. */}
      <fieldset className="m-0 min-w-0 border-0 p-0">
        <legend className="sr-only">Team number</legend>
        <div className="grid w-fit grid-cols-3 gap-ce-4 md:flex md:flex-wrap">
          {teamNumbers.map((number) => (
            <TeamTile
              key={number}
              number={number}
              selected={selected === number}
              pending={pending}
              onSelect={setSelected}
            />
          ))}
        </div>
      </fieldset>

      {data.workspace === null ? null : (
        // `md:w-0 md:min-w-full`: fill the tile row's width without widening
        // it, so the button below still lines up with the last tile.
        <div className="flex items-center gap-ce-3 md:w-0 md:min-w-full">
          <TeamBadgeArt className="size-8 shrink-0 text-ce-primary" />
          <p className="ce-type-body text-ce-ink" data-slot="exercise-entry-current">
            This browser is already in team {data.workspace.team_number}, working in{" "}
            <strong>{data.workspace.dataset_label}</strong>.
          </p>
        </div>
      )}

      {refusal === null ? null : (
        <div className="md:w-0 md:min-w-full">
          <ExerciseNotice message={refusal} />
        </div>
      )}

      {/* §7.2: right-aligned under the tiles on desktop; on a phone, full width
          and pinned to the bottom safe area once a tile is chosen. */}
      <div
        data-slot="exercise-entry-actions"
        data-sticky={chosen ? "true" : undefined}
        className={cn(
          "flex md:justify-end",
          chosen &&
            "max-md:sticky max-md:bottom-0 max-md:z-10 max-md:-mx-ce-4 max-md:border-t max-md:border-ce-line max-md:bg-ce-page max-md:px-ce-4 max-md:pt-ce-3 max-md:pb-[max(var(--ce-space-4),env(safe-area-inset-bottom))]",
        )}
      >
        <Button
          type="submit"
          pending={pending}
          pendingLabel="Opening your team's work…"
          disabled={!chosen}
          describedBy={chosen ? undefined : TEAM_HELPER_ID}
          className="w-full md:w-auto"
        >
          Open this team's work
        </Button>
      </div>
    </form>
  );
}

/** Below `md` (Tailwind's 48rem), where the open bar sticks to the bottom. */
const PHONE_QUERY = "(max-width: 47.99rem)";

/**
 * On a phone, choosing a tile pins the open bar to the bottom of the screen,
 * which can cover the lower row of tiles. Scroll the chosen tile just far
 * enough to clear it (its `scroll-margin-bottom` is the bar's height).
 * Wider screens never pin the bar, so the page stays where it is.
 */
function revealAbovePhoneBar(tile: HTMLElement | null): void {
  if (
    tile === null ||
    typeof window.matchMedia !== "function" ||
    typeof tile.scrollIntoView !== "function" ||
    !window.matchMedia(PHONE_QUERY).matches
  ) {
    return;
  }
  tile.scrollIntoView({ block: "nearest" });
}

/**
 * One numbered place card (§6.4). The radio is visually hidden inside its
 * label; the label draws the card, the ring (focus-within) and the states.
 */
function TeamTile({
  number,
  selected,
  pending,
  onSelect,
}: {
  readonly number: number;
  readonly selected: boolean;
  readonly pending: boolean;
  readonly onSelect: (number: number) => void;
}): React.JSX.Element {
  const tile = React.useRef<HTMLLabelElement>(null);

  function choose(): void {
    onSelect(number);
    revealAbovePhoneBar(tile.current);
  }

  return (
    <label
      ref={tile}
      data-selected={selected ? "true" : undefined}
      data-pending={pending ? "true" : undefined}
      className={cn(
        "ce-press relative flex size-24 cursor-pointer items-center justify-center overflow-hidden rounded-ce-card lg:size-28",
        // Room for the sticky open bar (48px button + 12 + 16 padding + 1px
        // rule = 77px) plus air, so `scrollIntoView` stops above it.
        "max-md:scroll-mb-[96px]",
        "font-ce-display text-[44px] leading-none font-bold tabular-nums",
        "has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-[3px] has-[:focus-visible]:outline-ce-primary has-[:focus-visible]:outline-solid",
        selected
          ? "bg-ce-primary text-ce-on-primary shadow-ce-2"
          : "ce-lift bg-ce-surface text-ce-ink shadow-ce-1 hover:text-ce-primary",
        pending && "opacity-60",
      )}
    >
      <input
        type="radio"
        name="team_number"
        value={number}
        checked={selected}
        onChange={choose}
        // The accessible name is stated rather than inherited from the
        // label's text. The label holds both the big projected numeral
        // and a visually-hidden word, so an inherited name read out as
        // "4 Team 4".
        aria-label={`Team ${number}`}
        className="sr-only"
      />
      <span aria-hidden="true">{number}</span>
      {selected ? (
        <span
          aria-hidden="true"
          data-slot="exercise-team-tile-notch"
          className="absolute top-0 right-0 size-0 border-t-[18px] border-l-[18px] border-t-ce-gold border-l-transparent"
        />
      ) : null}
    </label>
  );
}
