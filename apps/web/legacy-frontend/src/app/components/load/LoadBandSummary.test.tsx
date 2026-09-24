/**
 * B26 T8d V-B (plan §6.3, §7.2, §7.3, §8): the current band for one Speaker.
 * A band word, sentences and the engagements without an end time: never a
 * number outside a date's `<time>` element (OQ-CBA-005).
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import type { EngagementWithoutEndTime, LoadBand, SpeakerLoad } from "@/lib/api";
import { speakerLoadFixture } from "@/test/speakerLoadFixture";

import { LoadBandSummary } from "./LoadBandSummary";

afterEach(cleanup);

const TITLE = "Corporate treasury guest lecture";
const OTHER_TITLE = "Alumni mentoring breakfast";

function gap(overrides: Partial<EngagementWithoutEndTime> = {}): EngagementWithoutEndTime {
  return {
    engagement_id: "e-one",
    shown: "event",
    event_title: TITLE,
    local_date: "2026-10-20",
    time_precision: "date_only",
    editable_here: false,
    ...overrides,
  };
}

function show(
  load: SpeakerLoad,
  audience: "speaker" | "connector",
  headingLevel: 2 | 4 = audience === "speaker" ? 2 : 4,
) {
  return render(
    <MemoryRouter>
      <LoadBandSummary
        load={load}
        audience={audience}
        headingLevel={headingLevel}
        idPrefix="test"
      />
    </MemoryRouter>,
  );
}

/** Text with every `<time>` element removed. */
function textOutsideTime(root: HTMLElement): string {
  const copy = root.cloneNode(true) as HTMLElement;
  for (const time of Array.from(copy.querySelectorAll("time"))) time.remove();
  return copy.textContent ?? "";
}

describe("<LoadBandSummary />", () => {
  it.each([
    ["light", "Light"],
    ["moderate", "Moderate"],
    ["heavy", "Heavy"],
    ["full", "Full"],
    ["unknown", "Load not measurable"],
  ] as [LoadBand, string][])("renders the band word for %s", (band, word) => {
    const { container } = show(speakerLoadFixture({ band }), "connector");
    expect(within(container).getByText(word)).toBeTruthy();
    expect(container.textContent).toMatch(/Measured/);
    const time = container.querySelector("time");
    expect(time?.getAttribute("datetime")).toBe("2026-10-06");
    expect(time?.textContent).toBe("October 6, 2026");
  });

  it("used_in_matching false shows the not-used sentence and no consequence sentence", () => {
    const { container, unmount } = show(speakerLoadFixture({ band: "heavy" }), "connector");
    expect(container.textContent).toContain("Matching does not use workload yet.");
    expect(container.textContent).not.toContain("Matching ranks this Speaker lower for workload.");
    unmount();
    const speaker = show(speakerLoadFixture({ band: "heavy" }), "speaker");
    expect(speaker.container.textContent).toContain("Matching does not use your workload yet.");
    expect(speaker.container.textContent).not.toContain("Matching ranks you lower");
  });

  it("used_in_matching true with full shows the no-override sentence (connector) and the not-put-forward sentence (speaker)", () => {
    const load = speakerLoadFixture({ band: "full", used_in_matching: true });
    const connector = show(load, "connector");
    expect(connector.container.textContent).toContain(
      "New matching runs leave this Speaker out until the workload drops. There is no override yet.",
    );
    connector.unmount();
    const speaker = show(load, "speaker");
    expect(speaker.container.textContent).toContain(
      "You are not put forward for new events until your workload drops. Your Speaker Connector can tell you more.",
    );
  });

  it("hours_unknown lists each engagement with its title and a time element", () => {
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [
          gap(),
          gap({ event_title: OTHER_TITLE, local_date: "2026-11-03", time_precision: "exact" }),
        ],
      }),
      "connector",
    );
    expect(container.textContent).toContain(
      "These confirmed engagements have no end time, so their hours cannot be counted:",
    );
    const items = within(container).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain(TITLE);
    expect(items[0].querySelector("time")?.getAttribute("datetime")).toBe("2026-10-20");
    expect(items[0].textContent).toContain("date only, no times");
    expect(items[1].textContent).toContain(OTHER_TITLE);
    expect(items[1].querySelector("time")?.getAttribute("datetime")).toBe("2026-11-03");
    expect(items[1].textContent).toContain("start time only");
  });

  it("truncated adds the more sentence", () => {
    const load = speakerLoadFixture({
      band: "unknown",
      reason: "hours_unknown",
      engagements_without_end_time: [gap()],
      engagements_without_end_time_truncated: true,
    });
    const connector = show(load, "connector");
    expect(connector.container.textContent).toContain("More engagements also have no end time.");
    connector.unmount();
    const speaker = show(load, "speaker");
    expect(speaker.container.textContent).toContain(
      "More of your engagements also have no end time.",
    );
  });

  it("an unresolved date says date not set and has no time element", () => {
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [gap({ local_date: null, time_precision: "unresolved" })],
      }),
      "speaker",
    );
    const [entry] = within(container).getAllByRole("listitem");
    expect(entry.textContent).toContain("date not set");
    expect(entry.querySelector("time")).toBeNull();
  });

  it("other_unit and event_missing items have their sentences and no link", () => {
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [
          gap({
            engagement_id: null,
            shown: "other_unit",
            event_title: null,
            local_date: null,
            time_precision: null,
          }),
          gap({ shown: "event_missing", event_title: null, local_date: null, time_precision: null }),
        ],
      }),
      "connector",
    );
    const items = within(container).getAllByRole("listitem");
    expect(items[0].textContent).toBe(
      "An engagement another unit recorded. That unit's Speaker Connector can add the end time.",
    );
    expect(items[1].textContent).toBe("An engagement whose event record is missing.");
    expect(within(container).queryByRole("link")).toBeNull();
  });

  it("extra numeric fields on the wire render no digit outside time elements", () => {
    const load = {
      ...speakerLoadFixture({
        band: "moderate",
        reason: "full_by_known_hours",
        used_in_matching: true,
        engagements_without_end_time: [gap({ editable_here: true }), gap({ time_precision: "exact" })],
        engagements_without_end_time_truncated: true,
      }),
      utilization: 0.61,
      completed_hours: "50",
    } as SpeakerLoad;
    for (const audience of ["speaker", "connector"] as const) {
      const view = show(load, audience);
      expect(textOutsideTime(view.container)).not.toMatch(/[0-9%]/);
      view.unmount();
    }
  });

  it("list items key by index, so two other_unit items with null ids both render", () => {
    const other = gap({
      engagement_id: null,
      shown: "other_unit",
      event_title: null,
      local_date: null,
      time_precision: null,
    });
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [other, other],
      }),
      "connector",
    );
    expect(within(container).getAllByRole("listitem")).toHaveLength(2);
  });

  it("connector: only editable_here items have a link, named with the title", () => {
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [
          gap({ editable_here: true }),
          gap({ event_title: OTHER_TITLE, editable_here: false }),
        ],
      }),
      "connector",
    );
    const links = within(container).getAllByRole("link");
    expect(links).toHaveLength(1);
    const link = screen.getByRole("link", {
      name: "Add the end time for Corporate treasury guest lecture on the Events page",
    });
    expect(link.getAttribute("href")).toBe("/coordinator-portal/events");
    const items = within(container).getAllByRole("listitem");
    expect(items[1].textContent).toContain(
      "Recorded from an imported listing, so it cannot be edited here.",
    );
  });

  it("speaker: no link at all", () => {
    const { container } = show(
      speakerLoadFixture({
        band: "unknown",
        reason: "hours_unknown",
        engagements_without_end_time: [gap({ editable_here: true })],
      }),
      "speaker",
    );
    expect(within(container).queryByRole("link")).toBeNull();
    expect(container.textContent).toContain(
      "These engagements have no end time yet, so their hours cannot be counted. Your Speaker Connector can add them:",
    );
  });

  it("heading level follows the prop; speaker: a section labelled by it; connector: a div with role=group labelled by it", () => {
    const speaker = show(speakerLoadFixture(), "speaker", 2);
    const h2 = screen.getByRole("heading", { level: 2, name: "Your workload" });
    expect(h2.id).toBe("test-load-heading");
    const region = screen.getByRole("region", { name: "Your workload" });
    expect(region.tagName).toBe("SECTION");
    expect(region.getAttribute("aria-labelledby")).toBe("test-load-heading");
    speaker.unmount();

    show(speakerLoadFixture(), "connector", 4);
    expect(screen.getByRole("heading", { level: 4, name: "Workload" })).toBeTruthy();
    const group = screen.getByRole("group", { name: "Workload" });
    expect(group.tagName).toBe("DIV");
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
