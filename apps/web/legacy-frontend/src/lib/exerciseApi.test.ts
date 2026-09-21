/**
 * The three rules `exerciseApi.ts` exists to keep, asserted on real calls.
 *
 * Each of these fails silently in a classroom if it regresses: a wrong prefix
 * loses the cookie and every screen says "enter your team number"; a missing
 * header turns every save into a 403; a refusal rendered as an exception puts
 * server prose on a projector. None of the three is visible in a type.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  EXERCISE_API_BASE,
  ExerciseRefusal,
  ExerciseUnreachable,
  exerciseRequest,
  exerciseUrl,
  isRefusal,
} from "./exerciseApi";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The last call's URL and init, for assertions. */
function lastCall(spy: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const call = spy.mock.calls.at(-1) as [string, RequestInit];
  return { url: call[0], init: call[1] };
}

function stubFetch(response: Response) {
  const spy = vi.fn(() => Promise.resolve(response));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the exercise URL is literal", () => {
  it("is /v1/exercise and never an /api prefix", () => {
    // The workspace cookie is Path=/v1/exercise and the instructor cookie
    // Path=/v1/exercise/instructor. An /api prefix proxies to the same backend
    // and simply does not carry the cookie.
    expect(EXERCISE_API_BASE).toBe("/v1/exercise");
    expect(EXERCISE_API_BASE.startsWith("/api")).toBe(false);
  });

  it("builds every path under that prefix", () => {
    expect(exerciseUrl("/workspaces/current/events")).toBe(
      "/v1/exercise/workspaces/current/events",
    );
    expect(exerciseUrl("/instructor/datasets", { label: "Autumn", source_filename: undefined })).toBe(
      "/v1/exercise/instructor/datasets?label=Autumn",
    );
  });

  it("sends the literal path to fetch", async () => {
    const spy = stubFetch(jsonResponse({ events: [] }));
    await exerciseRequest("/workspaces/current/events");
    const { url } = lastCall(spy);
    expect(url).toBe("/v1/exercise/workspaces/current/events");
    expect(url).not.toContain("/api/");
  });
});

describe("X-Exercise-Request", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE"])("is sent on %s", async (method) => {
    const spy = stubFetch(jsonResponse({}));
    await exerciseRequest("/workspaces", { method, json: { team_number: 1 } });
    const headers = new Headers(lastCall(spy).init.headers);
    expect(headers.get("X-Exercise-Request")).toBe("1");
  });

  it("is not sent on GET, which the backend does not gate", async () => {
    const spy = stubFetch(jsonResponse({}));
    await exerciseRequest("/workspaces/current");
    const headers = new Headers(lastCall(spy).init.headers);
    expect(headers.get("X-Exercise-Request")).toBeNull();
  });
});

describe("cookies", () => {
  it("sends same-origin credentials, because the cookie is the whole identity", async () => {
    const spy = stubFetch(jsonResponse({}));
    await exerciseRequest("/workspaces/current");
    expect(lastCall(spy).init.credentials).toBe("same-origin");
  });
});

describe("refusals", () => {
  it("carries the server's code and its sentence, unchanged", async () => {
    stubFetch(
      jsonResponse(
        {
          error: {
            code: "exercise_results_rule_not_confirmed",
            message: "The course owner has not confirmed the results rule yet.",
          },
        },
        409,
      ),
    );
    const error = await exerciseRequest("/workspaces/current/events/a/results", {
      method: "POST",
    }).catch((caught: unknown) => caught);

    expect(isRefusal(error)).toBe(true);
    const refusal = error as ExerciseRefusal;
    expect(refusal.status).toBe(409);
    expect(refusal.code).toBe("exercise_results_rule_not_confirmed");
    expect(refusal.message).toBe("The course owner has not confirmed the results rule yet.");
  });

  it("does not leak a non-envelope body as a message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("<html>Traceback…</html>", { status: 500 }))),
    );
    const error = (await exerciseRequest("/workspaces/current").catch(
      (caught: unknown) => caught,
    )) as ExerciseRefusal;
    expect(error).toBeInstanceOf(ExerciseRefusal);
    expect(error.message).not.toContain("Traceback");
  });

  it("turns a transport failure into one sentence, not the underlying error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("NetworkError when attempting to fetch"))),
    );
    const error = await exerciseRequest("/workspaces/current").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ExerciseUnreachable);
    expect((error as Error).message).not.toContain("NetworkError");
  });
});

describe("bodies", () => {
  it("sends JSON with its content type", async () => {
    const spy = stubFetch(jsonResponse({}));
    await exerciseRequest("/workspaces", { method: "POST", json: { team_number: 4 } });
    const { init } = lastCall(spy);
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe('{"team_number":4}');
  });

  it("sends the upload as a raw text/csv body, not multipart", async () => {
    // Design spec §3 "As shipped" (PR #184): the route takes the bytes as the
    // request body with label and source_filename as query parameters, because
    // the repository does not carry `python-multipart`.
    const spy = stubFetch(jsonResponse({}));
    await exerciseRequest("/instructor/datasets", {
      method: "POST",
      rawBody: { body: "profile_no\n1\n", contentType: "text/csv" },
      query: { label: "Autumn" },
    });
    const { url, init } = lastCall(spy);
    expect(url).toBe("/v1/exercise/instructor/datasets?label=Autumn");
    expect(new Headers(init.headers).get("Content-Type")).toBe("text/csv");
    expect(init.body).toBe("profile_no\n1\n");
  });
});
