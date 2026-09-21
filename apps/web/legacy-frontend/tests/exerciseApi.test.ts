/**
 * The three rules `src/lib/exerciseApi.ts` exists to keep, on real calls.
 *
 * Each of them fails *silently* in a classroom if it regresses, and none is
 * visible in a type:
 *
 * - a wrong prefix reaches the same backend carrying no cookie, so every
 *   screen answers "enter your team number" with nothing explaining why;
 * - a missing `X-Exercise-Request` turns every save into a 403;
 * - a refusal rendered as an exception puts server prose on a projector.
 *
 * Runs under `node --test tests/` rather than under Vitest: the module is
 * JSX-free, and `fetch`, `Response` and `Headers` are Node globals, so this
 * needs no DOM and no component runner. The screens' rendered behaviour is
 * asserted in the `*.test.tsx` files beside them.
 */
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  EXERCISE_API_BASE,
  ExerciseRefusal,
  ExerciseUnreachable,
  exerciseRequest,
  exerciseUrl,
  isRefusal,
} from "../src/lib/exerciseApi.ts";

/** Every call the stub saw, in order. */
let calls: { url: string; init: RequestInit }[] = [];
const realFetch = globalThis.fetch;

/** Answer every request with this, and record what was asked. */
function answerWith(make: () => Response): void {
  globalThis.fetch = ((url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(make());
  }) as typeof globalThis.fetch;
}

function failWith(error: Error): void {
  globalThis.fetch = (() => Promise.reject(error)) as typeof globalThis.fetch;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastCall(): { url: string; init: RequestInit } {
  const call = calls.at(-1);
  assert.ok(call !== undefined, "no request was made");
  return call;
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

test("the prefix is the literal /v1/exercise, never an /api path", () => {
  // The workspace cookie is Path=/v1/exercise and the instructor cookie
  // Path=/v1/exercise/instructor. An /api prefix is proxied to the same
  // backend and simply does not carry the cookie.
  assert.equal(EXERCISE_API_BASE, "/v1/exercise");
  assert.equal(EXERCISE_API_BASE.startsWith("/api"), false);
});

test("every path is built under that prefix", () => {
  assert.equal(exerciseUrl("/workspaces/current/events"), "/v1/exercise/workspaces/current/events");
  assert.equal(exerciseUrl(""), "/v1/exercise");
});

test("an undefined query value is omitted rather than sent as the word undefined", () => {
  assert.equal(
    exerciseUrl("/instructor/datasets", { label: "Autumn", source_filename: undefined }),
    "/v1/exercise/instructor/datasets?label=Autumn",
  );
});

test("the literal path is what reaches fetch", async () => {
  answerWith(() => json({ events: [] }));
  await exerciseRequest("/workspaces/current/events");
  assert.equal(lastCall().url, "/v1/exercise/workspaces/current/events");
  assert.ok(!lastCall().url.includes("/api/"));
});

for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
  test(`X-Exercise-Request is sent on ${method}`, async () => {
    answerWith(() => json({}));
    await exerciseRequest("/workspaces", { method, json: { team_number: 1 } });
    const headers = new Headers(lastCall().init.headers);
    assert.equal(headers.get("X-Exercise-Request"), "1");
  });
}

test("X-Exercise-Request is not sent on GET, which the backend does not gate", async () => {
  answerWith(() => json({}));
  await exerciseRequest("/workspaces/current");
  assert.equal(new Headers(lastCall().init.headers).get("X-Exercise-Request"), null);
});

test("the cookie is sent: credentials are stated, not left to a default", async () => {
  answerWith(() => json({}));
  await exerciseRequest("/workspaces/current");
  assert.equal(lastCall().init.credentials, "same-origin");
});

test("a refusal carries the server's code and its sentence, unchanged", async () => {
  answerWith(() =>
    json(
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
  }).then(
    () => null,
    (caught: unknown) => caught,
  );

  assert.ok(isRefusal(error));
  assert.equal(error.status, 409);
  assert.equal(error.code, "exercise_results_rule_not_confirmed");
  assert.equal(error.message, "The course owner has not confirmed the results rule yet.");
});

test("a non-envelope body does not become the message shown on screen", async () => {
  // ADR-0025 D6's implementation note: raw server text must not reach a
  // screen. A 500 whose body is an HTML error page is exactly that case.
  answerWith(() => new Response("<html>Traceback (most recent call last)…</html>", { status: 500 }));
  const error = (await exerciseRequest("/workspaces/current").then(
    () => null,
    (caught: unknown) => caught,
  )) as ExerciseRefusal;
  assert.ok(error instanceof ExerciseRefusal);
  assert.ok(!error.message.includes("Traceback"));
});

test("a transport failure becomes one sentence, not the underlying error", async () => {
  failWith(new TypeError("NetworkError when attempting to fetch resource"));
  const error = (await exerciseRequest("/workspaces/current").then(
    () => null,
    (caught: unknown) => caught,
  )) as Error;
  assert.ok(error instanceof ExerciseUnreachable);
  assert.ok(!error.message.includes("NetworkError"));
});

test("a JSON body is sent with its content type", async () => {
  answerWith(() => json({}));
  await exerciseRequest("/workspaces", { method: "POST", json: { team_number: 4 } });
  assert.equal(new Headers(lastCall().init.headers).get("Content-Type"), "application/json");
  assert.equal(lastCall().init.body, '{"team_number":4}');
});

test("the upload is a raw text/csv body, not multipart", async () => {
  // Design spec §3 "As shipped" (PR #184), confirmed by the owner on
  // 2026-09-21: the route takes the bytes as the request body, with the label
  // and the file name as query parameters, because the repository does not
  // carry `python-multipart`.
  answerWith(() => json({}));
  await exerciseRequest("/instructor/datasets", {
    method: "POST",
    rawBody: { body: "profile_no\n1\n", contentType: "text/csv" },
    query: { label: "Autumn" },
  });
  assert.equal(lastCall().url, "/v1/exercise/instructor/datasets?label=Autumn");
  assert.equal(new Headers(lastCall().init.headers).get("Content-Type"), "text/csv");
  assert.equal(lastCall().init.body, "profile_no\n1\n");
});
