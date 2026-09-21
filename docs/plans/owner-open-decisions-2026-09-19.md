# Owner open decisions — 2026-09-19

**Decide #1 now: reply "Yes to all three — set `SMARTMATCH_EXERCISE_COOKIE_SECURE=true`, generate the workspace secret, create the `exercise_*`-only DB role."**

Twenty-one decisions are open across PRs #155–#184. Ten are yours alone, two are
yours with Ann, six are Ann's, three are Ann's with Chau.

---

## Do now (max 5)

1. **Hosting settings on the VM** → yes to all three → reply: *"Yes: cookie Secure true, new 32+ char workspace secret, DB role granted on `exercise_*` only."*
2. **The site's stable address** → pick the pilot VM hostname today → reply: *"The exercise runs at `<hostname>`, exercise scope only."*
3. **Data-file upload shape** → keep the raw `text/csv` body → reply: *"Keep raw text/csv. No multipart, no new dependency."*
4. **Instructor session storage** → keep the 12-hour signed cookie → reply: *"Keep the signed cookie. No session table before Nov 20."*
5. **Chau's numbers** → send the one Chau message below today (covers #5, #6, #7) → it has the longest lead time of anything open.

## Ask Ann this week (one message, ready to paste)

> Ann — six things I need from you to finish the exercise build. Short answers are fine.
>
> 1. **File layout.** Is the data file one CSV with a `record_type` column marking each row as a profile or an event, or two files, or something else? If the 12 events arrive separately, how?
> 2. **Inside a cell.** What separates several interests, topics, majors or past events in one cell? We assume a semicolon.
> 3. **`class_year` values.** Freshman/Sophomore/Junior/Senior, 1–4, or graduation years? And the final spelling of the columns for major, year, past events, stated interests, career goal, and the hidden true interests.
> 4. **Past events.** Is a past event named on a profile by its key or by its title? And can a profile have "a card with nothing on it" — or does an empty interests cell always mean no card?
> 5. **CSV or XLSX?** CSV needs nothing extra. XLSX adds a library we would carry for one screen.
> 6. **Two browser tabs, same team number.** Same saved runs in both tabs, or a separate workspace per tab? We built "same saved runs".
> 7. **Reason lines.** Your two phrases are shown capitalised and full-stopped — "Same major; nothing else on file." and "Tied on major; ordered by year." — and a single-factor line reads "What counted: same major." Are those acceptable? Three tie sentences are mine, not yours, and need your words: "Tied on what counted; ordered by year.", "Tied; more information on file first.", "Tied; placed in a fixed order that never changes." And when a major-only profile's place was decided by the year, both of your lines fit — which one should a participant see?
> 8. **"Asking for more."** Confirm 30 / 55 / 80 percent and the 15 percent who stop opening messages. When the share lands on an exact half (30% of 25 invited = 7.5), round up or down?
> 9. **The five quick questions.** What are the five questions on the profile card? The requirements name only stated interests and career goal.
> 10. **License line.** The sentence for the opening screen, whenever you have it.

## Ask Chau this week (one message, ready to paste)

> Chau — three sets of numbers block the results screen. The code refuses to run results until they exist, by design.
>
> 1. **The results rule needs eight quantities, not four:** `true_fit_lift`, `frequent_attender_lift`, `same_major_lift`, `chance_spread`, `attend_given_signup`, `base_signup_rate`, `frequent_attender_events` (how many past events counts as "many"), `true_interest_share_of_fit` (how much of the fit lift comes from interests vs career goal). The code enforces Ann's ordering — `true_fit_lift` must exceed the other two lifts — whatever you pick. Propose a set by Oct 2; Ann confirms before the Nov 9 practice run.
> 2. **Default weights** for the four matching factors when a team opens an event. Placeholder is 0.25 each.
> 3. **Points** per attended event and per completed card. Placeholder is 1 and 1.

## Later

Cards #15–#21 below: rate limiting, `unlock` scope, passcode delivery,
`registry_hash` naming, ADR-0026 status, CBA funnel percentages, npm audit gate.

---

## Already decided (2026-09-19 and 2026-09-18) — do not re-open

- Per-team reset moves behind the instructor passcode. **Yes.** (#181, #184)
- On re-entry, a team's existing workspace wins over the newest data file. **Yes.** Only a re-point moves a team. Note: #184 changed the instructor side; the public entry route still lands on the newest file and is an open engineering follow-up, not an open decision.
- `hide_parameters=True` on the shared DB engine. **Yes, env-switchable.** In progress on `fix/engine-hide-parameters`.
- `factor_registry.py` may be edited for the behaviour-preserving parameterisation only. Done in #173.
- G1 registry status `approved` is the contract.
- ADR-0015 quota-vs-spend amendment owner: GitHub user **BrooklynD23**.
- `/u/{token}` and `/i/{token}` are gated out of the exercise scope. Done in #176.
- Ingest builds to the PLACEHOLDER columns without Ann's sample.

## Gated — no action

- **#159** speaker-events board prototype: *"if the design is approved, the component gets rebuilt against main's speaker-pipeline contract."* Speaker accounts are gated. Leave as a prototype file.
- **#169** six workshop decision packets (D6/D7 rewards, OQ-SE-01/02 student ranking, metrics role-gating, A1b IdP). All on the hard-gated list. The packets are written; nobody builds from them.

---

## 1 — Hosting settings on the VM

**Decide** Whether the exercise deployment gets the three security settings it needs before it is public.
**Recommended** Yes to all three. Each is a one-line change and each closes a real hole.
**Options**
- All three (recommended): about 1 hour, plus generating one secret.
- Cookie `Secure` only: the workspace token still has no secret and the process refuses to boot. Not viable.
- Defer: the classroom cookie ships without `Secure` over HTTP.

**If you wait** The site cannot go live for the Oct 2 milestone — a class-exercise process with no `SMARTMATCH_EXERCISE_WORKSPACE_SECRET` does not boot at all.
**Who** Danny alone.
**Say this to close it** "Yes: cookie Secure true, new 32+ char workspace secret, DB role granted on `exercise_*` only."
**Source** #181: *"give the exercise deployment a database role with `GRANT` only on the `exercise_` tables — that, not a source walk, is the real ADR-0025 D2 control"*; #184 owner decision 6.

## 2 — The site's stable address

**Decide** Where the exercise lives and what URL Ann sends to the class (OQ-CE-06).
**Recommended** The existing pilot VM path in `docs/operations/vm-deploy.md`, exercise scope only, no CBA routers registered. It is already documented and already runs.
**Options**
- Pilot VM, exercise scope only (recommended): no new infrastructure; about 2 hours to configure and verify a 5-second load in Chrome.
- New host: unknown — needs a 15-minute look at cost and DNS.
- Subpath on an existing CBA host: cookie paths and the capability table get harder; not worth it.

**If you wait** Oct 2 ("matching working on the site with the full data") slips; every other exercise deadline hangs off a working address.
**Who** Danny alone.
**Say this to close it** "The exercise runs at `<hostname>`, exercise scope only, no CBA routers."
**Source** OQ-CE-06; #176: *"Decision owner: **Danny** (hosting), tracked as **OQ-CE-06**."*

## 3 — Data-file upload: raw CSV body or multipart

**Decide** Whether the instructor's upload route takes a file field (multipart) or a raw `text/csv` body.
**Recommended** Keep the raw body. A browser file picker works either way; multipart buys nothing for one route.
**Options**
- Raw `text/csv` (recommended, already built): zero new dependencies.
- Multipart: adds the `python-multipart` runtime dependency and a re-lock of hash-pinned requirements compiled `--no-index`, plus one handler signature change. About 2 hours.

**If you wait** CE-MOUNT builds the instructor upload screen against a shape that may change; rework lands close to Oct 2.
**Who** Danny alone.
**Say this to close it** "Keep raw text/csv. No multipart, no new dependency."
**Source** #184 owner decision 2: *"FastAPI needs `python-multipart`, which this repo does not have — a new runtime dependency and a re-lock of hash-pinned requirements … for one route."*

## 4 — Instructor session: signed cookie or a session table

**Decide** Whether the instructor login keeps its stateless 12-hour signed cookie or gets a server-side session row.
**Recommended** Keep the signed cookie. One instructor, one classroom, twelve hours; revocation is not worth a migration before Nov 20.
**Options**
- Signed cookie (recommended, shipped): no revocation before expiry; the levers are the 12-hour lifetime and rotating the secret.
- Server-side table: real revocation. One migration and about half a day.

**If you wait** Nothing breaks; the risk is that a leaked passcode stays usable for up to twelve hours with no way to cut it off during a session.
**Who** Danny alone.
**Say this to close it** "Keep the signed cookie. No session table before Nov 20."
**Source** #184 owner decision 1: *"The cost, stated rather than hidden: there is no revocation."*

## 5 — The eight simulation coefficients (OQ-CE-03)

**Decide** How to get the eight numbers the results rule needs. The register names four; the rule needs eight.
**Recommended** Send Chau the eight-name list today with a Oct 2 deadline for a proposal, Ann confirming before Nov 9. Do not propose values — the code refuses to run results until real ones arrive, and that is correct.
**Options**
- Chau proposes by Oct 2, Ann confirms by Nov 9 (recommended): keeps both owners.
- Wait for the Nov 9 practice run to surface them: results are untested until the week they are demonstrated.
- Ask Ann first: she defers the mechanics to Chau; adds a round trip.

**If you wait** Oct 16 ("results with lock, comparison, repeatable runs") cannot be met — `require_coefficients()` raises until they exist.
**Who** Chau + Ann.
**Say this to close it** Send the Chau message above, item 1.
**Source** #177: *"`EXERCISE_SIMULATION_COEFFICIENTS` is `None`; `require_coefficients()` raises … The rule needs **eight**, and the four extra ones are flagged here rather than invented."*

## 6 — Default factor weights (OQ-CE-02)

**Decide** How to get the four default weights a team sees when it opens an event.
**Recommended** Fold into the Chau message; Ann confirms. The placeholder is four named constants at 0.25 each, marked `PLACEHOLDER (OQ-CE-02)` — a team can already adjust them per run, so this sets only the starting point.
**Options**
- Ask in the Chau message (recommended): no extra round trip.
- Leave the equal-weight placeholder to Nov 20: participants start from a number nobody chose.

**If you wait** Oct 2 ships with equal weights. Recoverable — changing four constants is minutes — but the practice run on Nov 9 should not be the first time Ann sees them.
**Who** Chau + Ann.
**Say this to close it** Send the Chau message above, item 2.
**Source** #180: *"OQ-CE-02 | **OPEN — not closed** | Four named constants at 0.25 each, marked `PLACEHOLDER (OQ-CE-02)`."*

## 7 — Points per attendance and per card (OQ-CE-10)

**Decide** How to get the two point values. Points are "if time allows" in Ann's build table.
**Recommended** Fold into the Chau message. Equal placeholders (1 and 1) are deliberate so the code does not rank attendance above card completion.
**Options**
- Ask with the other two number sets (recommended): one message.
- Drop points from the deliverable: legitimate — the requirements say "Not required" — and saves nothing, since the code is written.

**If you wait** Nothing blocks. The counter shows placeholder values at the Nov 9 practice run.
**Who** Ann + Chau.
**Say this to close it** Send the Chau message above, item 3.
**Source** #166: *"OQ-CE-10 | How many points does a profile earn per attended event, and for completing a card? | Ann + Chau | OPEN — Ann confirms before the November practice run."*

## 8 — File layout and column names (OQ-CE-01)

**Decide** How to get the final column names, the list separator, the `class_year` values, and whether events arrive in the same file.
**Recommended** Send Ann the message above. Do not guess: the ingest code holds every name in one `ExerciseFileLayout` object precisely so closing this is a one-object change.
**Options**
- Ask Ann with the 20-row sample (recommended): the sample was due Sept 18 and has not arrived; chase it.
- Keep building to the placeholder layout: already the rule; costs nothing until the full file lands Sept 25.

**If you wait** The Sept 25 full file arrives in a shape nothing parses, and Oct 2 slips by however long re-shaping takes.
**Who** Ann.
**Say this to close it** Send the Ann message above, items 1–4.
**Source** #179: *"**File layout** — one CSV with a `record_type` column per row (what this branch assumes), two files, or something else?"*

## 9 — CSV or XLSX (OQ-CE-05)

**Decide** Whether Ann's data file arrives as CSV or as an Excel workbook.
**Recommended** Ask for CSV. XLSX is refused today with a sentence asking for a CSV export.
**Options**
- CSV (recommended): standard library only, no dependency, shipped.
- XLSX: adds `openpyxl` as a runtime dependency for one screen, plus a re-lock. About 3 hours.
- Accept both: two code paths to test for no product gain.

**If you wait** The Sept 25 file may be an .xlsx the instructor page rejects, on a Friday, with Oct 2 four days away.
**Who** Danny + Ann.
**Say this to close it** Send the Ann message above, item 5.
**Source** #184: *"OQ-CE-05 | CSV via the merged ingest core; XLSX still refused with a sentence. No new dependency. | **OPEN**"*

## 10 — Reason-line wording and precedence (OQ-CE-12)

**Decide** How to get Ann's words for three tie sentences she did not write, her approval of two renderings, and which line wins when both fit.
**Recommended** Ask Ann. Never write her words for her; the current behaviour (`TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE = True`) is a placeholder, and flipping it is one line.
**Options**
- Ask in this week's message (recommended): no cost.
- Ship the placeholders and revise after Oct 16: participants read sentences nobody approved during Ann's own session.

**If you wait** Oct 2 shows reason lines next to every name — the one screen feature Ann named as a keep — in wording she has not seen.
**Who** Ann.
**Say this to close it** Send the Ann message above, item 7.
**Source** #180: *"all three are placeholders awaiting her words"*; register row OQ-CE-12.

## 11 — The three percentages and the half-rounding (OQ-CE-04)

**Decide** How to get Ann's confirmation of 30 / 55 / 80 percent and 15 percent non-responding, and what happens when a share lands on an exact half.
**Recommended** Ask both in one line. The rounding is the only part you may settle yourself: if she has no view, use round-half-up, which is what a classroom expects. The percentages are hers.
**Options**
- Ask both (recommended): one sentence added to her message.
- Keep Python's `round()` (half to even) silently: 30% of 25 invited gives 7, not 8, and nobody can explain why.

**If you wait** Nothing breaks before Nov 9, when the practice run is exactly where the percentages get reviewed.
**Who** Ann (percentages); Danny may settle the rounding if she declines.
**Say this to close it** Send the Ann message above, item 8.
**Source** #177: *"**Question for Ann:** when `share × n` lands exactly on `.5` … should it round to even or up?"*

## 12 — Two tabs, one team number (OQ-CE-08)

**Decide** How to get Ann's confirmation that two browser tabs on the same team number share one workspace.
**Recommended** Ask her to confirm the shipped reading. Her build table says "one browser tab per team, team number entered", which reads as shared, and the database constraint already encodes it.
**Options**
- Confirm shared (recommended): no change.
- Per tab: `workspace_token.py` changes, plus the unique constraint. One migration, about half a day.

**If you wait** Low risk — the current reading is defensible. The cost of being wrong rises after Oct 2, when saved runs exist.
**Who** Ann.
**Say this to close it** Send the Ann message above, item 6.
**Source** #181: *"OQ-CE-08 … Built to the register's default — shared per team number … If Ann answers 'per tab', `workspace_token.py` is what changes."*

## 13 — The five quick questions (OQ-CE-11)

**Decide** How to get the five questions on the profile card. The requirements name only stated interests and career goal.
**Recommended** Ask Ann, and keep the mock-up labelled as a mock-up until she answers. It depends on OQ-CE-01's column wording, so it can ride in the same message.
**Options**
- Ask with the layout questions (recommended): one message.
- Ship the five design-spec fields as final: publishes a card nobody designed.

**If you wait** Nothing blocks before Nov 9. This is an "if time allows" item.
**Who** Ann.
**Say this to close it** Send the Ann message above, item 9.
**Source** #166: *"OQ-CE-11 | What are the five questions on the 'five quick questions' card? | Ann | OPEN — confirm before the November practice run."*

## 14 — The license line (OQ-CE-09)

**Decide** How to get the one sentence the opening screen shows.
**Recommended** Ask now, accept it any time before Nov 20. The field is already nullable, and null means "she has not said", not "there is none".
**Options**
- Ask now, ship when it arrives (recommended): zero cost either way.
- Chase at Nov 20: the deliverable review is the wrong moment to discover a missing attribution.

**If you wait** Nov 20 is the deadline. Nothing technical blocks.
**Who** Ann.
**Say this to close it** Send the Ann message above, item 10.
**Source** #171: *"OQ-CE-09 (license line) | Deliberately not in the response; the opening screen gets it when Ann provides the sentence."*

## 15 — Rate limiting for the no-login routes (OQ-CE-06)

**Decide** Whether the exercise routes are rate limited in the process or at the VM's proxy.
**Recommended** Keep the in-process placeholder and add proxy limiting when you fix the address (#2). The in-process limiter is honest about being per process and cannot bound CPU; the proxy can.
**Options**
- In-process placeholder only (shipped): bounds attempts, not work; breaks the moment the deployment scales out.
- Proxy/edge on the VM (recommended alongside): about 1 hour of nginx config; the in-process module is then deleted and one dependency comes off the route.
- Neither: an unauthenticated entry `POST` does a database insert attempt per call.

**If you wait** The passcode route goes public on Oct 2 with a per-process bound only. Not fatal for a classroom; unacceptable for a URL anyone can find.
**Who** Danny alone.
**Say this to close it** "Proxy limiting on the VM alongside #2; keep the in-process limiter until it is in place."
**Source** #184: *"If the answer is 'the VM's proxy does it', this module is deleted and one dependency comes off the route."*

## 16 — May `unlock` open results on a non-active data file

**Decide** Whether the instructor can unlock an event on a data file no team is working in.
**Recommended** No. Keep it resolving through the teams' file, honouring an explicit `dataset_id` only when a team is actually in it.
**Options**
- Teams' file only (recommended, shipped): an unlock always has a visible effect.
- Any file: an unlock reports success while nothing changes for anyone — the hardest class of bug to see in a classroom.

**If you wait** CE-RESULTS-API builds on the current rule anyway; confirming costs one reply and removes the risk of rework before Oct 16.
**Who** Danny alone.
**Say this to close it** "Confirmed: `unlock` only targets a file teams are in. A file with zero workspaces is never targeted."
**Source** #184 owner decision 3: *"Today it is scoped to the active file … but it is a product call."*

## 17 — How the passcode reaches Ann and Dr. Lin (OQ-CE-07)

**Decide** How the instructor passcode is generated and delivered. The mechanism (one environment variable per deployment) is settled; the delivery is not.
**Recommended** Generate a 24-character random passcode, set the variable on the VM, send it to Ann and Dr. Lin in a direct message — never in the repository, an issue, or a PR. Rotate after the spring run.
**Options**
- Direct message, rotate after spring (recommended): about 15 minutes.
- A shared document: it outlives the course and nobody remembers to revoke it.
- Let Ann choose the passcode: memorable means guessable, and the route has only the placeholder limiter in front of it.

**If you wait** Ann cannot unlock results or upload the data file for the Oct 16 session she runs herself.
**Who** Danny + Ann.
**Say this to close it** DM Ann and Dr. Lin: "Instructor page passcode for the exercise site: `<value>`. Do not paste it anywhere shared; I rotate it after the spring run."
**Source** #184: *"OQ-CE-07 | One env var per deployment, `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` … | **OPEN**"*

## 18 — `registry_hash` names two different digests (B-10)

**Decide** Which of two meanings keeps the name `registry_hash`, and what the other becomes.
**Recommended** The persisted `match_run.registry_hash` column keeps the name; rename the contracts document's `FactorRegistry` property to `factor_registry_digest`. The column is shipped, in the schema, in OpenAPI and in ADR-0016; the other meaning exists only in a document.
**Options**
- Rename the document's meaning (recommended): docs only today, about 1 hour, because #173 already deleted the property from the code.
- Rename the column: one migration plus an OpenAPI change, and it breaks a shipped contract.
- Leave both: two `sha256:`-prefixed values under one name, indistinguishable in a log.

**If you wait** Nothing blocks until a second registry ships. The cost of deciding rises the moment one does.
**Who** Danny alone.
**Say this to close it** "The column keeps `registry_hash`. Rename the contracts-doc property to `factor_registry_digest`."
**Source** #173: *"That is a naming decision for a later track; this PR only declines to add a third meaning."* Logged as B-10 in `adr-backlog.md`.

## 19 — ADR-0026 status

**Decide** Whether to accept ADR-0026 (the student program and the student-centric classroom) or leave it Proposed.
**Recommended** Leave it Proposed until after Nov 20. It records direction for work that is hard-gated; accepting it now invites someone to build from it.
**Options**
- Leave Proposed (recommended): no cost, and the record still exists.
- Accept: needs a ratifier line and a decision on what "push notifications" meant in the 12 Sept relay — unknown, needs a 15-minute look.
- Withdraw: throws away an accurate record of the direction.

**If you wait** Nothing blocks. The exercise track does not depend on it.
**Who** Danny alone.
**Say this to close it** "ADR-0026 stays Proposed until after the Nov 20 deliverable."
**Source** #160: *"Adds ADR-0026, Status **Proposed** — the owner accepts it, not this PR."*

## 20 — Funnel conversion percentages on the CBA screen

**Decide** Whether conversion rates belong on a CBA screen at all. They shipped in #156.
**Recommended** Keep them. OQ-CBA-005 forbids a score *about a person*; a conversion rate divides two counts a reader can drill into and is owned by one server definition.
**Options**
- Keep (recommended): no change; two test rules already hold the line that no match score reaches that surface.
- Remove: stop the server sending them — not a browser filter. About 3 hours.

**If you wait** Nothing blocks. The rates are live on the pilot dashboard today.
**Who** Danny alone (as CBA product owner).
**Say this to close it** "Conversion rates stay. They are server-owned counts, not a score about a person, so OQ-CBA-005 does not reach them."
**Source** #156: *"Whether conversion rates belong on a CBA screen at all is a product decision, not one a test can settle."*

## 21 — Runtime npm audit gate threshold

**Decide** Whether the runtime `--omit=dev` audit gate moves from `high` to `moderate`, as the dev-tree gate already did in #172.
**Recommended** Leave it at `high` for now and revisit after Nov 20. The exercise deadline is the binding constraint; a moderate advisory in a runtime dependency would block every branch.
**Options**
- Stay at `high` (recommended): no cost.
- Raise to `moderate`: about 30 minutes to change, then unknown — depends on what the audit finds.

**If you wait** Nothing blocks.
**Who** Danny alone.
**Say this to close it** "Runtime gate stays at `high` until after Nov 20."
**Source** #172: *"OQ-3 | The runtime `--omit=dev` gate stays at `high`. Raise it to `moderate` too, in a follow-up? | Not here."*

---

## Status

| # | Decision | Who | Blocks | Recommended | Status |
|---|---|---|---|---|---|
| 1 | Hosting settings on the VM | Danny | Oct 2 site | Yes to all three | OPEN |
| 2 | Stable public address | Danny | Oct 2 site | Pilot VM, exercise scope only | OPEN |
| 3 | Upload: raw CSV vs multipart | Danny | CE-MOUNT, Oct 2 | Keep raw `text/csv` | OPEN |
| 4 | Instructor session storage | Danny | Nothing hard | Keep the signed cookie | OPEN |
| 5 | Eight simulation coefficients | Chau + Ann | Oct 16 results | Chau proposes Oct 2, Ann confirms Nov 9 | OPEN |
| 6 | Default factor weights | Chau + Ann | Oct 2 defaults | Ask in the Chau message | OPEN |
| 7 | Points per attendance / card | Ann + Chau | Nov 9 | Ask in the Chau message | OPEN |
| 8 | File layout and column names | Ann | Sept 25 file, Oct 2 | Ask Ann; chase the sample | WAITING ON ANN |
| 9 | CSV or XLSX | Danny + Ann | Sept 25 file | Ask for CSV | WAITING ON ANN |
| 10 | Reason-line wording and precedence | Ann | Oct 2 reason lines | Ask Ann; never write her words | WAITING ON ANN |
| 11 | Three percentages + half-rounding | Ann | Nov 9 | Ask Ann; half-up if she declines | WAITING ON ANN |
| 12 | Two tabs, one team number | Ann | Nothing hard | Confirm shared | WAITING ON ANN |
| 13 | The five quick questions | Ann | Nov 9 | Ask Ann | WAITING ON ANN |
| 14 | License line | Ann | Nov 20 | Ask now, ship when it arrives | WAITING ON ANN |
| 15 | Rate limiting for no-login routes | Danny | Oct 2 public URL | Proxy on the VM, alongside #2 | OPEN |
| 16 | `unlock` on a non-active file | Danny | Oct 16 results | No — teams' file only | OPEN |
| 17 | Passcode delivery | Danny + Ann | Oct 16 session | DM, rotate after spring | OPEN |
| 18 | `registry_hash` naming clash | Danny | Nothing yet | Column keeps the name | OPEN |
| 19 | ADR-0026 status | Danny | Nothing | Stays Proposed until after Nov 20 | OPEN |
| 20 | CBA funnel percentages | Danny | Nothing | Keep them | OPEN |
| 21 | Runtime npm audit gate | Danny | Nothing | Stays at `high` | OPEN |
| — | Per-team reset behind passcode | Danny | — | Yes | DECIDED |
| — | Existing workspace wins on re-entry | Danny | — | Yes | DECIDED |
| — | `hide_parameters=True`, env-switchable | Danny | — | Yes | DECIDED |
| — | FactorRegistry parameterisation edit | Danny | — | Allowed | DECIDED |
| — | G1 registry `approved` is the contract | Danny | — | Yes | DECIDED |
| — | ADR-0015 amendment owner | Danny | — | BrooklynD23 | DECIDED |
| — | `/u/` and `/i/` out of exercise scope | Danny | — | Gated out | DECIDED |
| — | Build ingest to PLACEHOLDER columns | Danny | — | Yes | DECIDED |

---

**Next action, under two minutes:** paste the Ann message above into an email to her and send it. It unblocks six of the twenty-one.
