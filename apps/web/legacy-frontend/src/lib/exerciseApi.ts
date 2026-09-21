/**
 * The class exercise's one network boundary.
 *
 * Every call an exercise screen makes goes through this module, and nothing
 * else in the app does. That is not tidiness — it is three rules that each
 * fail silently if a screen is allowed to write its own `fetch`:
 *
 * 1. **The path is literal.** The workspace cookie is set with
 *    `Path=/v1/exercise` and the instructor cookie with
 *    `Path=/v1/exercise/instructor`. A call to `/api/exercise/...` would be
 *    proxied to the same backend and would simply *not carry the cookie*; the
 *    server would answer "enter your team number" to a browser that had, and
 *    nobody would know why. So `EXERCISE_API_BASE` is a constant here,
 *    `exerciseUrl` is the only thing that builds an exercise URL, and
 *    `exerciseApi.test.ts` fails the build on any `/api/` exercise call.
 * 2. **`X-Exercise-Request: 1` is on every mutating call.** The backend's
 *    `require_exercise_request_header` refuses a `POST`/`PUT`/`PATCH`/`DELETE`
 *    without it with `exercise_request_header_required`. It is added here by
 *    method rather than by each caller remembering, because "remembering" is
 *    exactly the thing that does not survive a sixth screen.
 * 3. **A refusal is a sentence, not an exception dump.** Exercise routes
 *    answer `{"error": {"code", "message"}}` where `message` is one plain
 *    sentence written for a projector (`smartmatch_api/exercise_errors.py`).
 *    That sentence is what a screen shows, verbatim; `code` is what a screen
 *    branches on. ADR-0025 D6's implementation note is emphatic that raw
 *    server text must not reach a screen, and this is the layer that makes
 *    "show the server's sentence" the easy path and "show the exception" the
 *    hard one.
 *
 * **Deliberately not `src/lib/api.ts`.** ADR-0025 D1 puts the exercise in its
 * own product scope: in that scope the authenticated CBA routers are not
 * registered at all. An exercise screen that imported the CBA client would
 * pull in the bearer token, the principal and the unit id — none of which
 * exist here — and would make the import graph claim a relationship the two
 * products do not have. `apps/web/DESIGN.md` asks that pages not call `fetch`
 * directly and that transport live at a boundary; this module *is* that
 * boundary, for the second product.
 *
 * **No React Query.** `src/lib/queryClient.ts` keys every entry by principal
 * first and clears on identity change. There is no identity here, and a cache
 * whose isolation rests on a principal would be isolating exercise teams by a
 * value that is always `undefined`. Exercise screens load with
 * `useExerciseResource`, which holds no cache at all: a team's workspace is a
 * server row addressed by a cookie, and re-reading it is one request.
 */

/**
 * The literal prefix every exercise route sits under.
 *
 * Both exercise cookies are path-scoped to this prefix or below it, so this
 * string is not a preference — changing it, or prefixing it with `/api`,
 * stops the cookies being sent at all. Vite's dev server already proxies
 * `/v1` to the API (`vite.config.ts`), so no proxy entry needs adding.
 */
export const EXERCISE_API_BASE = "/v1/exercise";

/** The header the backend requires on every state-changing exercise call. */
export const EXERCISE_REQUEST_HEADER = "X-Exercise-Request";

/** Its only value. The backend checks for presence; `1` is what it documents. */
export const EXERCISE_REQUEST_HEADER_VALUE = "1";

/** The methods `require_exercise_request_header` guards. */
const MUTATING_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Build an exercise URL from a path *relative to the exercise prefix*.
 *
 * Callers pass `/workspaces/current/events`, never `/v1/exercise/...`, so the
 * prefix appears once in this file and nowhere else. Relative to the page
 * origin, per DESIGN.md, so a deployment supplies the origin.
 */
export function exerciseUrl(path: string, query?: Readonly<Record<string, string | undefined>>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) {
      search.set(key, value);
    }
  }
  const suffix = search.toString();
  return `${EXERCISE_API_BASE}${path}${suffix === "" ? "" : `?${suffix}`}`;
}

/**
 * A refusal from an exercise route: its status, its stable code, its sentence.
 *
 * `message` is the server's own sentence and is rendered as-is. Screens branch
 * on `code` — never on the text, which is Ann's wording and may change without
 * any behaviour changing with it.
 */
export class ExerciseRefusal extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ExerciseRefusal";
    this.status = status;
    this.code = code;
  }
}

/**
 * A request that never reached the server, or an answer that was not the
 * envelope. Carries a sentence a participant can act on rather than the
 * underlying error's text, which may be a transport detail or, on a 500, the
 * server's own prose — neither belongs on a projector.
 */
export class ExerciseUnreachable extends Error {
  constructor(message = "The exercise could not be reached. Check the connection and try again.") {
    super(message);
    this.name = "ExerciseUnreachable";
  }
}

/** Narrowing helper, so a screen can branch without `instanceof` noise. */
export function isRefusal(error: unknown): error is ExerciseRefusal {
  return error instanceof ExerciseRefusal;
}

/** The envelope shape `smartmatch_api/errors.py` renders for every refusal. */
interface ErrorEnvelope {
  readonly error?: { readonly code?: unknown; readonly message?: unknown };
}

/**
 * The one sentence shown when the refusal is not the exercise's own.
 *
 * Exported so the screens' own fallbacks read identically — there is exactly
 * one sentence for "this did not work and the reason is not yours to read".
 */
export const NOT_THE_EXERCISE =
  "This part of the exercise is not available at this address. Check the link, or ask your instructor.";

/**
 * Whether a refusal's sentence was written for a class participant.
 *
 * Only the exercise's own codes carry one. `exercise_errors.py` documents the
 * contract: one plain sentence, naming no table, no column and no identifier,
 * for a student in a marketing class to read on a projector. `invalid_request`
 * is the shared validation code and its message is plain too, so it is allowed
 * through.
 *
 * Everything else is somebody else's refusal reaching this code by accident —
 * a Starlette 404 whose whole body is `"Not Found"`, which is what a mistyped
 * event URL produces, and what *every* exercise call produces in a CBA-scope
 * deployment where these routers are not registered at all (ADR-0025 D1).
 * Rendering `Not Found` verbatim on a projector is the failure this guards.
 */
function hasParticipantSentence(code: string): boolean {
  return code.startsWith("exercise_") || code === "invalid_request";
}

function refusalFrom(status: number, payload: unknown): ExerciseRefusal {
  const body = payload as ErrorEnvelope | null;
  const code = typeof body?.error?.code === "string" ? body.error.code : "exercise_unknown_refusal";
  const stated =
    typeof body?.error?.message === "string" && body.error.message.trim() !== ""
      ? body.error.message
      : null;
  if (!hasParticipantSentence(code)) {
    // The code is kept on the object — a screen may still branch on it and a
    // developer may still read it — but it never becomes the text on screen.
    return new ExerciseRefusal(status, code, NOT_THE_EXERCISE);
  }
  return new ExerciseRefusal(status, code, stated ?? "The exercise refused that, and did not say why.");
}

export interface ExerciseRequestOptions {
  readonly method?: string;
  /** Sent as JSON. Use `rawBody` for the instructor upload's `text/csv`. */
  readonly json?: unknown;
  /** A non-JSON body with its own content type — see `uploadDataset`. */
  readonly rawBody?: { readonly body: BodyInit; readonly contentType: string };
  readonly query?: Readonly<Record<string, string | undefined>>;
  readonly signal?: AbortSignal;
}

/**
 * One exercise request, returning the parsed body or throwing a refusal.
 *
 * `credentials: "same-origin"` is stated rather than left to the default: the
 * whole of a team's identity here is a cookie, and a boundary whose most
 * important property is implicit is a boundary that breaks when someone moves
 * it. `"include"` is deliberately *not* used — these calls are same-origin by
 * construction (relative URL, proxied `/v1`), and `include` would start
 * sending the cookie cross-origin if a later deployment moved the API.
 */
export async function exerciseRequest<T>(
  path: string,
  options: ExerciseRequestOptions = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers({ Accept: "application/json" });
  if (MUTATING_METHODS.has(method)) {
    headers.set(EXERCISE_REQUEST_HEADER, EXERCISE_REQUEST_HEADER_VALUE);
  }

  let body: BodyInit | undefined;
  if (options.rawBody !== undefined) {
    headers.set("Content-Type", options.rawBody.contentType);
    body = options.rawBody.body;
  } else if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }

  let response: Response;
  try {
    response = await fetch(exerciseUrl(path, options.query), {
      method,
      headers,
      body,
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ExerciseUnreachable();
  }

  // 204 has no body; every other exercise route answers with one.
  const text = response.status === 204 ? "" : await response.text();
  let payload: unknown = null;
  if (text !== "") {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw refusalFrom(response.status, payload);
  }
  if (response.status !== 204 && payload === null) {
    // A 200 whose body is not JSON is not an exercise response at all. The way
    // this happens is mundane and total: a dev server that proxies `/api` but
    // not `/v1` answers every exercise call with the SPA's `index.html` at
    // status 200, and returning `null as T` from here let that HTML travel on
    // as a `TeamWorkspaceView` — the first property read threw, react-router
    // caught it, and a participant got the 404 page with nothing pointing at
    // the proxy. It stops here, as one sentence.
    throw new ExerciseUnreachable();
  }
  return payload as T;
}
