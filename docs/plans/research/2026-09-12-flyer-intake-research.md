# Flyer intake — a photographed poster as an event candidate

**Status:** research only. No source file changes, no route, no migration, no
dependency added, no provider authorized.

**Question asked:** can a physical flyer reach the platform's event database
through OCR or a phone photo?

**Short answer:** yes, and the hard part is not the OCR. It is that the
repository has no place to put an image, and that a flyer is a *claim* about an
event rather than *evidence* of one. Both of those are decisions with owners.
The recognition step is the cheapest part of the whole track.

**Parent brief:**
[`../2026-09-12-student-centric-prioritization-brief.md`](../2026-09-12-student-centric-prioritization-brief.md)
(Tracks E2 and F).

---

## 1. What already exists, and what does not

| | |
|---|---|
| Canonical event write path | `smartmatch_persistence.events.EventRepository` — the only writer, used by both the crawler ingest and manual entry |
| Manual event entry by an administrator | `POST /v1/units/{unit_id}/events`, `origin='coordinator_entry'` (`routers/manual_events.py`) |
| Deterministic event identity, dedupe on write | ADR-0012 — host unit + normalized title + resolved date window |
| Temporal honesty | ADR-0010 — `exact` / `date_only` / `unresolved`; an `unresolved` event has **no identity key** and cannot resolve against anything |
| A review queue for extracted events | `discovery_review_item` (migration `0017`), `POST /v1/review-items/{id}/decision` |
| A closed tag vocabulary | `smartmatch_domain.event_vocabulary`, twelve terms, version `g3-2026-08-29`; unmapped terms quarantine |
| **Object storage** | **Absent.** No bucket, no upload route, no `media` table, no content-type allowlist, no size cap |
| **Any OCR** | **Absent.** No dependency, no provider seam |

So the pipeline has a well-defended *destination* and no *front door*.

## 2. Why the OCR is the easy part

Three facts make it easy, and all three are properties of this repository rather
than of OCR:

1. **The output has somewhere honest to go.** `discovery_review_item` already
   exists for exactly this: a machine produced a candidate, and a human decides.
   An OCR result is a lower-confidence instance of the same shape the crawler
   ingest produces, and it can reuse the queue rather than needing one.
2. **The temporal model already refuses guesses.** A flyer that says "Thursday
   5pm" with no date is `unresolved` under ADR-0010, gets no identity key under
   ADR-0012, and is therefore *unpublishable* by CHECK constraint
   (`ck_event_publishable`) rather than by anyone's discipline. The worst OCR
   failure mode — a confident wrong date — collides with a constraint before it
   reaches a student.
3. **The vocabulary is closed.** A flyer saying "Networking Mixer & Boba Social"
   cannot invent a thirteenth tag; the term quarantines and a human sees it.

The single genuine recognition risk is the opposite of the obvious one. It is not
"OCR misreads a character". It is **OCR reading a flyer correctly and the
extractor resolving a relative date wrongly** — "this Friday" photographed three
weeks after it was posted. That is finding **F-003** wearing a camera, and the
mitigation is not a better model. It is: the *photograph's* timestamp is not the
*flyer's* reference date, so a relative date on a flyer is `unresolved`, full
stop, and a human supplies the date at review.

## 3. Why the storage is the hard part

An uploaded flyer is the first **user-supplied binary** this system would hold.
Everything that follows is new surface:

- **Where it lives.** No bucket is provisioned; F5 deployment is deferred and
  `ALLOW_CLOUD_DEPLOY` is false. A local-disk path in `docker compose` is a dev
  appliance, not a design.
- **Who may read it.** A flyer photographed inside a classroom can contain a
  roster on a whiteboard, a face, or a phone number. It is not automatically
  publishable content merely because a poster is public.
- **How long it is kept.** Attendance evidence already has an unanswered retention
  question (OQ-E03). A flyer image is a second one, with a different answer.
- **What is accepted.** Content-type allowlist, size cap, and a decode step that
  treats the file as hostile — an image parser is a classic attack surface, and
  this repository has no precedent for one.
- **Whether the *image* is kept at all** once the fields are extracted, which is
  the cheapest privacy answer available and should be the default.

This is OQ-SC-05 in the parent brief, and it gates the video/summary ask
identically — Lisa's "attach a short video or an Associate Dean news flash" is the
same missing capability with a larger blob and a harder hosting answer.

## 4. Recommended shape

Four stages, each of which can ship and be reviewed alone.

### Stage 1 — upload, with no recognition at all

An administrator attaches an image to an event **they have already filed** through
the existing manual-event route. No extraction, no candidate, no queue. This
delivers Lisa's "upload flyers directly" ask in full, and it is the whole of the
media-plane work with none of the OCR work attached to its review.

Answering OQ-SC-05 is the entire cost of this stage.

### Stage 2 — recognition into a candidate, never into an event

A photograph produces a `discovery_review_item`-shaped candidate carrying:

- the extracted fields, each with a per-field confidence;
- **provenance as structured fields** — that this came from an image, when the
  image was taken if the file says so, which extractor version ran. ADR-0012 is
  explicit that provenance is never part of the title, and "photographed flyer" is
  provenance;
- `time_precision` computed by the *existing* rules, with the relative-date rule
  from §2 applied: no absolute date on the flyer means `unresolved`.

The candidate is **never** written as a published event, and the route that
creates it must not be able to. Structurally, not by policy — the same way
`routers/engagement.py` is pinned read-only by a test that fails if a `POST`
appears.

### Stage 3 — human review, on the queue that already exists

A coordinator sees the extracted fields beside the image, corrects them, and
accepts or rejects. Acceptance goes through `EventRepository` with
`origin='coordinator_entry'` — because that is what happened: a named human
asserted these facts, having looked at a picture. Recording the origin as an
extraction would overstate what the machine did.

### Stage 4 — a student-submitted flyer (only if wanted)

The "phone image" half of the ask. Everything in Stages 1–3 holds, plus: a student
is not an administrator, so a student-submitted candidate needs its own rate limit,
its own abuse posture, and a coordinator who never sees an unreviewed one on a
public surface. **Recommendation: do not build this in the first pass.** It changes
the trust model of the whole intake path for a volume of flyers a coordinator could
photograph themselves.

## 5. Recognition options, if and when Stage 2 is authorized

Ordered by how little they commit the program to.

| Option | Sends a photo where | Notes |
|---|---|---|
| **On-device / in-browser OCR** (e.g. a WASM Tesseract in the coordinator's browser) | Nowhere — the image never leaves the device for recognition | Weakest accuracy on stylised flyer typography, which is exactly what flyers use. But it makes the vendor question *not exist*, and Stage 3's human is already correcting fields |
| **Self-hosted OCR in the worker** | Nowhere outside the deployment | Real dependency and image weight; needs F5 to be less deferred than it is |
| **A hosted OCR / vision API** | A third party | Best accuracy on flyer typography by a wide margin. Requires a vendor decision, a credential, a per-call cost, and an answer to "may this image go to a vendor" — which is OQ-SC-05 again, harder |

**Recommendation: build Stage 2 behind the provider seam this repository already
uses** — `build_semantic_topic_provider` and `build_paid_extraction_provider` both
ship a deterministic fixture, refuse a live client under every edition, and fail
closed when a credential appears in the environment. A flyer extractor built to
that pattern can be developed, tested and demonstrated with fixtures while the
vendor question stays open, and acquiring a live client stays a change that fails a
test citing the gate rather than passing as a diff.

## 6. What this research recommends

1. **Split the ask.** "Upload a flyer" (Stage 1) is a media-plane decision and
   should ship on Lisa's registration track. "Read the flyer" (Stage 2) is a
   separate track that depends on it.
2. **Answer OQ-SC-05 before writing any of it.** Storage location, read
   authorization, retention, and whether the image is kept after extraction.
3. **Answer OQ-SC-06 explicitly:** a photographed flyer is a *claim*, and the
   recommended answer is that it always requires a human. Recording that answer is
   what stops a later "just auto-publish the high-confidence ones" from looking
   reasonable.
4. **Do not put a flyer image on a student-visible surface** until OQ-SC-05 says
   what may be in one.
5. **Do not treat Instagram as the flyer source.** `../prep/campus-event-discovery-capability.md`
   §4a already ruled it out — automated collection is contrary to Meta's terms and
   image-first content makes it the least reliable evidence base for a date. A
   coordinator photographing a poster on a wall is a different act with a different
   posture, and it is the one this document is about.
