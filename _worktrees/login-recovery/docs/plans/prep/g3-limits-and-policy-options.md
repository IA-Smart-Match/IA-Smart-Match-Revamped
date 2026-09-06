# G3 limits, ceilings, and policy options — proposed values for owner approval

**Status:** DRAFT — proposed values for owner approval; **not a decision; changes no code.**
**Date:** 2026-08-29 · **Branch:** `friday-deliverable-828`
**Feeds:** the G3 decision artifact required by plan P6
(`docs/plans/2026-08-28-g3-events-s3-s5-plan.md`), specifically the stop-gate's
required-non-blank sections *extraction limits (pages, depth, bytes, wall time)*,
*per-run/per-tenant rate and cost ceilings*, and *human escalation behavior*.
**Also answers:** open questions 7, 8, and 10 of
`docs/plans/prep/campus-event-discovery-capability.md` §8.

**This document authorizes nothing.** No allowlist entry, no vocabulary term, no
provider, no route, no outbound message, no live fetch. Every number below is a
**proposal** carrying its reasoning, presented so the program owner can
**approve, amend, or reject** it in place. A number the owner has not ratified is
not a limit; it is a suggestion in a markdown file.

**Sibling prep documents** (owned by other authors, not modified here):
`docs/plans/prep/g3-allowlist-candidates.md`,
`docs/plans/prep/g3-eval-and-vocabulary-candidates.md`,
`docs/security/r3-technical-review-findings.md`.

## How to use this document

Each table has an **Owner decision** column. Write `approve`, or write the value
you want instead. A row left blank is a blank section in the G3 artifact, and the
stop-gate reads a blank section as *stop and report*.

---

## 0. What was verified in the code, and what follows from it

Read during preparation (paths so each claim is re-checkable):

- `services/worker/smartmatch_worker/handlers.py` — the failure taxonomy is
  **real and already exactly the shape this design needs**. `HandlerFailure` is
  the base; `ProviderFailure` → `failed_provider` (*re-drivable*),
  `PolicyFailure` → `failed_policy` (*terminal*), `BudgetFailure` →
  `failed_budget` (*terminal*). Each carries a `reason: str` — "a stable
  machine-readable label, recorded on the job's failure event" — with a
  `default_reason` class var (`"budget_failure"`, `"policy_failure"`,
  `"provider_failure"`) that a raiser may override with something more specific.
  `BudgetFailure`'s own docstring already states the escalation logic verbatim:
  *"Retrying against a ceiling burns attempts and changes nothing; the ceiling
  has to move first, and that is a decision, not a retry."*
- `services/worker/smartmatch_worker/execution.py` — `_FAILURE_STATES` maps
  those three classes to `JobState.FAILED_POLICY` / `FAILED_BUDGET` /
  `FAILED_PROVIDER`, resolved along the exception MRO, so **a new subclass of
  `BudgetFailure` inherits `failed_budget` without touching the map**.
  `_UNEXPECTED_FAILURE_STATE = JobState.FAILED_PROVIDER` — an unclassified
  exception is re-drivable by design.
- `python/smartmatch_domain/smartmatch_domain/jobs.py` — `JobState` has
  `queued, dispatched, running, succeeded, partial, failed_provider,
  failed_budget, failed_policy, cancelled, timed_out, redrive_pending,
  abandoned`. `TRANSITIONS` allows `failed_provider → {queued, redrive_pending}`
  and `timed_out → {queued, redrive_pending}`; `failed_budget` and
  `failed_policy` have **empty** transition sets and are in `TERMINAL_STATES`.
- `HandlerResult.state` accepts only `succeeded` or `partial` — "a handler
  reports failure by raising". **`partial` already exists** and is the state a
  budget-truncated run's *retained* work belongs in, except that a raise
  bypasses it (see §4.4, the one genuine gap).
- `services/worker/smartmatch_worker/config.py` + `smartmatch_persistence.jobs`
  — `DEFAULT_JOB_LEASE = timedelta(minutes=10)`; `job_lease_seconds` "**bounds
  silence, not duration** … a handler that emits progress is never swept however
  long it runs". This directly constrains the wall-time proposal in §1.
- `python/smartmatch_domain/smartmatch_domain/events.py` —
  `resolve_identity_key(*, host_org_unit, title, event_time)` requires
  `host_org_unit` non-blank (`_require_non_blank`) and returns `None` for
  unresolved time. **It keys on host org unit, not source domain** — so an
  unmapped org unit does not merely lose a label, it makes the key uncomputable
  and deduplication impossible (§5).
- `python/smartmatch_persistence/smartmatch_persistence/schema.py` — the only
  review queue that exists is `review_item`, whose composite FK is to
  `import_batch` and whose `ck_review_item_status` CHECK is
  `status IN ('pending','accepted','rejected')`. **There is no crawl-scoped
  review queue today.**
- `docs/architecture/decisions/ADR-0006-…` — `rate_limit_counter` keyed
  `(tenant_id, subject, operation, window_start)`, consumed with one
  `INSERT … ON CONFLICT … DO UPDATE … RETURNING` statement, no read-then-write
  window. This is reusable machinery for per-host politeness (§2).
- `docs/architecture/decisions/ADR-0011-accountable-numbers.md` rules 2 and 3 —
  the constraint on a numeric confidence score (§6).
- `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` stop-gate — what a
  score-shaped output would inherit (§6).

**Headline:** the failure taxonomy the research document recommends
(`BudgetFailure` → `failed_budget`, terminal, escalate) is **two-thirds already
built**. `BudgetFailure` and `failed_budget` exist with exactly the intended
semantics. **"Escalate" does not exist anywhere** — grep for `escalat` across
`services/worker/` returns nothing — and neither does a review queue a crawl job
could escalate *into*. §4 says precisely what must be created.

---

## 1. Extraction limits

Scope: one execution of the proposed `discover_events` durable command for one
allowlisted source (a host plus its approved path patterns).

The sizing intuition throughout: **a university department events calendar is
tens of pages, not thousands.** A central university calendar's `.ics` feed is a
single file. A department seminar-series page is one listing plus a few dozen
detail pages. Any job that finds itself fetching 500 pages from a campus host has
not found a richer calendar — it has fallen into a pagination loop, a session-id
URL space, or a link farm, and the correct outcome is to stop and tell a human.

| # | Limit | Proposed value | Reasoning | Failure mode it prevents | Owner decision |
|---|---|---|---|---|---|
| L1 | **Max pages per job** | **50** fetches | A central calendar is 1 feed; a department listing plus its detail pages is realistically 20–40. 50 leaves headroom for the largest plausible legitimate source and is still small enough that a human can read the whole audit trail for one job. | Pagination/calendar-navigation loops (`?date=2027-04-01`, `?date=2027-04-02`, … forever); crawler-trap link farms; unbounded spend on one host. | |
| L2 | **Max crawl depth** | **2** hops from the seed URL | Depth 0 = the allowlisted seed (feed or listing); 1 = a listing page it paginates to; 2 = an individual event detail page. Every legitimate Tier-1/Tier-2 shape in the research doc §2 is reachable in ≤2. Depth 3+ is where you leave the calendar and enter the whole site. | Drifting off the events section into the rest of the university web estate; exponential fan-out (50 links × 50 links); fetching content nobody approved for this purpose. | |
| L3 | **Max bytes per response** | **5 MiB**, enforced as a **streaming cap** (abort mid-read, never buffer-then-check) | An HTML events page is typically 50 KB–1 MB; a large `.ics` feed for a whole university year is a few MB. 5 MiB clears real content with margin. The *streaming* part is the control: a limit checked after `read()` has already allocated the body is not a limit. | Threat **T-04 (response bomb)**. Decompression bombs, infinite `chunked` responses, a misconfigured endpoint streaming a database dump, worker OOM. | |
| L4 | **Max total bytes per job** | **100 MiB** across all responses | Deliberately **less than L1 × L3** (50 × 5 MiB = 250 MiB). A job may have one or two large feeds *or* many small pages, not fifty maximal ones. 100 MiB is ~2× the largest realistic legitimate job. | Death by a thousand legal-sized responses — every response passes L3 and the job still exhausts memory, disk, and egress. | |
| L5 | **Max wall time per job** | **300 s (5 min)** hard ceiling; **emit a progress event at least every 60 s** | Must sit **well inside** `DEFAULT_JOB_LEASE = 10 min` (`smartmatch_persistence/jobs.py:76`). Critically, that lease **bounds silence, not duration** (`config.py`), so the 60 s progress emission — not the 300 s cap — is what keeps the J9 stalled-job sweep from timing out live work. At the L11 politeness rate, 300 s comfortably covers 50 pages. | A hung TLS handshake or a slow-loris server pinning a worker slot; the J9 sweep marking a healthy job `timed_out` and discarding its outcome. | |
| L6 | **Max redirect hops** | **3** | A legitimate campus redirect chain is short: `http→https`, `bare→www`, maybe one canonical-path rewrite. Three covers all of them. **Every hop re-validates the allowlist and re-checks the resolved address** — this is the count, not the policy; the policy is threat **T-03**. | Threat **T-03 (redirect chain to internal)** and **T-02 (DNS rebinding)**: an allowlisted host 302-ing into `169.254.169.254` or an internal service. Also redirect loops. | |
| L7 | **Connect timeout** | **5 s** | A reachable public host completes a TCP+TLS handshake in well under a second from a cloud region. Five seconds is generous for a slow campus host and short enough that a black-holed address fails fast rather than eating the L5 budget. | Connections to firewalled/black-holed addresses hanging until the wall-time ceiling, converting one bad URL into a whole wasted job. | |
| L8 | **Read timeout (per socket read)** | **15 s** | Per-read, not total: a large `.ics` that streams slowly is fine as long as bytes keep arriving. Fifteen seconds of *no bytes at all* from a public web server means it is not coming. | Slow-loris / trickle responses that never exceed L3 or L4 but consume all of L5. | |
| L9 | **Total time per single fetch** | **30 s** (connect + read + parse) | The backstop for L7/L8: a server that sends one byte every 14 s passes L8 forever. A per-fetch total makes that terminate. | The composed pathology L7 and L8 each individually permit. | |
| L10 | **Max extraction artifacts per page** | **200** candidate events | A department listing page with more than 200 events on it is a full-year archive dump, not a "what's coming up" page — worth a human look before ingesting. | Unbounded parse output from one malformed or hostile page flooding the event table and the review queue in a single job. | |

**Two structural notes for the R3 reviewer** (this document does not sign
anything): L3–L5 and L9 must be enforced in the **fetch layer**, before any
parser sees a byte, because threat **T-05 (parser escape)** assumes the parser is
the untrusted boundary. And **every one of L1–L10 needs a denial test** — P6's
evidence ladder item 4 requires that "every control named in the signed threat
model has a denial test (blocked address, redirect escape, size/time overrun,
tool outside allowlist)".

---

## 2. Rate and politeness

A crawler's rate limit is not primarily a cost control. It is how the system
avoids being a nuisance on somebody else's server — a server belonging to an
institution this program wants a *relationship* with. Being blocked by a campus
network is a far more expensive outcome than a slow refresh.

| # | Control | Proposed value | Reasoning | Owner decision |
|---|---|---|---|---|
| L11 | **Requests per host per minute** | **10/min** (i.e. a minimum **6 s** interval between requests to one host) | Deliberately slower than a human clicking through a calendar. Campus calendars change on the scale of days; there is no product reason to go faster. At 10/min a full 50-page job takes ~5 min, which is exactly why L5 is 300 s. | |
| L12 | **Concurrency per host** | **1** | Sequential per host, always. Concurrency against one host is where politeness and the per-host rate limit both quietly break, and it buys nothing when the host has ≤50 pages. | |
| L13 | **Global outbound concurrency** | **4** distinct hosts in flight | Throughput comes from *breadth* (many hosts, one connection each), never depth. Four is a starting value tied to worker instance sizing; raise it only with a measured reason. | |
| L14 | **Minimum interval between jobs against the same host** | **6 h** | Independent of the per-run budget, and enforced **across jobs**, so scheduling three jobs for one campus does not produce three times the load. Combined with conditional requests (§3), a same-day re-run is nearly free anyway. | |
| L15 | **Backoff on 429 / 503** | Honor `Retry-After` when present. Otherwise exponential from **30 s**, doubling, **max 3 attempts** per host per job, capped at **300 s**. After the third: **abandon that host for the run** and raise `ProviderFailure` (re-drivable). | A 429 is the server explicitly asking for less. Ignoring `Retry-After` while calling yourself a polite crawler is not defensible. `ProviderFailure` (not `BudgetFailure`) because "the host was busy" genuinely may succeed later — matching the taxonomy's own words: "outages, timeouts against a provider, and anything else where the same command might succeed later". | |
| L16 | **Backoff on 403 / 401** | **Zero retries.** Stop the host immediately; raise `PolicyFailure` with `reason="host_refused"`; the host goes to the human queue for allowlist re-review. | A 403 is a refusal, not congestion. Retrying a refusal is how a crawler earns a network-level ban. Terminal is correct: nothing changes on re-drive; a human must decide whether the host stays on the allowlist. | |
| L17 | **`robots.txt`** | **Fetch before the first request to any host; honor `Disallow` for our declared User-Agent and for `*`; cache 24 h; a fetch failure means DENY the host for this run.** | Fail-closed matches the repo's stated rule for configuration ("a missing setting must degrade towards refusal, never towards access" — `config.py`). A crawler that treats an unreachable `robots.txt` as permission has inverted the whole point. | |
| L18 | **`Crawl-delay`** | **Honor it, and take `max(Crawl-delay, 6 s)`** — the directive can only make us slower, never faster. | Some campus hosts publish `Crawl-delay: 1`. Letting a remote file *raise* our request rate would let a target (or an attacker who controls a target's file) dictate our resource use. One-directional is the safe reading. | |
| L19 | **User-Agent identification** | A **fixed, honest, contactable** UA string. Proposed shape: `IAWestEventDiscovery/0.1 (+https://<ia-west-domain>/crawler; contact: <role-address>@<domain>)` | See below. | |
| L20 | **UA rotation / evasion** | **Forbidden.** One UA string, no rotation, no browser impersonation, no proxy rotation, no ignoring a block. | Also forbidden: rotating source IPs or domains to evade a block. §6.2 of the research doc already bans the outreach equivalent; the discovery equivalent belongs in the G3 artifact for the same reason. | |

### Why the User-Agent must identify the organization

This is a policy point, not a technical one, and it is worth stating in the
artifact rather than leaving to an implementer's default:

1. **A site operator must be able to find out who we are and ask us to stop.**
   A contact URL in the UA is the only channel a sysadmin has that does not
   involve blocking us first and finding out later. An organization that wants to
   *partner* with these campuses (research doc §2, Tier 2: "ask the campus")
   cannot simultaneously be an anonymous unidentified crawler in their logs.
2. **It makes `robots.txt` compliance meaningful.** `robots.txt` is addressed to
   named agents. A crawler that will not say its name cannot honestly claim to
   honor a directive aimed at it.
3. **It is the difference between "polite automated fetching" and "evasion."**
   Impersonating a browser is an affirmative choice to be hard to identify. Every
   subsequent conversation about this system's legitimacy goes worse if that
   choice is in the code.
4. **It is cheap and it is reversible.** If a host blocks the UA, that is
   *information* the program wanted anyway: that host does not consent, and the
   right response is to ask them, not to disguise ourselves.

**Interaction with the threat model.** `docs/security/crawler-threat-model-draft.md`
scopes these controls as follows, and the R3 reviewer should confirm each:

- **T-08 (cost runaway)** — L11–L15 are the *rate* half; §3 is the *cost* half.
  The threat model's stated expectation is "budget exceeded → quarantine", which
  §4 makes precise.
- **T-04 (response bomb)** — L3/L4 with a streaming cap.
- **T-03 / T-02 / T-01** — L6's hop count is the *bound*; the per-hop allowlist
  and address revalidation are the *control*, and they belong to R3, not here.
- **T-06 (credential leakage)** — the UA carries a role address, never a personal
  one, and never a token. No credential may ever appear in a URL or a log line.
- **Not covered by any existing threat entry:** L17's fail-closed `robots.txt`
  and L20's no-evasion rule are *policy* controls with no T-number. **Proposal:
  add them to the threat model as a new entry (T-11, "evasion of a host's stated
  access policy") before R3 signature**, so they get a denial test like every
  other control.

---

## 3. Cost ceilings

### 3.1 The shape of the cost, and why the cascade dominates it

The research doc §3.1 defines a strict four-tier cascade. Its cost consequence
deserves stating as arithmetic rather than as a preference:

| Tier | What it is | Marginal cost per page |
|---|---|---|
| 1 | Official feed (`.ics` / RSS / documented JSON) | **$0** — bandwidth only. Deterministic parse. |
| 2 | `schema.org` JSON-LD / microdata on an allowlisted page | **$0** — bandwidth only. Deterministic parse. |
| 3 | Prose page → **LLM extraction** | **~$0.035** (assumption A3 below) |
| 4 | Search API → host proposals for a human | **~$0.008/query** (A2), and **never per event** — seeding only |

Tier 4 is not in the per-refresh path at all under the cascade: search proposes
*hosts to allowlist*, which is a human, occasional activity. So the entire
variable cost of a refresh is **tier-3 pages** — which makes "what fraction of
pages fall to tier 3" the single most important cost lever in the design, far
more than any price negotiation.

That is also why **conditional requests are a cost control, not an optimization**
(research doc §3.3): an `ETag`/`If-Modified-Since` 304, or an unchanged content
hash, short-circuits extraction entirely and costs $0 even on a tier-3 page.

### 3.2 Arithmetic assumptions (all marked; none verified by a network call)

- **A1 — Institution set:** **N = 10** institutions, **~12 allowlisted sources
  each = 120 sources**. *(Placeholder. Open question 1 owns the real list.)*
- **A2 — Search API price:** **$0.008 per query**. *(Order-of-magnitude only, from
  general knowledge of search-API list pricing; **not verified**, and it barely
  matters because search is not in the refresh path.)*
- **A3 — LLM extraction price:** **$0.035 per prose page**, from ~8,000 input
  tokens (a trimmed page) at ~$3/M and ~600 output tokens at ~$15/M ≈ $0.024 +
  $0.009. *(Mid-tier frontier model list pricing, from general knowledge, **not
  verified**. Confirm against the actual provider and the actual chosen model
  before this number is ratified.)*
- **A4 — Tier mix:** **60%** of pages resolve at tier 1, **20%** at tier 2,
  **20%** at tier 3. *(This is the number most worth **measuring** rather than
  assuming — the research doc §3.2 calls the measurement "a good first card",
  and Stage 0's source-structure survey produces it. If tier 3 turns out to be
  50%, every figure below multiplies by 2.5.)*
- **A5 — Pages per source per full pass:** **30** (well inside L1 = 50).
- **A6 — Change rate between weekly refreshes:** **10%** of pages return changed
  content; 90% are a 304 or an unchanged content hash. *(Campus calendars change
  slowly; verify from real `ETag` behavior once a pilot host is authorized.)*

### 3.2a Correction — assumptions re-derived after the CPP source survey (2026-08-29)

**Added after §3.2 was written.** Two inputs changed on 2026-08-29: the program
owner set scope to **Cal Poly Pomona only**, and a desk survey verified which CPP
sources are actually structured (recorded at §8 of
`g3-allowlist-candidates.md`). A1 and A4 were placeholders; they now have
better values, and one *structural* error in the model is corrected here.

**The structural error: feed and API sources do not cost per page.**
A5 prices "30 pages per source per pass," which is right for prose crawling and
wrong for a feed. One request to `asi.cpp.edu/wp-json/tribe/events/v1/events`
returns *many* events. Tier-1 sources therefore contribute approximately **zero**
LLM cost and a handful of fetches, not thirty. The original worked example
applied a per-page price to sources that are not paginated in that sense.

Revised assumptions, replacing A1/A4/A5 for the CPP-only scope:

- **B1 — Institution set:** **N = 1** (Cal Poly Pomona), **~6 allowlisted hosts**.
- **B2 — Feed/API hosts:** `asi.cpp.edu`, `cpp.libcal.com`,
  `events.vtools.ieee.org` — few requests each, **0 LLM calls**.
- **B3 — Structured aggregators:** `devpost.com`, `mlh.io`, Eventbrite —
  structured access, **~0 LLM calls**. *(Not re-verified in the survey pass.)*
- **B4 — Prose pages:** `www.cpp.edu` department pages, **~30 per full pass** at
  tier 3. *(The only real LLM cost in the CPP corpus.)*
- A2, A3, A6 carry forward unchanged and remain **unverified**.

Revised figures, at A3's unverified $0.035 per prose page:

| Pass | Calculation | Cost |
|---|---|---|
| Full cold pass | 30 prose pages × $0.035 | **≈ $1.05** |
| Warm weekly refresh (A6: 10% changed) | 3 prose pages × $0.035 | **≈ $0.11** |

Against §3.3's original placeholder figures (≈$25 cold, ≈$2.50 warm at N=10),
this is roughly a **24× reduction** — most of it from the scope decision, the
remainder from the per-page/per-feed correction above.

> **A ceiling conflict this surfaces.** Proposed ceiling **L21 is $1.00 per
> job**, and a full cold pass now prices at **≈$1.05**. A cold pass would trip
> its own ceiling. Either raise L21, or split the cold pass across jobs per
> source — the latter is preferable, since it also bounds blast radius per host.
> **This needs an owner decision before the numbers are ratified.**

The tier mix that A4 called "the number most worth measuring" has now been
measured for one institution, by observation rather than assumption: at CPP the
university-wide calendar is **tier 1**, and prose is confined to department
pages. What remains genuinely unmeasured is the *yield* — what fraction of those
tier-1 events are speaking opportunities at all. Early indication from ASI is
**low** (observed entries include SCUBA training and recreational volleyball),
which argues the eligibility rubric will do real work rather than rubber-stamp.

### 3.3 Worked example

**Cold refresh (first pass, no cache):**

```
sources                 = 10 institutions x 12 sources     =   120
pages fetched           = 120 x 30 (A5)                    = 3,600
tier-3 prose pages      = 3,600 x 20% (A4)                 =   720
LLM spend               = 720 x $0.035 (A3)                = $25.20
search spend            = $0 (seeding only, not per-refresh)
------------------------------------------------------------------
COLD FULL REFRESH                                          ~ $25
```

**Warm weekly refresh (conditional requests + content hashing):**

```
pages fetched           = 3,600  (cheap: 304s and unchanged hashes)
pages actually changed  = 3,600 x 10% (A6)                 =   360
tier-3 among those      = 360 x 20% (A4)                   =    72
LLM spend               = 72 x $0.035                      =  $2.52
------------------------------------------------------------------
WARM WEEKLY REFRESH                                        ~ $2.50
ANNUAL (52 warm passes + 1 cold)                           ~ $156
```

**Contrast — the legacy shape (search-first, LLM every page, no caching):**

```
every page to the model = 3,600 x $0.035                   = $126.00
plus a search query per source, every pass  = 120 x $0.008 =   $0.96
per pass, every pass, cached never                         ~ $127
ANNUAL (52 passes)                                         ~ $6,600
```

**The cascade plus conditional requests is roughly a 50x reduction on the steady
state** ($2.50 vs $127 per weekly pass), for the same coverage — and the tier-1
and tier-2 fractions are also the *higher-quality* extractions, with no
hallucination surface. That is the whole argument for the cascade in one number.

### 3.4 Proposed ceilings

| # | Ceiling | Proposed value | Reasoning | Owner decision |
|---|---|---|---|---|
| L21 | **LLM spend per job** | **$1.00** | A single-source job at A3–A5 costs ~$0.21 (30 pages × 20% × $0.035). $1.00 is ~5× the expected worst case for one source — enough headroom for a prose-heavy host, tight enough that a runaway loop stops in seconds. | |
| L22 | **LLM calls per job** | **150** | A count ceiling as well as a dollar ceiling, because a model price change silently moves a dollar-only limit. 150 ≈ 3× the L1 page cap. | |
| L23 | **Search-API queries per job** | **0 in an ingest job** | Structural, not budgetary: under the cascade a `discover_events` job never queries search. Host seeding is a **separate command with its own ceiling (L24)** so the two budgets can never be confused. | |
| L24 | **Search-API queries per seeding run** | **50 queries**, ≈ **$0.40** (A2) | A seeding run proposes hosts for a human to allowlist. 50 queries is far more than a human will review in one sitting, so the *human* is the real ceiling; this just bounds the accident. | |
| L25 | **Per-tenant LLM spend per day** | **$25.00** | ~One full cold refresh of the entire A1 institution set per day. If a tenant is spending more than a complete from-scratch rebuild every day, something is wrong and a human should know before the money is gone. | |
| L26 | **Per-tenant LLM spend per calendar month** | **$250.00** | ~10 cold refreshes' worth, against an expected steady state of ~$11/month (4 warm passes). ~20× expected — a genuine circuit breaker, not a throttle that fires in normal operation. | |
| L27 | **Per-tenant fetches per day** | **5,000** | ~1.4 full cold refreshes of the whole set (3,600). Bounds bandwidth and, more importantly, bounds how much load this system can put on other people's servers in a day even if every other limit is misconfigured. | |
| L28 | **Global kill switch** | **A single configuration flag that disables all discovery commands for all tenants, checked at handler entry, defaulting to DISABLED.** | `BudgetFailure`'s docstring already says it covers "a spend ceiling **or kill switch**" — the taxonomy anticipates this. Default-disabled matches the repo's fail-closed configuration rule. Also the only control that helps at 3 a.m. | |

**Ceiling semantics (proposal).** ADR-0015 establishes *charge-quota-before-refusal*
for rate limiting. For **cost**, propose the opposite ordering: **reserve before
spend, reconcile after.** Estimate a call's cost, reserve it against the ceiling,
make the call, then true up to the actual. A ceiling checked only *after* the
spend is a ceiling that is always exceeded by exactly one call — tolerable at
$0.035, not tolerable if a future extractor call is $5. *This is an ADR-0015
divergence and needs explicit owner and architect assent, not a silent choice.*

---

## 4. Exceed behavior and human escalation

This is the section the stop-gate names as *"human escalation behavior"*. It must
be non-blank, and it must be specific enough that an implementer has no
discretion left.

### 4.1 The disposition table

Grounded in the real taxonomy: `HandlerFailure` subclasses in
`services/worker/smartmatch_worker/handlers.py`, mapped by `_FAILURE_STATES` in
`execution.py` to `JobState` members from
`python/smartmatch_domain/smartmatch_domain/jobs.py`.

| Limit exceeded | Proposed exception | Proposed `reason` | Job state | Terminal? | Human queue? | Owner decision |
|---|---|---|---|---|---|---|
| L1 pages | `BudgetFailure` | `page_limit_exceeded` | `failed_budget` | **Yes** | **Yes** | |
| L2 depth | `BudgetFailure` | `depth_limit_exceeded` | `failed_budget` | **Yes** | Yes | |
| L3 response bytes | `BudgetFailure` | `response_size_exceeded` | `failed_budget` | **Yes** | **Yes — and flag to security**: T-04 | |
| L4 job bytes | `BudgetFailure` | `job_size_exceeded` | `failed_budget` | **Yes** | Yes | |
| L5 wall time | `BudgetFailure` | `wall_time_exceeded` | `failed_budget` | **Yes** | Yes | |
| L6 redirect hops | `PolicyFailure` | `redirect_limit_exceeded` | `failed_policy` | **Yes** | **Yes — security review**: T-03 | |
| Redirect leaves allowlist / resolves private | `PolicyFailure` | `allowlist_violation` / `blocked_address` | `failed_policy` | **Yes** | **Yes — security, high priority**: T-01/T-02 | |
| L7/L8/L9 timeouts | `ProviderFailure` | `fetch_timeout` | `failed_provider` | **No — re-drivable** | Only after re-drive exhaustion | |
| L10 artifacts/page | `BudgetFailure` | `artifact_limit_exceeded` | `failed_budget` | **Yes** | Yes | |
| L15 429/503 after backoff | `ProviderFailure` | `host_unavailable` | `failed_provider` | **No** | Only after exhaustion | |
| L16 403/401 | `PolicyFailure` | `host_refused` | `failed_policy` | **Yes** | **Yes — allowlist re-review** | |
| L17 `robots.txt` disallow or unfetchable | `PolicyFailure` | `robots_denied` / `robots_unavailable` | `failed_policy` | **Yes** | Yes (`robots_denied` may be a *permanent* allowlist removal) | |
| L21/L22 LLM ceiling | `BudgetFailure` | `llm_budget_exceeded` | `failed_budget` | **Yes** | Yes | |
| L25/L26/L27 tenant ceiling | `BudgetFailure` | `tenant_budget_exceeded` | `failed_budget` | **Yes** | **Yes — program owner, not just operator** | |
| L28 kill switch engaged | `BudgetFailure` | `discovery_disabled` | `failed_budget` | **Yes** | No (expected state) | |
| Org unit unmappable (§5) | *not a job failure* | — | job continues | — | **Yes — per-event review row** | |
| Unmapped tag | *not a job failure* | — | job continues | — | **Yes — quarantine (T-09)** | |
| `UnresolvedTime` | *not a job failure* | — | job continues | — | Yes — no identity key, unpublishable (T-10, ADR-0010) | |

**Verifying the research doc's recommendation.** It recommends `BudgetFailure` →
`failed_budget`, terminal, escalate. **The first two exist today, exactly as
described and with matching semantics; "escalate" does not exist at all.**
Specifically:

- ✅ `BudgetFailure` exists (`handlers.py`), exported in `__all__`, documented as
  "a spend ceiling or kill switch stopped the work".
- ✅ `failed_budget` exists (`JobState.FAILED_BUDGET`) and **is genuinely
  terminal** — `TRANSITIONS[JobState.FAILED_BUDGET] == frozenset()`, so it is in
  `TERMINAL_STATES` and cannot even be re-driven by mistake. The state machine
  enforces "the ceiling has to move first"; it is not a convention.
- ✅ The `reason` field already exists for the per-limit labels proposed above,
  and is explicitly designed for exactly this ("so a consumer can branch on the
  kind of failure without parsing prose").
- ✅ Adding `class ExtractionBudgetFailure(BudgetFailure)` would work without
  touching `_FAILURE_STATES`, because `_state_for` resolves along the MRO. *(But
  see the deliberate warning at `execution.py:613` about a subclass landing in
  the wrong bucket — any new subclass needs a test asserting its state.)*
- ❌ **"Escalate" is not implemented.** No escalation function, no operator
  queue, no notification, no `escalat*` symbol anywhere under `services/worker/`.
- ❌ **There is no review queue a crawl job can escalate into.** `review_item`
  (`schema.py:548`) has a **composite FK to `import_batch`** and a status CHECK of
  `('pending','accepted','rejected')`. It is structurally an *import* artifact.
  A crawl escalation is not an import batch and must not be forced into one.

### 4.2 What must be created (proposal, not a decision)

1. **A review target for crawl escalations.** Two options for the owner:
   (a) a new `discovery_review_item` table scoped to a job rather than a batch;
   or (b) generalize `review_item`'s parent from `import_batch` to a nullable
   discriminated source. **Recommend (a)** — generalizing a table whose FK is
   `ondelete="CASCADE"` from `import_batch` risks the existing import path, and
   the two queues have genuinely different columns (a review item holds
   `row_data` from a validated import; a discovery item holds an event candidate
   plus provenance plus the fired-limit reason). This is a **migration**, so it
   belongs in the portfolio's serial migration queue alongside S3/S5f/S5m — it is
   **not free**, and the owner should see that cost before approving.
2. **An escalation write that is atomic with the failure.** The escalation row
   must be written on `CommandContext.session` so it commits with the terminal
   transition — the executor "commits it only with an applied terminal
   transition". **Caution:** on the failure path the executor's handling of the
   business session must be checked before relying on this; if a raise rolls the
   session back, the escalation must instead go through `context.emit`, which
   writes "one job event **immediately, in its own transaction**". **Verify
   before implementing; do not assume.**
3. **Nothing else.** No new job state, no new transition, no change to
   `_FAILURE_STATES`, no change to the dispatcher. The state machine is
   sufficient as it stands.

### 4.3 What the operator sees (proposal)

For every escalated job, one queue entry showing: job id and tenant; the command
and its payload; the **`reason` label** and its human sentence; the terminal
`JobState`; the source URL(s) and the **last URL attempted** when a limit fired;
counters at the moment of the stop (pages fetched, bytes, elapsed, LLM calls,
spend); how many event candidates were extracted **before** the stop; and the
available actions.

**Available actions, by failure class:**

| State | Re-drive? | Actions offered |
|---|---|---|
| `failed_budget` | **No — the state machine forbids it** | Raise the ceiling (a recorded decision), narrow the source's path patterns, split the source into several jobs, or remove it from the allowlist. Then **create a new job.** |
| `failed_policy` (allowlist/redirect/blocked address) | No | **Security review first.** Then: remove the host, or amend the allowlist with a written justification. |
| `failed_policy` (`robots_denied`, `host_refused`) | No | Remove the host from the allowlist, or **contact the institution and ask** — the research doc's Tier-2 "ask the campus" posture. |
| `failed_provider` | **Yes** — `failed_provider → queued`, bounded automatic retry; exhausted retries park at `redrive_pending` | Re-drive, or `redrive_pending → abandoned` if the host is durably gone. |

The operator surface **must not offer a re-drive button for `failed_budget`**.
The transition would be rejected by `assert_transition`, and offering an action
the system will refuse trains operators to distrust the UI — `execution.py`
already makes this argument for choosing `failed_policy` over `failed_provider`
so as not to "invite an operator to press a button that cannot work".

### 4.4 What state the partial data ends in

**This is the one place where the existing machinery does not straightforwardly
give the desired outcome, and the owner should decide it explicitly.**

The intent: **a job stopped by a limit keeps the events it already extracted.**
Fifty pages of good extraction should not be discarded because page 51 tripped a
byte ceiling. The domain already has the right vocabulary —
`HandlerResult.state` accepts `partial`, and `JobState.PARTIAL` exists, added
because "v1.1 §3.6 N2 requires it: work that half succeeded is labeled as such
with its results retained, and is never reported as success".

The obstacle: **a handler reports failure by raising**, and a raise cannot also
return a `HandlerResult(state="partial")`. So the two available shapes are:

- **Option A — raise, retain via `emit`.** Persist each extracted candidate
  incrementally through `context.emit` (its own transaction, so it survives a
  rollback), then raise `BudgetFailure`. Job ends `failed_budget`; the data
  survives; the escalation is unambiguous.
  *Cost:* per-candidate transactions, and candidate persistence stops looking
  like an ordinary business write.
- **Option B — return `partial`, escalate separately.** Return
  `HandlerResult(state="partial", summary=…)` on a budget stop, write an
  escalation row on the business session, and let the terminal transition commit
  data and escalation atomically. Job ends `partial`; **`failed_budget` is never
  reached**, so the budget stop is no longer visible in the job state.
  *Cost:* it contradicts the research doc's recommendation and weakens
  `failed_budget` as a signal; `partial` is also terminal with no transitions, so
  nothing is lost operationally, but a dashboard counting budget stops would
  under-report.

**Recommendation: Option A**, with the extracted candidates written as
`review_status = pending` and **never** as publishable. Rationale: the stop-gate
asks for *escalation behavior*, and a job whose state does not say "a ceiling
stopped this" has not escalated. Option B optimizes for a cleaner write path and
loses the signal the gate exists to produce.

**Regardless of A or B, invariant:** data extracted before a limit fired is
**always `pending`, never publishable, never matchable**. A budget stop means the
job did not see everything, so nothing it did see is complete enough to publish
unreviewed. And per ADR-0010/T-10, any candidate with `UnresolvedTime` has no
identity key at all and is unpublishable independently of this.

---

## 5. Org-unit mapping policy (open question 8)

### 5.1 The claim about the S3 prep design, verified

**Verified true.** `docs/plans/prep/s3-s5-event-persistence-design.md` was read
in full (91 lines). It specifies `owning_unit_id` as `FK → org_unit` with the
note "Host org unit for identity key", and `schema.py:540` confirms the composite
FK pattern with `ondelete="RESTRICT"`. **The document contains no mapping table,
no mapping policy, and no statement of what happens when an extracted host string
has no `org_unit` row.** Its "Identity resolution flow" section begins at
"extracted title + host unit", treating "host unit" as an input the pipeline is
simply handed. The research doc's characterization of this as "a genuine gap the
S3 prep design does not currently address" is accurate.

### 5.2 Why this is not cosmetic

`resolve_identity_key` (`events.py:398`) takes `host_org_unit` as a **required
keyword** and calls `_require_non_blank(host_org_unit, "host_org_unit")` — a
blank raises `ValueError`. It then builds `EventIdentityKey(host_org_unit=…,
normalized_title=…, resolved_date=…)`.

So an unmapped org unit is **not a missing label on an otherwise-fine event**. It
means:

- **No identity key can be computed.** The key is `(host org unit, normalized
  title, resolved date)`; one component is missing, so there is no key.
- **Deduplication is impossible for that event.** The docstring is explicit that
  keying on host org unit rather than source domain is precisely what makes "the
  university calendar, the department page, an aggregator" collapse to one key.
  Without the host unit, the four sources cannot collapse — you get the exact
  legacy defect the whole design exists to prevent (research doc §3.4).
- **It cannot be persisted as a normal event anyway.** `owning_unit_id` is a
  `NOT NULL` FK with `ondelete="RESTRICT"`; the S3 prep design also requires
  `identity_key IS NULL` ⟹ not publishable/matchable.
- **Inventing a unit is the worst option and is already forbidden.** A fabricated
  org unit is a fabricated value under ADR-0011 rule 1, and it would produce a
  *confidently wrong* identity key — silently splitting or merging real events.

### 5.3 The two options

**Option (a) — route to review, unmapped.**

- Candidate is persisted in a holding state with `owning_unit_id` **unset**, the
  raw extracted host string retained verbatim, full provenance, and
  `review_status = pending`. No identity key. Not publishable, not matchable, not
  deduplicated.
- A human either maps the string to an existing `org_unit`, creates a new
  `org_unit`, or rejects the candidate.
- On mapping, the identity key is computed **then**, and the normal upsert on
  `(tenant_id, identity_key)` runs — so an event that arrives before its unit
  exists still deduplicates correctly against later observations once mapped.
- **Consequences:** *Positive* — no data loss; the review queue becomes the
  discovery channel for org units the program has not yet recorded, which is
  genuinely useful for a pilot expanding its institution set; a wrong mapping is
  visible and fixable. *Negative* — needs a holding shape that the S3 design does
  not have (either a nullable `owning_unit_id` guarded by a CHECK that pairs it
  with a null `identity_key` and non-publishable status, or a separate staging
  table); the queue can fill with noise from a badly-scoped allowlist; someone
  must actually work the queue or it is just a landfill.

**Option (b) — drop.**

- Candidate is discarded. Log a counter and the rejected string; store no row.
- **Consequences:** *Positive* — no schema change; no queue growth; every stored
  event is guaranteed to have a valid key, so the invariants stay simple.
  *Negative* — **silent, unbounded data loss**. A single mistyped or renamed unit
  ("USC Viterbi ACM" vs "ACM at USC Viterbi") drops every event from that source
  forever, and the only symptom is an absence — precisely the class of defect
  ADR-0011 exists to prevent (rule 1: absence must be *visible* as unknown, not
  rendered as nothing). The program would not learn which units it is missing,
  which is exactly the information a pilot most needs.

### 5.4 Recommendation

**Adopt (a) — route to review, unmapped.** Concurring with the research doc, and
for one additional reason it does not state: because `resolve_identity_key`
returns a key rather than mutating anything, **mapping later is not a repair —
it is the normal path run at the normal time.** The key computed after a human
maps the unit is byte-identical to one computed during extraction, so a
retroactively-mapped event deduplicates correctly against every observation
before and after. Option (b) throws away data to avoid a queue, and the queue is
cheaper than the data.

**Guard against the landfill failure mode:** propose an **unmapped-candidate
ceiling per job — 20 candidates**. Beyond that, stop the job with
`PolicyFailure(reason="unmapped_org_unit_flood")`. A source producing more than
20 unmappable host strings in one run is misconfigured or has been added to the
allowlist without its org units being set up first, and grinding through it
produces a queue nobody will read.

### 5.5 Who curates the mapping, and how a mapping is added (proposal)

| Question | Proposal | Owner decision |
|---|---|---|
| **Who owns the `org_unit` ↔ source-string mapping table?** | The **named G3 program owner**, or a single explicitly delegated program coordinator. Not engineering. An org unit is a claim about how a real institution is organized; that is program knowledge. Consistent with P6's rule that "the executor never invents terms" for the vocabulary — same principle, different table. | |
| **How does a new mapping get added?** | Through the **review queue**, as the resolution of an unmapped candidate. The curator sees the raw extracted string, the source URL, `fetched_at`, and the candidate event, and either binds it to an existing `org_unit` or creates one. **No mapping is ever created by the pipeline**, and no mapping is created from a bare string with no source context. | |
| **Is a mapping reversible?** | **Yes, and it must be audited.** Unbinding a mapping does **not** delete the events already keyed under it; it marks them for re-review, because their identity keys were computed under the old mapping and may now be wrong. **Flag for the owner: re-keying existing events on a mapping change is a real operation this design does not yet specify, and it is where an unnoticed duplicate-explosion would come from.** | |
| **Can one source string map to two org units?** | **No.** Many-to-one is fine (several strings → one unit); one-to-many would make the identity key non-deterministic, which contradicts ADR-0012's whole premise that the key is something "anyone can recompute". | |
| **Aliases** | The mapping table should be an explicit **alias list** (many strings → one unit), not a fuzzy matcher. ADR-0012: "a threshold nobody can justify is a worse contract than a key anyone can recompute." An alias a human typed is justifiable; a 0.87 cosine similarity is not. | |

---

## 6. Confidence representation (open question 10)

### 6.1 What a numeric score would actually cost

Read: `docs/architecture/decisions/ADR-0011-accountable-numbers.md` (rules 1–4)
and `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` (stop-gate).

If `confidence` is a **number a user can see**, ADR-0011 applies in full:

- **Rule 2 — one canonical name, one written definition.** "Every user-visible
  aggregate is registered with a name and a one-sentence definition of what it
  counts, in a metric register that ships in the repository. **A metric with no
  register entry does not ship.**" The register is
  `METRIC_REGISTER` in `python/smartmatch_domain/smartmatch_domain/metrics.py`
  (`MetricDefinition`, `get_metric`). So a numeric confidence requires a
  ratified canonical name and a one-sentence definition **before it renders
  anywhere**. And "0.72 confidence" is not a definition; it needs a sentence of
  the form the ADR models — the ADR's own worked example rejects
  "Opportunities" in favor of "Events in the match pool with at least one
  speaker above the score floor, excluding events whose date is `unresolved`".
- **Rule 3 — one owning query.** One implementation, in one place. A confidence
  computed one way in the review UI and another way in a filter is defect #5
  reproduced.
- **Rule 4 — the drill-down contract.** If any surface aggregates or filters on
  confidence, clicking through must return **exactly** the constituent rows, and
  that is a contract test.
- **Rule 1 — unknown is not zero.** A candidate with no basis for a confidence
  judgment must render `unknown`, never `0.0`. A float field invites exactly the
  coercion the ADR was written against.

**And if the score gates anything, it inherits G1.** The G1 stop-gate
(`2026-08-28-g1-matching-m1-m10-plan.md`) requires a committed D1/G1 decision
"ratified or signed by a **named IA West program owner** (the repository's
self-assigned interim owner does not qualify)", carrying the approved factor list
and weights, approved golden cases with expected outputs, and weight governance.
Its standing constraint: "No user-visible score, rank, match run, or matching UI
reaches any surface before this plan's stop-gate passes; every scoring path calls
`assert_registry_approved()`" — and
`smartmatch_domain/factor_registry.py` has `REGISTRY_STATUS = "proposed"` with
`assert_registry_approved()` raising `RegistryNotApprovedError` today.

So a numeric confidence that filters the review queue, orders candidates, or sets
a publish threshold is **a scoring path**, and G3 would have silently acquired a
dependency on G1. The opportunities metric inventory already records the parallel
case: "events above a score floor **inherits G1**".

**A model-emitted number is disqualified regardless.** "Confidence: 0.85" from an
LLM is not a measurement of anything; it is a token sequence shaped like a
measurement. It has no owning query, no definition anyone can check, and no way
to be wrong in a detectable manner — the exact profile ADR-0011 exists to
eliminate.

### 6.2 Recommendation: ordinal enum with a written derivation rule

**Recommend the ordinal enum.** It says everything a reviewer needs, is derived
from facts the pipeline already records (extraction tier, field presence, source
count), is trivially explainable ("high because a tier-1 feed gave an exact
start time"), does not require a `METRIC_REGISTER` entry to render as a *label*,
and does not risk inheriting G1. A number buys arithmetic nobody has asked for at
the cost of two gates.

**Proposed values** (ordered; the ordering is part of the contract):

| Value | Meaning |
|---|---|
| `high` | Deterministically parsed from a machine-readable source; all required fields literally present. |
| `medium` | Deterministically parsed, but with a required field absent or coarse; **or** an LLM extraction corroborated by a second independent source. |
| `low` | Derived by LLM extraction from prose, uncorroborated. |
| `unknown` | No basis for a judgment — e.g. extraction produced fields but the tier could not be determined. Never coerced to `low`; ADR-0011 rule 1. |

Four values, not five: a scale finer than the evidence supports invites people to
argue about the boundary instead of reading the derivation.

### 6.3 Proposed derivation rule

**Deterministic, computed from recorded facts, never from a model's opinion.**
The evaluation is ordered; the first matching clause wins, and **the clause that
fired is stored alongside the value** so the level is always explainable.

```
INPUTS (all already recorded on the observation, per research doc §4.4):
  tier            in {feed, structured, llm_prose}   -- extraction_tier
  time_precision  in {exact, date_only, unresolved}  -- ADR-0010
  corroborated    = >= 2 independent source observations agree on
                    (normalized title, resolved date)
  core_complete   = title AND event_time AND owning_unit_id all present

DERIVATION (first match wins; record the clause id):
  C0  tier is unknown or unrecorded                     -> unknown
  C1  time_precision == unresolved                      -> low
        (no identity key exists at all; ADR-0010/ADR-0012)
  C2  tier == feed       AND time_precision == exact
                         AND core_complete              -> high
  C3  tier == structured AND time_precision == exact
                         AND core_complete              -> high
  C4  tier in {feed, structured}                        -> medium
        (deterministic parse, but date_only or a missing core field)
  C5  tier == llm_prose  AND corroborated
                         AND core_complete              -> medium
  C6  tier == llm_prose                                 -> low

INVARIANTS:
  - An LLM-derived field can never reach `high`. A model may corroborate;
    it may not be the sole basis for the top level.
  - Confidence is recomputed on every new observation for an event, never
    edited by hand. A human disagreeing uses `review_status`, which is the
    field that records a human judgment; confidence records the evidence.
  - The stored value is (level, clause_id, vocabulary/derivation version), so
    changing this rule later does not silently reinterpret stored rows -- the
    same discipline `TagVocabulary.version` applies to tags.
```

**If the owner nonetheless wants a number**, the minimum obligations are: a
ratified `METRIC_REGISTER` entry with a canonical name and a one-sentence
definition; a single owning query; a drill-down contract test; `None` (never
`0.0`) for unknown; and — **if it gates, filters, orders, or thresholds
anything** — passage of the **G1** stop-gate first, including a named program
owner and approved golden cases. That is the honest price, and it is why the
enum is recommended.

---

## 7. Summary — everything that needs a signature

| Ref | Item | Proposal |
|---|---|---|
| L1–L10 | Extraction limits | 50 pages, depth 2, 5 MiB/response, 100 MiB/job, 300 s, 3 redirects, 5 s connect, 15 s read, 30 s/fetch, 200 artifacts/page |
| L11–L20 | Rate and politeness | 10 req/host/min, 1 concurrent/host, 4 global, 6 h between jobs per host, `Retry-After` honored, fail-closed `robots.txt`, identified UA with contact URL, no evasion |
| L21–L28 | Cost ceilings | $1/job and 150 calls/job LLM; 0 search queries in an ingest job; $25/tenant/day; $250/tenant/month; 5,000 fetches/tenant/day; default-disabled kill switch |
| §4 | Escalation | `BudgetFailure` → `failed_budget`, terminal, escalate — **existing taxonomy supports it; the escalation target does not exist and needs a migration** |
| §4.4 | Partial data | Retained, always `pending`, never publishable — Option A recommended |
| §5 | Org-unit mapping | Route to review unmapped (option a); program owner curates; mappings added only through review; 20-unmapped-per-job ceiling |
| §6 | Confidence | Ordinal enum `high/medium/low/unknown` with the C0–C6 derivation rule; not a float |
| — | **New threat entry** | T-11, evasion of a host's stated access policy (L17/L20), for R3 |
| — | **ADR-0015 divergence** | Reserve-before-spend for cost ceilings, opposite to charge-quota-before-refusal — needs explicit assent |

---

## References

Read during preparation:

- `docs/plans/prep/campus-event-discovery-capability.md` (§7 roadmap; §8 Q7, Q8, Q10)
- `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` (P6 stop-gate; cards; evidence ladder)
- `docs/security/crawler-threat-model-draft.md` (T-01…T-10; workshop decisions required)
- `docs/plans/prep/s3-s5-event-persistence-design.md` (read in full to verify §5.1)
- `services/worker/smartmatch_worker/handlers.py` (`HandlerFailure`, `BudgetFailure`, `PolicyFailure`, `ProviderFailure`, `HandlerResult`, `CommandContext`)
- `services/worker/smartmatch_worker/execution.py` (`_FAILURE_STATES`, `_UNEXPECTED_FAILURE_STATE`)
- `services/worker/smartmatch_worker/dispatcher.py`, `config.py`
- `python/smartmatch_domain/smartmatch_domain/jobs.py` (`JobState`, `TRANSITIONS`, `TERMINAL_STATES`)
- `python/smartmatch_domain/smartmatch_domain/events.py` (`resolve_identity_key`, `TagVocabulary`)
- `python/smartmatch_domain/smartmatch_domain/metrics.py` (`METRIC_REGISTER`)
- `python/smartmatch_persistence/smartmatch_persistence/schema.py` (`review_item`, `ck_review_item_status`)
- `python/smartmatch_persistence/smartmatch_persistence/review.py`, `jobs.py` (`DEFAULT_JOB_LEASE`)
- `docs/architecture/decisions/` — ADR-0006, ADR-0010, ADR-0011, ADR-0012, ADR-0015
- `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` (G1 stop-gate)

**No network call was made during the preparation of this document. It changes no
code, chooses no allowlist entry, ratifies no limit, and makes no
production-readiness claim. Every value above is a proposal awaiting the named
G3 program owner's approval.**
