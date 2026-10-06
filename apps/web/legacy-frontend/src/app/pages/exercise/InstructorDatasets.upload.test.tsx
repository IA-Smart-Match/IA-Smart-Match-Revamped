/**
 * What the data-files panel says after an upload, and after a refused one.
 *
 * Ann's checklist §2 (2026-10-02), #325: "Upload Ann's 300-row workbook. You
 * see a message: file name, '300 profiles, 12 events loaded.'" and "Upload a
 * workbook with one column removed. You see a plain message naming the missing
 * column, and the old file stays in use."
 *
 * The second half is the one that was wrong on screen: a refused upload left
 * the previous upload's report standing beside the refusal, so the page said
 * "loaded" and "refused" at once.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InstructorDatasets } from "./InstructorDatasets";

const DATASETS = "/v1/exercise/instructor/datasets";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

const UPLOADED = {
  dataset: {
    dataset_id: "22222222-2222-2222-2222-222222222222",
    label: "October file",
    source_filename: "SmartMatch_Student_Body_300.xlsx",
    uploaded_at: "2026-10-06T10:00:00Z",
    row_count: 300,
    event_count: 12,
    checksum: "abc",
    invite_limit: 30,
    license_line: null,
  },
  report: {
    profile_count: 300,
    event_count: 12,
    exercise_event_count: 2,
    distinct_class_years: ["Freshman"],
    profiles_without_card: 230,
    distinct_stated_interest_terms: 13,
    distinct_topic_tag_terms: 13,
    events_without_topic_tags: 0,
    major_only: 166,
    major_plus_events: 64,
    completed_card: 70,
  },
  notice: "The teams are still working in the data file they entered on.",
};

const MISSING_COLUMN = {
  error: {
    code: "exercise_ingest_missing_columns",
    message: "The Events sheet is missing the column seats.",
  },
};

/** Answers each upload in turn; every list read is an empty list. */
function stubUploads(answers: readonly { readonly body: unknown; readonly status: number }[]): void {
  let next = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const isUpload = url.startsWith(DATASETS) && (init.method ?? "GET") === "POST";
      const answer = isUpload ? answers[next++] : { body: [], status: 200 };
      return Promise.resolve(new Response(JSON.stringify(answer.body), { status: answer.status }));
    }),
  );
}

function upload(fileName: string): void {
  fireEvent.change(screen.getByLabelText(/call this file/i), { target: { value: "October file" } });
  const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], fileName, { type: XLSX });
  fireEvent.change(screen.getByLabelText(/excel workbook/i), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /upload this file/i }));
}

function report(): Element | null {
  return document.querySelector('[data-slot="exercise-upload-report"]');
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<InstructorDatasets /> upload", () => {
  it("says the file name and what was loaded, in one sentence", async () => {
    stubUploads([{ body: UPLOADED, status: 201 }]);
    render(<InstructorDatasets />);
    await screen.findByText("No data file has been uploaded yet.");

    upload("SmartMatch_Student_Body_300.xlsx");

    const sentence = await screen.findByText(
      "SmartMatch_Student_Body_300.xlsx — 300 profiles, 12 events loaded.",
    );
    // Said politely to a screen reader, as the other "it worked" lines are.
    expect(sentence.closest('[role="status"]')).not.toBeNull();
    expect(report()?.contains(sentence)).toBe(true);
    // The server's own sentence about the teams still stands beside it.
    expect(screen.getByText(UPLOADED.notice)).toBeDefined();
  });

  it("takes the earlier upload's report away when a later upload is refused", async () => {
    stubUploads([
      { body: UPLOADED, status: 201 },
      { body: MISSING_COLUMN, status: 422 },
    ]);
    render(<InstructorDatasets />);
    await screen.findByText("No data file has been uploaded yet.");

    upload("SmartMatch_Student_Body_300.xlsx");
    await waitFor(() => expect(report()).not.toBeNull());

    upload("one-column-removed.xlsx");

    // The server's sentence, exactly as it arrived.
    await screen.findByText("The Events sheet is missing the column seats.");
    expect(report()).toBeNull();
    expect(screen.queryByText(/events loaded\./)).toBeNull();
    // The file that was refused is still named on the dropzone.
    expect(screen.getByText("one-column-removed.xlsx")).toBeDefined();
  });
});
