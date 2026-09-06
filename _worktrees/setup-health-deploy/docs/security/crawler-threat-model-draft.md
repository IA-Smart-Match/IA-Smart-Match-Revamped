# Crawler threat model — revision 4, draft for R3 sign-off

**Status:** **SIGNED — design requirements approved 2026-09-03.** Not implemented; live fetch gated on S6a evidence pass.
**Revision:** 4 (2026-08-30). Revisions 1, 2 and 3 remain in git history.
**Gate:** R3. G3 itself was **signed** 2026-08-29 (`docs/decisions/g3-crawler-decision.md`).
**Reviews that produced this revision:**
  - `docs/security/r3-technical-review-findings.md` — the self-review behind revision 2
  - an **adversarial** independent review of revision 2, conducted by a reviewer
    explicitly told that revision 2 was a self-review, which returned
    **DO NOT SIGN** and twelve minimum required edits. Revision 3 answered it.
  - a second **adversarial** independent review, of **revision 3**, which again
    returned **DO NOT SIGN**: three blocking findings — T-02's proxy escape
    hatch, C-6 granting exactly the capability C-4 denies, and C-1 requiring
    storage T-14 prohibits — plus seven further required edits.
    **Revision 4 exists to answer that review.** Its findings are reproduced
    here in the rows and sections they touch; the review pass itself made no
    code or document change.
**T-11 depth:** `docs/security/prompt-injection-assessment.md`
**Related ADRs:** ADR-0003, ADR-0010, ADR-0012, ADR-0015 (amendment pending), MM-A08.

## Stabilization note — read before signing

The adversarial review found the checkout unstable for a durable signature: this
document was modified but uncommitted, and G3 plus both supporting reviews were
untracked. **A signature must not be applied to an artifact whose referenced
evidence is not committed.** Before any signature:

1. This revision **and** every artifact it references
   (`docs/decisions/g3-crawler-decision.md`,
   `docs/security/r3-technical-review-findings.md`,
   `docs/security/prompt-injection-assessment.md`) must be committed, so the
   signature names a fixed set of bytes.
2. The signing commit replaces the draft status line, records the named
   reviewer, and **flips
   `tests/unit/test_gate_decision_artifacts.py::test_g3_threat_model_is_signed_requirements`
   in the same human-authorized commit.** No agent performs that flip without
   program-owner authorization.

## What changed in revision 4

Revision 4 answers an adversarial independent review of **revision 3** that
returned **DO NOT SIGN**. Three findings were blocking; each is fixed below in
the row or section it touches, and every fix that would require changing a
signed G3 decision is recorded as a tension for the human reviewer instead of
being applied unilaterally.

| Change | Reason (adversarial review of revision 3) |
|---|---|
| **T-02: the client-side validating connector is now unconditional** (BLOCKING) | Revision 3 said the three TLS/transport bindings were expressible through a custom connector **or** a validating egress proxy, then conceded a proxy peer assertion "proves nothing about the target". An engineer could satisfy T-02 with zero client-side address validation, passing every T-02 test vacuously against the proxy's own IP, and inverting T-13's purpose into the proxy being the *only* barrier. The "or" is deleted |
| **C-6: the auto-update allowlist is now scoped by derivation, not only by field** (BLOCKING) | C-4 forbids extraction output driving a state transition; C-6 permitted auto-update of `status: cancelled`, `registration_url`, `description`, `location_text` and `capacity` with no tier scoping, so injected prose on an allowlisted department page could unpublish a live event with no human in the loop. Model-derived (tier-3) output now auto-updates **nothing** |
| **C-1 vs T-14: the evidence/retention tension is stated, not papered over** (BLOCKING) | C-1 requires persisting raw payload hashes and the exact normalized model-input bytes; T-14 prohibits all storage of raw third-party content. Normalized model-input bytes from a department page **are** third-party prose. Recorded as a named blocking dependency; this document does **not** decide P9 Gate B |
| **C-3: two validation rules restored** | Revision 3 dropped the URL rule and the contact-fields rule from the six-row source table in `prompt-injection-assessment.md` §C-3 — and in the same pass added a URL auto-update permission to C-6. Both rules are restored, and the compounding error is noted |
| **T-15: `/robots.txt` carved out of the path-pattern rule** | The fetch boundary accepts only allowlisted host **plus path patterns**, T-03 re-checks path pattern per hop, and T-15 routes the robots fetch through T-01/T-02/T-03 fail-closed. `/robots.txt` is on no event path pattern, so a faithful implementation refuses it, robots fails closed, and nothing is ever crawled |
| **T-08: reclaim direction imported from ADR-0015 Amendment A1** | "Abandoned reservation reclaimed" is satisfied by *releasing* it, which is the fail-open behavior A1 explicitly forbids |
| **T-27, T-28, T-29 relabelled "cannot close"** | Revision 3 rejected revision 2's T-14 as "an instruction to make later decisions, which cannot honestly be signed as a design requirement" — then wrote three rows in exactly that shape |
| **T-19 recorded as a tension with signed G3** | T-19 requires a second approver and proposer/approver separation; signed G3 §2.1 and decision #1 name **one** approver, and §2.4's seeding flow has that person proposing. Surfaced for a G3 amendment, not silently overridden and not deleted |
| **T-06 / C-1 provenance reconciled** | Reconstructing the stored URL from the approved *path pattern* destroys the per-page provenance C-1 needs. An opaque source-page identifier is stored alongside |
| **T-04, T-16, T-23 tightened; T-05 extended to in-process domain parsers** | The compressed cap had no value; T-16 never said how the cap is observed; T-23's "no field the schema does not require" is incoherent for prose bytes; and the newly landed tier-1 `ical_parser` / `jsonld_parser` sit inside the pure domain library, a different isolation posture from T-05's process boundary |
| **Stale reference corrected in the review-findings file** | `r3-technical-review-findings.md` still described its subject as "(81 lines, unsigned)" |

Everything revision 3 got right is retained unchanged: the fourteen new rows
T-17…T-30, the T-01 canonicalization rules, the T-02 prohibition on
`verify=False`, the T-06 structural URL policy, and the honest "cannot close"
labels on T-07 and T-13. Revision 4 is a targeted fix pass, not a rewrite.

## What changed in revision 3

| Change | Reason (adversarial review) |
|---|---|
| **T-02 rewritten again** | Revision 2's "connect to validated IP with explicit `Host`" *invites* `verify=False`; TLS SNI, proxies, pooling, HTTP/2 coalescing and Happy Eyeballs were undefined |
| **T-01 extended** | "Globally-routable unicast" was undefined; canonicalization and mixed-answer rules were missing |
| **T-03 extended** | Redirect re-authorization did not cover credential forwarding, HTTPS downgrade, or `Location` encoding |
| **T-04 extended** | Budget summary dropped G3's 5 s / 15 s / 30 s timeouts; post-fetch complexity limits were absent |
| **T-05 rewritten** | "Parser isolation" was not a boundary definition; an isolated *function* in the privileged worker satisfied the words |
| **T-06 rewritten** | "Credential-shaped segment" is a heuristic, not a boundary; query-string secrets were uncovered |
| **T-07 corrected** | Sources and methods were listed; the runtime tool/provider dimension is named as **unfilled** |
| **T-08 corrected** | G3's 5,000-fetches/tenant/day ceiling restored; review queue named as a DoS amplifier |
| **T-11 C-1 rewritten** | "The reviewer sees exactly what the model saw" was false; replaced with an evidence contract |
| **T-11 C-2 rewritten** | The enumerated strip cannot remove the invisible surface; capability denial is now load-bearing |
| **T-11 C-5 tightened** | LLM fallback, description-field summarization and reconciliation reprocessing now prohibited |
| **T-11 C-6 enumerated** | Revision 2 instructed engineering to enumerate later — an unfinished control. The allowlist is enumerated here |
| **T-11 C-7 strengthened** | A fixed corpus proves behavior on that corpus; metamorphic and repeated-run oracles added |
| **T-13 reframed** | Now a **deferred pre-live prerequisite**, not "live operation without egress control accepted"; enforcement point proposed, not decided |
| **T-14 narrowed to a prohibition** | Gate B is undecided and this document must not decide it; all live and raw-content collection is prohibited until it is signed |
| **T-17 … T-30 added** | Fourteen architecture-relevant threats the 16-row catalog omitted |
| **Trust-boundary text corrected** | "Scraped text is unconstructible in titles" was false |
| **Test expectations rewritten** | Vague fixture expectations replaced with denial/property oracles |
| **Stabilization note added** | The artifact and its evidence must be committed before a durable signature |

## Scope

Threats and required controls for a **future** constrained event-discovery
adapter. This document does **not** authorize HTTP crawl code, worker routes,
UI, or live provider calls. Implementation waits on R3 sign-off; live targets
additionally require the egress prerequisite in T-13 and the P9 Gate B decision
in T-14.

## Non-goals (explicit)

- No port of legacy `CrawlerFeed`, `CrawlerContext`, or `POST /api/crawler/start`.
- No operational legacy crawler code ported. See
  `docs/security/prompt-injection-assessment.md` §2 for the assessed reasons.
- No production egress configuration or credentials.

## Trust boundaries

```
[ Approved sources ]──▶[ Fetch boundary ]──▶[ Deterministic parser ]──┐
   allowlist only        validated-peer       tier 1 / tier 2         │
   (G3 §2.2)             connector, no auto-  never sees the model    │
                         redirect, budgets                            │
                                │                                     ▼
                                └──▶[ LLM extractor ]──▶[ Validation boundary ]
                                      tier 3 prose only     schema + closed vocab
                                      OUTPUT IS UNTRUSTED   unmapped ⇒ quarantine
                                                                      │
                                                                      ▼
                                              [ event_source_observation ] immutable
                                                                      │
                                                                      ▼
                                              [ discovery_review_item ]  ◀── human
                                                                      │
                                                                      ▼
                                              [ event + provenance ] accepted only
```

Untrusted input enters at URL fetch and response body. **Model output is also
untrusted input**, not trusted output.

**Correction to revision 2 (adversarial review §5 item 1).** Revision 2 stated
that scraped text in titles is unconstructible. That is false.
`normalize_title` accepts **any** non-blank string and only folds it;
`EventProvenance` being a separate dataclass means only that no helper *merges*
provenance into a title — nothing prevents a caller from passing scraped text or
a provenance string as the title. Keeping provenance and scraped prose out of
titles therefore requires **explicit adapter and persistence validation**, which
is a required control (T-30 below), not a property the domain layer already
holds. C-3 permits bounded free text, so the two statements were also in direct
conflict.

## Threat catalog

Test expectations are all **post-G3** — see "What a signature means" below. Each
expectation is written as a denial or property oracle: a test that a plausible
broken implementation would fail.

| ID | Threat | Required control | Test expectation (post-G3) |
|---|---|---|---|
| T-01 | SSRF to internal/metadata addresses | **Allow only globally-routable unicast** per the normative definition below, deny all else by default; canonicalize before classifying; resolved address must belong to an allowlisted host; **any single disallowed answer rejects the whole host**; no raw IP literals without separate review | Denial cases: IPv6 ULA/link-local, IPv4-mapped (`::ffff:169.254.169.254`), decimal/octal/hex literals, `0.0.0.0/8`, CGNAT, `192.0.0.0/24`, `198.18.0.0/15`; **mixed public+private answer set rejects**; scoped IPv6 (`fe80::1%eth0`) rejected pre-resolution; IDNA/trailing-dot/percent-encoding canonicalization cases; CNAME chain at and beyond depth limit; re-validation on each new physical connection; policy-version change invalidates |
| T-02 | DNS rebinding **and unsafe transport binding** | **Client-side validating connector, unconditionally** — see §T-02 below. Dial only members of the single validated address set while preserving original-host TLS SNI and certificate hostname verification. **A validating egress proxy is additive defense in depth and never a substitute**; a proxy deployment does not relieve the client of address validation, and both enforcement points must independently satisfy T-01's denial set. **Disabling certificate verification (`verify=False`, custom permissive verifiers, hostname-check suppression) is a prohibited implementation.** | Resolution and connection instrumented separately; assert the connected peer is in the validated set; assert SNI **and** certificate-verification hostname equal the original host; pooled second request reuses the bound peer; forced HTTP/2 coalescing attempt refused; `HTTP(S)_PROXY`/`ALL_PROXY` env set and ignored (or routed to the named enforcement point **while client-side validation still runs**); mixed-family answer set; negative test asserting no code path sets `verify=False`; **non-vacuity test — with any proxy removed from the path, the client alone still refuses every T-01 denial case, so no expectation above can be satisfied by the proxy's own address** |
| T-03 | Redirect chain escape | **Automatic redirects disabled**; each hop re-runs the *entire* authorization cycle — allowlist host **and path pattern**, HTTPS, port, userinfo, T-01, T-02; **no `Authorization`, cookie, or conditional header forwarded across a host change**; max 3 hops | Redirect-to-internal refused at every hop; cross-host `Authorization`/cookie **not** present on hop 2; HTTPS→HTTP downgrade refused; relative, percent-encoded, and malformed `Location` refused; redirect to an allowlisted host but unapproved path refused |
| T-04 | Response bomb (size/time/compression) and post-fetch complexity | Byte and time ceilings enforced **before buffering**; the 5 MiB per-response cap applies to decompressed bytes with a separate compressed cap — **the compressed cap is UNQUANTIFIED** (revision 4): signed G3 §3 gives 5 MiB/response and 100 MiB/job as *streaming* caps and states no compressed figure, so no value is derivable from G3 and this document does not invent one; the owner must set it, and until then the row's compressed-cap expectation is not writable; the 100 MiB cap is per job; transparent client decompression must be disabled or instrumented so decompressed volume is observable; header-size limit; nested/multiple content encodings refused; explicit **total** deadline per fetch in addition to per-read timeouts; G3's 5 s connect / 15 s read / 30 s per-fetch timeouts | Oversized, slow-drip (repeated small chunks defeating a per-read timeout only), nested-encoding, oversized-header, and zip-bomb bodies refused; decompressed-byte counter asserted, not compressed; total-deadline test |
| T-05 | Parser escape / RCE / wrong parser | **Parser isolation as a boundary** — see §T-05. Separate OS process or container, no network namespace access, minimal read-only filesystem, CPU/memory/wall limits, external entity resolution disabled (XXE), accepted-media-type list, pinned dependencies with recorded provenance. Parser selected from validated content type, not URL suffix; unaccepted types refused unparsed. **An "isolated function" in the same privileged worker does not satisfy this row.** | Sandbox oracles: parser process attempting a socket connection is denied; attempting a write outside its tmpdir is denied; CPU/memory/wall limit terminates a pathological input; XXE fixture resolves no entity and makes no request; polyglot (valid HTML *and* XML) input parses by validated type only; type-mismatch refusal; media type not on the accepted list is refused unparsed |
| T-06 | Credential leakage, incl. secret-bearing source URLs | **Structured URL policy** — see §T-06. Userinfo rejected; path and **query-string** secrets removed by structural rule, not shape heuristic; redaction on write is **irreversible**; **raw fetch URLs are never persisted**; allowlist `credentials:` names an environment variable, never a value; **an opaque, irreversible, per-deployment-salted source-page identifier is stored alongside the approved pattern** so C-1's per-page provenance survives (revision 4, §T-06 rule 2a) | Property test: for every persisted provenance URL, no query string survives except an explicitly allowlisted parameter set, and no path segment beyond the approved path pattern survives; irreversibility test (no stored mapping recovers the original); iCal token in path **and** in query both redacted; userinfo URL rejected at the boundary; CI log scan; negative test that no code path writes an unredacted fetch URL; **two distinct pages under one approved path pattern produce two distinct source-page identifiers and one shared reconstructed URL, and no stored mapping recovers either original** |
| T-07 | Tool sprawl | Closed **allowed tools** list *and* closed **domains** list per G3. The domains dimension is filled (G3 §2.2). **The runtime tool/provider dimension is UNFILLED** — see "Allowed tools and domains" below | Allowlist enforcement test on **both** dimensions; the tools-dimension test cannot be written until the list exists, and this row therefore cannot close |
| T-08 | Cost runaway | Per-run and per-tenant budget incl. G3's **5,000 fetches/tenant/day**; reserve-before-spend with an atomic concurrency contract, idempotent reconciliation, defined retry semantics and **conservative** abandoned-reservation reclamation per **ADR-0015 Amendment A1** (not yet landed): an expired, unreconciled reservation is **unconditionally treated as spent at its reserved maximum**, flagged as an estimate, and not released (A1 withdrew the "positive evidence the call never happened" exception: nothing in the design produces such evidence, and an exception no component can establish invites supplying it by inference) — releasing by default turns every worker crash into free budget, a control that fails open; **escalation** to `discovery_review_item`, rate-limited and deduplicated so budget failures cannot flood the queue (see T-17) | Concurrent reserve test (N parallel workers cannot exceed the ceiling); retry does not double-charge; **an expired unreconciled reservation with no evidence about the call leaves remaining headroom *reduced by its reserved maximum*, not restored — a reclaim implemented as a release fails this test** (revision 4: "abandoned reservation reclaimed" was satisfiable by releasing it, which is the direction A1 forbids); no input releases an expired unreconciled reservation — a test asserting a release path exists must fail; reconciliation is idempotent under a sweep and a late worker both reaching the same reservation; budget exceeded ⇒ `failed_budget`, terminal; escalation row created **once** per failure class per window, not per failure |
| T-09 | Open-ended tags | Map through `TagVocabulary`; unmapped ⇒ quarantine. **Every** persistence, read, matching, and serialization path consumes the typed resolution, never raw input. Quarantined raw text is attacker-controlled and must be rendered inertly (T-18) | Unmapped never in **any** read API or serialization, not one endpoint; bypass test writing raw input directly to the repository is refused |
| T-10 | Unresolved dates published | `unresolved` ⇒ no identity key; no publish/match transition | DB constraint plus refusal at **every** transition and at direct repository writes, not only an API route |
| T-11 | **Indirect prompt injection** | See §T-11 — seven controls; C-1/C-2/C-6/C-7 rewritten in revision 3; in revision 4 **C-6 is scoped by derivation so no field auto-updates from model-derived output**, C-3's URL and contact-field rules are restored, and C-1's tension with T-14 is recorded as a blocking pre-live dependency | See §C-7: structural invariants, metamorphic with/without-injection comparison, repeated runs under a pinned model configuration, multi-page and long-context cases. A fixed fixture corpus proves behavior **on that corpus**, not the absence of injection vulnerability |
| T-12 | **Untrusted seeding input** | Search proposes only; no code path to events; promotion is a human write to a committed file; **the approver sees the provenance explaining why the host was proposed** (restored — revision 2 dropped it); capped proposal volume | No-path test; promotion requires a human write; proposal record carries and displays provenance; volume cap enforced; proposal content rendered inertly (T-18). Note that "requires a human write" is not fully unit-testable without authenticated identity — see T-28 |
| T-13 | **Egress policy** | Network-level egress restriction enforced independently of application code. **Deferred pre-live prerequisite** — see §T-13 | Integration test proving private/metadata destinations are denied with application-level allowlist logic bypassed. **The enforcement point is unnamed, so this test cannot be written and the row cannot close** |
| T-14 | **Incidental PII** | **All live fetching and all raw-content collection and retention are prohibited until P9 Gate B is signed** — see §T-14 | Test that no live fetch and no raw-payload persistence path exists. Note: a test checking only normalized event output can pass while raw pages retain PII, so the oracle must inspect stored artifacts, not emitted events |
| T-15 | **Robots/ToS and anti-evasion** | Fail-closed `robots.txt`; **the robots fetch itself passes through T-01/T-02/T-03** and must not use an ordinary client; identified UA with contact URL; **no rotation, no CAPTCHA solving, no block evasion**; permission basis and its review date recorded per source. **`/robots.txt` is an explicit allowlist-host-scoped carve-out from the *path-pattern* rule only** (revision 4) — without it the robots fetch is refused, robots fails closed, and nothing is ever crawled; the carve-out relaxes no address validation. See "Fetch boundary" item 1 | Unfetchable, 4xx, 5xx, redirected, timed-out, malformed, and oversized `robots.txt` each deny; UA asserted; robots fetch asserted to go through the validating connector; **`/robots.txt` on an allowlisted host is fetchable despite matching no event path pattern; `/robots.txt` on a non-allowlisted host is refused; a path other than exactly `/robots.txt` gets no carve-out; a `robots.txt` URL resolving to a private/metadata address is still refused by T-01/T-02**; negative test that no UA/IP rotation code path exists; permission-basis freshness assertion |
| T-16 | **Capped response read as complete** | Subdivide any saturated window; explicit `partial` at minimum window; never report truncation as completeness. **The cap value must not be hard-coded to 200** — saturation is "returned exactly the observed cap". **How the cap is known (revision 4):** the cap is a **per-source registry field**, human-set from the source's documented or measured limit (G3 §2.2a records 200 for the CPP master calendar) and versioned with the allowlist entry; where the response itself declares a limit or total, that declared value is **cross-checked** against the configured one and a mismatch is a **failure, not an adopted new cap** — an attacker-controlled response must never be able to raise the saturation threshold and thereby suppress subdivision. A source with **no** configured cap is treated as saturating at any full page, i.e. subdivide by default | 200-record fixture proves subdivision; a fixture whose **configured** cap is 100 also proves subdivision (cap drift); a response *declaring* a cap different from the configured one fails rather than adopting it; a source with no configured cap subdivides; recursion terminates; boundary inclusivity, stable ordering and duplicate suppression asserted |
| T-17 | **Review-queue DoS / reviewer fatigue** | Queue capacity ceiling, deduplication, per-source fairness, aging, backpressure that pauses ingestion rather than growing the queue, and an emergency pause control. G3 §1 names review capacity as the binding constraint; 200 artifacts/page and per-failure escalation rows (T-08) both amplify into it | A single job producing 200 artifacts does not create 200 queue rows; duplicate observations collapse; one source cannot occupy more than its fairness share; queue at capacity applies backpressure to ingestion and does not drop review items silently; emergency pause halts ingestion |
| T-18 | **Stored XSS and active review content** | Review-facing content — normalized text, verbatim spans, quarantined raw tags, proposal provenance, parser errors — is rendered **inert**: contextual output encoding, a restrictive CSP, no auto-linking, no image/preview/remote-font loading, no browser-initiated fetch of any kind originating from stored content | Script payload in a quarantined tag, a verbatim span, and a proposal record each render as text; CSP header asserted; review page issues **zero** network requests derived from stored content |
| T-19 | **Compromised reviewer / insider** — **control retained, but in TENSION with signed G3** | Separation of duties between allowlist approval and event approval; a second approval for allowlist changes; reviewer revocation; anomaly detection on approval volume and pattern; **tamper-evident** append-only audit trail. Human approval is currently treated as dispositive with none of these. **Tension (revision 4):** as written this row is **unsatisfiable under signed G3** — G3 §2.1 and decision #1 name **one** approver, and G3 §2.4's seeding flow has that same person proposing hosts they then approve. The control is **not deleted and G3 is not silently overridden**; closing T-19 requires a **G3 amendment** naming a second approver (or an accepted, recorded single-approver risk). See §T-19 below | Testable independently of the tension: revoked reviewer's approvals refused; audit entries are append-only and detect modification; anomalous approval burst raises an alert. **Blocked on the amendment:** "a single identity cannot both propose and approve an allowlist entry" cannot pass while exactly one approver exists, so this expectation is **not writable today** |
| T-20 | **Compromised allowlisted source** | Post-approval takeover, vandalism, ownership change, **dangling CNAME**, and expired-domain reclamation are in scope. Require periodic re-verification of the permission basis, registrar/DNS-change detection, CNAME target re-validation on every crawl, and a content-anomaly signal that returns a previously auto-updating source to review | Allowlisted host whose CNAME now points to an unapproved target is refused; registrar/nameserver change forces re-verification; a source that begins emitting anomalous volume or content returns to review rather than auto-updating |
| T-21 | **Cache poisoning and stale authorization** | DNS, `robots.txt`, HTTP response, parser output, LLM result, and review-evidence caches all use **authenticated cache keys** including tenant, allowlist/policy generation, parser version, and model version; bounded TTLs; invalidation on any allowlist, permission-basis, or policy change | Cache key includes policy generation; bumping the allowlist generation misses every prior entry; a removed allowlist host cannot be served from cache; cross-tenant cache read is impossible by key construction; TTL bound asserted |
| T-22 | **Parser/client dependency supply chain** | Pinned dependencies with hashes, recorded provenance/SBOM, vulnerability review before adoption, signed artifacts where available, restricted install and build paths, and containment of native parser code within the T-05 boundary | Lockfile hash pinning enforced in CI; unpinned or hash-mismatched dependency fails the build; SBOM produced for the parser boundary; native parser code runs inside the T-05 sandbox |
| T-23 | **LLM-provider data disclosure** | Scraped content reaches an external model provider. Required: a named provider endpoint on the tool allowlist (T-07), a recorded retention policy, a contractual **no-training-on-submitted-data** term, a defined processing region, prompt-logging posture stated explicitly, and a prohibition on submitting raw payloads rather than the normalized model-input bytes. **The provider is not yet named** (T-07 unfilled), so this row cannot close | Only the allowlisted provider endpoint is reachable from the extractor; **the submitted request body is byte-identical to the stored normalized model input plus the versioned prompt template, and contains nothing else** — no raw payload, no response headers, no fetch URL, no tenant or reviewer identifier, and no field the request schema does not define (revision 4: "no field the schema does not require" was incoherent, since the submitted bytes are prose, not a record with fields — the oracle is byte-equality against the stored input plus a closed request envelope, which is testable); provider retention/training/region terms recorded in the artifact before first use |
| T-24 | **Log injection and audit-trail deception** | Untrusted URLs, titles, raw quarantined tags, parser errors, and model output can carry newlines, terminal escape sequences, bidi controls, and forged structured-log fields. Logs are structured with untrusted values carried as **data fields, never interpolated into the message**; control characters, bidi marks and newlines escaped on write; audit entries carry an integrity chain (see T-19) | Newline/CR payload in a title produces one log record, not two; ANSI/terminal escape neutralized; forged `"level":"ERROR"` inside a value does not become a log field; bidi control visible-marked in audit render |
| T-25 | **Durable job/outbox replay and duplicate side effects** | The platform intentionally retries durable work. Required: idempotent observation and review writes keyed on payload hash plus source, once-only budget charging (T-08), **policy re-check at delivery time, not only at enqueue**, and defined redrive semantics | Redelivering the same job produces no duplicate observation, no duplicate review item, and no second budget charge; a job enqueued while a host was allowlisted and delivered after its removal is refused at delivery |
| T-26 | **Replay of stored observations under changed policy** | An immutable observation may be reprocessed under a changed prompt, parser, model, vocabulary, permission basis, or PII policy. Replay requires **renewed authorization**: the source's permission basis must still be valid, and the output must be stamped with the prompt/parser/model/vocabulary versions used. Old and new decisions coexist as distinct stamped records; replay never silently overwrites a human-reviewed decision | Replay under a bumped model or prompt version produces a new stamped record and returns the item to review rather than auto-updating; replay of an observation whose source permission basis has lapsed is refused; a prior human decision is never overwritten by replay |
| T-27 | **Tenant isolation and IDOR** — **CANNOT CLOSE** | **Partially signable.** Signable now: `event_source_observation`, `event_provenance`, and `discovery_review_item` must state tenant ownership explicitly and use composite `(tenant_id, id)` keys and composite foreign keys, matching the existing job-read discipline. **Not signable:** whether observations are shared globally or per-tenant. Revision 3 wrote that as "a design decision this row requires to be made", which is an instruction to decide later, not a requirement — the same defect revision 3 correctly rejected in revision 2's T-14. **The scoping decision is a human's to make and this document does not make it**, so the row **cannot close**; see Open Questions §5 | The composite-key half is testable now: cross-tenant read of an observation, provenance row, or review item by id alone returns nothing; composite FK asserted in the migration; no query in the discovery path selects by bare `id`. The scoping half **has no test until the decision exists**, because global and per-tenant observations have opposite expected results for the same query |
| T-28 | **Review-action authorization / CSRF / confused deputy** — **CANNOT CLOSE** | **Partially signable.** Signable now, because they hold under any identity model: anti-CSRF on every state-changing review action; refusal of cross-origin state change; recording of every approval in the tamper-evident audit trail (T-19); and the rule that authorization is checked server-side at the action, never inferred from the UI. **Not signable:** *who* may approve, for which tenant and org unit, and how reviewer identity is proven. Revision 3 wrote "**Define** who may approve…", which is an instruction to decide later. **No authenticated identity model exists in this design yet and this document does not invent one** — filling these would be inventing values a human must choose. The row therefore **cannot close**; it is what T-12's "requires a human write" leaves undefined | Testable now: approval without a valid anti-CSRF token refused; cross-origin form submission to the review endpoint refused; approval action recorded in the tamper-evident audit trail. **Not writable yet:** "approval by an identity lacking the tenant/unit grant is refused" cannot be written until the grant model exists |
| T-29 | **Post-fetch resource exhaustion** — **CANNOT CLOSE (unquantified)** | The threat and the *dimensions* are signable; the **numbers are not, and this document does not invent them**. Byte ceilings do not bound the work a small payload can cause. Limits are required along these dimensions: DOM node count and tree depth, JSON nesting depth and total node count, **iCal recurrence-expansion bounds** (occurrence count and horizon), decompression CPU, LLM tokenization cost per document, evidence-span count, database rows created per job, and review-rendering complexity. **Signed G3 quantifies none of these** — G3 §3 bounds pages, depth, bytes, and wall time only — so every value above is **UNQUANTIFIED** and must be set by the owner before implementation. Revision 3 listed the dimensions as though they were requirements; a limit with no value is not one | Each dimension gets a test **once its value exists**. The shape is fixed even though the numbers are not: deeply nested JSON, a DOM-node-explosion document, and an iCal `RRULE` expanding to an unbounded occurrence set are each refused before parsing completes; per-document token cost ceiling enforced pre-call; rows-created-per-job ceiling enforced. **No such test can be written against an unset ceiling**, so the row cannot close |
| T-30 | **Provenance or scraped text reaching display fields** | `normalize_title` accepts any non-blank string, so adapter and persistence validation must explicitly reject provenance strings, URLs, and unbounded scraped prose in titles and other display fields | Title containing a URL, a provenance string, or an over-length scraped span is refused at the adapter **and** at persistence; property test over the fixture corpus that no persisted title equals or contains its source URL |

---

## T-02 — the validating connector (rewritten)

**This is the highest-value correction in revision 3.** Revision 2's wording —
"connect to the validated IP with explicit `Host`" — closes the second-lookup
TOCTOU and then *invites the next bug*. A high-level request to
`https://<validated-ip>/path` with a `Host` header commonly performs TLS
certificate verification against the **IP**, not the `Host` value; the
verification fails, and the plausible engineer response is to disable it.

**`verify=False`, custom permissive verifiers, and any suppression of hostname
checking are prohibited implementations of this row.** Trading DNS rebinding for
an unauthenticated channel is a net loss.

A conforming HTTPS connection maintains **three separate bindings simultaneously**:

1. The socket dials **only** a member of the single validated address set.
2. TLS **SNI** carries the original hostname.
3. Certificate **hostname verification** runs against the original hostname.

**The client-side validating connector is unconditional (revision 4, blocking
finding 1).** Revision 3 said these bindings were expressible through a custom
transport/connector **or** through a validating egress proxy. That "or" voided
the row. An engineer could satisfy T-02 completely by routing through the T-13
proxy and writing **zero** client-side address validation: every T-02 test
expectation then passes vacuously against the proxy's own IP, and all protection
rests on a component this document declines to name (T-13's enforcement point is
UNNAMED). It also inverted T-13's stated purpose — egress control exists so that
the application allowlist is *not the only* barrier — into the proxy being the
only barrier. Revision 4 deletes the "or".

The required implementation is a **custom transport/connector in the client**: a
connector that accepts the pre-validated address set and the original host, dials
only a member of that set, and performs the TLS handshake against the original
host over the dialed address. This is **not** safely expressible as URL-rewriting
inside an ordinary high-level request call, and it is not delegable.

**An egress proxy is additive defense in depth, never a substitute.**
Specifically:

- Deploying a validating egress proxy **does not relieve the client of address
  validation.** The connector above is required whether or not a proxy is in
  path.
- The two enforcement points must **independently** satisfy T-01's denial set.
  Neither may be implemented by trusting the other, and neither passes its own
  tests by observing the other's verdict.
- A T-02 conformance test that can pass against a proxy's IP without exercising
  client-side classification is, by construction, not a T-02 test.
- Under `CONNECT` the client cannot observe the real target peer at all. In
  revision 3 that fact sat next to an escape hatch; in revision 4 it is an
  argument **for** the client-side connector — precisely because the socket-peer
  assertion alone proves nothing there, the address set the client dials must
  already have been validated by the client before the tunnel is requested.

The connector must additionally satisfy:

- **Happy Eyeballs / dual stack.** Race only addresses drawn from the single
  validated set. Never hand the hostname back to the connector for its own
  resolution. **Assert the winning peer is in the validated set** before any
  bytes are sent.
- **Peer assertion.** After connect, read the actual socket peer and assert
  membership. Where a proxy is in path, the socket peer is the *proxy* and this
  assertion proves nothing about the target. That is a **limit of the peer
  assertion, not a licence to skip client-side validation** — the target address
  set must have been classified and validated by the client before the proxy is
  asked for anything. See proxies below.
- **Connection-pool reuse.** Pool by original scheme/host/port **and policy
  generation**. Retain the validated peer binding for the **life of the
  connection**. A pooled connection is never reused across a policy generation
  change; changing the allowlist or policy invalidates the pool.
- **HTTP/2 cross-origin coalescing.** Disable it, or require each coalesced
  origin to independently pass the same peer, certificate, and policy
  authorization. A shared certificate must not silently authorize a second host.
- **Proxies.** Environment-derived proxies (`HTTP_PROXY`, `HTTPS_PROXY`,
  `ALL_PROXY`, `NO_PROXY`) and ordinary forward/`CONNECT` proxies are
  **disabled**, unless the proxy is the T-13 named enforcement point and performs
  equivalent target resolution and denial **in addition to**, never instead of,
  the client-side connector. Under `CONNECT`, the client cannot observe the real
  target peer at all, so at that layer only the proxy's own policy protects the
  connection — which is exactly why the client must have validated the target
  address set itself before requesting the tunnel. A proxy deployment is a
  second independent enforcement point, not a first and only one.
- **DNS TTL and policy invalidation.** No second resolution occurs during a
  connection attempt. TTL expiry does not tear down an established connection —
  it prevents *new* reuse; established connections remain bound to their
  originally validated peer. Any allowlist or policy change bumps the policy
  generation and invalidates cached resolutions and pooled connections.
- **CNAME chains and zone identifiers.** Resolve the chain once to a complete
  approved address set with depth and loop limits. Reject IPv6 zone identifiers
  before dialing so that a URL parser and a socket parser cannot interpret the
  host differently.

**Tension with signed G3, recorded not resolved.** G3 §8 requires the fetch
boundary to "bind validation to the actual peer connection." That wording is
satisfiable by a proxy deployment in which the observable peer is the proxy.
This section keeps G3's requirement and adds the TLS bindings G3 does not
mention; it does not weaken or override G3. If the reviewer selects a proxy as
the T-13 enforcement point, the peer-assertion clause must be read as applying
**additionally** at the proxy, and G3 §8 should be amended to say so.
**Revision 4 note:** that amendment must not be read as permitting the proxy to
*replace* the client-side connector. G3 §8's "bind validation to the actual peer
connection" is a floor, and this document raises it; a proxy satisfying G3 §8
alone does not satisfy T-02.

## T-01 — canonicalization and classification (extended)

"Globally-routable unicast" is a policy, not a library call. A drifting
third-party `is_global` predicate is not itself a security policy; the accepted
authority and its version must be recorded, and its verdicts pinned by test.

Required canonicalization, **before** any classification or comparison:

- Hostnames to **IDNA** form; trailing dot removed; case folded.
- Percent-encoding resolved once and rejected if it re-introduces structure.
- IPv6 literals bracket-parsed; **scoped IPv6 (`fe80::1%eth0`) rejected outright**.
- **IPv4-mapped IPv6 normalized to IPv4 before classification**, so
  `::ffff:169.254.169.254` classifies as link-local.
- Alternate IPv4 notations (decimal, octal, hexadecimal, mixed) rejected rather
  than normalized.
- Userinfo rejected; non-approved ports rejected.
- CNAME chains resolved once with a **maximum depth** and loop detection.

**Any single disallowed answer rejects the entire host.** A mixed answer set —
one public address and one private — is a rejection, not a filtered success.
Revalidate on every new physical connection, and invalidate on policy-generation
change.

## T-05 — parser isolation as a boundary (rewritten)

"Parser isolation" without a boundary definition is satisfied linguistically by
an isolated *function* in the same privileged worker. **That does not satisfy
this row.** Required, concretely:

- **Process or container boundary.** The parser runs in a separate OS process or
  container, not merely a separate module, and not in the worker's privileged
  context.
- **No network.** The parser has no network namespace access. Any attempted
  socket connection fails.
- **Minimal filesystem.** Read-only root; a single writable temporary directory;
  no access to credentials, source, or configuration.
- **Resource limits.** CPU, memory, and wall-clock limits, each of which
  terminates the parser rather than degrading the worker.
- **External entities disabled.** XML external entity resolution off (XXE),
  DTD processing off, no network-backed entity or schema fetch.
- **Accepted media types.** A closed list; the parser is chosen from the
  *validated* content type, never the URL suffix; anything off the list is
  refused unparsed. Content-Type is attacker-controlled, so type selection is a
  routing rule, not a trust decision — polyglot inputs must parse under exactly
  one validated type.
- **Dependency provenance.** Pinned versions with hashes and recorded provenance
  (T-22); native parser code contained inside this boundary.

**Deterministic in-process domain parsers — scope of this boundary (revision
4).** The repository has since landed two tier-1 parsers **inside the pure domain
library**: `python/smartmatch_domain/smartmatch_domain/ical_parser.py` and
`.../jsonld_parser.py`. That is a different isolation posture from the process or
container boundary this row requires, and revision 4 states the relationship
rather than ignoring it.

They are a **genuinely different risk class** from a native HTML/XML parser, and
the difference is structural, not a judgement call:

- They are **pure functions over text**: the caller supplies the document as a
  string. No transport, no file access, no environment. The domain package's
  import-linter contract forbids `os`, `pathlib` and `socket` inside it, so the
  "no network, minimal filesystem, no credentials" properties this row obtains
  by sandboxing are obtained there by **static import constraint** — which is
  enforced in CI and is stronger evidence than a runtime sandbox for those three
  specific properties.
- They are **pure Python with no native extension**, so the memory-safety and
  RCE surface T-05 was written against — the reason a process boundary exists —
  is absent. `ical_parser` uses `re` and stdlib parsing; `jsonld_parser` walks a
  decoded object graph.
- There is **no entity-resolution surface**: neither format has an XXE analogue,
  and neither parser fetches a schema, entity, or remote reference.

What therefore still applies to them, unchanged:

- **T-29's post-fetch complexity limits are the live risk for these two.** A pure
  function cannot escape, but it can be made to burn CPU or memory —
  `RRULE` occurrence explosion in `ical_parser`, object-graph depth and node
  count in `jsonld_parser` — and it runs **in the worker's own process**, where
  there is no sandbox to terminate it. **CPU, memory and wall-clock bounds must
  therefore be imposed by the caller**, at the worker's job boundary, since the
  domain library cannot impose them on itself.
- **T-22 applies**: their dependencies are the pinned stdlib plus the domain
  package itself, recorded like any other.
- Their **output is still untrusted input** to everything downstream. Being
  deterministic makes a parse trustworthy as a *rendering of the document*; it
  says nothing about the document. C-6's derivation rule treats tier-1 output as
  auto-updatable precisely because it is a mechanical function of a source a
  human approved — not because the parser is safe.

**What is not claimed:** this is not a general exemption. A **native** HTML or
XML parser, or any parser that performs I/O, resolves entities, or executes
content, sits outside the domain library and **must** run inside the process or
container boundary above. The tier-3 HTML path in particular is unaffected by
this paragraph. Whether the two domain parsers should additionally be moved
behind the process boundary once a worker exists is a design question for the
reviewer; this document records the current posture and its actual residual
risk (CPU/memory exhaustion in-process, T-29) rather than asserting either that
the row is satisfied or that it is violated.

## T-06 — structured URL policy (rewritten)

Revision 2 required stripping "credential-shaped path segments." A private iCal
token is an arbitrary opaque slug and is not reliably distinguishable from a
legitimate path component; and secrets equally appear in **query strings**,
which revision 2 did not cover. A faithful regex implementation still persists
bearer credentials.

Required instead, structurally:

1. **Userinfo** (`https://user:pass@host/`) is rejected at the fetch boundary —
   never stripped and fetched.
2. **Raw fetch URLs are never persisted.** What is stored is a reconstructed URL
   built from the allowlist entry's approved host and path pattern plus
   explicitly allowlisted parameters — a deny-by-default projection, not a
   redaction of the original.
   - **Rule 2a — provenance survives the projection (revision 4).** A path
     *pattern* is
     shared by every page it matches, so a reconstructed-URL-only record cannot
     tell a reviewer **which page** a field came from — which is exactly what
     C-1's evidence contract and its per-page derivation graph require, and what
     T-30's "no persisted title equals or contains its source URL" property test
     needs a per-page referent for. Revision 3 left T-06 and C-1 in conflict.
     The reconciliation: alongside the approved pattern, store an **opaque
     source-page identifier** — a stable, collision-resistant digest of the
     canonicalized fetch URL, salted per deployment, carrying no recoverable
     secret and readable by nobody as a URL. It distinguishes pages, groups every
     observation from one page, and survives redaction, while remaining
     irreversible under rule 4 below. The review UI shows the reconstructed
     pattern-scoped URL **plus** this identifier; where a human needs the literal
     page, the path is re-deriving it from the allowlist entry and the source's
     own navigation, never from stored bytes.
     The identifier is **not** an exemption from rule 4: it must not be a
     reversible tokenization, must not be derived in a way that permits offline
     recovery of a short or guessable URL (hence the per-deployment salt), and no
     stored mapping from identifier back to URL may exist.
3. **Query strings** are dropped in full except for an explicitly allowlisted
   parameter set per source.
4. **Redaction is irreversible.** No stored mapping, key, or reversible
   tokenization recovers the original. If a reversible token is ever proposed,
   the artifact must name **who may recover the original and under what
   authorization** — as written, nobody can, and that is the intended state.
5. The **fact** of redaction is recorded (which components were dropped), never
   the redacted value.
6. Allowlist entries never embed credentials. A `credentials:` field names an
   **environment variable name**, never a value.

## T-11 — Indirect prompt injection (expanded)

The highest-priority threat in this design. Full analysis:
`docs/security/prompt-injection-assessment.md`.

Untrusted third-party content is fed to an LLM extractor. Any page under
attacker or vandal control can carry text addressed to the extractor — in body
prose, HTML comments, `alt` text, or elements hidden from human view. T-05
covers code execution; this threat requires none.

**The asymmetry that makes it serious:** human approval of every first-seen
event is the primary safety control, and hidden text is invisible to the
reviewer while fully legible to the model. Injection's best target is the
reviewer's eyes.

**Required controls:**

### C-1 — Evidence contract for review (rewritten)

Revision 2 claimed "the reviewer sees exactly what the model saw." **That claim
is false** and revision 3 withdraws it. The reviewer saw a normalized record and
field spans; the model was also exposed to system and developer instructions,
prompt template text, delimiters and serialization, model-version behavior,
preprocessing and parser versions, token truncation and ordering, other merged
observations, and any normalization applied between raw bytes and stored text.

Replaced with a **concrete evidence contract**. Every extraction persists, and
the review UI can display:

- the **raw payload hash** of each contributing fetch, and an assertion that the
  stored artifact still matches it;
- the **exact normalized model-input bytes** — not a paraphrase, not a
  re-render;
- the **prompt template and its version**, including system and developer
  instructions and the delimiters used;
- the **model identifier and version**, and the decoding parameters;
- the **truncation map** — what was omitted, from where, and how much, with the
  omission visible in the UI rather than silent;
- **every contributing observation** for a merged candidate, and the derivation
  graph showing how the candidate was assembled across pages;
- **span offsets** into the normalized bytes for every prose-derived field; a
  field with no span displays `unknown`, never a value;
- the **opaque source-page identifier** of T-06 §2a for each contributing fetch,
  so the derivation graph names distinct *pages* rather than a path pattern
  shared by all of them. This is how C-1's per-page provenance survives T-06's
  rule that raw fetch URLs are never persisted (revision 4).

Rendering is **inert and Unicode-aware**: contextual output encoding; no
auto-linking; no images, previews, remote fonts, or any remote fetch initiated
by the review UI; and **visible markers** for bidi controls, zero-width
characters, confusables, and invalid encoding. Identical code points are not
identical human evidence once bidi layout, font substitution, ligatures, or
whitespace collapse are applied — the UI must show the logical code-point order
the model consumed.

Review renders from the stored `event_source_observation`, never a live page or
a re-fetch.

**Unresolved tension with T-14 — recorded, not decided (revision 4, blocking
finding 3).** The evidence contract above and the prohibition in T-14 are in
**direct tension**, and revision 3 shipped both without noticing:

- C-1 requires persisting the **raw payload hash** of each contributing fetch,
  **an assertion that the stored artifact still matches it**, and the **exact
  normalized model-input bytes**.
- T-14 prohibits "all collection, storage, and retention of raw third-party
  content", stating that "no raw fetched page, response body, or payload is
  persisted".
- Normalized model-input bytes from a `www.cpp.edu` department page **are**
  third-party prose, and carry exactly the names, email addresses and phone
  numbers T-14 exists to exclude. A hash assertion that the stored artifact
  "still matches" a raw payload additionally implies the raw payload, or
  something derived closely enough from it to re-verify, is retained somewhere.
- **An implementer cannot satisfy both as written.**

Why this is latent rather than live today: under the current fixture-only scope
**no third-party content is fetched at all**. Every byte in the pipeline comes
from committed fixtures whose PII content is known and controlled, so nothing
C-1 stores is third-party content and nothing T-14 prohibits is being collected.
The contradiction bites at the first live fetch, not before.

**Required before any live fetch — one of the two, decided by a human:**

1. **P9 Gate B defines retention, access, and purge for evidence artifacts** —
   how long normalized model-input bytes and payload hashes are held, who may
   read or export them, how they are encrypted, what triggers purge, and how the
   evidence contract survives purge (a reviewed decision whose evidence has been
   purged must still be auditable); **or**
2. **C-1 is restated to store no third-party prose** — which means finding an
   evidence form that lets a reviewer see what the model saw without retaining
   the prose itself. That is a real design problem, not a formality: C-1 exists
   because A1 (the reviewer validating a different artifact than the model acted
   on) is the critical finding of `prompt-injection-assessment.md`, and a
   weakened C-1 re-opens it.

**This document does not choose between them, and must not.** P9 Gate B is
undecided and deciding it is not within this artifact's authority. The tension is
recorded as a **named blocking dependency** in the signature block below. It is
not resolved by preferring whichever of C-1 or T-14 a reader happens to read
second.

### C-2 — Inert, logical-form model input (rewritten)

Revision 2 claimed to "strip the invisible surface." **It cannot, and revision 3
withdraws the claim.** An engineer can remove HTML comments, the `hidden`
attribute, inline `display:none`, inline `visibility:hidden`, inline zero
opacity, and obvious negative positioning — exactly as revision 2 enumerated —
while all of the following still reach the model: CSS classes in embedded or
external stylesheets, inherited opacity and visibility, `clip-path` and
clipping, transforms and extreme translations, zero-size containers, same
foreground/background color, tiny fonts, overflow clipping, media-query rules,
pseudo-elements, Unicode bidi overrides, zero-width characters, homoglyphs, and
**ordinary visible prose**.

Determining what a human would see requires a rendering environment, stylesheet
resolution, viewport, font state, and possibly scripting. The deterministic
parser has none of these. Visibility filtering is therefore a **best-effort
noise reduction, not a security boundary**.

What is required:

- The enumerated strip is still performed, as noise reduction, and its limits
  are stated here so nobody later mistakes it for a boundary.
- **Fail closed if the parser dependency is unavailable** — never fall back to
  raw HTML. (Retained from revision 2; the legacy code's silent fallback is the
  sharpest defect in that path.)
- All model input is **stored** and **rendered inertly in logical form** (C-1).
- Suspicious Unicode — bidi controls, zero-width characters, confusables — is
  made **visible** rather than removed silently.
- **The load-bearing control is C-4, structural capability denial, not
  visibility filtering.** Stated in those terms: the design assumes injected
  instructions *will* reach the model, and is built so that a successful
  injection acquires no capability and bypasses no review.

### C-3 — Validate every field or make it `unknown`

**Two rules restored in revision 4.** The source table in
`prompt-injection-assessment.md` §C-3 has **six** rows; revision 3's C-3 kept
only three of them — tags, dates, and free text — silently dropping the URL rule
and the contact-fields rule. **Note the compounding error:** revision 3 dropped
the URL validation rule *and*, in the same pass, added a `registration_url`
auto-update permission to C-6. The two omissions together produced a document in
which a model-supplied URL was neither validated against the source nor barred
from auto-updating a published record. Both rules are restored here, and the C-6
derivation rule closes the other half.

The full validation table, matching the assessment row for row:

| Field | Rule |
|---|---|
| tags | closed vocabulary (twelve terms, G3 §6.2) or quarantine — already built |
| dates | parse to the ADR-0010 precision enum; unparseable ⇒ `unresolved` |
| `host_org_unit` | **never from model output** — human-curated mapping only (C-4) |
| **URLs** | **must equal the fetched source URL, or be dropped.** Restored in revision 4. A model-emitted URL is never fetched (C-4), never stored as provenance, and never auto-updates a published field (C-6). "Equal" means equal after T-01 canonicalization, not merely same-host |
| **contact fields** | **forbidden while P9 Gate B is open** (MP-4, T-14). Restored in revision 4. Not "validated then stored" — not collected, not emitted, not persisted |
| free text | length-bounded, control characters stripped, Unicode format characters handled explicitly, stored as data |

Note the limits: length bounds and control-character
stripping do not establish safety at browser, log, CSV, JSON, SQL, or prompt
sinks — each sink needs its own encoding (T-18, T-24). Homoglyphs and
semantically deceptive text survive validation by construction. Quarantined tags
deliberately retain exact unnormalized attacker text for review, so they are a
rendering problem (T-18), not a validation one.

### C-4 — Deny capability, not merely bad output

Extraction output may never select a URL to fetch, drive a state transition,
alter allowlist or budget, or choose `host_org_unit`.

**A "value object with no methods" is not sufficient.** Data needs no methods to
become capability: orchestration code that reads `candidate.url` and fetches it
has granted the model a fetch capability regardless of the object's shape. The
requirement therefore constrains **the DTO schema and every consumer dataflow**:

- the DTO carries no field that any consumer treats as a fetch target, a state
  transition, an allowlist or budget mutation, or an owning-unit selector;
- fetch targets come only from the allowlist; transitions only from human review;
  `host_org_unit` only from a human-curated mapping;
- consumer dataflow tests, not only object-shape tests, prove this.

### C-5 — The cascade is a security property

Tier-1/tier-2 sources are parsed deterministically and **never reach the model**.
Recorded here so it is not later traded away as a mere cost optimization.
Specifically prohibited:

- **LLM fallback when deterministic parsing fails.** A failed tier-1 parse fails
  the job; it does not escalate to the model.
- Sending structured-feed description fields into a later summarization or merge
  model.
- Reprocessing tier-1/tier-2 observations through the model during
  reconciliation.

**C-5 does not remove tier 3.** G3 §7.1 retained tier-3 LLM extraction of
department-page prose in the first release, and revision 3 does not contradict
that signed decision.

### C-6 — Auto-update field allowlist (enumerated)

Revision 2 instructed engineering to enumerate this later, which made it an
unfinished control. It is enumerated here. **Deny by default: any field not
listed returns to review.**

**Governing rule — derivation, then field (revision 4, blocking finding 2).**
Revision 3's allowlist was scoped **by field only, never by source tier or
derivation**, and so granted exactly the capability C-4 denies. G3 §7.1 signs
tier-3 LLM extraction into the first release, so under revision 3 injected prose
on an allowlisted department page could auto-update `registration_url` or set
`status: cancelled` — **a state transition driven by model output, with no human
in the loop** — which is the A4 patient-persistence attack in
`prompt-injection-assessment.md` §3 executed through a permission this document
itself granted. Revision 4 closes it:

> **No field auto-updates from model-derived output.** Auto-update applies
> **only** to deterministic tier-1/tier-2 parses (`ical_parser`,
> `jsonld_parser`, the master-calendar JSON adapter, and any successor
> deterministic parser) whose output is a mechanical function of the source
> document. **Every tier-3 (LLM-derived) observation returns to review, for
> every field, without exception.** The "Yes" column below is read as "yes, when
> derived deterministically"; for a tier-3 derivation every row reads **No**.

Consequences worth stating so nobody re-derives the hole:

- C-4's prohibition on model output driving a state transition is **not waived**,
  for cancellation or for anything else. A tier-3 `status: cancelled` is a review
  item, never an unpublish.
- `registration_url` is off the yes-list for LLM-derived observations
  unconditionally. Combined with C-3's restored URL rule, a model-supplied URL
  that is not the fetched source URL is dropped rather than stored, and a
  model-supplied URL never auto-updates a published record even when it does
  match.
- This does **not** weaken G3 §5. G3 §5's immediate-unpublish rule for
  same-source cancellations is preserved in full for **deterministic** parses —
  a `STATUS:CANCELLED` in an ICS feed or `eventStatus: EventCancelled` in JSON-LD
  from the same approved source still unpublishes or tombstones immediately.
  What is removed is only the extension of that rule to prose an LLM read.
- The derivation stamp is not advisory. Every observation records the tier and
  the parser/prompt/model versions that produced it (see **Version** below), and
  an observation with a missing or ambiguous derivation stamp is treated as
  tier-3 — deny by default.

| Field | Derivation | May auto-update from the same approved source? |
|---|---|---|
| **Any field whatsoever** | **tier 3 — model-derived** | **No** — returns to review, always (C-4) |
| `description` / summary body | tier 1 / tier 2, deterministic | **Yes**, within length bounds and C-3 validation |
| `location_text` (non-identity-bearing) | tier 1 / tier 2, deterministic | **Yes** |
| `registration_url` matching the source's approved host and path pattern | tier 1 / tier 2, deterministic | **Yes** |
| `capacity` / seats remaining | tier 1 / tier 2, deterministic | **Yes** |
| `source_updated_at`, `fetch_timestamp`, `payload_hash`, `parser_version` | system-generated, not source-derived | **Yes** — observation metadata |
| `status: cancelled` from the same source | tier 1 / tier 2, deterministic | **Yes** — see cancellation semantics below (G3 §5) |
| `status: cancelled` from the same source | **tier 3 — model-derived** | **No** — review item only; C-4 is not waived |
| `title` | any | **No** — reviewer relied on it |
| start/end date, time, or precision | any | **No** |
| `host_org_unit` | any | **No** — never from extraction at all (C-4) |
| organizer / contact of any kind | any | **No** — and forbidden entirely while P9 Gate B is open (T-14, MP-4, and C-3's restored contact-fields rule) |
| `tags` | any | **No** — a vocabulary change is a reviewed decision |
| identity-key components | any | **No** |
| `permission_basis` | any | **No** — human-set only |
| any field currently `unknown` acquiring a value | any | **No** |

**Cancellation.** G3 §5 requires same-source cancellations to **unpublish or
tombstone immediately**. That rule stands and is not overridden **for
deterministic tier-1/tier-2 parses**: such a same-source cancellation applies
immediately *and* raises a review item for after-the-fact confirmation. A
**tier-3, model-derived** cancellation raises the review item and does **not**
unpublish, because an immediate unpublish driven by attacker-controlled prose is
a denial-of-service against real events and is the state transition C-4 forbids.
Un-cancellation is **not** an auto-update at any tier — a cancelled event
returning to published requires review. This asymmetry is deliberate: immediate
unpublish fails safe *against a trustworthy source*, and a tier-3 source is by
construction not one.

**Conflict.** Any cross-source disagreement, and any same-source change to a
denied field, returns to review (G3 §5). An auto-update that would change a
denied field as a side effect is rejected in whole, not applied in part.

**Version and derivation stamp.** Every auto-update is stamped with the
**derivation tier**, the parser, prompt, model, and vocabulary versions in force,
and the observation payload hash it derives from. An update produced under
different versions than the reviewed record is not an auto-update — it is a
replay, governed by T-26. An update whose derivation tier is absent, unknown, or
mixed is treated as tier 3 and returns to review.

**Test expectation for the derivation rule.** A tier-3 fixture carrying an
injected `status: cancelled`, an injected `registration_url`, and injected
`description`/`location_text`/`capacity` values produces **zero** auto-updates
and one review item; the same fields arriving from a deterministic tier-1 fixture
auto-update as the table permits. This is a structural, deterministic test in the
sense of C-7 — it does not depend on model behavior.

### C-7 — Prove it (strengthened)

"The injected instruction has no effect on output" is **not a sound general
oracle**: a fixed fixture set can be overfit; stochastic model behavior can pass
one run and fail the next; a visible false partnership claim is content rather
than a distinguishable instruction; "no effect" can reward dropping legitimate
values; an injection may shift confidence, evidence selection, ordering, or
reviewer-facing phrasing without changing final field values; and single-page
fixtures miss cross-page and delayed attacks.

Required test set:

- **Structural invariant tests** — C-4's capability denial, asserted over the
  DTO schema and every consumer dataflow. These are deterministic and are the
  tests that actually hold.
- **Metamorphic comparison** — the same fixture with and without the injected
  span. The oracle is that extracted field values, spans, ordering, and
  reviewer-facing evidence are **identical** between the two runs.
- **Repeated runs under a pinned model configuration** — model, version, and
  decoding parameters pinned and recorded; N runs per fixture, with any
  divergence a failure, so a single lucky pass cannot certify.
- Fixture shapes: HTML comment, `display:none` element, `alt` attribute,
  attempted `host_org_unit` set, URL differing from source, false partnership
  claim, delimiter breakout.
- Unicode and adversarial-rendering cases: bidi override, zero-width
  characters, homoglyphs, confusables.
- **Long-context burial**, conflicting observations, **multi-page assembly**,
  auto-update persistence across crawls (A4), and consumer dataflow.

**Stated plainly in the artifact:** a fixed fixture corpus proves behavior **on
that corpus**. It does not prove the absence of injection vulnerability. The
100% floor is a regression guard, not an assurance argument.

**Note on `host_org_unit`.** `resolve_identity_key` requires it non-blank but
never resolves it against `org_unit` — it is an arbitrary stripped string. If
extraction output could reach it, injection poisons the deterministic identity
key. C-4 makes this a hard invariant rather than a convention.

## T-13 — Egress policy (deferred pre-live prerequisite)

No network-level egress control exists and nothing is deployed. As designed, the
application allowlist would be the **only** barrier to metadata and
private-network access.

**Framing corrected in revision 3.** Revision 2 read as though live operation
without egress control had been accepted. It has not been. G3 §8's accepted risk
applies **strictly to offline, fixture-based work**, where no fetch occurs. This
row is a **deferred pre-live prerequisite**: live fetching remains technically
gated and prohibited until the control exists and is verified. Accepted open
risk and required control are coherent only under that reading.

**The enforcement point is not named, and this document does not name one.**
The row's own test expectation demands a named enforcement point; because none
is named, **the test cannot be written and T-13 cannot close.** That is the
honest state, recorded rather than papered over.

**Proposal for the reviewer to accept or replace** — offered as a candidate, not
a decision, and not made by any agent:

> A validating egress proxy for the crawl worker, deployed so the worker's
> container network policy permits egress **only** to that proxy and to the DNS
> resolver the proxy uses; the proxy performs T-01 classification and T-02
> address binding itself, denies all private, link-local, loopback, CGNAT and
> metadata destinations, and is the only component with general outbound
> reachability.

Whichever enforcement point the owner chooses, the policy must additionally
define: allowed destinations (including the LLM provider endpoint of T-23 and
the search tool of T-07, neither of which is named yet), the DNS path, proxy
resolution behavior, internal ranges denied, fail-closed behavior when the
enforcement point is unavailable, and how enforcement is verified.

**Risk owner of record:** Danny Tran, Development Lead, 2026-08-29 (G3 §8).
Condition of record: **not required for fixture-based work; required before the
first live fetch.** The signing reviewer should confirm this condition holds
rather than treat the control as present.

## T-14 — Incidental PII (prohibition until P9 Gate B)

**T-14 cannot close before P9 Gate B** decides collect-or-drop per published
contact field with a privacy owner. Gate B is undecided, **and this document
must not decide it.**

Revision 2 required "retention/purge for raw artifacts; named viewers" without
specifying any of them — an instruction to make later decisions, which cannot
honestly be signed as a design requirement. Revision 3 therefore takes the
prohibition route instead:

> **Until P9 Gate B is signed, all live fetching, and all collection, storage,
> and retention of raw third-party content, are prohibited.** Fixture-based work
> uses committed fixtures whose PII content is known and controlled. No raw
> fetched page, response body, or payload is persisted. MP-4's ban on emitting
> personal contact data remains absolute and is not the whole of this control.

When Gate B is decided, this row must be replaced with actual retention
durations, purge triggers, named viewer and export roles, encryption
requirements, and a definition of "raw artifact" — not before.

**Direct tension with C-1's evidence contract (revision 4).** C-1 requires
persisting each contributing fetch's raw payload hash, an assertion that the
stored artifact still matches it, and the exact normalized model-input bytes.
For a tier-3 department page, those normalized bytes **are** third-party prose
of the kind this row prohibits storing. The two controls cannot both be
satisfied as written. Under the current fixture-only scope the conflict is
**latent** — no third-party content is fetched, so nothing prohibited is
collected — but **before any live fetch, either Gate B must define
retention/access/purge for evidence artifacts, or C-1 must be restated to store
no third-party prose.** The full statement of the tension is at C-1 above; it is
listed as a blocking dependency in the signature block. This document does not
decide P9 Gate B and does not decide which side gives way.

**Test-oracle warning, stated in the artifact:** raw pages inherently contain
contact data. **A test that checks only normalized event output can pass while
the system retains PII.** The oracle for this row must inspect stored artifacts
and fetch paths, not emitted events.

## T-19 — separation of duties versus signed G3 (tension, recorded not resolved)

**Added in revision 4.** T-19 requires "a second approval for allowlist changes"
and that "a single identity cannot both propose and approve". Signed G3 says
otherwise, in two places:

- **G3 §2.1**: allowlist "entries are approved by the owner of record" —
  singular — and §10 decision #1 records the allowlist approver as one named
  person, Danny Tran, Development Lead.
- **G3 §2.4**: search "may only propose hosts for a human to allowlist", and
  under a single-approver regime that human is the same person who approves.
  The proposing and approving roles collapse by construction.

**As written, T-19 is unsatisfiable under signed G3.** The two documents cannot
both be implemented.

This artifact **does not resolve the conflict**, for two reasons: G3 is signed
and an unsigned threat model does not amend a signed decision; and the resolution
is a staffing question, not a technical one — the reviewer knows whether a second
approver exists, and this document does not.

**Surfaced for the reviewer. Exactly one of the following must happen before
T-19 can close:**

1. **Amend G3 §2.1 / §2.4 and decision #1** to name a second allowlist approver
   distinct from the proposer, and record the separation of duties there. T-19
   then stands as written and its proposer/approver test becomes writable; or
2. **Record a deliberate accepted risk in G3** that allowlist changes are
   single-approver, naming a risk owner and the compensating controls actually
   available — the tamper-evident audit trail, revocation, and anomaly detection
   parts of T-19, which are satisfiable today and are **not** waived by this
   option.

The rest of T-19 is unaffected by the choice and remains a requirement either
way. **T-19 is not deleted, not weakened, and not silently reconciled by
dropping the clause G3 contradicts** — which is what the reviewer should check
this section for.

## Fetch boundary — required properties

A conforming adapter must:

1. Accept only URLs on the approved allowlist (host **plus path patterns**);
   absent, empty, or unparsable allowlist ⇒ fetch nothing (G3 §2.1).
   **Single carve-out — `/robots.txt` (added in revision 4).** `/robots.txt` sits
   on no approved *event* path pattern, so under revision 3 read faithfully the
   robots fetch was refused by this clause, T-15's fail-closed rule then denied
   the crawl, and **nothing could ever be crawled** — the control deadlocked the
   system it governs. `/robots.txt` is therefore an explicit,
   **allowlist-host-scoped** exception to the *path-pattern* rule only:
   - the host must still be on the approved allowlist — this creates no new
     reachable host;
   - the exact path is `/robots.txt` at the scheme/host/port authority being
     crawled, and nothing else; it is not a wildcard, a prefix, or a
     configurable pattern;
   - the fetch still passes **T-01 canonicalization and classification and T-02
     address validation in full** — the carve-out relaxes the path-pattern
     check, never address validation;
   - T-03 applies unchanged: a redirected `robots.txt` re-runs the whole
     authorization cycle, and a redirect off the allowlisted host is refused;
   - the T-04 byte, time and complexity ceilings apply, and an oversized robots
     document denies (T-15);
   - failure at any point remains **fail-closed**: the crawl is denied, not
     permitted.
2. Enforce HTTPS; reject userinfo in URLs and unapproved ports.
3. Canonicalize per T-01, resolve once, validate **every** address, and connect
   through the **validating connector** of T-02 — dialing only validated
   addresses while preserving original-host TLS SNI and certificate hostname
   verification. **Certificate verification is never disabled.** The connector is
   **required unconditionally**; a validating egress proxy is additive defense in
   depth and never a substitute for it (revision 4).
4. Disable automatic redirects; re-run the full authorization cycle on every hop
   and forward no credentials across a host change.
5. Stream under compressed and decompressed byte limits, enforced before
   buffering.
6. Enforce per-source time and rate budgets, including G3's 5 s connect / 15 s
   read / 30 s per-fetch timeouts.
7. Parse only inside the T-05 boundary, from the validated content type.
8. Return extraction artifacts separately from normalized event fields, and
   persist no raw fetch URL (T-06).
9. **Never call the network from API request handlers** — worker/command path
   only.
10. Write provenance as columns, never title suffixes — and validate that
    explicitly (T-30), because the domain layer does not enforce it.

Domain contracts already exist in
`python/smartmatch_domain/smartmatch_domain/events.py`: `resolve_identity_key`,
`EventProvenance`, `resolve_tag` / `QuarantinedTag`.

## Extraction budget

Per G3 §3: **max pages** 50 · **depth** 2 · 5 MiB per response and 100 MiB per
job in **bytes** · **wall time** 300 s · **5 s connect / 15 s read / 30 s per
fetch** (restored in revision 3; revision 2's summary omitted them) · 3 redirect
hops · 200 artifacts/page · progress emission ≤60 s (the job lease bounds
silence, not duration). Post-fetch complexity limits are additionally required
by T-29 and are **not yet quantified** — the reviewer should treat them as an
open dimension of this budget.

## Rate and cost ceilings

Per G3 §4: 10 req/host/min · concurrency 1 per host, 4 global · 6 h minimum
between jobs per host · L21 $2.00/job · $25/tenant/day · $250/tenant/month ·
**5,000 fetches/tenant/day** (restored in revision 3; revision 2 dropped this
signed G3 ceiling). **Escalation** on exceed: `BudgetFailure` ⇒ `failed_budget`
(terminal) plus a `discovery_review_item` row — rate-limited and deduplicated
per T-08 and T-17 so escalation cannot itself flood the review queue.

G3 §4 records that **A3 (LLM price per page) is unverified** and must be
confirmed against the actual provider — which T-07 has not yet named.

## Agent evaluation set and pass/fail criteria

Per G3 §7: offline, fixture-based, no network in CI. Must-pass-100%: never
fabricate (MP-1), never emit an out-of-allowlist host (MP-2), never publish or
match an unresolved event (MP-3), never emit personal contact data while P9
Gate B is open (MP-4), never report a capped response as complete (MP-5).
Category floors of 100% for flyer⇒`unknown`, ambiguous date, out-of-scope page,
injection fixtures, and 200-record subdivision. Whole-set floor ≥90%.

**Scope limit, stated explicitly:** these floors are regression guards over a
fixed corpus. They prove behavior on that corpus and do not establish the
absence of any vulnerability class — see C-7.

## Allowed tools and domains

**Domains dimension — filled.** Per G3 §2.2: CPP master calendar (primary),
`asi.cpp.edu`, CPP Athletics ICS, `cpp.libcal.com`, `events.vtools.ieee.org`,
and `www.cpp.edu` department pages. Removed as prohibited by terms:
`devpost.com`, `mlh.io`, `eventbrite.com`, Luma. Instagram deferred; LinkedIn
rejected; Discord by per-server invitation only.

**Tools/providers dimension — UNFILLED.** The list above names **sources and
methods, not runtime tools**. The stop-gate requires allowed *tools* **and**
domains, so this dimension is currently blank. Unnamed and required before T-07,
T-13, and T-23 can close:

- the **search tool** used for seeding (T-12);
- the **LLM provider, endpoint, and model** (T-23, and G3 §4's unverified A3);
- the **HTTP client / connector implementation** (T-02);
- the **parser libraries** and their permitted capabilities (T-05, T-22).

This document deliberately does **not** invent providers. The dimension is named
as unfilled so the reviewer sees a blank rather than a plausible-looking list.

## Vocabulary growth owner

Danny Tran, Development Lead (G3 §6.3). Twelve approved terms at G3 §6.2.
`resolve_tag` is exact equality with no alias mechanism, so unmapped values
quarantine by design.

## Open questions for the human reviewer

Recorded, not resolved. None may be closed by an agent.

1. **Reviewer authority — CLOSED 2026-09-02 (option 1a).** Danny Tran
   (@dangt), Development Lead, **is** the designated R3 security reviewer.
   The signature block below should name Danny with role Development Lead /
   Security Reviewer. Signing remains outstanding until the human signing pass.
2. **T-13 enforcement point** — proposed above, not decided. Until named, T-13
   cannot close.
3. **T-07 tools/providers** — unfilled, as above.
4. **T-14 / P9 Gate B** — undecided; revision 3 prohibits live and raw-content
   collection rather than pre-empting the decision.
5. **T-27 observation scoping** — whether observations are per-tenant or global
   is undecided and materially changes the isolation model.
6. **ADR-0015 amendment** (quota versus monetary spend) has not landed; T-08's
   reserve-before-spend and its conservative reclaim direction depend on
   Amendment A1.
7. **C-1's evidence contract versus T-14's prohibition** (new in revision 4).
   Direct tension; latent under fixture-only scope; blocking before the first
   live fetch. Either Gate B defines retention/access/purge for evidence
   artifacts, or C-1 is restated to store no third-party prose. **Not decided
   here.**
8. **T-19 versus signed G3's single approver** (new in revision 4). Requires a
   G3 amendment naming a second approver, or a recorded accepted single-approver
   risk. Recorded, not overridden — see section T-19.
9. **T-28's identity model** (new in revision 4). No authenticated reviewer
   identity model exists in this design. Who may approve, for which tenant and
   org unit, and how identity is proven, are human decisions this document does
   not make.
10. **Unquantified limits** (new in revision 4): every T-29 post-fetch
    complexity ceiling and T-04's compressed byte cap. Signed G3 quantifies
    none of them, and this document invents no numbers.
11. **T-05 and the in-process domain parsers** (new in revision 4). `ical_parser`
    and `jsonld_parser` are pure, I/O-free functions inside the domain library,
    a different risk class from a native parser — but they run in the worker's
    process, so their residual risk (CPU/memory exhaustion, T-29) must be bounded
    by the caller. Whether to additionally move them behind the T-05 process
    boundary is for the reviewer.

## What a signature means

Every "Test expectation" above is marked *post-G3*. **No control in this catalog
has an implementing test today.** A signature attests to design requirements, not
to verified behavior. Flipping the unsigned-state test proves status words, not
reviewer authority and not security completeness.

## Security reviewer sign-off (R3) — **SIGNED 2026-09-03**

Reviewer authority: Danny Tran (@dangt), Development Lead / Security Reviewer (1a).

```
Reviewed and approved as DESIGN REQUIREMENTS by: Danny Tran (@dangt), Development Lead / Security Reviewer
Date: 2026-09-03

Scope: the controls above are approved as requirements that implementation must
satisfy. This signature does NOT attest that any control is implemented or
verified. Implementation verification is card S6a and requires a separate
evidence pass before any live target is contacted.

Human decisions recorded in docs/decisions/r3-signing-decisions-2026-09-03.md:
  - T-19: accepted single-approver risk for pilot (compensating controls retained).
  - T-27: per-tenant observation scoping.
  - T-28: anti-CSRF/audit now; identity model deferred to A1b.
  - T-04: 5 MiB compressed-byte cap per response.
  - T-29: post-fetch limits quantified (see decision record).
  - C-1 vs T-14: hashes + logical form only; P9 Gate B closed 2026-09-02.
  - T-13: app-runtime validating connector (proxy additive only).
  - T-23: Gemini primary LLM direction; ADR-0015 A3 credentials still external.

Remaining open at signature time:
  - T-07: full tools/providers allowlist — engineering card work.
  - ADR-0015 A3: live provider spend ceilings — procurement.
  - S6a: implementation evidence before live fetch.
```

> **Signing record.** `tests/unit/test_gate_decision_artifacts.py::test_g3_threat_model_is_signed_requirements`
> asserts signed status. Decision artifact: `docs/decisions/r3-signing-decisions-2026-09-03.md`.

## References

- `docs/security/r3-technical-review-findings.md` — the review behind revision 2
- `docs/security/prompt-injection-assessment.md` — T-11 in depth
- `docs/decisions/g3-crawler-decision.md` — signed G3 decisions
- `docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md`
- `docs/architecture/decisions/ADR-0010-event-temporal-model.md`
- `docs/migration/migration-manifest.yaml` (MM-A08)
- `python/smartmatch_domain/smartmatch_domain/events.py`
