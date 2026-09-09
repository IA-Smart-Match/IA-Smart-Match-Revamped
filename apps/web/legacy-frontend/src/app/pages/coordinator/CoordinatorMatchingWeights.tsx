/**
 * Matching weights — Speaker Connector portal (customer §13, §5).
 *
 * The panel `docs/plans/open-questions/cba-phase-deferred.md` deferred in
 * writing, built to the four obligations that entry names and to nothing more.
 *
 * ## Nothing on this page prints a registry default
 *
 * The deferral entry's central prohibition: "must not print a registry default
 * as a placeholder — the response's `modes` is where an effective weight comes
 * from, and a placeholder typed into a form would be the duplicated default
 * this whole card exists to prevent."
 *
 * So a factor this unit has not overridden renders as **not set**, with an
 * empty box, and the page says what an empty box means. It does not helpfully
 * fill in the number the registry currently uses, because that number is not
 * this unit's setting and would keep being shown after ADR-0016 revised it.
 * What the registry currently amounts to is beside the form, read out of the
 * server's `modes` — the effective weighting, normalised server-side, rendered
 * here verbatim.
 *
 * There is not a single numeric literal in this file, and
 * `tests/unit/test_frontend_matching_weights_contract.py` refuses one.
 *
 * ## The version round-trips, and a conflict is a person's to resolve
 *
 * `GET` returns the `version` these settings are at; the `PATCH` sends it as
 * `expected_version`. When somebody else saved in between, the server answers
 * `409 matching_weights_stale` and this page stops and says so, keeping what
 * was typed. It does not re-read the version and send again — that is the lost
 * update the refusal exists to prevent, performed politely. Re-reading is a
 * button the Connector presses, and it says what it replaces.
 *
 * ## Nothing is computed here
 *
 * Effective weights per scoring mode are derived on every read and deliberately
 * never stored. This page renders them and does not total them, round them,
 * scale them, or express them as a share of anything. There is no percentage on
 * a CBA surface (OQ-CBA-005), and no scoring in the browser.
 *
 * ## Saving is what the server confirms, and it moves no run
 *
 * The state shown after a save is the response, never the form. A refusal is
 * the server's own message — `invalid_matching_weights` names every offending
 * field at once — and no field is cleared, so nothing typed is lost. And a
 * `match_run` row carries the weights it was scored with: changing a weight
 * here does not re-run or alter any stored match run, which the page states
 * where the Connector saves rather than in a document they will not read.
 *
 * ## A Connector label in this shell is not permission
 *
 * Both routes are `{admin, coordinator}` server-side, authorized per request
 * against the loaded unit. This page renders its controls and shows the
 * server's `403` as the answer it is, rather than hiding a control and
 * implying it does not exist.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Check, ShieldAlert, SlidersHorizontal } from "lucide-react";

import {
  ApiRequestError,
  fetchMatchingWeights,
  updateMatchingWeights,
  type MatchingWeights,
} from "../../../lib/api";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * The form's text, keyed by factor. A key absent from `overrides` starts empty,
 * which is what "this unit has not set one" looks like — and stays empty until
 * a person types.
 */
type DraftOverrides = Record<string, string>;

function draftFrom(weights: MatchingWeights): DraftOverrides {
  const draft: DraftOverrides = {};
  for (const key of weights.configurable_factors) {
    const stored = weights.overrides[key];
    draft[key] = stored === undefined ? "" : String(stored);
  }
  return draft;
}

export function CoordinatorMatchingWeights() {
  // `GET /v1/me` — the only source of who this is.
  useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id. Never composed here.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [weights, setWeights] = useState<MatchingWeights | null>(null);
  const [draft, setDraft] = useState<DraftOverrides>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refused, setRefused] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<MatchingWeights | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const current = await fetchMatchingWeights(unitId);
      setWeights(current);
      setDraft(draftFrom(current));
      setConflict(null);
      setSaveError(null);
      setSaved(null);
      setLoadError(null);
      setRefused(false);
    } catch (cause) {
      if (cause instanceof ApiRequestError) {
        // A refusal is an answer. The server decides, per request, and this
        // page reports what it decided instead of pretending the surface does
        // not exist. `403` is the shape a student or a volunteer gets.
        setRefused(cause.status === 403);
        setLoadError(cause.message);
      } else {
        setLoadError("The weights could not be read and the server gave no reason.");
      }
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Why the button is disabled, in words a person can act on. A courtesy, not a
  // validation: every rule about what a weight may be lives server-side, and
  // the only case declined here is text that cannot be sent as a number at all.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit whose weights it could change.";
    }
    const unreadable = Object.entries(draft)
      .filter(([, text]) => text.trim().length > 0 && Number.isNaN(Number(text.trim())))
      .map(([key]) => key);
    if (unreadable.length > 0) {
      return `These boxes do not hold a number: ${unreadable.join(", ")}.`;
    }
    return null;
  }, [unitId, draft]);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || weights === null || blockingReason !== null || saving) return;

    // The complete override set after the change — the route's semantics, not a
    // patch of a patch. An emptied box is an override cleared, and an empty
    // object returns the unit to the registry's weighting.
    const overrides: Record<string, number> = {};
    for (const [key, text] of Object.entries(draft)) {
      const trimmed = text.trim();
      if (trimmed.length > 0) overrides[key] = Number(trimmed);
    }

    setSaving(true);
    setSaveError(null);
    setConflict(null);
    setSaved(null);
    try {
      const stored = await updateMatchingWeights(unitId, {
        overrides,
        expected_version: weights.version,
      });
      // The response, not the form. Everything shown as saved is a value the
      // server read back out of the committed rows, including its new version.
      setWeights(stored);
      setDraft(draftFrom(stored));
      setSaved(stored);
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.code === "matching_weights_stale") {
        // 409. Nothing was written, nothing typed is thrown away, and this page
        // does not send the change again under a fresher version — that would
        // discard whoever saved in between while reporting success.
        setConflict(cause.message);
      } else if (cause instanceof ApiRequestError && cause.code === "invalid_matching_weights") {
        // 422. The server's message names every offending field at once, so it
        // is shown as written rather than summarised.
        setSaveError(cause.message);
      } else if (cause instanceof ApiRequestError) {
        setSaveError(cause.message);
      } else {
        setSaveError("The weights could not be saved and the server gave no reason.");
      }
    } finally {
      setSaving(false);
    }
  }

  // `CoordinatorPortalLayout` renders `PortalGate` when the server granted no
  // such portal, so reaching here without a grant means the mapping is still
  // resolving.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-8 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Matching weights</h1>
        <p className="text-sm text-muted-foreground">
          What your unit&rsquo;s next match run scores with. Customer §13.
        </p>
      </header>

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there are no weights to show.
        </p>
      ) : null}

      {loadError !== null ? (
        <div className="flex gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
          <ShieldAlert className="mt-1 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
          <div className="space-y-1 text-sm">
            <p className="font-medium text-foreground">
              {refused
                ? "The server did not grant this account these settings."
                : "The weights could not be read."}
            </p>
            <p className="text-muted-foreground">{loadError}</p>
          </div>
        </div>
      ) : null}

      {weights !== null && unitId !== null ? (
        <>
          <section className="space-y-2 rounded-xl border border-border/70 p-5">
            <h2 className="text-lg font-semibold text-foreground">What is in force</h2>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Factor registry</dt>
                <dd className="text-foreground">{weights.registry_version}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Settings version</dt>
                <dd className="text-foreground">
                  {weights.version === null
                    ? "This unit has never configured weights."
                    : weights.version}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Last changed</dt>
                <dd className="text-foreground">
                  {weights.updated_at === null ? "Never" : weights.updated_at}
                </dd>
              </div>
            </dl>
          </section>

          {weights.ignored_factor_keys.length > 0 ? (
            <section className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
              <AlertCircle className="mt-1 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
              <div className="space-y-1 text-sm">
                <p className="font-medium text-foreground">
                  Stored keys the current registry does not use
                </p>
                <p className="text-muted-foreground">
                  Your unit has a weight recorded for these and no scoring model in the
                  registry admits them, so nothing scores with them. The server reports them
                  rather than dropping them silently:{" "}
                  <span className="font-mono text-foreground">
                    {weights.ignored_factor_keys.join(", ")}
                  </span>
                </p>
              </div>
            </section>
          ) : null}

          <form onSubmit={handleSave} className="space-y-4 rounded-xl border border-border/70 p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              Your unit&rsquo;s overrides
            </h2>
            <p className="text-sm text-muted-foreground">
              An empty box is a factor your unit has <strong>not set</strong>: there is no
              stored weight for it anywhere, and it scores at whatever the factor registry
              says today. Emptying a box clears the override rather than storing a zero. This
              page does not fill in the registry&rsquo;s own figure &mdash; that number
              belongs to the registry, and printing it here would be a second copy of it.
            </p>

            <ul className="space-y-3">
              {weights.configurable_factors.map((key) => {
                const text = draft[key] ?? "";
                const stored = weights.overrides[key];
                return (
                  <li key={key} className="grid gap-2 sm:grid-cols-2 sm:items-center">
                    <label htmlFor={`weight-${key}`} className="text-sm text-foreground">
                      <span className="font-mono">{key}</span>{" "}
                      <span className="text-muted-foreground">
                        {stored === undefined ? "(not set)" : "(set by your unit)"}
                      </span>
                    </label>
                    <input
                      id={`weight-${key}`}
                      type="text"
                      inputMode="decimal"
                      value={text}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, [key]: event.target.value }))
                      }
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                    />
                  </li>
                );
              })}
            </ul>

            <p className="text-sm text-muted-foreground">
              Saving changes what your unit&rsquo;s <strong>next</strong> match run scores
              with. It does not re-run anything and does not alter a match run already
              recorded &mdash; every stored run keeps the weights it was scored with.
            </p>

            <button
              type="submit"
              disabled={saving || blockingReason !== null}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save weights"}
            </button>
            {blockingReason !== null ? (
              <p className="text-xs text-muted-foreground">{blockingReason}</p>
            ) : null}

            {conflict !== null ? (
              <div className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
                <AlertCircle className="mt-1 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
                <div className="space-y-2 text-sm">
                  <p className="font-medium text-foreground">
                    Nothing was saved &mdash; somebody else changed these weights first (409
                    matching_weights_stale).
                  </p>
                  <p className="text-muted-foreground">{conflict}</p>
                  <p className="text-muted-foreground">
                    What you typed is still here. Read the current weights, decide what your
                    change should be against them, and save again.
                  </p>
                  <button
                    type="button"
                    onClick={() => void load()}
                    className="rounded-lg border border-border/70 px-3 py-2 text-sm font-medium text-foreground"
                  >
                    Read the current weights (replaces what you typed)
                  </button>
                </div>
              </div>
            ) : null}

            {saveError !== null ? (
              <div className="flex gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
                <ShieldAlert className="mt-1 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
                <div className="space-y-1 text-sm">
                  <p className="font-medium text-foreground">
                    Nothing was saved. The server refused this change
                    (invalid_matching_weights, or the refusal it names below).
                  </p>
                  <p className="text-muted-foreground">{saveError}</p>
                </div>
              </div>
            ) : null}

            {saved !== null ? (
              <div className="flex gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
                <Check className="mt-1 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">
                  Saved by the server at settings version{" "}
                  <span className="text-foreground">{saved.version}</span>. No stored match run
                  changed.
                </p>
              </div>
            ) : null}
          </form>

          <section className="space-y-4 rounded-xl border border-border/70 p-5">
            <h2 className="text-lg font-semibold text-foreground">
              What a run would score with today
            </h2>
            <p className="text-sm text-muted-foreground">
              Worked out by the server for this read, from the registry plus your overrides,
              and stored nowhere. These are shown exactly as they came back.
            </p>
            {weights.modes.map((mode) => (
              <div key={mode.scoring_mode} className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">
                  <span className="font-mono">{mode.scoring_mode}</span>{" "}
                  <span className="font-normal text-muted-foreground">
                    (registry {mode.registry_version})
                  </span>
                </h3>
                <ul className="space-y-1 text-sm">
                  {Object.entries(mode.weights).map(([key, weight]) => (
                    <li key={key} className="flex justify-between gap-4">
                      <span className="font-mono text-muted-foreground">{key}</span>
                      <span className="text-foreground">{weight}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        </>
      ) : null}
    </div>
  );
}
