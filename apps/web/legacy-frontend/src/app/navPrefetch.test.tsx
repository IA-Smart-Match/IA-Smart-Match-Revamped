/**
 * The Speaker Portal's hover prefetch (B26 T6b-4 §2.3): each `/speaker-portal`
 * href warms exactly the keys its page reads, built from the same
 * `SPEAKER_SELF_RESOURCE` names the pages use, and nothing while the principal
 * key is unresolved.
 */
import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SPEAKER_SELF_RESOURCE } from "./hooks/useSpeakerSelf";
import { prefetchPortalRoute } from "./navPrefetch";

const UNIT = "33333333-3333-4333-8333-333333333333";

function keysFor(href: string, principalKey: string | null = "principal-1"): unknown[] {
  const client = new QueryClient();
  const prefetch = vi.spyOn(client, "prefetchQuery").mockResolvedValue(undefined);
  prefetchPortalRoute(client, principalKey, UNIT, href);
  return prefetch.mock.calls.map(([options]) => options.queryKey);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SPEAKER_PREFETCH", () => {
  it.each([
    [
      "/speaker-portal/contact-preferences",
      [["principal-1", SPEAKER_SELF_RESOURCE.contactChannels]],
    ],
  ])("%s prefetches the keys its page reads", (href, expected) => {
    expect(keysFor(href)).toEqual(expected);
  });

  it("the resource names are the four my-* names", () => {
    expect(SPEAKER_SELF_RESOURCE).toEqual({
      invitations: "my-invitations",
      engagements: "my-engagements",
      availability: "my-availability",
      contactChannels: "my-contact-channels",
    });
  });

  it("nothing is prefetched while the principal key is null", () => {
    expect(keysFor("/speaker-portal/contact-preferences", null)).toEqual([]);
  });
});
