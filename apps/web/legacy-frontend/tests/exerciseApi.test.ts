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
  NOT_THE_EXERCISE,
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

test("a 200 whose body is not JSON is unreachable, not an empty success", async () => {
  // F2. A dev server that proxies `/api` but not `/v1` answers every exercise
  // call with the SPA's own `index.html` at status 200. This used to return
  // `null as T`, so the HTML travelled on as a `TeamWorkspaceView`, the first
  // property read threw, and react-router rendered the 404 page — with nothing
  // anywhere pointing at the proxy.
  //
  // Fails on the old code: it resolved with `null`, so `assert.ok(error
  // instanceof ExerciseUnreachable)` had `null` to work with and threw.
  answerWith(() => new Response("<!doctype html><title>Smart Match</title>", { status: 200 }));
  const error = await exerciseRequest("/workspaces/current").then(
    () => null,
    (caught: unknown) => caught,
  );
  assert.ok(error instanceof ExerciseUnreachable);
});

test("a 204 is still a success, with no body to parse", async () => {
  answerWith(() => new Response(null, { status: 204 }));
  const answer = await exerciseRequest("/workspaces/current");
  assert.equal(answer, null);
});

test("a refusal that is not the exercise's own does not put its words on screen", async () => {
  // F4. Starlette's own 404 body is `{"detail": "Not Found"}` or plain text,
  // and a CBA-scope deployment answers every `/v1/exercise` call that way
  // because the routers are not registered at all (ADR-0025 D1). Rendering
  // "Not Found" verbatim on a projector is what this stops.
  //
  // Fails on the old code: `refusalFrom` took any `message` string it found,
  // so `refusal.message` was "Not Found" and the assertion below failed.
  answerWith(() =>
    json({ error: { code: "not_found", message: "Not Found" } }, 404),
  );
  const error = (await exerciseRequest("/workspaces/current/events/nope/list").then(
    () => null,
    (caught: unknown) => caught,
  )) as ExerciseRefusal;

  assert.ok(error instanceof ExerciseRefusal);
  assert.equal(error.message, NOT_THE_EXERCISE);
  assert.ok(!error.message.includes("Not Found"));
  // The code is still there to branch on and to read in a console.
  assert.equal(error.code, "not_found");
});

test("the exercise's own sentence is still shown exactly as written", async () => {
  answerWith(() =>
    json(
      {
        error: {
          code: "exercise_event_unknown",
          message: "That event is not in your team's data file.",
        },
      },
      404,
    ),
  );
  const error = (await exerciseRequest("/workspaces/current/events/nope/list").then(
    () => null,
    (caught: unknown) => caught,
  )) as ExerciseRefusal;
  assert.equal(error.message, "That event is not in your team's data file.");
});

test("the shared validation refusal keeps its own plain sentence", async () => {
  // `invalid_request` is the API's shared validation code and its message is
  // written plainly, so it is allowed through with the exercise's own codes.
  answerWith(() =>
    json({ error: { code: "invalid_request", message: "Team number must be between 1 and 6." } }, 422),
  );
  const error = (await exerciseRequest("/workspaces", { method: "POST" }).then(
    () => null,
    (caught: unknown) => caught,
  )) as ExerciseRefusal;
  assert.equal(error.message, "Team number must be between 1 and 6.");
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
