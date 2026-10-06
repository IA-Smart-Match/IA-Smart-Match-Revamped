/**
 * The instructor's data files: list, upload, invite limit, re-point.
 *
 * Design spec §3 and §5. Four facts shape this panel:
 *
 * **Uploading moves nobody.** The server says so itself, in the `notice` field
 * on the upload response, and that sentence is rendered as-is. PR #186's
 * ruling made it load-bearing: a team's entry lands on the workspace it
 * already has, so after an upload the teams keep working in the old file until
 * the instructor re-points them, and a team's entry screen may legitimately
 * show the older label.
 *
 * **Re-pointing resets every team.** It is the one thing that moves a team,
 * and it discards their work, so it asks first. `teams_moved` and
 * `teams_discarded` come back and are shown — the instructor should see what
 * the button did rather than infer it.
 *
 * **The upload is Ann's Excel workbook as a raw .xlsx body.** OQ-CE-05 closed
 * on 2026-09-24: the instructor uploads Ann's .xlsx as-is, not a CSV exported
 * from it. The owner's 2026-09-21 ruling still stands — no multipart. The file
 * is read in the browser and its bytes are the request body, with the label
 * and the file name as query parameters; there is no `FormData` here. The
 * shape lives in `exerciseClient.uploadDataset`, so a later change to it is
 * one function and this one form.
 *
 * **A dataset's license line is rendered only when the server has one.**
 * OQ-CE-09 closed 2026-09-25: the exercise's license line is a constant shown
 * on the opening screen (`EXERCISE_LICENSE_LINE` in `ExerciseEntry.tsx`), not
 * a per-upload value. The ingest does not fill `license_line`, so it is `null`
 * here and nothing stands in for it.
 *
 * **An upload answers in one sentence, and a refusal stands alone.** Ann's
 * checklist §2 (2026-10-02, #325): after an upload, "file name, '300 profiles,
 * 12 events loaded.'"; after a refused one, "a plain message naming the missing
 * column, and the old file stays in use". So the report leads with that
 * sentence, composed here from the server's own file name and counts, and the
 * report of an earlier upload is taken away the moment another upload starts
 * or anything on this panel is refused: "loaded" never sits beside "refused".
 *
 * An expired session signs the page out, from the list read or from any
 * action, as every instructor panel does (`instructorSession.ts`). Visual
 * layout: DESIGN.md §6.24 (dropzone, dataset row, invite limit).
 */
import * as React from "react";
import { CircleCheck, FileSpreadsheet } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  XLSX_CONTENT_TYPE,
  listDatasets,
  repointWorkspaces,
  setInviteLimit,
  uploadDataset,
  type DatasetView,
  type UploadedDatasetView,
} from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { Button } from "./desk";
import { ExerciseNotice } from "./ExerciseScreen";
import { useSignOutOnExpiredRead } from "./instructorSession";
import { INSTRUCTOR_INPUT, INSTRUCTOR_WELL, PanelCard, PanelSkeleton } from "./instructorUi";
import { INSTRUCTOR_SESSION_REQUIRED } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

/** Which action is in flight, so only its own button shows the in-progress verb. */
type PendingAction = "upload" | "limit" | "repoint";

export function InstructorDatasets({
  onDataChanged,
  onSignedOut,
}: {
  /**
   * Called after an upload or a re-point lands, so the page can reload the
   * panels that read the same facts: the teams list and the unlock panel.
   */
  readonly onDataChanged?: () => void;
  /** Called when the instructor session has expired; the page shows the passcode form. */
  readonly onSignedOut?: () => void;
} = {}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listDatasets, []);
  useSignOutOnExpiredRead(state, onSignedOut);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  /**
   * What just worked, in its own slot.
   *
   * A re-point's outcome used to be pushed through `setRefusal`, so "moved 4
   * teams" was rendered by the panel that otherwise only ever says something
   * went wrong. Two different things deserve two slots, and this one is a
   * polite live region: an instructor using a screen reader hears the outcome
   * without it arriving as an alert.
   */
  const [done, setDone] = React.useState<string | null>(null);
  const [uploaded, setUploaded] = React.useState<UploadedDatasetView | null>(null);
  const [pendingAction, setPendingAction] = React.useState<PendingAction | null>(null);
  const pending = pendingAction !== null;
  /**
   * The in-flight guard. `pending` is state, so two submits handled before a
   * re-render both read `false`; the ref is set the moment the first starts.
   */
  const pendingRef = React.useRef(false);

  async function run(kind: PendingAction, action: () => Promise<void>): Promise<void> {
    if (pendingRef.current) {
      return;
    }
    pendingRef.current = true;
    setPendingAction(kind);
    setRefusal(null);
    setDone(null);
    if (kind === "upload") {
      // The report on screen is about the previous file, not this one.
      setUploaded(null);
    }
    try {
      await action();
    } catch (error) {
      // A refusal never sits next to an earlier upload's "loaded".
      setUploaded(null);
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
      if (isRefusal(error) && error.code === INSTRUCTOR_SESSION_REQUIRED) {
        onSignedOut?.();
      }
    } finally {
      pendingRef.current = false;
      setPendingAction(null);
    }
  }

  return (
    <PanelCard title="Data files">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : <DoneNotice slot="exercise-instructor-done">{done}</DoneNotice>}

      <UploadForm
        pending={pending}
        uploading={pendingAction === "upload"}
        onUpload={(file, label) =>
          run("upload", async () => {
            // The read happens inside the guard, so a file that cannot be read
            // becomes a sentence on screen rather than an exception nobody
            // sees. It used to be `file.text()` outside it, which threw where
            // `Blob.prototype.text` is missing and killed the upload silently.
            const workbook = await readFileAsBytes(file);
            setUploaded(await uploadDataset(workbook, label, file.name));
            reload();
            onDataChanged?.();
          })
        }
      />

      {uploaded === null ? null : (
        <div className="flex flex-col gap-ce-3" data-slot="exercise-upload-report">
          <DoneNotice slot="exercise-upload-done">{uploadSentence(uploaded)}</DoneNotice>
          {/* The server's own sentence about what an upload did and did not do. */}
          <ExerciseNotice message={uploaded.notice} />
          <dl className="grid grid-cols-2 gap-ce-3">
            <Pair label="Profiles" value={uploaded.report.profile_count} />
            <Pair label="Events" value={uploaded.report.event_count} />
            <Pair label="Events in the exercise" value={uploaded.report.exercise_event_count} />
            <Pair label="Profiles with no card" value={uploaded.report.profiles_without_card} />
            <Pair
              label="Different interest words"
              value={uploaded.report.distinct_stated_interest_terms}
            />
            <Pair label="Different topic words" value={uploaded.report.distinct_topic_tag_terms} />
          </dl>
        </div>
      )}

      <div className="border-t border-ce-line" aria-hidden="true" />

      {state.status === "loading" ? <PanelSkeleton what="the data files" rows={1} /> : null}
      {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem" />
      ) : null}
      {state.status === "ready" ? (
        <ul className="flex flex-col gap-ce-4">
          {state.data.length === 0 ? (
            <li className="ce-type-body text-ce-ink-muted">No data file has been uploaded yet.</li>
          ) : null}
          {state.data.map((dataset) => (
            <li key={dataset.dataset_id}>
              <DatasetRow
                dataset={dataset}
                pending={pending}
                onLimit={(limit) =>
                  run("limit", async () => {
                    await setInviteLimit(dataset.dataset_id, limit);
                    reload();
                  })
                }
                onRepoint={() =>
                  run("repoint", async () => {
                    const moved = await repointWorkspaces(dataset.dataset_id);
                    setDone(
                      `Moved ${moved.teams_moved} ${
                        moved.teams_moved === 1 ? "team" : "teams"
                      } to ${moved.dataset_label}, clearing the work of ${
                        moved.teams_discarded
                      } of them.`,
                    );
                    reload();
                    onDataChanged?.();
                  })
                }
              />
            </li>
          ))}
        </ul>
      ) : null}
    </PanelCard>
  );
}

/**
 * What just worked (DESIGN.md §6.20, "Done"): a polite live region, so it is
 * heard without arriving as an alert.
 */
function DoneNotice({
  slot,
  children,
}: {
  readonly slot: string;
  readonly children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      data-slot={slot}
      className="ce-notice-in flex items-start gap-ce-3 rounded-ce-card bg-ce-avocado-tint p-ce-4 text-ce-ink"
    >
      <CircleCheck aria-hidden="true" className="mt-[3px] size-6 shrink-0 text-ce-primary" />
      <p className="ce-type-body min-w-0 break-words">{children}</p>
    </div>
  );
}

/**
 * Ann's one sentence for an upload (checklist §2): the file's name and what
 * was in it. Every part is the server's; only the order of the words is ours.
 */
function uploadSentence(uploaded: UploadedDatasetView): string {
  const { dataset, report } = uploaded;
  return `${dataset.source_filename} — ${report.profile_count} profiles, ${report.event_count} events loaded.`;
}

/**
 * The chosen file's bytes, as an `ArrayBuffer`.
 *
 * `FileReader` rather than `Blob.prototype.arrayBuffer()`: the latter is absent in
 * some environments — jsdom among them — and when it is, calling it throws
 * inside a submit handler, where the exception goes nowhere and the upload
 * simply never happens. `FileReader` has been in every browser since long
 * before any machine in this classroom, and its failure arrives as a rejection
 * this screen can show as a sentence.
 */
function readFileAsBytes(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const unreadable = () =>
      reject(new Error("That file could not be read. Try choosing it again."));
    reader.onload = () =>
      reader.result instanceof ArrayBuffer ? resolve(reader.result) : unreadable();
    reader.onerror = unreadable;
    reader.readAsArrayBuffer(file);
  });
}

/**
 * The upload: a dropzone (§6.24) over the native file input, a name, a button.
 *
 * The file input itself covers the whole dashed zone, transparent, so a click
 * anywhere opens the picker and a dropped file lands on the input exactly as
 * the browser delivers it — the same `change` event, no drag-and-drop code in
 * the upload path. The zone draws the focus ring for it, and keeps the chosen
 * file's name on screen, including after a refusal.
 */
function UploadForm({
  pending,
  uploading,
  onUpload,
}: {
  readonly pending: boolean;
  readonly uploading: boolean;
  readonly onUpload: (file: File, label: string) => Promise<void>;
}): React.JSX.Element {
  const [label, setLabel] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [dragging, setDragging] = React.useState(false);

  return (
    <form
      className="flex flex-col gap-ce-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (file === null || label.trim() === "") {
          return;
        }
        // The route takes the workbook as a raw .xlsx body, not a multipart part, so
        // there is no `FormData` in this path. The caller reads the bytes.
        void onUpload(file, label.trim());
      }}
    >
      <div className="flex min-w-0 flex-col gap-ce-2">
        <label htmlFor="exercise-upload-file" className="ce-type-label text-ce-ink">
          Ann&apos;s Excel workbook (.xlsx)
        </label>
        <div
          className={cn(
            "relative flex flex-col items-center gap-ce-2 rounded-ce-card border-2 border-dashed px-ce-4 py-ce-5 text-center transition-colors",
            "has-[:focus-visible]:[outline:3px_solid_var(--ce-primary)] has-[:focus-visible]:[outline-offset:3px]",
            dragging
              ? "border-ce-primary bg-ce-primary-tint"
              : "border-ce-line-strong hover:border-ce-primary hover:bg-ce-primary-tint",
          )}
        >
          <FileSpreadsheet aria-hidden="true" className="size-8 text-ce-primary" />
          <p aria-hidden="true" className="ce-type-body font-semibold text-ce-ink">
            Drop Ann&apos;s workbook here, or choose a file
          </p>
          <p id="exercise-upload-file-help" className="ce-type-meta text-ce-ink-muted">
            Choose Ann&apos;s workbook exactly as she sent it. Do not save it as a CSV first.
          </p>
          {file === null ? null : (
            <p className="ce-type-meta max-w-full break-all font-semibold text-ce-ink">
              {file.name}
            </p>
          )}
          <input
            id="exercise-upload-file"
            type="file"
            accept={`.xlsx,${XLSX_CONTENT_TYPE}`}
            aria-describedby="exercise-upload-file-help"
            onChange={(event) => {
              setDragging(false);
              setFile(event.target.files?.[0] ?? null);
            }}
            onDragEnter={() => setDragging(true)}
            onDragLeave={() => setDragging(false)}
            onDrop={() => setDragging(false)}
            className="absolute inset-0 size-full cursor-pointer opacity-0"
          />
        </div>
      </div>
      <div className="flex flex-col gap-ce-2">
        <label htmlFor="exercise-upload-label" className="ce-type-label text-ce-ink">
          Call this file
        </label>
        <input
          id="exercise-upload-label"
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          className={`${INSTRUCTOR_INPUT} w-full`}
        />
      </div>
      <Button
        type="submit"
        variant="secondary"
        pending={uploading}
        pendingLabel="Uploading and checking the file…"
        disabled={pending || file === null || label.trim() === ""}
        className="w-full"
      >
        Upload this file
      </Button>
    </form>
  );
}

function DatasetRow({
  dataset,
  pending,
  onLimit,
  onRepoint,
}: {
  readonly dataset: DatasetView;
  readonly pending: boolean;
  readonly onLimit: (limit: number) => Promise<void>;
  readonly onRepoint: () => Promise<void>;
}): React.JSX.Element {
  const [limit, setLimit] = React.useState(String(dataset.invite_limit));
  const [confirming, setConfirming] = React.useState(false);
  const limitId = `exercise-invite-limit-${dataset.dataset_id}`;

  return (
    <div className={cn(INSTRUCTOR_WELL, "flex flex-col gap-ce-3")}>
      <div className="flex min-w-0 flex-col gap-ce-1">
        <p className="ce-type-h3 text-ce-ink">{dataset.label}</p>
        <p className="ce-type-meta ce-tabular break-words text-ce-ink-muted">
          {dataset.source_filename} — {dataset.row_count} profiles, {dataset.event_count} events
        </p>
        {/* A per-upload line, rendered only when one is stored (see OQ-CE-09 above). */}
        {dataset.license_line === null ? null : (
          <p className="ce-type-meta text-ce-ink">{dataset.license_line}</p>
        )}
      </div>

      <form
        className="flex flex-col gap-ce-2 border-t border-ce-line pt-ce-3"
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = Number.parseInt(limit, 10);
          if (!Number.isNaN(parsed)) {
            void onLimit(parsed);
          }
        }}
      >
        <label htmlFor={limitId} className="ce-type-label text-ce-ink">
          How many names a list may hold
        </label>
        <div className="flex flex-wrap items-center gap-ce-3">
          <input
            id={limitId}
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            className={`${INSTRUCTOR_INPUT} ce-tabular w-24`}
          />
          <Button type="submit" variant="secondary" disabled={pending}>
            Set the limit
          </Button>
        </div>
      </form>

      {confirming ? (
        <div className="flex flex-col gap-ce-3 rounded-ce-control bg-ce-surface p-ce-3">
          <p className="ce-type-body text-ce-ink">
            This moves every team to this file and clears the work of every team it moves.
          </p>
          <div className="flex flex-wrap items-center gap-ce-3">
            <Button
              variant="destructive"
              disabled={pending}
              onClick={() => {
                setConfirming(false);
                void onRepoint();
              }}
            >
              Yes, move every team here
            </Button>
            <Button variant="quiet" onClick={() => setConfirming(false)}>
              Keep them where they are
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button variant="quiet" className="-ml-ce-2" onClick={() => setConfirming(true)}>
            Move every team to this file
          </Button>
        </div>
      )}
    </div>
  );
}

function Pair({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-ce-1">
      <dt className="ce-type-meta text-ce-ink-muted">{label}</dt>
      <dd className="ce-type-value text-ce-ink">{value}</dd>
    </div>
  );
}
