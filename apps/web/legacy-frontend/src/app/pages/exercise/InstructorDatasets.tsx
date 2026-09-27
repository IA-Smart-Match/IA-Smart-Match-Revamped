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
 */
import * as React from "react";
import { FileSpreadsheet, Upload } from "lucide-react";

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
import { ExerciseLoading, ExerciseNotice } from "./ExerciseScreen";
import { ceButton, Spinner } from "./exerciseUi";
import { useExerciseResource } from "./useExerciseResource";

export function InstructorDatasets({
  onDataChanged,
}: {
  /**
   * Called after an upload or a re-point lands, so the page can reload the
   * panels that read the same facts: the teams list and the unlock panel.
   */
  readonly onDataChanged?: () => void;
} = {}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listDatasets, []);
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
  const [pending, setPending] = React.useState(false);

  async function run(action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    setDone(null);
    try {
      await action();
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

  return (
    <section className="ce-card flex flex-col gap-4 p-5 md:p-6">
      <h2 className="ce-h2 text-ce-ink">Data files</h2>

      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : (
        <p
          role="status"
          aria-live="polite"
          data-slot="exercise-instructor-done"
          className="ce-body ce-notice-in rounded-[14px] bg-ce-avocado-tint px-4 py-3 text-ce-ink"
        >
          {done}
        </p>
      )}

      <UploadForm
        pending={pending}
        onUpload={(file, label) =>
          run(async () => {
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
        <div className="flex flex-col gap-3" data-slot="exercise-upload-report">
          {/* The server's own sentence about what an upload did and did not do. */}
          <ExerciseNotice message={uploaded.notice} />
          <dl className="ce-well grid grid-cols-2 gap-3 p-4">
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

      {state.status === "loading" ? <ExerciseLoading what="the data files" /> : null}
      {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem" />
      ) : null}
      {state.status === "ready" ? (
        <ul className="flex flex-col gap-3 border-t border-ce-line pt-4">
          {state.data.length === 0 ? (
            <li className="ce-body text-ce-ink">No data file has been uploaded yet.</li>
          ) : null}
          {state.data.map((dataset) => (
            <li key={dataset.dataset_id}>
              <DatasetRow
                dataset={dataset}
                pending={pending}
                onLimit={(limit) =>
                  run(async () => {
                    await setInviteLimit(dataset.dataset_id, limit);
                    reload();
                  })
                }
                onRepoint={() =>
                  run(async () => {
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
    </section>
  );
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
 * The upload (DESIGN.md §6.24): a dashed dropzone that is also the file
 * input's label, so a click chooses a file and a drop hands one over. The
 * file's name stays on screen once chosen, and through a refusal.
 */
function UploadForm({
  pending,
  onUpload,
}: {
  readonly pending: boolean;
  readonly onUpload: (file: File, label: string) => Promise<void>;
}): React.JSX.Element {
  const [label, setLabel] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [over, setOver] = React.useState(false);

  return (
    <form
      className="flex flex-col gap-4"
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
      <label
        htmlFor="exercise-upload-file"
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          const dropped = event.dataTransfer.files[0];
          if (dropped !== undefined) {
            setFile(dropped);
          }
        }}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-[14px] border-2 border-dashed px-4 py-6 text-center transition-colors has-[input:focus-visible]:outline-3 has-[input:focus-visible]:outline-offset-3 has-[input:focus-visible]:outline-ce-primary ${
          over || file !== null
            ? "border-ce-primary bg-ce-primary-tint"
            : "border-ce-line-strong hover:border-ce-primary hover:bg-ce-primary-tint"
        } ${pending ? "pointer-events-none opacity-45" : ""}`}
      >
        <FileSpreadsheet aria-hidden="true" className="size-8 text-ce-primary" />
        <span className="ce-label text-ce-ink">Drop Ann's workbook here, or choose a file</span>
        <span className="ce-meta text-ce-muted">Ann&apos;s Excel workbook (.xlsx)</span>
        {file === null ? null : (
          <span className="ce-meta break-all text-ce-ink" data-slot="exercise-upload-chosen">
            {file.name}
          </span>
        )}
        <input
          id="exercise-upload-file"
          type="file"
          accept={`.xlsx,${XLSX_CONTENT_TYPE}`}
          aria-describedby="exercise-upload-file-help"
          disabled={pending}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="sr-only"
        />
      </label>
      <p id="exercise-upload-file-help" className="ce-meta -mt-2 text-ce-muted">
        Choose Ann&apos;s workbook exactly as she sent it. Do not save it as a CSV first.
      </p>
      <div className="flex flex-col gap-1">
        <label htmlFor="exercise-upload-label" className="ce-label text-ce-ink">
          Call this file
        </label>
        <input
          id="exercise-upload-label"
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          className="ce-input w-full"
        />
      </div>
      <button
        type="submit"
        disabled={pending || file === null || label.trim() === ""}
        className={ceButton("secondary", "w-full")}
      >
        {pending ? <Spinner /> : <Upload aria-hidden="true" className="size-5" />}
        {pending ? "Uploading and checking the file…" : "Upload this file"}
      </button>
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
    <div className="ce-well flex flex-col gap-3 p-4">
      <div>
        <p className="ce-label text-ce-ink">{dataset.label}</p>
        <p className="ce-meta break-words text-ce-muted">
          {dataset.source_filename} — {dataset.row_count} profiles, {dataset.event_count} events
        </p>
      </div>
      {/* A per-upload line, rendered only when one is stored (see OQ-CE-09 above). */}
      {dataset.license_line === null ? null : (
        <p className="ce-meta text-ce-ink">{dataset.license_line}</p>
      )}

      <form
        className="flex flex-col gap-2 border-t border-ce-line pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = Number.parseInt(limit, 10);
          if (!Number.isNaN(parsed)) {
            void onLimit(parsed);
          }
        }}
      >
        <label htmlFor={limitId} className="ce-label text-ce-ink">
          How many names a list may hold
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id={limitId}
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            className="ce-input ce-num w-24"
          />
          <button type="submit" disabled={pending} className={ceButton("secondary")}>
            Set the limit
          </button>
        </div>
      </form>

      {confirming ? (
        <div className="flex flex-col gap-3 border-t border-ce-line pt-3">
          <span className="ce-meta text-ce-ink">
            This moves every team to this file and clears the work of every team it moves.
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={pending}
              className={ceButton("danger")}
              onClick={() => {
                setConfirming(false);
                void onRepoint();
              }}
            >
              Yes, move every team here
            </button>
            <button
              type="button"
              className={ceButton("quiet", "min-h-11")}
              onClick={() => setConfirming(false)}
            >
              Keep them where they are
            </button>
          </span>
        </div>
      ) : (
        <div className="border-t border-ce-line pt-2">
          <button
            type="button"
            className={ceButton("quiet", "min-h-11 px-0")}
            onClick={() => setConfirming(true)}
          >
            Move every team to this file
          </button>
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
    <div>
      <dt className="ce-meta text-ce-muted">{label}</dt>
      <dd className="ce-value text-ce-ink">{value}</dd>
    </div>
  );
}
