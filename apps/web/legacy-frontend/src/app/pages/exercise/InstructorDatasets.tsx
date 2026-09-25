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
 * **The license line is rendered only when the server has one.** OQ-CE-09 is
 * open and `license_line` is `null` until Ann provides the sentence; nothing
 * stands in for it.
 */
import * as React from "react";

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
import { useExerciseResource } from "./useExerciseResource";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-4 py-2 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

const INPUT =
  "rounded-lg border-2 border-slate-400 px-3 py-2 text-xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50";

export function InstructorDatasets(): React.JSX.Element {
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
    <section className="flex flex-col gap-4">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">Data files</h2>

      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : (
        <p
          role="status"
          aria-live="polite"
          data-slot="exercise-instructor-done"
          className="rounded-lg border-2 border-slate-300 px-5 py-4 text-xl text-slate-800 dark:border-slate-600 dark:text-slate-100"
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
          })
        }
      />

      {uploaded === null ? null : (
        <div className="flex flex-col gap-2" data-slot="exercise-upload-report">
          {/* The server's own sentence about what an upload did and did not do. */}
          <ExerciseNotice message={uploaded.notice} />
          <dl className="grid gap-2 text-xl sm:grid-cols-3">
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
        <ul className="flex flex-col gap-4">
          {state.data.length === 0 ? (
            <li className="text-xl text-slate-700 dark:text-slate-200">
              No data file has been uploaded yet.
            </li>
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

function UploadForm({
  pending,
  onUpload,
}: {
  readonly pending: boolean;
  readonly onUpload: (file: File, label: string) => Promise<void>;
}): React.JSX.Element {
  const [label, setLabel] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);

  return (
    <form
      className="flex flex-wrap items-end gap-3"
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
      <div className="flex flex-col gap-1">
        <label htmlFor="exercise-upload-label" className="text-xl">
          Call this file
        </label>
        <input
          id="exercise-upload-label"
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          className={INPUT}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="exercise-upload-file" className="text-xl">
          Ann&apos;s Excel workbook (.xlsx)
        </label>
        <input
          id="exercise-upload-file"
          type="file"
          accept={`.xlsx,${XLSX_CONTENT_TYPE}`}
          aria-describedby="exercise-upload-file-help"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className={INPUT}
        />
        <p id="exercise-upload-file-help" className="text-lg text-slate-600 dark:text-slate-300">
          Choose Ann&apos;s workbook exactly as she sent it. Do not save it as a CSV first.
        </p>
      </div>
      <button type="submit" disabled={pending || file === null || label.trim() === ""} className={BUTTON}>
        Upload this file
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
    <div className="rounded-lg border-2 border-slate-300 px-5 py-4 dark:border-slate-600">
      <p className="text-2xl font-semibold text-slate-900 dark:text-slate-50">{dataset.label}</p>
      <p className="text-xl text-slate-600 dark:text-slate-300">
        {dataset.source_filename} — {dataset.row_count} profiles, {dataset.event_count} events
      </p>
      {/* OQ-CE-09: rendered only when Ann's sentence is actually there. */}
      {dataset.license_line === null ? null : (
        <p className="text-xl text-slate-700 dark:text-slate-200">{dataset.license_line}</p>
      )}

      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = Number.parseInt(limit, 10);
          if (!Number.isNaN(parsed)) {
            void onLimit(parsed);
          }
        }}
      >
        <div className="flex flex-col gap-1">
          <label htmlFor={limitId} className="text-xl">
            How many names a list may hold
          </label>
          <input
            id={limitId}
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            className={`${INPUT} w-32`}
          />
        </div>
        <button type="submit" disabled={pending} className={BUTTON}>
          Set the limit
        </button>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {confirming ? (
          <>
            <span className="text-xl">
              This moves every team to this file and clears the work of every team it moves.
            </span>
            <button
              type="button"
              disabled={pending}
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
                void onRepoint();
              }}
            >
              Yes, move every team here
            </button>
            <button type="button" className={BUTTON} onClick={() => setConfirming(false)}>
              Keep them where they are
            </button>
          </>
        ) : (
          <button type="button" className={BUTTON} onClick={() => setConfirming(true)}>
            Move every team to this file
          </button>
        )}
      </div>
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
      <dt className="text-lg text-slate-600 dark:text-slate-300">{label}</dt>
      <dd className="text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</dd>
    </div>
  );
}
