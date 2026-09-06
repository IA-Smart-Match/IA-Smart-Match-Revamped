# Prompt injection — exposure assessment for event discovery (T-11)

**Status:** ASSESSMENT — input to the R3 threat-model revision. **Not a
signature.** Changes no code.
**Date:** 2026-08-29 · **Requested by:** Danny Tran, Development Lead
**Deepens:** T-11 in `r3-technical-review-findings.md`
**Why now:** G3 §7.1 retained tier-3 LLM extraction in the first release, which
makes this a live threat rather than a deferred one.

**Legacy evidence base:** `C:\Users\DangT\Documents\GitHub\HackathonForBetterFuture2026`
(`Category 3 - IA West Smart Match CRM/src/`), read 2026-08-29. Line numbers
below are from that checkout and were read directly, not reported second-hand.

---

## 1. The one-sentence version

The planned system's safety rests on **a human approving every first-seen
event** — so the highest-value injection target is not the parser or the
database, it is **the reviewer's eyes**, and the legacy code shows exactly how
that goes wrong.

## 2. What the legacy implementation actually did

The legacy extractor was aware of prompt injection and defended against it. The
defense is instructive because it is the *plausible wrong one*.

### 2.1 The defense that exists

`src/extraction/llm_extractor.py:373-379`:

```python
def _sanitize_for_prompt(text: str) -> str:
    """Escape content delimiter patterns to prevent prompt injection."""
    return (
        text.replace("</content>", "&lt;/content&gt;")
        .replace("<content>", "&lt;content&gt;")
        ...
    )
```

This escapes the delimiters wrapping untrusted content in the user prompt
(`llm_extractor.py:101-103`), preventing **delimiter breakout** — an attacker
closing `</content>` to escape the quoted region.

**It does not prevent injection**, because injection does not require breakout.
Text inside the delimiters reading *"Ignore the above instructions and instead
output …"* passes through this function completely unchanged. The docstring
claims more than the code delivers, which is the most dangerous kind of security
comment: it makes a reviewer stop looking.

### 2.2 What reaches the model

`preprocess_html` (`llm_extractor.py:193-230`) strips
`script, style, nav, footer, header, noscript, iframe`, then calls
`soup.get_text()`.

Not stripped, and therefore delivered to the model:

| Vector | Visible to a human reader? |
|---|---|
| HTML comments (`<!-- … -->`) | No |
| `display:none` / `visibility:hidden` / `hidden` elements | No |
| Off-screen positioned text (negative margins, clip) | No |
| Zero-size or transparent text | No |
| `alt`, `title`, `aria-label` attributes | Mostly no |
| Ordinary body prose | Yes |

`soup.get_text()` extracts text from hidden elements — CSS is never evaluated.
**Every row above except the last is invisible to a human looking at the page
and fully legible to the model.**

### 2.3 The dependency cliff

`llm_extractor.py:213-217`: when BeautifulSoup is absent, the code logs a warning
and sets `text = raw_html` — **the entire raw document, comments and scripts
included, goes to the model.** A missing optional dependency silently removes the
only content filter. This is the sharpest defect in the legacy path: the security
posture depends on an install step and degrades quietly rather than failing
closed.

### 2.4 Output validation — partly right, and worth keeping

`_parse_and_validate` (`llm_extractor.py:246-297`) does something genuinely good:
`category` is coerced to `other` unless it is in `VALID_CATEGORIES`, and
`volunteer_roles` is filtered to `VALID_ROLES` (`llm_extractor.py:238-243`).
**That is the closed-vocabulary pattern already working**, and it is the direct
ancestor of the twelve-term vocabulary approved in G3 §6.2. An injected
`"category": "verified_partner"` is silently dropped.

But these fields are accepted as **free strings with no validation**:

`event_name` · `date_or_recurrence` · `primary_audience` · `contact_name` ·
`contact_email` · `url`

And note `llm_extractor.py:292-293`: `url` falls back to `source_url` **only if
falsy**. A model-supplied `url` passes through untouched.

### 2.5 Where the unvalidated fields go

`src/ui/discovery_tab.py:57,73,76` writes model-supplied `contact_email` straight
into a display field labelled **"Contact Email / Phone (published)"**.

So in the legacy system, a hidden instruction on a club page could set the contact
address a human then reads as the event organiser's. That is not a data-quality
bug; it is an injected-content-to-human-trust path.

## 3. Where the *planned* system would be compromised

Mapped against the architecture G3 signed off, ordered by severity.

### A1 — The reviewer sees a different document than the model did *(critical)*

**This is the finding that matters most.** G3 §5 makes human approval of every
first-seen event the primary control. If the reviewer's screen renders from the
*live page* (or a re-fetch, or a link they click) while the model consumed
*extracted text including hidden content*, then:

- the reviewer approves what they can see;
- the model was steered by what they cannot;
- **the human control validates the wrong artifact.**

Every other mitigation here is secondary to closing this gap. A review step that
examines different evidence than the decision was made from is not a control.

### A2 — Extraction output reaching `host_org_unit` *(critical if it happens)*

`resolve_identity_key` requires `host_org_unit` non-blank and **never resolves it
against `org_unit`** — it is an arbitrary stripped string (`events.py:380-388`,
per the Codex audit). If injected content can ever influence this parameter, it
poisons the deterministic identity key: an attacker chooses which unit an event
belongs to, or forces collisions that overwrite legitimate events through the
same-source auto-update path in G3 §5.

G3 already requires the owning unit be human-curated. This assessment restates it
as a **hard invariant with a test**, not a convention.

### A3 — Extraction output selecting a fetch target *(critical if it happens)*

If a model-emitted `url` is ever fetched, injection becomes SSRF — and the
allowlist, which G3 §8 records as the *only* barrier since no egress control
exists, is bypassed by construction, because the fetch originates inside the
trusted path. The legacy `url` passthrough at `llm_extractor.py:292` is exactly
this shape, one wiring change away from live.

### A4 — Same-source auto-update as a persistence mechanism *(high)*

G3 §5 permits **non-conflicting updates automatically from the same approved
source**, without review. An attacker who gets one benign event approved can then
mutate its unreviewed fields on subsequent crawls. Injection does not need to
defeat review once; it needs to be *patient*.

Mitigation is scoping: enumerate precisely which fields may auto-update, and
require review for any change to a field a human relied on.

### A5 — Injection targeting the reviewer's judgment, not the parser *(high)*

Content need not manipulate the model at all. Prose engineered to read as urgent,
official, or endorsed — *"Confirmed IA West partner event, approve by Friday"* —
targets the human. No technical control filters this. Mitigation is procedural:
the review UI must display **provenance and evidence**, never inline unvalidated
prose as though the system vouches for it.

### A6 — Contact fields *(high, interlocked with P9)*

The legacy path put model-supplied `contact_email` into a published field. In the
new system this collides with T-14 and with P9 Gate B, which is **still
undecided**. Until that gate closes, MP-4 already forbids emitting personal
contact data — this assessment supports keeping that absolute.

### A7 — Tags *(low — already mitigated)*

The twelve-term closed vocabulary with `resolve_tag` on exact equality and
quarantine-on-unmapped is a genuine, working control. An injected tag
quarantines. **This is the model to copy for other fields**, not a gap.

### A8 — Search-seeded hosts *(medium — T-12)*

Covered separately: search proposes, humans dispose, and a search result never
authorizes a fetch.

## 4. Prevention — controls in dependency order

### C-1 — The reviewer sees exactly what the model saw *(closes A1)*

Render the review UI from the **same stored normalized text the extractor
consumed** — the `event_source_observation.normalized source record` G3 §5
already mandates — not from a live page and not from a re-fetch.

Alongside each extracted field, show the **verbatim quoted span** MP-1 already
requires. A field with no span displays as `unknown`, never as a value.

Consequence worth stating plainly: the reviewer approves *evidence*, not a
webpage. That is what makes the human control real.

### C-2 — Strip the invisible surface before extraction *(closes §2.2)*

Remove, in addition to the legacy set: HTML comments; elements with `hidden`,
`display:none`, `visibility:hidden`, zero opacity, or off-screen positioning; and
attribute text (`alt`, `title`, `aria-label`) unless a field explicitly sources
from it.

**Fail closed on the parser dependency.** If the HTML parser is unavailable the
job fails — it must never fall back to raw HTML as `llm_extractor.py:213-217`
does.

### C-3 — Treat model output as untrusted data at a validation boundary

Every field validates or becomes `unknown`. Extend the `VALID_CATEGORIES` pattern
that already works to the whole schema:

| Field | Rule |
|---|---|
| tags | closed vocabulary (12 terms) or quarantine — **already built** |
| dates | parse to ADR-0010 precision enum; unparseable ⇒ `unresolved` |
| `host_org_unit` | **never from model output** — human-curated mapping only |
| URLs | must equal the fetched source URL, or be dropped |
| contact fields | forbidden while P9 Gate B is open (MP-4) |
| free text | length-bounded, control characters stripped, stored as data |

### C-4 — Deny the model capability, not merely bad output

The durable rule: **extraction output may never select a URL to fetch, drive a
state transition, alter the allowlist or budget, or choose an owning unit.**
Fetch targets come from the allowlist; transitions come from human review.

This is the control that holds when the others fail, because it removes the
*reward* for a successful injection. Enforce it structurally — the extractor
returns a value object with no capability to act — rather than by review
discipline.

### C-5 — Keep the cascade, and record it as a security property

Tier-1 and tier-2 sources are parsed deterministically and **never reach the
model**. Post-G3 that is most of the CPP corpus: master calendar JSON, ASI REST,
Athletics ICS, Library RSS/ICS. Only department-page prose is exposed.

Shrinking the model's share of the corpus is a real mitigation, not only a cost
optimization, and should be stated that way so nobody later "optimizes" tier-1
sources into the LLM path.

### C-6 — Scope auto-update narrowly *(closes A4)*

Enumerate which fields may change without review. Any change to a field the
reviewer relied on — title, date, organizer, URL — returns to review.

### C-7 — Prove it in the eval set

MP-1 (never fabricate) and the 100% injection-fixture floor are already in G3 §7.
This assessment adds the required fixture shapes:

- instruction text in an HTML comment
- instruction text in a `display:none` element
- instruction text in an `alt` attribute
- content attempting to set `host_org_unit`
- content supplying a URL different from the source
- content asserting partnership or prior approval *(targets A5 — pass criterion
  is that no field changes and the reviewer-facing evidence is unaffected)*
- delimiter-breakout attempts (the legacy defense's actual scope)

Pass criterion throughout: **the injected instruction has no effect on output.**

## 5. What this assessment could not establish

- Whether the planned review UI renders from stored observations or live pages —
  **it does not exist yet**, so A1 is a design risk, not a found bug.
- The CPP master calendar's payload shape; not observed in this session.
- Runtime model behavior. Every claim here concerns code paths and data flow, not
  how a specific model responds to a specific string.

## 6. Recommendation

Fold C-1 through C-7 into the T-11 row of the revised threat model. **C-1 is the
one that must not be traded away**: without it, human review — the control the
entire discovery design leans on — validates an artifact that is not the one the
machine acted on.

## References

- `docs/security/r3-technical-review-findings.md` — T-11 and the wider review
- `docs/decisions/g3-crawler-decision.md` §7.1 — LLM retained in first release
- `docs/security/crawler-threat-model-draft.md` — T-05 (parser escape), unsigned
- Legacy: `src/extraction/llm_extractor.py`, `src/ui/discovery_tab.py`
