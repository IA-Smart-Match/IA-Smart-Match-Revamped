# G3 allowlist — candidate options for owner approval

**Status:** DRAFT — candidate options for owner approval; **not a decision**;
**changes no code.**
**Date:** 2026-08-29 · **Branch:** `friday-deliverable-828`
**Feeds:** the "allowed tools and domains (explicit allowlist)" line of the G3
stop-gate in `docs/plans/2026-08-28-g3-events-s3-s5-plan.md`, and the egress-policy
item R3 requires on `docs/security/crawler-threat-model-draft.md`.
**Authorizes:** nothing. No host is approved by this file. No institution is
selected by this file. No credential, no provider, no fetch.

**Nothing in this document may be read as approved.** Every host, pattern, and
institution name below is a *candidate* or a *placeholder*. The allowlist becomes
real only when a named owner ratifies entries into a committed contract file, and
even then Stage 3 of the research doc (pointing anything at a live host) remains
separately prohibited by the portfolio's standing constraints.

## Method and epistemic status

Everything asserted about **this repository** was read while preparing this file
and is cited by path. Everything asserted about **the outside world** — whether a
platform has an official API, what its terms say, what its `robots.txt` contains —
is reasoning from general knowledge, was **not** verified by any network call
(no fetch of any candidate host, no Tavily query), and carries a confidence
marker: **High** / **Medium** / **Low**. This is required by the portfolio's
standing constraints (`docs/plans/2026-08-28-plan-portfolio-index.md`, "Standing
constraints": no live providers/data) and by P6's "No live crawl targets, live
providers, or real contact data".

No ToS statement here is legal advice. Every **Medium** and **Low** claim must be
confirmed by a human opening the page before the corresponding entry is ratified —
that human check is Stage 0's "source-structure survey" card in
`docs/plans/prep/campus-event-discovery-capability.md` §7.

Read to ground this file:
`docs/plans/prep/campus-event-discovery-capability.md` (§2, §8 Q1–Q3),
`docs/plans/2026-08-28-g3-events-s3-s5-plan.md` (stop-gate, cards S6a/S6b),
`docs/security/crawler-threat-model-draft.md` (T-01…T-10, adapter interface),
`docs/plans/2026-08-28-plan-portfolio-index.md` (standing constraints, serial
resources), `docs/pilot-data/columns.yaml` (house style for a committed,
ratified contract file), `docs/plans/prep/s3-s5-event-persistence-design.md`
(`owning_unit_id` FK → `org_unit`; `event_provenance.source_url`).

Three sibling prep documents are being drafted concurrently and own what this one
deliberately does not: extraction limits and rate/cost ceilings
(`g3-limits-and-policy-options.md`), the eval set and tag vocabulary
(`g3-eval-and-vocabulary-candidates.md`), and the R3 technical review
(`docs/security/r3-technical-review-findings.md`). Where a number belongs to one
of those, this file names the field and leaves the value blank on purpose.

---

## 1. Allowlist schema proposal

### 1.1 What an entry must specify, and why each field exists

The threat model's adapter interface requires "Accept only URLs on an approved
allowlist (**host + path patterns**)". That is the floor, not the ceiling: T-01,
T-02, T-03, T-06 and T-07 each impose an additional field, and the P6 S6a fence
requires the allowlist be "checked before and after every redirect
(revalidation)". The fields below are derived from those requirements, one by one.

| Field | Required | Why — traced to a control |
|---|---|---|
| `id` | yes | Stable handle for audit rows, denial-test names, and revocation. |
| `host` | yes | Exact registrable host, lowercase, IDNA/punycode-normalized before comparison. Threat model: "host + path patterns". |
| `include_subdomains` | yes | Must be stated, never inferred. A wildcard is a materially larger approval than a host and the owner must be seen to grant it. |
| `subdomain_allow` | when `include_subdomains: true` | An explicit list of permitted labels. **Recommendation: prefer enumerating subdomains over a bare wildcard**; a wildcard on a university host approves every departmental vhost including staging and internal-facing ones, which is exactly the surface T-01 is about. |
| `scheme` | yes | `https` only. An `http` entry needs a written justification and re-approval; plaintext defeats the point of pinning what you are talking to. |
| `port` | yes | Default `443`. Non-default ports named explicitly — an unconstrained port is an internal-service reach in disguise (T-01). |
| `path_prefixes` | yes, non-empty | Allowed path prefixes. **Empty means deny**, never "all paths". Fail-closed is the portfolio's standing rule for gated surfaces. |
| `path_denies` | optional | Explicit subtractions evaluated after prefixes (e.g. login, search, print-view, session-bearing paths). |
| `query_policy` | yes | `none` \| `allowlisted_params: [...]`. Never a free-form query string — free query is how a fetcher becomes an open proxy, and how a credential ends up in a URL (T-06). |
| `source_tier` | yes | `feed` \| `structured` \| `prose`. The §3.1 cascade tier this entry may serve. An entry approved for `feed` may not be used as an LLM-prose target; the tier is an authorization, not a hint. |
| `fetch_method` | yes | `GET` \| `HEAD`. **`GET`/`HEAD` only** — no POST, no form submission, no authenticated session. |
| `content_types` | yes | Expected media types (`text/calendar`, `application/rss+xml`, `application/ld+json`, `text/html`). A response outside the list is refused before parsing (T-04/T-05: the parser is chosen by declaration, not by sniffing the response). |
| `robots` | yes | `posture` (`obey`), `checked_at`, `checked_by`, `crawl_delay_seconds` (or `null` if absent), `notes`. A ratified entry must record that a human read that host's `robots.txt`. |
| `tos_note` | yes | One line on the terms posture and its confidence, or `"not assessed"`. Blank is not permitted. |
| `ip_literal` | yes | `false` for every ordinary entry. T-01: "no raw IP literals in allowlist without review". A `true` value requires a separate named security approval recorded in `approval`. |
| `resolved_ip_policy` | yes | `public_unicast_only` — the resolved address must be public unicast; private, loopback, link-local, CGNAT, multicast, and cloud-metadata ranges are refused at resolve time (T-01, T-02). |
| `redirects` | yes | `max_hops` and `revalidate_each_hop: true`. Every hop is re-checked against the whole allowlist (T-03; P6 S6a). |
| `credentials` | yes | `none` for every Tier-1/Tier-2 web entry. Where a credential exists (a licensed platform API), the field names an **environment variable name**, never a value (T-06, and the repo's secret-management rule). |
| `org_unit_hint` | optional | The `org_unit` row this host is expected to map to, for the §3.4 source→org_unit mapping. A hint for the curator; **never** an automatic mapping — an unmappable extraction still goes to review. |
| `tenant_scope` | yes | `global` or a tenant id. Open question — see §6. |
| `approval` | yes | `approved_by` (named human), `approved_at` (date), `review_by` (expiry date), `decision_ref` (the G3 artifact section). An entry with a blank `approved_by` is not an entry. |
| `status` | yes | `proposed` \| `approved` \| `suspended` \| `revoked`. Only `approved` is fetchable. Proposed entries are inert data (see §5). |

**Two stanzas, one file.** The stop-gate says "allowed tools **and** domains
(explicit allowlist)" and T-07 is *tool* sprawl, not domain sprawl. The research
doc's §2 covers domains only. So the contract file carries a `tools:` stanza
alongside `hosts:` — the closed set of adapter capabilities (`fetch_ics`,
`fetch_rss`, `parse_jsonld`, `llm_extract_prose`, `search_seed`), each with its
permitted tiers. An adapter capability not named there is unavailable, the same
way an unregistered worker command fails the job explicitly in
`services/worker/smartmatch_worker/handlers.py`.

### 1.2 Concrete file format (proposed), with a filled example

Proposed location: `config/crawl/allowlist.yaml`, committed, reviewed like
`docs/pilot-data/columns.yaml` — a ratified contract with a header that says who
ratified it and what is still open. **This path does not exist and this drop does
not create it.**

```yaml
# PROPOSED FORMAT ONLY -- no entry below is approved; names are PLACEHOLDERS.
version: 0                      # 0 = unratified draft; the signed artifact sets 1
schema_version: 1
default: deny                    # an empty or unparsable file fetches nothing

tools:
  fetch_ics:          { tiers: [feed],       parser: icalendar,  network: true  }
  fetch_rss:          { tiers: [feed],       parser: feed_xml,   network: true  }
  parse_jsonld:       { tiers: [structured], parser: jsonld,     network: false }
  llm_extract_prose:  { tiers: [prose],      parser: none,       network: false }
  search_seed:        { tiers: [],           parser: none,       network: true,
                        may_write_events: false }   # see section 5

hosts:
  - id: placeholder-univ-a-central-calendar
    host: events.placeholder-university-a.edu     # PLACEHOLDER -- not a real approval
    include_subdomains: false
    subdomain_allow: []
    scheme: https
    port: 443
    path_prefixes:
      - /calendar/
      - /api/2/events            # vendor JSON endpoint, if the survey confirms one
    path_denies:
      - /calendar/print/
      - /calendar/login
    query_policy:
      allowlisted_params: [start, end, days, type]
    source_tier: feed
    fetch_method: GET
    content_types: [text/calendar, application/json, application/rss+xml]
    robots:
      posture: obey
      checked_at: null           # BLANK -- Stage 0 survey has not run
      checked_by: null
      crawl_delay_seconds: null
      notes: "not yet read; no network call was made preparing this file"
    tos_note: "published .ics is an invitation to subscribe (confidence: High as a
               general posture; Medium for this host until surveyed)"
    ip_literal: false
    resolved_ip_policy: public_unicast_only
    redirects:
      max_hops: 3
      revalidate_each_hop: true
    credentials: none
    org_unit_hint: null
    tenant_scope: global
    approval:
      approved_by: null          # BLANK ON PURPOSE -- nothing here is approved
      approved_at: null
      review_by: null
      decision_ref: null
    status: proposed
```

Every `null` above is deliberate. A file in this shape with `status: proposed`
everywhere is exactly what the owner should be handed: the *shape* of the
approval, with the approval itself absent.

### 1.3 How enforcement works at fetch time

The allowlist is not a URL filter applied once at the top. It is a predicate
evaluated at every point where the identity of the peer could change. Sequence,
mapped to the threat catalog:

1. **Parse and normalize the candidate URL.** Lowercase and punycode the host,
   reject userinfo (`user:pass@`) outright, reject non-`https` schemes, reject
   non-default ports not named in the entry. *(T-06: a credential in a URL never
   gets as far as a socket.)*
2. **Match host → entry.** Exact host, or an explicitly listed subdomain label.
   No match ⇒ refuse. **No entry means no fetch**; there is no implicit allow.
3. **Match path and query** against `path_prefixes`, then `path_denies`, then
   `query_policy`. Path normalization (`..`, encoded separators, duplicate
   slashes) happens **before** matching, or prefix matching is defeated by
   traversal.
4. **Resolve DNS. Then check the resolved addresses, not the name.** Every
   returned address must be public unicast; any private/loopback/link-local/CGNAT/
   metadata address ⇒ refuse the whole resolution, not just that address.
   *(T-01.)*
5. **Pin the resolved address for the connection** and connect to the pinned
   address, so the name cannot be re-resolved to something else between the check
   and the connect. *(T-02 DNS rebinding: the threat model's own wording is
   "Re-resolve host before connect; pin resolved IP to policy". A check-then-
   connect-by-name adapter does not satisfy this and would pass a naive test.)*
6. **On every redirect hop, return to step 1 with the Location URL** — full
   re-normalization, re-match against the *whole* allowlist, re-resolve,
   re-pin — and count the hop against `max_hops`. A hop is not "trusted because
   its parent was". Cross-entry redirects (host A → host B, both approved) should
   be a recorded event, because a legitimate calendar rarely redirects to another
   approved institution and a chain that does is worth a human look. *(T-03; P6
   S6a: "checked before and after every redirect (revalidation)".)*
7. **Enforce the declared content type and the byte/time ceilings while
   streaming**, before any parser sees the body; select the parser from the
   entry's declaration, not from sniffing. *(T-04, T-05. Ceiling values are the
   sibling limits document's to propose.)*
8. **Record the decision either way.** Every allow and every denial writes an
   audit row naming the entry `id`, the final URL, the hop count, and the
   resolved address — with credentials redacted (T-06). A denial that leaves no
   trace cannot be reviewed and cannot be tested.

**Test shape that proves it (for S6a's denial-test ladder, evidence item 4):**
fixtures and fake transports only, never a live host — a URL off-allowlist; an
approved host redirecting to an unapproved one; an approved host redirecting to
`127.0.0.1`, `169.254.169.254`, and a private RFC1918 address; a host whose
second resolution differs from its first (rebinding); a path-traversal URL that
normalizes outside `path_prefixes`; a URL carrying userinfo credentials; a
response whose content type is outside `content_types`; and a tool invoked
outside the `tools` stanza. Each must fail closed and produce an audit row.

---

## 2. Institution-scope options for the owner

Open question 1 in the research doc is the owner's to answer and this file does
not answer it. What follows is the shape of each answer so the answer is cheap.

**All institution names below are PLACEHOLDERS** (`Placeholder University A`,
`Placeholder State System`, …). They are there to show structure. Substituting
real names is the owner's act, not this document's.

### 2.1 Decision table

| Option | Rough host count | Review burden | Crawl-budget consequence | Recovers from a wrong choice? |
|---|---|---|---|---|
| **(a) Named pilot set, 3–5 institutions** | ~3–5 central calendars + ~5–15 department/seminar hosts + 0–5 student-org platform hosts ⇒ **roughly 10–25 entries** | Every entry human-surveyed (robots, feed presence, ToS) and every extracted event reviewable by one person | Smallest per-run page count; per-host politeness intervals easy to honor; cost ceilings comfortably non-binding | Yes — add an institution by adding entries |
| **(b) One university system** | Campuses × (1 central + several department hosts); a mid-size system plausibly **50–200+ entries**, and department hosts are the long tail that never ends | Beyond one reviewer for the initial survey; ongoing entry churn as departments reorganize | Per-run page budget becomes binding; needs per-host scheduling and staleness tiering to avoid re-fetching everything | Partially — pruning a system back down is politically awkward once campuses expect coverage |
| **(c) Named metro region** | Every institution in the metro, all types (R1, regional, community college, possibly private high schools running hackathons) ⇒ **100–300+ entries**, heterogeneous platforms | High and *uneven* — small institutions often have no feed at all, which pushes work into Tier-3 prose and LLM extraction, the most expensive and least reliable path | Worst ratio of budget to yield: many hosts, few events each, high fraction requiring prose extraction | Yes, but the survey cost is sunk |
| **(d) All of a state** | **Hundreds to low thousands** of hosts | Not reviewable by a human at entry granularity — which means the allowlist stops being an allowlist and becomes a pattern language, and T-07's closed set stops being closed | Budget and politeness become the dominant engineering problem before a single event is placed | No — this is a one-way door on the review model |

### 2.2 Recommendation

**Option (a), a named set of 3–5 institutions**, and specifically ones where IA
West already has a human relationship.

Why, in order of weight:

1. **The binding constraint is human review, not fetching.** The research doc's
   §5.3 puts a human-authored eligibility rubric between extraction and anything
   publishable, and §4.4 puts every LLM-derived record into `review_status =
   pending`. The `pending_review_items` metric already exists in
   `smartmatch_domain/metrics.py`, so the backlog will be visible immediately.
   Scope should be set so the queue is drainable by the people who exist.
2. **The allowlist model only works while entries are individually reviewable.**
   T-07 asks for a *closed* set. At option (d) scale nobody reads entries, and an
   unreviewed allowlist entry is a fetch nobody authorized.
3. **The Stage 0 survey is manual browser work by a human** (research doc §7).
   Ten to twenty-five hosts is an afternoon. Two hundred is a project that will be
   skipped, and skipping it means ratifying entries whose robots and ToS posture
   is unknown — the exact thing the schema's non-blank `robots` and `tos_note`
   fields exist to prevent.
4. **A pilot answers the empirical question the whole design rests on**: what
   fraction of target pages actually carry `.ics`/JSON-LD? The research doc marks
   that Medium-High confidence and unmeasured. Three institutions measure it;
   three hundred just multiply an unvalidated assumption.
5. **It is the reversible choice.** Growth is additive entries. Options (b)–(d)
   are hard to walk back once campuses have been told they are covered.

**Sequencing suggestion (not a decision):** ratify option (a); require the
first-run measurement of feed prevalence and review-queue drain rate before
proposing (b); treat (c) and (d) as requiring a different allowlist model
(patterns + sampling + a much stronger automated denial story), i.e. a new gate,
not a bigger list.

### 2.3 What each option looks like structurally

Same schema throughout; only the entry population differs. **Placeholders.**

**(a) Named pilot set — enumerated hosts, one entry per host:**

```yaml
hosts:
  - { id: pu-a-calendar,  host: events.placeholder-university-a.edu,  include_subdomains: false, source_tier: feed,       status: proposed }
  - { id: pu-a-cs-dept,   host: cs.placeholder-university-a.edu,      include_subdomains: false, source_tier: structured, status: proposed,
      path_prefixes: [/events/, /seminars/] }
  - { id: pu-b-calendar,  host: calendar.placeholder-university-b.edu, include_subdomains: false, source_tier: feed,      status: proposed }
  # ... 10-25 total, each individually surveyed and individually approved
```

**(b) One university system — the temptation is a wildcard; resist it:**

```yaml
hosts:
  - id: placeholder-state-system-campuses
    host: placeholder-state-system.edu
    include_subdomains: true
    subdomain_allow: [events-campus1, events-campus2, events-campus3]   # ENUMERATED, not "*"
    source_tier: feed
    status: proposed
```
A bare `include_subdomains: true` with an empty `subdomain_allow` would approve
every vhost under the system's domain — staging calendars, internal portals,
whatever a department stands up next month. If the owner picks (b), the honest
form is still enumeration; the system choice buys a shared robots/ToS posture and
a single relationship contact, not a shortcut past per-host review.

**(c) Metro region — grouping is documentation, not authorization:**

```yaml
groups:
  placeholder-metro:
    description: "PLACEHOLDER metro region; grouping is for review ergonomics only"
    members: [pu-a-calendar, pu-b-calendar, pcc-c-calendar, ...]   # every member still an entry
```

**(d) All of a state — what it would actually require, stated so it can be
rejected on sight:** a pattern-based rule (`*.edu` within a state list) plus
automated robots fetching, automated ToS classification, sampling-based review,
and an entry-count ceiling. None of that exists, none of it is designed, and it
converts T-07's closed tool/host set into an open one. **Not recommended, and it
should not be adopted incrementally by letting (b) or (c) grow.**

---

## 3. Per-source-tier approval rows

One row per §2 source in the research doc. The owner marks each
**APPROVE / AMEND / REJECT** — including the rejections, so that Instagram and
LinkedIn are *rejected*, not silently omitted. A silent omission is
indistinguishable from an oversight and will be re-litigated by whoever ships
S6a.

Outside-world claims carry confidence markers and are unverified by any network
call.

| # | Source (research doc §2) | What it yields | Access method | Official API / feed? | Robots + ToS posture | Research doc's recommendation | Owner mark |
|---|---|---|---|---|---|---|---|
| 1 | University central calendar (Tier 1a) | Colloquia, seminars, career panels, info sessions — the highest-value target | `.ics` / RSS / JSON-LD; deterministic parse, no LLM | Often, vendor-dependent — Localist/Concept3D, Trumba, 25Live *(Medium)* | Published feed is an invitation to subscribe; obey robots and `Crawl-delay` *(High as posture; Medium per host)* | **Yes — first allowlist** | ☐ approve ☐ amend ☐ reject |
| 2 | Department / lab / seminar-series pages (Tier 1b) | Named speaker slots, recurring series, course-adjacent guest-lecture openings | HTML; JSON-LD when present, prose otherwise | Rarely *(High)* | Ordinary public pages; robots governs *(High)* | **Yes, narrow** — structured tier where markup exists, prose tier only for the remainder | ☐ approve ☐ amend ☐ reject |
| 3 | Student-org platforms — Engage/CampusLabs, CampusGroups, Presence (Tier 2a) | Club-hosted programming — the layer Tavily was guessing at | Public event pages; sometimes iCal export or a read API | Sometimes, **institution-gated** *(Medium)* | Institution-licensed products; the correct move is **asking the campus**, not scraping *(Medium)* | **Only via partnership** — ask for the feed or credential | ☐ approve ☐ amend ☐ reject |
| 4 | Devpost, MLH (Tier 2c) | Hackathons and datathons — highest conversion per record (judges, mentors, keynotes) | Public listing pages, semi-structured; MLH publishes a season list | Unclear; an officially supported unauthenticated JSON endpoint is **not** assumed *(Low)* | Ordinary platform ToS; check robots *(Medium)* | **Yes — small, enumerable, every record human-reviewable** | ☐ approve ☐ amend ☐ reject |
| 5 | Eventbrite, Luma (Tier 2b) | Externally-promoted campus and adjacent events | Documented API where available; public pages otherwise | Eventbrite historically yes but search narrowed over time *(Medium)*; Luma *(Low–Medium)* | Commercial ToS generally restrict automated collection; use the documented API within its terms *(Medium)* | **Defer** — API-first, and only within the API's own terms | ☐ approve ☐ amend ☐ reject |
| 6 | Tavily / any search or answer API (Tier 3) | *Pointers to hosts*, never events | Credentialed commercial API | Yes *(High)* | Provider terms govern the query; the **destination's** terms govern any fetch — search does not launder a forbidden fetch *(High as principle)* | **Seeding only, never ingest** — see §5 | ☐ approve ☐ amend ☐ reject |
| 7 | **Instagram** (Tier 4a) | Club posts — but event details usually live inside a flyer image | Would require OCR of marketing graphics | Graph API is oriented to accounts you own or are granted *(Medium)*; no arbitrary discovery path *(High)* | Automated collection without authorization is contrary to Meta's terms *(High posture / Medium detail)* | **REJECT — out of scope.** If a club's Instagram is the only source, a human follows the account | ☐ approve ☐ amend ☐ **reject (recommended)** |
| 8 | **LinkedIn** (Tier 4c) | Professional/event posts | Scraping | No *(High)* | User agreement prohibits automated scraping and it is actively enforced *(High)* | **REJECT — out of scope for automated collection entirely** | ☐ approve ☐ amend ☐ **reject (recommended)** |
| 9 | **Discord** (Tier 4b) — conditional | Club server announcements | Bot in a server | Yes, but a bot requires an **invitation from that server's administrators** *(High)* | Joining or reading without that grant is not legitimate; never a discovery sweep *(High)* | **CONDITIONAL — only by explicit per-server invitation, recorded** | ☐ approve-with-conditions ☐ reject |
| 10 | University subreddits, newsletters, mailing lists (Tier 4d) | Occasional signal, low structure | Varies | n/a | Varies | Better served by a human subscribing than an adapter | ☐ approve ☐ amend ☐ **reject (recommended)** |

**If row 9 is approved with conditions**, the per-server grant needs the same
evidentiary shape as a host entry — who invited the bot, which server, when, what
scope, and an expiry — and it is *not* a host in `allowlist.yaml` because it is
not an HTTP fetch. Recommendation: a separate `discord_grants` stanza (or a
separate file) so it can never be confused with a web entry, with `status:
proposed` and no grants recorded today.

**Rows the owner rejects should be written into the artifact as rejections with a
date**, so a future contributor reads "considered and declined on <date>" rather
than "nobody thought of it".

---

## 4. Generic host patterns that need no institution decision

These are in scope (or out) regardless of which institutions the owner picks, so
they can be surveyed and decided in parallel with open question 1. **Every claim
in this section is general knowledge, unverified by any network call**, and is
marked accordingly. None of these is approved; each still needs the Stage 0
survey and a named approver.

| Candidate host | Why it is institution-independent | Official API? | Confidence | Notes / what a human must check first |
|---|---|---|---|---|
| `devpost.com` | Hackathon listings are cross-institution by construction | Public pages carry structured metadata; an officially supported public JSON API is **not** something I can assert | **Low** on a documented public API; **Medium** that listing pages are stably structured | Reasoning from general knowledge only. Check `robots.txt`, check whether an API is documented, check ToS on automated collection. Population is small enough that every record is human-reviewable — the strongest argument for including it early |
| `mlh.io` | MLH publishes a season-wide event list spanning many campuses | A published season list exists in some form; whether a machine-readable endpoint is officially supported is unknown to me | **Medium** that a season list exists; **Low** on a supported API | General knowledge. Small, enumerable, high value per record |
| `eventbrite.com` (+ regional variants) | Organizer-side platform, not tied to one campus | Documented REST API has existed historically; search capability narrowed over time | **Medium** | General knowledge. If used at all, API-first and within the API's terms; a credential means the `credentials:` field names an env var, never a value |
| `lu.ma` / `luma` event pages | Increasingly common for tech-community and student events | Public event pages; some calendar subscription | **Low–Medium** | General knowledge. Verify before proposing an entry |
| Engage / CampusLabs (`*.campuslabs.com` style) | One vendor serving many campuses — one integration, many institutions | Institution-gated; per-campus configuration | **Medium** | General knowledge, and the vendor host pattern itself is **Medium** confidence — I have not verified current hostnames. **Ask the campus** rather than scraping; a partnership entry is a different, better artifact than an allowlist entry |
| CampusGroups (`*.campusgroups.com` style) | Same | Institution-gated | **Medium** | Same. Host pattern unverified |
| Presence (`*.presence.io` style) | Same | Unknown to me | **Low** | General knowledge; hostname pattern unverified |
| Localist / Concept3D calendar tenants | The vendor behind many university central calendars; a single parser serves many institutions | Documented iCal/JSON endpoints in common deployments | **Medium** | General knowledge. Note this is a *parser* reuse opportunity — the **hosts are still per-institution** and still need individual entries; the vendor does not authorize anything |
| Trumba, 25Live | Same class of higher-ed calendar vendor | Vendor-dependent | **Medium** | Same caveat: vendor-level parser reuse, institution-level approval |

**The distinction that matters here:** a shared *vendor* means shared *parsing
work*, not shared *authorization*. `parse_jsonld` and `fetch_ics` in the `tools`
stanza are written once; the host entries are still enumerated per institution and
approved per institution. Collapsing those two ideas is how a vendor pattern
quietly becomes a wildcard.

**Also institution-independent and worth stating: the deny side.** The owner
should approve an explicit permanent deny list alongside the allowlist —
`instagram.com`, `linkedin.com`, URL shorteners, and any host reached only via
redirect — so a redirect into a rejected platform is refused by name and produces
a specific audit reason, not a generic "not on the allowlist".

---

## 5. Search as seeding only — the mechanical control

Open question 3 asks the owner to confirm that Tavily (or any search API) may
**only propose hosts** for a human to allowlist and may **never** produce an event
record. Confirmation is a policy statement; below is what makes it true in code.

### 5.1 The mechanism

1. **Separate destination table.** Search output writes to
   `proposed_host` — the columns are a proposed host, the query that surfaced it,
   the provider and query timestamp, the raw result snippet, and
   `status ∈ {proposed, promoted, rejected}`. It writes **nothing** to `event` or
   `event_provenance`. Different table, different writer, no shared path.
2. **No code path from `proposed_host` to `event`.** The ingest function's
   signature takes an *allowlist entry id* plus a fetched artifact. It cannot be
   called with a `proposed_host` row, because a `proposed_host` row has no entry
   id — the type does not exist until a human creates the allowlist entry.
   This is the same discipline as `resolve_identity_key` returning `None` for
   `UnresolvedTime`: **the illegal state is unconstructible, not merely
   discouraged** (ADR-0010/ADR-0012, and the pattern already used in
   `smartmatch_domain/events.py`).
3. **`search_seed` is a tool with `tiers: []`.** The §3.1 cascade tier enum is
   `feed | structured | prose`. **Search is not a tier**, so no extraction record
   can carry `extraction_tier: search` — the enum has no such value and the column
   is `NOT NULL`. The research doc's §4.4 already says "search is never an ingest
   tier"; making that a DB enum rather than a comment is what enforces it.
4. **Promotion is a human write to a committed file.** A person reviews a
   `proposed_host` row, performs the Stage 0 survey on it (robots, ToS, feed
   presence), and writes an allowlist entry with their name in `approved_by`. The
   entry lands in version control, in a reviewed commit. There is no
   "auto-promote", no threshold, no confidence score that promotes. The runtime
   has **no write path to the allowlist at all** — it is read-only config, and
   that is the property to preserve.
5. **Search results are untrusted input.** A search result's title and snippet are
   attacker-influenceable text arriving from outside the trust boundary. They may
   be *displayed* to the reviewing human, never interpreted as instructions and
   never used to populate an event field. The threat model's trust-boundary
   diagram treats fetched bodies as untrusted; **search results deserve the same
   marking and the draft does not currently give it to them** (see §7).

### 5.2 Invariants and the tests that prove them

| Invariant | Test that proves it | Kind |
|---|---|---|
| No module that can call a search provider can also write to `event` / `event_provenance` | Import-graph / static test: the search-seeding module's transitive imports contain no persistence writer for those tables. Direct precedent: `tests/unit/test_no_external_calls_on_request_path.py` already asserts that **no module under `services/api/` imports an HTTP client at all** — the same technique, applied to a different pair | unit, static |
| `extraction_tier` cannot be `search` | Enum has three values (`feed`, `structured`, `prose`); a DB CHECK plus a unit test asserting the rejected write | unit + integration |
| Ingest cannot be called with an un-allowlisted host | Type-level: the ingest entry point takes an allowlist entry id, not a bare URL; a test asserts a raw-URL call does not type-check / raises | unit |
| A `proposed_host` row never becomes an event without a committed allowlist entry | Integration: seed a `proposed_host`, run the discovery command, assert zero `event` rows and a `failed_policy` (`PolicyFailure`) outcome, per the taxonomy in `services/worker/smartmatch_worker/handlers.py` | integration |
| The allowlist is read-only at runtime | Test that no module opens the allowlist path for writing; the loader exposes a read API only | unit, static |
| Promotion is attributable | Every `approved` entry has non-null `approved_by`, `approved_at`, `decision_ref`; a schema/lint test over the committed file fails the build otherwise | unit (file lint) |

The load-bearing one is the first. Everything else can be argued around; an
import-graph assertion cannot, and the repository already has the exact precedent
for writing it.

---

## 6. What remains blocked on the owner after this file

Each is a decision, not a task. Numbers in brackets map to the research doc's §8.

1. **[Q1] Institution scope option: (a), (b), (c), or (d)?** Recommendation:
   **(a), 3–5 named institutions.** *Blocks: every host entry; the Stage 0 survey
   cannot start without a target list.*
2. **[Q1] The names.** Once (a) is chosen — which institutions, and which
   departments within them. Engineering must not choose these. *Blocks: the
   allowlist contents.*
3. **[Q2] Mark every row of §3 approve / amend / reject** — including explicitly
   rejecting Instagram and LinkedIn, and explicitly deciding Discord's conditional
   status. *Blocks: the egress policy R3 must sign.*
4. **[Q3] Confirm search is seeding-only: yes / no.** A "no" changes the adapter
   design substantially and reopens whether a search credential is needed at all.
   *Blocks: §5, and the credential decision.*
5. **Wildcard policy.** May any entry use `include_subdomains: true` with an
   unenumerated `subdomain_allow`? Recommendation: **no**, and if ever yes, only
   with a separate named security approval per entry. *Blocks: the schema's final
   shape.*
6. **Tenant scoping.** Is the allowlist global to the deployment or per-tenant?
   T-08 already contemplates **per-tenant** budgets, so per-tenant allowlisting is
   at least arguable — but a per-tenant allowlist means a tenant can add fetch
   targets, which is a materially different threat model. Recommendation:
   **global, human-committed, read-only at runtime** for the pilot. *Blocks: the
   `tenant_scope` field and part of R3's egress policy.* **This question is not
   raised anywhere in the research doc or the threat model.**
7. **Entry expiry.** Does an approved entry expire (`review_by`) and what happens
   at expiry — suspend and stop fetching, or warn and continue? Recommendation:
   **suspend**; a stale approval is not an approval. *Blocks: the schema and the
   operational runbook.*
8. **Who owns the allowlist file.** A named human who approves entries, and the
   review process for changing one. The stop-gate requires a named owner for the
   vocabulary; the allowlist needs the same and the plan does not currently say
   so. *Blocks: ratification itself — an allowlist with no owner cannot be
   ratified.*
9. **The permanent deny list** (§4). Approve its initial contents. *Blocks:
   redirect-refusal behavior with specific audit reasons.*
10. **Partnership-versus-scrape posture for student-org platforms** (row 3). Is IA
    West willing to ask campuses for feed access, and who asks? Recommendation:
    ask — it is both the lower-risk and the higher-yield path. *Blocks: whether
    Tier 2a appears in the allowlist at all.*

Explicitly **not** blocked on this file and owned elsewhere: extraction limits and
rate/cost ceilings, the eval set and pass/fail criteria, the tag vocabulary terms,
and the R3 signature itself.

---

## 7. Constraints the threat model and P6 impose that the research doc did not surface

Recorded because they change the allowlist's shape, and a reader of the research
doc alone would miss them.

1. **The stop-gate says "allowed tools **and** domains", and T-07 is tool sprawl.**
   The research doc's §2 is entirely about domains. An allowlist that names only
   hosts leaves half the stop-gate line blank. Hence the `tools:` stanza in §1.1.
2. **T-01's "no raw IP literals in the allowlist without review" is an explicit
   schema requirement**, not just a runtime check. It implies an `ip_literal`
   field with a default of `false` and a separate approval to set it `true`. The
   research doc never mentions IP-literal entries.
3. **T-02 requires pinning the resolved IP, not merely re-resolving.** "Re-resolve
   host before connect; pin resolved IP to policy" — an adapter that validates the
   hostname and then hands the *name* to the HTTP client has a rebinding window
   and would still pass a shallow test. This is a property of how the entry is
   *used*, and the reason §1.3 step 5 exists.
4. **P6's S6a fence says the allowlist is checked "before **and after** every
   redirect"** — that phrasing (revalidation, not just a hop cap) is stronger than
   the research doc's summary line and is what §1.3 step 6 implements.
5. **T-06 constrains the entry format itself.** "No secrets in URLs/logs" means an
   entry may never carry an embedded credential in `host` or `path_prefixes`, and
   the `credentials` field must name an env var rather than hold a value. The
   research doc discusses credentials only as a Stage 3 concern.
6. **The portfolio's fail-closed rule fixes the empty-file semantics.** "Gated
   surfaces stay fail-closed until their written artifacts pass" means an absent,
   empty, or unparsable allowlist must fetch **nothing** — hence `default: deny`
   and non-empty `path_prefixes`. Worth stating because "no allowlist configured"
   defaulting to "allow all" is a classic and quiet failure.
7. **The allowlist file is a shared serial resource and the portfolio index does
   not list it.** `docs/plans/2026-08-28-plan-portfolio-index.md` tracks migration
   numbers, `contracts/openapi/smartmatch.json`, the policy matrix, the
   fail-closed scans, `api.ts`, `Opportunities.tsx`, and `test_metrics.py` — but a
   config file that multiple cards will touch (S6a adds the loader; S6b may add a
   status surface) has no ownership row. **Recommendation: add one, owned by
   P6·S6a.**
8. **The threat catalog has no entry for search-seeded host injection.** T-01…T-10
   cover fetching and parsing; nothing covers "an untrusted search result proposes
   a host and the proposal is trusted too far". Given that open question 3 makes
   search a first-class input, R3 should consider a **T-11: untrusted seeding
   input** — control: proposals are inert data, promotion is a human commit,
   snippets are displayed but never interpreted. Flagged here for the R3 reviewer;
   `docs/security/r3-technical-review-findings.md` is a sibling's file and this
   drop does not touch it.
9. **Nothing in either document says who owns the allowlist.** The stop-gate names
   an owner for the tag vocabulary and a named reviewer for R3, but not an
   approver for allowlist entries — and §1.1's `approval.approved_by` cannot be
   filled without one. See §6 item 8.

---

**This file changes no code, approves no host, selects no institution, sets no
limit value, creates no configuration file, and makes no production-readiness
claim. Every institution name in it is a placeholder. Every `approved_by` is
blank on purpose.**

---

## 8. Verified source survey — Cal Poly Pomona (2026-08-29)

**Added after the rest of this document.** Recorded by the orchestrating session
using ordinary web research (a browser-equivalent desk survey), not by the
product and not by any crawl code. No credential was used, no allowlist was
enforced, nothing was persisted. This is the Stage 0 "human-browser source
survey" the roadmap calls for, performed for one institution.

**Scope decided by the program owner on 2026-08-29: Cal Poly Pomona only.**

### 8.1 Why this section exists

The owner reported that "CPP does not have a public `calendar.cpp.edu`, same
goes for clubs," and identified that absence as the original motivation for
building a crawler. That report is **half right**, and the half that is wrong
changes the architecture materially — so it is recorded here with evidence
rather than left as a remembered remark.

### 8.2 Verified structured sources

| Host | Access method | Tier | Status |
|---|---|---|---|
| `asi.cpp.edu` | WordPress *The Events Calendar* REST API **and** iCal | 1 | **Verified — live data returned** |
| `cpp.libcal.com` | iCal subscription (Springshare LibCal; API also exists) | 1 | High confidence — subscribe offered, URL not captured |
| `events.vtools.ieee.org` | Per-event iCal at `/event/{id}/ical`; API at `/api/doc` | 1–2 | High confidence — a real CPP student-branch event confirmed |

**`asi.cpp.edu` is the strongest finding and is fully verified.** The site runs
`PRODID:-//ASI Cal Poly Pomona - ECPv6.17.3.1//NONSGML v1.0//EN` — *The Events
Calendar* WordPress plugin v6.17.3.1 — which exposes both:

- iCal: `https://asi.cpp.edu/activities-calendar/?ical=1` — returned a valid
  `BEGIN:VCALENDAR` document with `VTIMEZONE America/Los_Angeles` and real
  August 2026 `VEVENT` entries.
- REST: `https://asi.cpp.edu/wp-json/tribe/events/v1/events` — returned JSON
  with approximately thirty fields per event, including `title`, `description`,
  `start_date`, `end_date`, `timezone`, `venue`, `organizer`, `categories`,
  `tags`, `cost`, `url`, `image`, `is_virtual`.

This is a deterministic tier-1 source. Events from it **never need to reach an
LLM**, which is both a cost property and a security property (see T-11).

### 8.3 Verified absent — the real gap

| Source | Finding |
|---|---|
| `mybar.cpp.edu` | **Retired.** Every path, including deep API paths, `301`s to a placeholder page at `www.cpp.edu/blc/students/join.shtml` |
| `join.cpp.edu` | **Does not resolve** (`ENOTFOUND`). Announced as "launching", not live |
| `www.cpp.edu` department pages | Prose landing pages. No iCal, no RSS, no JSON-LD observed |

So the owner's report is accurate about **the student-organization platform
layer**, which is genuinely mid-migration with no live replacement. It is
inaccurate about the **university/ASI layer**, which publishes real feeds today.

### 8.4 The architectural consequence

Nationally affiliated club chapters publish through their **national**
platforms, which are structured, even when the campus platform is not. IEEE CPP
Student Branch events appear on IEEE vTools with iCal and an API. The same
pattern is worth checking for ACM, SWE, NSBE, and SHPE — and CPP's
technology-focused organizations (Computer Science Society, Data Science and AI
Club, Software Engineering Association, Women in Tech) are precisely the
chapters IA West would want to reach.

**This is a better route to club events than social media**: structured data,
stable URLs, no terms-of-service conflict, and no optical character recognition
of marketing graphics for the single most consequential field (the date).

### 8.5 Effect on earlier conclusions in this document

1. **Feeds-first is vindicated for a meaningful share of the corpus.** The
   four-tier cascade is not a fiction at CPP; tier 1 exists and carries the
   university-wide calendar.
2. **The cost model returns to the feeds-first profile.** See the correction
   recorded at §3.2a of `g3-limits-and-policy-options.md`.
3. **T-11's cascade mitigation partly survives.** Prompt injection remains a
   primary concern for tier-3 prose sources, but it is not the whole pipeline.

### 8.6 Verification status, stated honestly

- `asi.cpp.edu` iCal and REST API: **verified**, live data observed.
- `cpp.libcal.com`: subscribe affordance observed; **the iCal URL itself was not
  captured** and must be confirmed before allowlisting.
- `events.vtools.ieee.org`: a CPP student-branch event page observed with an
  iCal link and an API referenced in navigation; **the API was not exercised**.
- `devpost.com`, `mlh.io`, Eventbrite: carried forward from §4; **not
  re-verified in this pass**.
- Instagram: **deferred by owner decision**, 2026-08-29.

### 8.7 Next verification steps (not yet performed)

1. Exercise the ASI REST API against the eligibility rubric to measure what
   fraction of ASI events are plausibly *speaking* opportunities. Early
   indication is that the fraction is **low** — observed entries include SCUBA
   training and open recreational volleyball — which is itself a useful
   precision signal and argues for the rubric doing real work.
2. Capture the LibCal iCal URL.
3. Check whether ACM, SWE, NSBE, and SHPE national platforms carry CPP chapters.
