/**
 * The Speaker Pipeline's drill-down, against a stubbed `fetch` (B41, B42).
 *
 * ADR-0011 rule 4: clicking N opens exactly the N rows the number was counted
 * from, from the same owning query. The section reads
 * `GET /v1/units/{unit_id}/speaker-pipeline`, whose `metrics` array carries
 * each figure's server-issued `drill_down_url`; a click follows that link and
 * nothing else. The assertions check the request the section made rather than
 * trusting what it drew.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpeakerPipelineSection } from "./SpeakerPipelineSection";

const UNIT = "11111111-1111-4111-8111-111111111111";
const PIPELINE = `/v1/units/${UNIT}/speaker-pipeline`;
const drillUrl = (name: string) => `/v1/units/${UNIT}/metrics/${name}/drill-down?surface=cba`;

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

type Answer = { body: unknown; status?: number };
let calls: string[] = [];

function stub(answers: Record<string, Answer>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      const answer = answers[url] ?? {
        body: { error: { code: "test_unstubbed", message: url } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function stage(metric_name: string, display_name: string, value: number | null) {
  return {
    metric_name,
    display_name,
    description: `${display_name} caption`,
    definition: `${display_name} definition`,
    value,
    unknown_reason: value === null ? "No evidence source." : null,
    share_of_baseline_pct: value === null ? null : 100,
    share_display: value === null ? "—" : "100%",
  };
}

function summary(name: string, display_name: string, value: number | null) {
  return {
    name,
    display_name,
    definition: `${display_name} definition`,
    value,
    unknown_reason: value === null ? "No evidence source." : null,
    drill_down_url: drillUrl(name),
  };
}

const PAYLOAD = {
  unit_id: UNIT,
  range: { kind: "all_time", label: "All time", note: "Not filtered." },
  metrics: [
    summary("pipeline_matched", "Speakers matched", 2),
    summary("pipeline_contacted", "Speakers contacted", 1),
    summary("pipeline_confirmed", "Speakers confirmed", 0),
    summary("pipeline_attended", "Speakers attended", null),
    summary("opportunities", "Opportunities", 0),
    summary("pending_review_items", "Pending review items", 0),
  ],
  baseline_metric: "pipeline_matched",
  stages: [
    stage("pipeline_matched", "Speakers matched", 2),
    stage("pipeline_contacted", "Speakers contacted", 1),
    stage("pipeline_confirmed", "Speakers confirmed", 0),
    stage("pipeline_attended", "Speakers attended", null),
  ],
  companions: [
    {
      metric_name: "opportunities",
      display_name: "Opportunities",
      description: "caption",
      definition: "Opportunities definition",
      value: 0,
      unknown_reason: null,
    },
    {
      metric_name: "pending_review_items",
      display_name: "Pending review items",
      description: "caption",
      definition: "Pending definition",
      value: 0,
      unknown_reason: null,
    },
  ],
  conversions: [],
  insights: [],
};

function pipelineRow(id: string, contacted: string | null) {
  return {
    id,
    subject_id: `subject-${id}`,
    opportunity_event_id: `event-${id}`,
    matched_at: "2026-09-01T10:00:00Z",
    contacted_at: contacted,
    confirmed_at: null,
    attended_at: null,
    member_inquiry_at: null,
  };
}

const MATCHED_DRILL = {
  unit_id: UNIT,
  name: "pipeline_matched",
  definition: "Speakers matched definition",
  aggregate_value: 2,
  unknown_reason: null,
  rows: [pipelineRow("row-a", "2026-09-02T10:00:00Z"), pipelineRow("row-b", null)],
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpeakerPipelineSection unitId={UNIT} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Speaker Pipeline drill-down (B41 KPI cards)", () => {
  it("opens the rows behind a KPI card from the server's own drill-down link", async () => {
    stub({ [PIPELINE]: { body: PAYLOAD }, [drillUrl("pipeline_matched")]: { body: MATCHED_DRILL } });
    mount();

    const figures = await screen.findByRole("list", { name: "Speaker pipeline figures" });
    fireEvent.click(
      within(figures).getByRole("button", { name: "Open the 2 rows behind Speakers matched" }),
    );

    const sheet = await screen.findByRole("dialog");
    await waitFor(() => expect(within(sheet).getByText("row-a")).toBeTruthy());
    expect(within(sheet).getByText("row-b")).toBeTruthy();
    expect(calls).toContain(drillUrl("pipeline_matched"));
  });

  it("names the furthest stage each pipeline row reached", async () => {
    stub({ [PIPELINE]: { body: PAYLOAD }, [drillUrl("pipeline_matched")]: { body: MATCHED_DRILL } });
    mount();

    const figures = await screen.findByRole("list", { name: "Speaker pipeline figures" });
    fireEvent.click(
      within(figures).getByRole("button", { name: "Open the 2 rows behind Speakers matched" }),
    );

    const sheet = await screen.findByRole("dialog");
    await waitFor(() => expect(within(sheet).getByText("contacted")).toBeTruthy());
    expect(within(sheet).getByText("matched")).toBeTruthy();
  });

  it("offers no drill-down for an unmeasured figure", async () => {
    stub({ [PIPELINE]: { body: PAYLOAD } });
    mount();

    const figures = await screen.findByRole("list", { name: "Speaker pipeline figures" });
    expect(within(figures).queryByRole("button", { name: /rows behind Speakers attended/ })).toBeNull();
    // A measured zero is a real answer and still opens (to an empty row set).
    expect(
      within(figures).getByRole("button", { name: "Open the 0 rows behind Speakers confirmed" }),
    ).toBeTruthy();
  });

  it("shows the server's refusal when the caller may not read rows", async () => {
    stub({
      [PIPELINE]: { body: PAYLOAD },
      [drillUrl("pipeline_matched")]: {
        body: { error: { code: "forbidden", message: "Only admin or coordinator may drill down." } },
        status: 403,
      },
    });
    mount();

    const figures = await screen.findByRole("list", { name: "Speaker pipeline figures" });
    fireEvent.click(
      within(figures).getByRole("button", { name: "Open the 2 rows behind Speakers matched" }),
    );

    const sheet = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(sheet).getByText(/Only admin or coordinator may drill down/)).toBeTruthy(),
    );
  });
});

describe("Speaker Pipeline drill-down (B42 funnel bands)", () => {
  it("opens the rows behind a funnel band from the same link as its card", async () => {
    const contacted = {
      ...MATCHED_DRILL,
      name: "pipeline_contacted",
      aggregate_value: 1,
      rows: [pipelineRow("row-a", "2026-09-02T10:00:00Z")],
    };
    stub({ [PIPELINE]: { body: PAYLOAD }, [drillUrl("pipeline_contacted")]: { body: contacted } });
    mount();

    const funnel = await screen.findByRole("region", { name: "Speaker Pipeline Funnel" });
    fireEvent.click(
      within(funnel).getByRole("button", { name: "Open the 1 row behind Speakers contacted" }),
    );

    const sheet = await screen.findByRole("dialog");
    await waitFor(() => expect(within(sheet).getByText("row-a")).toBeTruthy());
    expect(calls).toContain(drillUrl("pipeline_contacted"));
  });

  it("draws no button on an unmeasured band", async () => {
    stub({ [PIPELINE]: { body: PAYLOAD } });
    mount();

    const funnel = await screen.findByRole("region", { name: "Speaker Pipeline Funnel" });
    expect(within(funnel).queryByRole("button", { name: /Speakers attended/ })).toBeNull();
  });
});
