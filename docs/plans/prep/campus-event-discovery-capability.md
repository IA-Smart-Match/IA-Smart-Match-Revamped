# Campus event discovery as a speaking-opportunity capability — design research

**Status:** DRAFT — design research, not a ratified decision. **Changes no code.**
**Date:** 2026-08-29 · **Branch:** `friday-deliverable-828`
**Feeds:** the G3 decision artifact required by plan P6
(`docs/plans/2026-08-28-g3-events-s3-s5-plan.md`) and the R3 sign-off required on
`docs/security/crawler-threat-model-draft.md`.
**Authorizes:** nothing. No provider, no allowlist entry, no vocabulary term, no
limit value, no route, no outbound message.

## Method and epistemic status

Everything asserted about **this repository** was read during the preparation of
this document; file paths are given so each claim can be re-checked. Everything
asserted about **the outside world** — platform APIs, terms of service, feed
formats, legal regimes — is reasoning from general knowledge, was **not**
verified by any network call during this work, and is marked with a confidence
level. No live fetch of Tavily, any university site, any club page, or any
social platform was performed, per the portfolio's standing constraints
(`docs/plans/2026-08-28-plan-portfolio-index.md`, "Standing constraints").

Every outside-world claim below carries one of:

- **High** — stable, long-standing, and unlikely to have changed materially.
- **Medium** — broadly true but detail-sensitive; verify before relying on it.
- **Low** — plausible but must be confirmed against the vendor's current terms.

**No ToS statement in this document is legal advice, and none of it substitutes
for reading the current terms of a named platform at the time a decision is
made.** Section 5 in particular describes a regulated activity and defers to
counsel.

---

## 0. The product idea, restated in the repo's vocabulary

The program owner's framing: an *opportunity* is a campus event or a course /
lecture session into which IA West can place an industry professional as a guest
speaker — hackathons, datathons, competitions, courses needing a guest lecturer,
club programming. Discovery today (in a previous repository) was: query Tavily,
let an agent read the results, write rows into a database. The owner's own word
for it is "crude", and the owner asks whether the agent could also reach out to
clubs to inquire about events.

Two distinct capabilities are bundled in that sentence, and they must be kept
apart because they carry entirely different risk:

| Capability | What it does | Risk class |
|---|---|---|
| **A — Discovery** | Reads public pages and feeds; produces candidate event records with provenance | Technical + ToS + SSRF; gated by G3 / R3 |
| **B — Outreach** | Sends messages to real people at named organizations under IA West's name | Legal, reputational, and human-subject risk; **not covered by G3/R3 at all** |

Plan P6's stop-gate and the R3 threat model address **A only**. Nothing in the
committed artifacts contemplates B. Section 5 treats that as the central finding
of this document, not a footnote.

---

## 1. What actually exists in this repository today

Read and verified:

- **No event table, no event route.**
  `services/api/smartmatch_api/routers/events.py` declares an `APIRouter`
  (prefix `/v1/units`, tag `events`) and **zero handlers**, with a docstring
  saying so deliberately. There is no `event` table; the persistence shape is
  still a proposal in `docs/plans/prep/s3-s5-event-persistence-design.md`.
- **The domain contracts the pipeline must land against already exist and are
  strong.** `python/smartmatch_domain/smartmatch_domain/events.py` provides:
  - `TimePrecision` (`exact` / `date_only` / `unresolved`) and the discriminated
    union `EventTime = ExactTime | DateOnlyTime | UnresolvedTime` (ADR-0010).
    `DateOnlyTime` has **no** `starts_at` field, so a date-only event cannot be
    collapsed to a fabricated midnight instant — the illegal state is
    unconstructible, not merely discouraged.
  - `resolve_identity_key(host_org_unit=, title=, event_time=)` returning
    `EventIdentityKey | None` — `None` for `UnresolvedTime` (ADR-0012). It takes
    **no provenance parameter**, precisely so the same event seen on the
    university calendar, the department page, and an aggregator resolves to one
    key.
  - `resolved_date()` converts an `ExactTime` into the event's **own** IANA zone
    before taking the date — the docstring is explicit that reading the UTC date
    would manufacture a second identity key for the same event across local
    midnight.
  - `EventProvenance(source_url, fetched_at, extractor_version)` — a structured
    value with no function anywhere in the module that combines it with a title.
  - `TagVocabulary` / `resolve_tag` / `MappedTag` / `QuarantinedTag` /
    `matchable_tags()` — a closed, versioned vocabulary whose **terms are
    deliberately not chosen** (S5 / G3 owner).
- **The legacy crawler is retired, not dormant.** Commit `b1204ed`
  ("retire the legacy crawler poll and its surface (lane F4)") removed the
  3-second `/api/crawler/status` poll.
  `apps/web/legacy-frontend/src/app/components/CrawlerContext.tsx` survives only
  as a truthful stub: `availability: "retired"`, `refresh()` a documented no-op
  that "never issues network requests". `CrawlerFeed.tsx` still exists in
  `apps/web/legacy-frontend/src/components/`. The legacy client functions in
  `apps/web/legacy-frontend/src/lib/api.ts` (~lines 1384–1416) still name
  `/api/crawler/start`, `/api/crawler/results`, `/api/crawler/status` and a
  `source?: "seed" | "gemini" | "tavily" | "search"` field (line 29) — these are
  **legacy client stubs against a backend that does not implement them**, not a
  working crawler.
- **Two independent structural guards stand between here and any crawl.**
  - `tests/unit/test_no_external_calls_on_request_path.py` — (1) the committed
    `contracts/openapi/smartmatch.json` may not expose a route whose path
    segments name a crawl/discovery/scrape/LLM/agent/outreach surface or a named
    vendor (`crawl`, `crawler`, `discover`, `scrape`, `llm`, `ai`, `agent`,
    `outreach`, `email`, `send`, `tavily`, `openai`, `anthropic`, `serp`, …);
    (2) **no module under `services/api/` may import an HTTP client library at
    all**, so the request path cannot reach the network by construction. Note
    that this list forbids `outreach`, `email`, and `send` as route segments —
    Capability B is fenced off by a committed test, today.
  - `tests/unit/test_matching_fail_closed.py` — rejects committed crawl routes;
    its deliberate flip is card S6b only.
- **The worker is where work is allowed to happen.**
  `services/worker/smartmatch_worker/handlers.py` documents the command registry:
  an unregistered command **fails the job explicitly**; failures are declared as
  `PolicyFailure` → `failed_policy`, `BudgetFailure` → `failed_budget`,
  `ProviderFailure` → `failed_provider` (the only re-drivable one); a handler
  reads parameters from `context.job.payload` re-read from PostgreSQL, **never**
  from the task delivery; business writes go on the executor-owned session and
  become durable only with the terminal transition.
  `services/worker/smartmatch_worker/dispatcher.py` is the only component that
  creates tasks, and nothing in the API path talks to Cloud Tasks.
  This is exactly the shape a crawl adapter needs, and it already works.
- **"Opportunities" is not yet a number anyone may print.**
  `docs/plans/opportunities-metric-inventory.md`: `METRIC_REGISTER` has no
  opportunities entry; `Opportunities.tsx` merged CSV + crawler rows with
  fabricated dates and roles; commit `df4e218` "stop fabricating opportunities
  until S12". Plan P8 (`2026-08-28-opportunities-s12-plan.md`, cards O1–O4) owns
  the definition, persistence, owning query, and the frontend.
- **Contact fields are an open privacy decision, not an available column.**
  `docs/pilot-data/event-contact-fields-decision-prep.md` lists `Public URL`,
  `Point(s) of Contact (published)` and `Contact Email / Phone (published)` as
  **TBD** in `columns.yaml`, and states under ADR-0014 that "published" is
  provenance, **not consent for platform disclosure**.
- **No agent framework exists, on purpose.** ADR-0003 forbids agent code and any
  agent dependency in Foundation, explicitly to prevent feature work routing
  through an agent module "before gate G3 has approved an eval set, tool
  allowlist, and cost controls". It also records why the legacy agent code is
  rejected on its own terms: it made provider calls in the browser request path
  and treated agent session state as authoritative.
- **The legacy outreach surface is still wired in the frontend and equally
  dead.** `apps/web/legacy-frontend/src/app/pages/Outreach.tsx` (482 lines) calls
  `/api/outreach/email`, `/api/outreach/ics`, `/api/outreach/workflow` and an
  `/api/outreach/agentic-workflow/stream` SSE endpoint via
  `apps/web/legacy-frontend/src/lib/api.ts` (~1247–1330), including an
  `OutreachEmailVoice` of `"school_coordinator" | "ia_west_chapter"`. None of
  these exist in `services/api/`. **The legacy system already had an agentic
  outreach workflow that composed email in IA West's voice.** That is the
  precedent this proposal would revive, and it is the one that most needs a
  written decision before anything is rebuilt.

**Consequence for this document:** the discovery capability described below is a
*worker-side extraction adapter* that fills the `event` table proposed in the S3
prep design, keyed by `resolve_identity_key`, with provenance in columns. It is
not a new subsystem; it is card S6 with a better source strategy.

---

## 2. Discovery sources, ranked by tractability and risk

Ranked best-first. "Tractability" = how cheaply a correct, stable extraction can
be built. "Risk" = ToS, robots, legal, and operational exposure.

### Tier 1 — Feed-based, structured, low risk

**1a. University event calendars (central + department).**
- **Yields:** the highest-value target for this product. Colloquia, seminar
  series, career panels, department info sessions, guest-lecture slots. These are
  where a "course/lecture session needing an industry guest speaker" actually
  surfaces publicly.
- **Access:** most university calendar platforms publish an **iCalendar (.ics)**
  feed per calendar and often per filtered view, plus RSS, and increasingly
  **JSON-LD `schema.org/Event`** embedded in the page head. *(Confidence: High
  that iCal/RSS/JSON-LD are widespread on university calendars; **Medium** for
  any specific institution — it must be checked per host.)*
- **Official API:** varies by vendor. Localist/Concept3D, Trumba, and 25Live are
  common higher-ed calendar platforms and several expose documented JSON or iCal
  endpoints. *(Confidence: Medium — vendor and version specific; verify per
  institution before it enters an allowlist.)*
- **ToS/robots:** a published `.ics`/RSS endpoint is an invitation to subscribe;
  fetching it politely at a low rate is the intended use. Still check
  `robots.txt` for the host and honor `Crawl-delay` where present. *(Confidence:
  High as a general posture.)*
- **Verdict:** **feed-based**. Start here. Deterministic parse, stable schema,
  clean provenance, no LLM required for the core fields.

**1b. Department and lab pages, seminar-series pages.**
- **Yields:** named speaker slots, recurring series with a visible organizer, and
  the course-adjacent guest-lecture opportunities that never reach the central
  calendar.
- **Access:** mostly HTML. Frequently carries JSON-LD `Event` or hCalendar
  microdata; frequently does not.
- **Official API:** rarely. *(Confidence: High.)*
- **ToS/robots:** ordinary public web pages; robots.txt governs. *(Confidence:
  High.)*
- **Verdict:** **mixed** — deterministic when structured data is present,
  LLM-assisted extraction only for the prose remainder (see §3).

### Tier 2 — Platform APIs, moderate tractability, licence-dependent

**2a. Student-organization platforms (Engage / CampusLabs, CampusGroups,
Presence, and similar).**
- **Yields:** the club-hosted programming the owner is actually describing —
  exactly the layer Tavily was being used to guess at.
- **Access:** these are institution-licensed products. Public event pages often
  exist for a given campus; some deployments expose read APIs or iCal exports,
  and API access is typically a matter of the **institution's** contract rather
  than a public developer signup. *(Confidence: Medium — differs by vendor and by
  campus configuration.)*
- **Official API:** sometimes, institution-gated. *(Confidence: Medium.)*
- **ToS/robots:** the correct move here is almost certainly **partnership, not
  scraping** — ask the campus for the feed or the API credential. That is also
  the move that makes the whole capability defensible.
- **Verdict:** **feed-based if you ask; scrape-based if you don't.** Ask.

**2b. Eventbrite, Luma.**
- **Yields:** externally-promoted campus and adjacent-community events.
- **Access:** both have public event pages; Eventbrite has historically offered a
  documented REST API, though its search capability has been narrowed over time.
  *(Confidence: Medium on current API surface — verify.)* Luma exposes public
  event pages and some calendar subscription. *(Confidence: Low–Medium — verify.)*
- **ToS/robots:** commercial platforms; ToS generally restrict automated
  collection and reserve the right to rate-limit or block. Use the documented API
  where one exists. *(Confidence: Medium.)*
- **Verdict:** **API-first, and only within the API's own terms.**

**2c. Devpost, Major League Hacking (MLH).**
- **Yields:** hackathons and datathons — a named target in the owner's framing,
  and the class of event most likely to want an industry judge, mentor, or
  keynote. High conversion potential per record.
- **Access:** MLH publishes a season event list. Devpost lists hackathons with
  structured metadata on public pages. *(Confidence: Medium on the presence of a
  documented public API for either; **Low** that an unauthenticated JSON endpoint
  is officially supported — verify.)*
- **ToS/robots:** ordinary platform ToS; check robots.txt. *(Confidence: Medium.)*
- **Verdict:** **mixed.** Small, high-value, and enumerable — a strong candidate
  for the first allowlist because the population is small enough that a human can
  review every record.

### Tier 3 — Search as a fallback discovery signal

**3. Tavily (or any search/answer API).**
- **Yields:** *pointers*, not events. Its correct role is to discover **which
  hosts and which pages exist** for an institution the program is targeting — a
  one-time or occasional seeding input to a human-approved allowlist.
- **Access:** commercial API, credentialed.
- **ToS/robots:** the search provider's terms govern the query; the terms of the
  **destination** govern any subsequent fetch. Using a search API does not
  launder a fetch that the destination forbids. *(Confidence: High as a
  principle.)*
- **Verdict:** **fallback and seeding only.** See §3 for why making this the
  primary path is the defect.

### Tier 4 — Social media: hardest, most ToS-encumbered, lowest priority

The owner is right that clubs post primarily to social media. That observation is
correct and it is also the reason this tier is last, not first.

**4a. Instagram.** *(Confidence: High on the general posture; Medium on current
detail.)* Automated collection of Instagram content without authorization is
contrary to Meta's terms; the Graph API paths that exist are oriented to accounts
you own or have been granted access to, not to arbitrary discovery. Content is
image-first — the event details are frequently **in the flyer graphic**, meaning
extraction requires OCR of a marketing image, which is both technically brittle
and the least reliable evidence base imaginable for a date. **Recommendation: out
of scope. If a club's Instagram is the only source, the right action is a human
following that account, not an agent scraping it.**

**4b. Discord.** *(Confidence: High.)* Club servers are typically invite-gated
community spaces. A bot in a server requires an invitation from that server's
administrators — which is a *relationship*, and is legitimate when granted.
Joining or reading without that grant is not. **Recommendation: only ever
by explicit invitation, per server, recorded.** Never as a discovery sweep.

**4c. LinkedIn.** *(Confidence: High.)* LinkedIn's user agreement prohibits
automated scraping, and the platform actively enforces it. LinkedIn is also where
automated outreach would be most tempting and most damaging. **Recommendation:
out of scope for automated collection entirely.**

**4d. University subreddits, club newsletters, mailing lists.** Occasionally
useful, low structure, and generally better served by a human subscribing than by
an adapter.

### Summary table

| Rank | Source | Structured? | Official API | Posture | Recommended for first allowlist |
|---|---|---|---|---|---|
| 1 | University central calendar | iCal / RSS / JSON-LD | Vendor-dependent (Med) | Intended-use fetch | **Yes** |
| 2 | Department / seminar pages | Sometimes JSON-LD | No (High) | robots.txt governs | Yes, narrow |
| 3 | Student-org platform (Engage etc.) | Sometimes iCal | Institution-gated (Med) | **Ask the campus** | Only via partnership |
| 4 | Devpost / MLH | Semi-structured | Unclear (Low) | Platform ToS | Yes, small + reviewable |
| 5 | Eventbrite / Luma | Platform records | Yes, narrowed (Med) | API-only | Defer |
| 6 | Tavily / search | No | Yes | Seeding only | Seeding, not ingest |
| 7 | Instagram / LinkedIn | No | Restricted (High) | Prohibited/enforced | **No** |
| 8 | Discord | No | By invitation | Per-server grant | **Only by invitation** |

---

## 3. Why "Tavily + LLM extraction" alone is the crude version

The legacy approach was: search → hand results to a model → write rows. Five
things are wrong with it, and each has a specific correction.

### 3.1 Search was the primary path; it should be the fallback

A search API returns *what a ranking function thinks is relevant to a string*.
It is non-deterministic across runs, unattributable (you cannot say why a result
appeared), unbounded (you cannot enumerate what you missed), and it silently
substitutes recall for precision. It is a poor *ingest* mechanism and a decent
*reconnaissance* mechanism.

**Correction — a strict source cascade, checked in order:**

1. **Official feed** — `.ics`, RSS/Atom, or a documented JSON API on an
   allowlisted host. Deterministic parse. No model involved.
2. **Structured markup on an allowlisted page** — JSON-LD `schema.org/Event`,
   microdata, hCalendar. Deterministic parse.
3. **Unstructured prose on an allowlisted page** — the only place an LLM
   extractor is permitted, and it emits low-confidence candidates.
4. **Search** — used to *propose hosts and pages to a human for allowlisting*.
   Never to produce an event record directly.

The cascade is not a preference; it should be enforced. An extraction record
should carry which tier produced it, and the eligibility rules in §4 should treat
tier as evidence.

### 3.2 It used a model where a parser was correct

`schema.org/Event` JSON-LD on university calendars is common enough that a
deterministic parser will cover a large fraction of Tier 1 with exact fields and
zero hallucination risk. *(Confidence: Medium-High on prevalence; must be
measured on the actual target set — that measurement is itself a good first
card.)* An LLM asked to read a page that already contains a machine-readable
`startDate` is strictly worse: slower, costlier, non-deterministic, and capable
of returning a date that is not on the page.

**Correction:** deterministic-first. The LLM's job is narrowed to (a) prose pages
with no structured data, and (b) the genuinely judgmental field — "is a speaker
slot plausibly available here" — where it produces a *proposal for human review*,
not a stored truth. This aligns with ADR-0003's logic: the agent arrives into
infrastructure that already works, and only where it adds something a parser
cannot.

### 3.3 It re-fetched blindly; there was no caching or conditional request

Campus calendars change slowly. A pipeline that refetches everything every run
burns budget, generates avoidable load on someone else's server (which is how you
get blocked and how you deserve to be), and makes rate ceilings meaningless.

**Correction:**
- Store `ETag` and `Last-Modified` per source URL; send `If-None-Match` /
  `If-Modified-Since`; treat `304` as a first-class, cheap outcome that still
  refreshes `fetched_at` without a re-parse.
- Content-hash the normalized body; an unchanged hash short-circuits extraction
  entirely (this is the same discipline lane F3 is applying to the metrics API
  with weak `ETag`s in `services/api/smartmatch_api/routers/metrics.py`).
- Per-host politeness: a minimum interval between requests to the same host,
  independent of the per-run budget, and honored across concurrent jobs.
- Respect `robots.txt` and any `Crawl-delay`, cached with its own TTL.
- **Budget exhaustion raises `BudgetFailure` → `failed_budget`** (terminal,
  non-redrivable) per `services/worker/smartmatch_worker/handlers.py`. That
  mapping already exists and is exactly right: re-driving into a ceiling is
  pointless. Threat T-08 in the draft threat model says budget-exceeded escalates
  to quarantine; the handler taxonomy already supports saying so precisely.

### 3.4 It had no deduplication, so the same event became three rows

A regional hackathon appears on MLH, on Devpost, on the hosting university's
calendar, and on the CS department page. The legacy pipeline had no way to know
these were one thing; the metric inventory records the visible consequence —
`Opportunities.tsx` merged CSV and crawler rows with fabricated dates and roles.

**Correction — the repo already has the mechanism, and it is good:**
`resolve_identity_key(host_org_unit, title, event_time)` in
`smartmatch_domain/events.py`. Note what it deliberately does:

- It keys on **host org unit, not source domain**, so four sources collapse to
  one key (the docstring says this explicitly).
- It takes **no provenance parameter**, so provenance cannot leak into identity.
- It returns **`None`** for `UnresolvedTime` — an event whose date could not be
  resolved has no identity and cannot be deduplicated against anything. It sits
  as its own row, unpublishable, awaiting review. This is correct and must not be
  "fixed" by inventing a key.
- `normalize_title` folds case, collapses punctuation to boundaries (so
  `"AI-Panel"` and `"AI Panel"` match, but `"aipanel"` is never produced), and
  **refuses fuzzy matching** — ADR-0012: "a threshold nobody can justify is a
  worse contract than a key anyone can recompute."

**Entity resolution beyond the key.** The key handles the common case exactly.
Two residual cases need a *declared* policy rather than a clever one:

- **Same event, materially different titles across sources** ("HackSC 2026" vs
  "HackSC — Spring Hackathon"). The key will not merge these, and it should not
  guess. Correct handling: both rows exist; a **review-queue "these are the same
  event" human merge action** records the merge with an audit row. Fuzzy
  auto-merge is out of scope and contrary to ADR-0012.
- **Org-unit resolution.** `host_org_unit` must come from the `org_unit` table
  (the S3 prep design has `owning_unit_id` FK → `org_unit`). Mapping a scraped
  string like "USC Viterbi ACM" to an org unit is itself an entity-resolution
  problem. **Recommendation: an explicit, human-curated source→org_unit mapping
  table.** If a source cannot be mapped to a known org unit, the extraction does
  **not** get to invent one — it goes to review. This is a genuine gap the S3
  prep design does not currently address and the G3 artifact should close.

### 3.5 It had no provenance, so no field could be defended

**Correction — already designed, needs to be honored:**
`EventProvenance(source_url, fetched_at, extractor_version)` plus the
`event_provenance` table in the S3 prep design (`source_url`, `fetched_at`,
`extractor_version`, `raw_snapshot_ref` as an object-storage pointer, **not**
inline HTML). One row per source observation, so a deduplicated event carries
*all* the observations that produced it.

Two additions this document recommends for the G3 artifact:

- **Field-level provenance.** For an event assembled from more than one source,
  record which observation supplied each field. Otherwise "this event's date came
  from the department page, its contact from the calendar" is unanswerable.
  Minimum viable form: a per-field `source_observation_id` on the event row, or
  a narrow `event_field_provenance` table.
- **Extraction tier and extractor identity on every observation.** Which tier of
  the §3.1 cascade produced it, and for LLM-derived fields, the model identifier
  and prompt version folded into `extractor_version`. This is what makes replay
  meaningful and what makes an LLM regression detectable.

ADR-0012's rule stands in code, not convention: there is no function in
`events.py` that accepts both a title and an `EventProvenance` and returns a
combined string. Provenance in a title is unconstructible, not merely forbidden.

### 3.6 The architecture, in one diagram

```
[ human-approved allowlist ]   [ org_unit mapping table ]
            |                            |
            v                            v
  +---------------------------------------------+
  |  worker command: discover_events (durable)  |   <- never an API route
  +---------------------------------------------+
     | 1. feed (.ics/RSS/JSON API)   deterministic
     | 2. JSON-LD / microdata        deterministic
     | 3. prose  -> LLM extractor    low-confidence proposal
     | 4. search -> host proposals   -> HUMAN, not ingest
            |
            v
   [ conditional fetch: ETag / If-Modified-Since / content hash ]
            |
            v
   [ SSRF + allowlist revalidation per redirect hop  (T-01..T-04) ]
            |
            v
   [ extraction artifact  (raw, isolated parser, byte/time capped) ]
            |
            v
   resolve_identity_key()  --None-->  unresolved row: no key, no publish, review
            |
       upsert on (tenant_id, identity_key)
            |
            +--> event_provenance row (URL, fetched_at, extractor_version, tier)
            +--> resolve_tag() -> MappedTag | QuarantinedTag -> review queue
            +--> eligibility evaluation (§4) -> review queue
                                                     |
                                                     v
                                        [ HUMAN REVIEW ] -- and only then --> §5
```

---

## 4. The extraction schema

Fields a speaking-opportunity record needs. The `Unknown allowed?` column is
load-bearing: **ADR-0011 — unknown never becomes a fabricated value**, and the
portfolio's standing constraint says "unknown never becomes zero". A field marked
"Yes" must render as *unknown* in every surface, never as a default, a guess, an
empty string presented as data, or a placeholder like the legacy's
`date: "See link for details"` (recorded as finding H21 in
`docs/plans/frontend-migration.md`).

### 4.1 Identity and temporal

| Field | Type | Unknown allowed? | Notes |
|---|---|---|---|
| `title` | text | **No** — refuse the record | `normalize_title` requires non-blank |
| `title_normalized` | text | No | Derived; `normalize_title()` |
| `owning_unit_id` | FK `org_unit` | **No** — unmapped → review, never invented | See §3.4 org-unit gap |
| `event_time` | `EventTime` union | **Yes → `UnresolvedTime`** | ADR-0010 |
| `time_precision` | enum | No — always one of three | `exact`/`date_only`/`unresolved` |
| `timezone` | IANA name | Only with `unresolved` | Validated against tzdb at construction |
| `ends_at` / duration | timestamptz | **Yes** | Very often absent; do not infer |
| `identity_key` | text | **Null iff unresolved** | DB CHECK per S3 prep design |

### 4.2 Placement-relevant

| Field | Type | Unknown allowed? | Notes |
|---|---|---|---|
| `event_type` | mapped tag | **Yes → quarantine** | `resolve_tag`; terms are S5/G3's to choose, **not this document's** |
| `location` / `modality` | text / enum | **Yes** | In-person / virtual / hybrid is frequently unstated |
| `audience_scale` | int | **Yes — and usually is** | Never estimate attendance |
| `speaker_slot_signal` | enum + evidence | **Yes → `unknown`** | §4.3; a *signal*, not a fact |
| `call_for_speakers_url` | url | **Yes** | Only when literally present |
| `application_deadline` | date | **Yes** | Only when literally present |

### 4.3 Contact route — the most constrained group

| Field | Type | Unknown allowed? | Notes |
|---|---|---|---|
| `public_contact_url` | url | **Yes** | A public *page* (contact form, org page) — the safest route |
| `published_contact_name` | text | **Yes** | **PII. Gated on the open `columns.yaml` decision** |
| `published_contact_email` | text | **Yes** | **PII. Gated. ADR-0014: "published" ≠ consent to platform disclosure** |

`docs/pilot-data/event-contact-fields-decision-prep.md` records all three as TBD.
**Until that decision lands, the defensible default is: store
`public_contact_url` only, and do not extract or persist personal names, emails,
or phone numbers at all.** A public "Contact us" page is a route; a scraped
person's email address is a personal data holding with a retention obligation
attached to it.

### 4.4 Provenance and confidence (never optional)

| Field | Type | Unknown allowed? | Notes |
|---|---|---|---|
| `source_url` | url | **No** | `EventProvenance` requires non-blank |
| `fetched_at` | tz-aware datetime | **No** | Aware datetime enforced at construction |
| `extractor_version` | text | **No** | Pin for replay; includes model+prompt version for LLM tiers |
| `extraction_tier` | enum | **No** | feed / structured / llm_prose (search is never an ingest tier) |
| `raw_snapshot_ref` | object ref | No | Pointer, never inline HTML |
| `http_etag` / `http_last_modified` | text | Yes | Cache keys |
| `confidence` | enum or scalar | **No** | See below |
| `review_status` | enum | **No** | Includes quarantine / approved |

**On `confidence`:** it must not be a number a model invented. The honest form is
a **derived, explainable** value: tier-1 feed with an exact `startDate` is `high`
by construction; LLM-extracted prose with no corroborating source is `low` by
construction; two independent sources agreeing raises it. If the G3 owner wants a
numeric score, it must have a written definition and a registered name under
ADR-0011 — otherwise it is exactly the kind of unaccountable number ADR-0011
exists to prevent. **Recommendation: an ordinal enum with a stated derivation
rule, not a float.**

**Explicit non-fields.** Do not store: an inferred attendance estimate, an
inferred "fit score" (that inherits G1), an inferred organizer seniority, or any
"likely" date. The legacy's fabricated crawler dates and roles are the named
defect this schema exists to prevent.

---

## 5. Relevance and eligibility — is this a *speaking* opportunity?

Most campus events are not speaking opportunities. A study session, a social, a
club GBM, and an already-fully-programmed conference are all campus events; none
is a slot IA West can fill.

### 5.1 What can be decided mechanically (high confidence, cheap, auditable)

- **Hard exclusions.** Past events; events with `UnresolvedTime` (no identity, so
  they cannot publish at all — ADR-0010 rule 2, enforced by DB CHECK per the S3
  prep design); events outside the program's geography or institution set; events
  whose `owning_unit_id` could not be resolved.
- **Lead time.** An event 6 days out cannot absorb a speaker placement; one 10
  weeks out can. This is arithmetic on `resolved_date`, and the threshold is a
  **program decision** (see open question 6), not a model's.
- **Explicit positive signals in the source text.** The literal presence of
  "call for speakers", "seeking judges", "seeking mentors", "guest lecturer",
  "industry panel", "sponsors welcome" — a **human-curated phrase list**, matched
  deterministically, with the matched span recorded as evidence.
- **Structural signals.** `schema.org` event subtype where present; a form linked
  from the page whose label names speakers/judges/mentors.

### 5.2 What genuinely needs a model — and what its output is allowed to be

For prose pages with none of the above, an LLM can propose "this looks like an
event that could host an industry guest speaker, because …". Its output must be:

- **A proposal with a quoted evidence span**, not a verdict.
- **Written to `review_status = pending`**, never to a publishable state.
- **Evaluated against the G3 eval set**, with pass/fail criteria that P6's
  stop-gate requires be non-blank before any of this runs.

### 5.3 Where this needs human-approved criteria, stated honestly

**The core eligibility question is a program-policy question, not a modeling
question, and it should not be delegated to a model at all.** "Is this the kind of
organization IA West wants to be associated with?" "Is a datathon judging slot the
same product as a guest lecture?" "Do we approach a club with 12 members?" A model
asked these questions will produce fluent answers with no accountability behind
them, and the wrong ones will be invisible because they will read well.

**Recommendation:** the G3 artifact carries a **written, human-authored
eligibility rubric** — the exclusion list, the lead-time threshold, the phrase
list, the institution set. The pipeline applies that rubric mechanically and
records which clause fired. The model's role is confined to surfacing candidates
for a human to run the rubric against. The `pending_review_items` metric already
exists in `smartmatch_domain/metrics.py`, so the review backlog is measurable
from day one.

**Non-negotiable:** no eligibility decision may promote an event to publishable
or matchable without a human transition, and any score-shaped output inherits
gate G1 (per the metric inventory's note that "events above a score floor
**inherits G1**").

---

## 6. The outreach idea — analyzed, and the defensible version

The owner floated: "we could have the agent reach out and inquire about events on
behalf of IA West." This section is the most important in the document.

### 6.1 What changes in kind, not degree

Reading a public page is an act of *observation*. Sending a message is an act of
*speech, by a named real organization, to a named real person*. Everything about
the risk profile changes at that line:

1. **It is speech attributed to IA West.** An agent that gets a fact wrong in an
   email — the wrong event, the wrong date, a claim about what IA West will
   provide — has not produced a bad database row. It has produced a
   misrepresentation by a real professional organization to a university
   partner. There is no rollback. The threat model in
   `docs/security/crawler-threat-model-draft.md` covers SSRF, parsers, budgets,
   and provenance; **it has no control at all for "the system said something
   false to a human under the org's name"**, because it was never scoped to
   consider outbound messages.
2. **The recipients are students, and some are minors.** University clubs include
   dual-enrollment and early-admit students; campus outreach can reach
   pre-college programs. Automated messaging to minors carries obligations that
   automated messaging to a business contact does not. *(Confidence: High that
   this is a real category of concern; specific obligations are for counsel.)*
3. **Anti-spam law applies.** In the US, CAN-SPAM governs commercial email:
   accurate header and subject information, identification of the message as
   solicitation where applicable, a valid physical postal address, a functioning
   opt-out honored promptly (commonly cited as within 10 business days), and
   liability that attaches to the party on whose behalf the message is sent —
   i.e. **IA West**, not the vendor and not the agent. Canada's CASL is stricter
   (consent-based, with significant penalties) and would apply to Canadian
   recipients; jurisdictions with GDPR-adjacent regimes add lawful-basis and data
   subject rights on top. *(Confidence: High on the existence and general shape
   of these regimes; **Medium** on any specific numeric threshold; **this is not
   legal advice** and the numbers should be confirmed by counsel.)*
4. **Platform ToS forbid a large part of the obvious implementation.** Automated
   messaging via LinkedIn is prohibited by its user agreement and actively
   enforced; automated DMs on Instagram are likewise outside the terms; Discord
   prohibits unsolicited bot DMs. *(Confidence: High on posture; Medium on
   current specifics.)* Whatever the legal analysis concludes, **the platforms
   where clubs actually live are largely closed to automated outbound by
   contract**, independent of law.
5. **University communication norms are a real constraint.** Many institutions
   route external-organization contact with student groups through a student
   affairs or corporate-relations office. Bypassing that with automated messages
   to club officers is a fast way to be blocked at the institutional level — and
   losing a campus relationship costs far more than any discovery pipeline saves.
   *(Confidence: Medium-High.)*
6. **The legacy repo already did a version of this.** `Outreach.tsx` +
   `api.ts` (~1247–1330) reference `/api/outreach/email`,
   `/api/outreach/workflow`, an `/api/outreach/agentic-workflow/stream` SSE
   endpoint, and an `OutreachEmailVoice` of `"school_coordinator" |
   "ia_west_chapter"`. **An agentic workflow composing email in IA West's voice
   already existed and was not carried forward.** Rebuilding it should therefore
   be treated as a deliberate reversal requiring a written decision, not as a
   natural extension of the crawler.
7. **The repo currently forbids it structurally.**
   `tests/unit/test_no_external_calls_on_request_path.py` bars `outreach`,
   `email`, and `send` as OpenAPI path segments and bars any HTTP client import
   under `services/api/`. Shipping outbound messaging means deliberately flipping
   a committed guard — which is good, because it forces the decision to be
   visible in a commit.

### 6.2 What is not acceptable, stated plainly

**Do not build:** bulk sending; list-buying or list-harvesting of student contact
data; scraping personal email addresses off club pages to message them;
sending from rotated domains, subdomains, or aliases to evade filters or blocks;
messaging through a platform whose ToS forbid it; any message that obscures that
it was machine-composed on behalf of IA West; or any flow where a message reaches
a recipient without a specific human having read that specific message.

**Fully autonomous outbound messaging is not something to ship without
institutional and legal sign-off.** Not "later" — it needs a named accountable
human, counsel review, and where a campus has a required channel, that campus's
agreement. This document does not design it and recommends against pursuing it.

### 6.3 The defensible version: human-in-the-loop drafting

The version worth building keeps the agent on the *composition* side of the line
and a person on the *sending* side.

**Shape:**

1. **Agent drafts; a person reviews and sends.** The system produces a draft
   addressed to a **public** contact route (a club's public contact form or a
   department's public inbox — not a scraped personal address, until and unless
   the `columns.yaml` contact-field decision says otherwise). The draft is
   presented to a named IA West staff member with the **event record and its full
   provenance beside it**, so the reviewer can check every factual claim against
   the source URL and `fetched_at` before sending.
2. **Send happens from a human's own account and action.** The safest v1 sends
   nothing at all from the platform: it produces text the person pastes into
   their own mail client. Every escalation beyond that (a "send" button, a
   platform mail integration) is a separate decision with its own review.
3. **Disclosure is in the message, not the policy doc.** Every draft states who
   is contacting (IA West, named chapter), why (offering an industry guest
   speaker for a specific named event), where the event information came from
   ("we saw your event listed on <source URL>"), a real human's name and reply
   address, and how to decline or opt out.
4. **Opt-out is a first-class, enforced record.** An organization-level
   suppression list that is checked **before a draft is even generated**, is
   permanent by default, requires no justification to enter, and is enforced in
   the persistence layer rather than in UI. An opt-out honored only by
   convention is not honored.
5. **Per-organization frequency caps.** A hard ceiling on contacts per
   organization per period, enforced server-side, with the count visible to the
   reviewer at draft time. The specific numbers are a program decision (open
   question 7). Precedent exists in the codebase: the repo already implements
   fixed-window rate limiting in PostgreSQL (ADR-0006) and
   charge-quota-before-refusal semantics (ADR-0015).
6. **Full audit trail.** For every draft: which event and which provenance rows
   it was based on, the exact text generated, the model and prompt version, the
   reviewer's identity, the edits they made, the send decision and timestamp, and
   any reply or opt-out. This is what makes "an agent said something wrong" a
   answerable question rather than an unanswerable one. The durable-command path
   in `services/worker/smartmatch_worker/` is already the right home for this —
   API records intent, worker performs it, evidence is persisted.
7. **The contact target is an organization, not a student.** Prefer public org
   inboxes and contact forms. If a decision is ever made to contact named
   individuals, ADR-0014's separation of disclosure consent from contact consent
   applies, and the privacy review named in
   `docs/pilot-data/event-contact-fields-decision-prep.md` must close first.
8. **A written escalation and correction path.** What happens when a draft goes
   out with a wrong fact — who is told, how it is corrected, and how the record is
   marked. Assume it will happen.

**Honest assessment of the value:** with a human reviewing every message, the
throughput ceiling is the reviewer's attention, not the agent's. That is not a
flaw in the design — it is the correct ceiling for outbound speech by a named
organization to students. The agent's leverage here is in *drafting well from
verified provenance*, and above all in **discovery** (§2–§4), where the volume
actually is. **Recommendation: build discovery; treat drafting as a later,
separate, smaller capability; do not build sending.**

---

## 7. Staged roadmap, mapped onto plan P6

P6's cards are S3 (event persistence), S4 (identity + upsert), S5 (vocabulary,
quarantine, review queue), S5f (attendance FK), S5m (optional tag/review schema),
S6a (constrained crawl adapter), S6b (conditional HTTP surfaces). Nothing below
adds a card outside that structure without saying so.

### Stage 0 — buildable now, against fixtures, no gate movement

Genuinely available today because it touches no network, no migration, and no
route:

- **Source-structure survey (documentation card).** For a candidate institution
  set, record for each host: does a `.ics` or RSS feed exist, is `schema.org`
  JSON-LD present, what does `robots.txt` say, is there a documented API. This is
  the empirical input the G3 allowlist decision needs — and it can be done by a
  **human opening pages in a browser**, which is not a live-provider action by the
  system. It converts §2's Medium-confidence claims into facts.
  *(Fence: a new doc under `docs/plans/prep/`. No code.)*
- **Deterministic parser work against committed fixtures.** An iCal parser and a
  JSON-LD `Event` parser, exercised entirely against **synthetic or
  recorded-and-committed fixture files**, mapping into `ExactTime` /
  `DateOnlyTime` / `UnresolvedTime` and `EventProvenance`. This is pure domain
  work with no transport, so it does not need G3 — but it should still be
  **confirmed as in-scope with the P6 owner** before starting, because P6's
  stop-gate says S3/S4 need explicit human authorization to start early.
- **§4 schema review.** Circulate the field table above, especially the
  unknown-allowed column, and get the contact-field group decided.
- **Eligibility rubric drafting.** §5.1's exclusion list, lead-time threshold, and
  phrase list, authored by the program owner as prose. No code.

### Stage 1 — after the **G3 decision** artifact lands

P6's stop-gate requires the artifact to contain, non-blank: the approved agent
evaluation set and pass/fail criteria; allowed tools and domains as an explicit
allowlist; extraction limits (pages, depth, bytes, wall time); per-run and
per-tenant rate and cost ceilings; human escalation behavior; and the named owner
and versioning process for the closed tag vocabulary with its approved initial
terms.

- **S3** — the `event` table per the prep design, with the CHECK constraints that
  make an unresolved event unpublishable. Serial migration resource.
- **S4** — identity key computed before insert, unique index, upsert on duplicate,
  provenance stored as columns. This is where §3.4's dedup lands.
- **S5** — the vocabulary module with terms **copied exactly from the G3
  artifact** (P6: "the executor never invents terms"), quarantine, and the review
  queue that §5's eligibility flow depends on.
- **S5f** — the `attendance_record.event_id` composite FK.
- **Additions this document proposes for the G3 artifact** (each is a decision,
  not code): the source-cascade tier enum; the per-host politeness interval as a
  distinct limit from the per-run budget; the conditional-request/caching
  requirement; the source→`org_unit` mapping policy from §3.4; and the
  eligibility rubric from §5.3.

### Stage 2 — after the **R3 threat-model signature**

R3 requires the threat model no longer marked draft, signed by a **named security
reviewer**, covering SSRF, DNS rebinding, redirect chains, private/link-local
addresses, egress policy, response limits, parser isolation, credential handling,
and audit/provenance.

- **S6a** — the constrained fetch/extract adapter in
  `services/worker/`, implementing exactly the signed controls, running only
  through the durable job path, tested against **local fixtures and fake
  transports**. Every control in the signed model gets a denial test (blocked
  address, redirect escape, size/time overrun, tool outside the allowlist) per
  P6's evidence ladder item 4.
- **S6b (conditional)** — HTTP command/status surfaces *only if the signed G3
  artifact calls for them*, with routes, policy-matrix rows, OpenAPI
  regeneration, and the deliberate flip of the fail-closed scan all in one commit.

### Stage 3 — live targets: prohibited today

**Pointing any of this at live Tavily, a live university calendar, or a real club
site is a live-provider action.** The portfolio's standing constraints — "no live
providers/data, no production credentials" — and P6's own "No live crawl targets,
live providers, or real contact data in tests" prohibit it now, and neither the
G3 decision nor the R3 signature by itself lifts that prohibition. Going live is
a **separate, explicitly human-authorized step** requiring at minimum: the signed
artifacts, a credential-handling decision, a named operator, and agreement on
which institutions are in scope. This document does not authorize it and no card
below Stage 3 should be read as approaching it.

### Stage 4 — outreach: outside P6 entirely

Nothing in §6 maps onto an existing P6 card, and it should not be smuggled into
one. Outbound messaging needs its own gate with its own artifact — institutional
sign-off, legal review, the opt-out and audit design, and a named accountable
human — plus a deliberate flip of the `outreach`/`email`/`send` guard in
`tests/unit/test_no_external_calls_on_request_path.py`. **Recommendation: do not
open this until discovery has produced reviewed events that a human has
successfully acted on manually.** If manual outreach off a good discovery feed is
not already working, automating the drafting will not be what fixes it.

### Interactions with other plans

- **P8 (`opportunities-s12`, cards O1–O4)** owns the canonical "opportunities"
  metric definition and `Opportunities.tsx`. Discovery **produces the rows**; P8
  decides what counts and what is displayed. Per the metric inventory, distinct
  UI filters need distinct registered names, and no opportunities total may
  appear on the Dashboard until a register entry exists. Discovery must not add
  a count anywhere.
- **P5 (G1 matching)** — any score-shaped eligibility output inherits G1. Keep
  eligibility as a rubric with named clauses, and this dependency never forms.
- **P4 (perf)** — the latency invariant is shared: no API request ever waits on a
  fetch. The `services/api/` HTTP-client import ban already enforces it
  structurally.
- **Serial migration resource** — S3, S5f, and S5m sit in the portfolio's
  single-file migration queue; do not open a second migration card in parallel.

---

## 8. Open questions for the program owner

Each is written to be answerable with a decision. Answers feed the G3 decision
artifact P6 requires.

1. **Institution scope.** Which named institutions (and which of their
   departments or campuses) are in scope for the pilot? A list of 3–10 named
   institutions, or "all of <region>"? — *Blocks: the G3 domain allowlist.*
2. **Source tiers approved.** Which of §2's tiers may the system read at all?
   Recommendation: approve Tiers 1 and 2 only; explicitly reject Instagram and
   LinkedIn; allow Discord only by per-server invitation. **Approve / amend /
   reject each row of the §2 summary table.** — *Blocks: the G3 allowlist and the
   R3 egress policy.*
3. **Search's role.** Confirm that Tavily (or any search API) is used **only** to
   propose hosts for a human to allowlist, and **never** to produce an event
   record directly. **Yes / no.** — *Blocks: adapter design; also determines
   whether a search credential is needed at all.*
4. **Contact fields.** For each of `Public URL`, `Point(s) of Contact
   (published)`, `Contact Email / Phone (published)` in
   `docs/pilot-data/event-contact-fields-decision-prep.md`: **collect or drop.**
   Recommendation: collect `Public URL`; drop both personal-contact fields for
   the pilot. — *Blocks: §4.3 of the schema and all of §6.*
5. **Tag vocabulary terms and owner.** The 10–12 initial terms of the closed
   vocabulary, whether "role" and "type" are one vocabulary or two, and the named
   person who owns adding terms. **P6 forbids engineering from inventing these.**
   — *Blocks: card S5 entirely.*
6. **Eligibility rubric.** (a) Minimum lead time in weeks for an event to be
   worth pursuing. (b) The hard exclusion list. (c) The approved
   positive-signal phrase list. **Concrete values.** — *Blocks: §5; without it,
   eligibility becomes a model's opinion.*
7. **Budgets and politeness.** Max pages, crawl depth, bytes, and wall time per
   job; requests per host per minute; per-run and per-tenant cost ceiling; and
   what happens on exceed (recommendation: `BudgetFailure` → `failed_budget`,
   terminal, escalate to the human queue). **Numbers.** — *Blocks: G3's
   extraction-limits section, which the stop-gate requires be non-blank.*
8. **Org-unit mapping policy.** When an extracted host string cannot be mapped to
   a row in `org_unit`, does the event (a) go to review unmapped, or (b) get
   dropped? Recommendation: (a). And who curates the mapping table? — *Blocks:
   card S4; this gap is not currently addressed by the S3 prep design.*
9. **Duplicate merge authority.** When two records are the same event but the
   deterministic key does not merge them (different titles), who may perform the
   human merge, and is it reversible? **Named role.** — *Blocks: the S5 review
   queue's transition set.*
10. **Confidence representation.** Ordinal enum with a written derivation rule
    (recommended), or a numeric score? A numeric score needs a registered name
    and definition under ADR-0011 and, if it gates anything, inherits G1.
    **Pick one.** — *Blocks: §4.4 and P8's metric definition.*
11. **Named security reviewer for R3.** Who signs
    `docs/security/crawler-threat-model-draft.md`, and by when? The stop-gate
    requires a *named* reviewer, and an unsigned model means stop-and-report. —
    *Blocks: card S6a.*
12. **Outreach — proceed at all?** Choose one: (a) no outreach capability in this
    program; (b) agent-drafted, human-reviewed, human-sent, org-inbox-only, per
    §6.3; (c) anything more autonomous — which requires institutional and legal
    sign-off before design begins. **Recommendation: (a) for the pilot, revisit
    (b) once discovery is producing reviewed events.** — *Blocks: whether a
    Stage 4 gate is opened at all.*
13. **If outreach proceeds — accountable human.** Who is the named IA West person
    accountable for every message sent, and who at the institution(s) has agreed
    that contacting their student organizations this way is acceptable?
    **Names.** — *Blocks: any outreach work whatsoever.*
14. **Legal review owner for outreach.** Who obtains counsel review on CAN-SPAM /
    CASL / applicable privacy law before a single message is sent, and by when?
    — *Blocks: any outreach work whatsoever.*
15. **Live-target authorization.** Who authorizes pointing the adapter at real
    hosts, and what evidence must exist first? Today the standing constraints
    prohibit it and this document does not request an exception. — *Blocks:
    Stage 3.*

---

## References

Read during preparation:

- `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` (plan P6, stop-gate, cards)
- `docs/security/crawler-threat-model-draft.md` (unsigned; T-01…T-10)
- `docs/plans/prep/s3-s5-event-persistence-design.md`
- `docs/plans/opportunities-metric-inventory.md`
- `docs/plans/2026-08-28-plan-portfolio-index.md` (standing constraints; serial resources)
- `docs/plans/2026-08-28-performance-caching-plan.md` (lane F4, lane F3)
- `docs/plans/2026-08-28-opportunities-s12-plan.md` (cards O1–O4)
- `docs/pilot-data/event-contact-fields-decision-prep.md`
- `docs/architecture/decisions/ADR-0003-no-agents-in-foundation.md`
- `docs/architecture/decisions/ADR-0014-disclosure-consent.md`
- ADR-0010, ADR-0011, ADR-0012, ADR-0006, ADR-0015 (referenced)
- `python/smartmatch_domain/smartmatch_domain/events.py`
- `services/api/smartmatch_api/routers/events.py`
- `services/worker/smartmatch_worker/handlers.py`, `dispatcher.py`
- `tests/unit/test_no_external_calls_on_request_path.py`
- `apps/web/legacy-frontend/src/app/components/CrawlerContext.tsx`
- `apps/web/legacy-frontend/src/app/pages/Outreach.tsx`
- `apps/web/legacy-frontend/src/lib/api.ts`
- commit `b1204ed` (lane F4), `df4e218` (stop fabricating opportunities)

**This document changes no code, authorizes no provider, chooses no vocabulary
term, sets no limit value, and makes no production-readiness claim.**
