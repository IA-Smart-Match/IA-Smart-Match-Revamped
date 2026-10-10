/** #272: the header names the persona, not the stored role key. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CoordinatorReviewQueue } from "./CoordinatorReviewQueue";

vi.mock("../../hooks/useSession", () => ({
  useAuthenticatedPrincipal: () => ({
    user_id: "u1",
    tenant_id: "t1",
    email: "connector@example.edu",
    suspended: false,
    memberships: [],
  }),
}));

vi.mock("../../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({
    status: "ready",
    mapping: {
      portals: [
        {
          portal: "coordinator",
          display_name: "Connector Dashboard",
          home_path: "/coordinator-portal",
          role: "coordinator",
          roles: ["coordinator"],
          default_unit_id: "11111111-1111-4111-8111-111111111111",
          org_unit_path: "/cba/finance",
        },
      ],
    },
  }),
}));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CoordinatorReviewQueue", () => {
  it("shows the role label, not the raw role key", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 404 }))),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CoordinatorReviewQueue />
      </QueryClientProvider>,
    );
    const line = screen.getByText(/Signed in as/).textContent;
    expect(line).toMatch(/Speaker Connector/);
    expect(line).not.toMatch(/· coordinator ·/);
  });
});
