# ADR-0012 — Deterministic event identity, and a closed tag vocabulary

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §1.5, gate G3
**Backlog:** S4, S5
**Findings:** Stakeholder test log, 19–20 August 2026 — Fix #4

## Context

Fix #4 has three halves. The temporal half is ADR-0010. The other two are here:

- **Duplicates.** The same event appeared more than once, because two pages
  described it and each description became a row.
- **Titles carrying their source.** Event titles included the name of the page
  they were scraped from — provenance leaking into the display string.
- **Open-ended tags.** Extraction produced whatever role and type words appeared
  in the source text, so the tag set grew without bound and no two events could
  be reliably compared.

All three are properties of an extraction pipeline that does not exist yet.
`MM-A08` records the legacy crawler as `REPLACE`, `status: archived`, deferred
to R3 pending a threat model, with the note "Not yet inventoried in depth;
revisit at R3 with a security reviewer."

**That is exactly why this ADR is written now rather than at R3.** The
disposition says the legacy crawler's *code* does not carry forward. It says
nothing about the legacy crawler's *output shape*, and a rebuilt crawler with no
constraint on its output reproduces all three defects honestly.

## Decision

### Event identity is a deterministic key, computed before insert

An extracted event resolves to an existing event, or creates one, by a key
derived from:

- **host org unit** — the `org_unit` the event belongs to, not the page it was
  found on;
- **normalized title** — case-folded, whitespace-collapsed, punctuation-stripped,
  with the source-page name removed (it is a separate field, below);
- **resolved date window** — the date, at the precision ADR-0010 records. An
  event at `unresolved` precision **has no identity key** and cannot be
  resolved against anything.

Two extractions producing the same key are the same event, and the second
updates the first rather than inserting. This is the same discipline as
`generate_ics`'s deterministic UID derivation, which `MM-001` records as
retained behaviour precisely so "a regenerated invite updates rather than
duplicates".

### Source provenance is a field, never part of the title

The page an event was extracted from is recorded as structured provenance —
URL, fetch time, extractor version — on its own. It never appears in the title,
the description, or any other display string. `apps/web/DESIGN.md §1.1` already
requires provenance to be *visible*; this says where it lives, which is not
inside another value.

### Role and type tags come from a closed vocabulary

A controlled vocabulary of 10–12 terms, versioned in the repository. Extraction
**maps into** it; it does not extend it.

A value that does not map is **quarantined**: stored with the event, visible to
a human review queue, and **never rendered and never matched on**. Growing the
vocabulary is a deliberate versioned change with a human in the loop, which is
the R3 "human verification queue" the backlog already lists.

## Rationale

**Why the key is computed rather than assigned.** An assigned surrogate id makes
the second extraction of the same event a new row by construction. Determinism
is what makes re-crawling idempotent, and re-crawling is the normal case, not
the exception.

**Why the host org unit and not the source domain.** A department's events
appear on the university calendar, the department page, and an aggregator. The
source domain differs across all three; the host does not. Keying on the source
would preserve exactly the duplicates this closes.

**Why `unresolved` events have no key.** Two events with unknown dates are not
evidence of being the same event, and a key that ignores the date would merge
them. Leaving them unkeyed keeps them distinct, unmatchable (ADR-0010), and
visible to review — which is the honest state.

**Why quarantine rather than dropping unmapped values.** Dropping loses the
signal that the vocabulary is wrong. The unmapped values are the input to the
next vocabulary revision, and discarding them is how a closed vocabulary
ossifies into a wrong one.

**Why a closed vocabulary at all.** An open tag set cannot support ADR-0011's
metric register: "events tagged X" has no stable definition if X is whatever the
extractor found this week.

## Consequences

- **MM-A08** is amended to carry this ADR and ADR-0010, so the R3 crawler
  inherits both invariants rather than rediscovering them after the same bug
  report.
- **S4** (entity-resolution key) and **S5** (tag vocabulary plus quarantine) are
  the implementing backlog items. Both are R3 and both remain behind gate G3 and
  the crawler threat model, which this does not alter or shortcut.
- The vocabulary's actual 10–12 terms are not chosen here. They are a product
  decision, and picking them in an ADR would be exactly the kind of silent
  decision this document exists to prevent.
- Manual event entry uses the same key and the same vocabulary. A coordinator
  typing an event is not exempt, or the duplicate class reopens through a second
  door.

## Alternatives considered

**Fuzzy title matching with a similarity threshold.** Rejected. It makes
identity non-deterministic and non-reproducible, and a threshold nobody can
justify is a worse contract than a key anyone can recompute.

**Free tags with a curated display allowlist.** Rejected: the unmapped values
still enter the matching path, so "never matched on" is unenforceable.

**Defer all of this to R3 with the crawler.** Rejected. The crawler is deferred;
the *constraints on its output* are what stop it being rebuilt wrong, and they
cost nothing to record now. `MM-A08`'s note already shows what deferring the
whole question produces: an entry nobody has inventoried.
