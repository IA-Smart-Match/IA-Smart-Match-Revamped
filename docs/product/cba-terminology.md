# CBA terminology sweep — what changed, and what deliberately did not

**Status:** Implemented (Wave 1, `CBA-TERMINOLOGY`)
**Enforced by:** [`tools/scan_cba_terminology.py`](../../tools/scan_cba_terminology.py),
[`tests/unit/test_cba_terminology_strings.py`](../../tests/unit/test_cba_terminology_strings.py)
**Customer source:** [`cba-smart-match-customer-requirements.md`](cba-smart-match-customer-requirements.md) §4, §25 (P0)
**Depends on:** [`cba-capability-policy.md`](cba-capability-policy.md) (Wave 0)

The customer replaced an institutional vocabulary. This document records the
replacement and — more importantly — the places the old words were left
standing on purpose, because an exclusion nobody wrote down looks identical to
an omission.

## The renames

| Old term | New term | Where it was applied |
|---|---|---|
| IA West / IA West Chapter | **CBA** | admin shell header, landing and login brand copy, coordinator surfaces, QR card, outreach templates and panel, campus heatmap |
| Insights Association | **CBA** | outreach email templates |
| Chapter (institution) | **CBA** | campus heatmap, outreach templates, outreach voice copy |
| Event Coordinator Portal | **Connector Dashboard** | `CoordinatorPortalLayout.tsx` |
| Member Portal | **Student Portal** | already correct in `StudentLayout.tsx`; now guarded |
| Volunteer opportunity / Opportunities (page) | **Speaker Requests** | admin nav item, `Opportunities.tsx` heading, `opportunities` metric `display_name` |
| Chapter membership / dues wording | **removed** | outreach template body |

**Speaker stays Speaker** (§4 maps it to itself). The sweep replaced
"IA West volunteer" with "CBA speaker" and "IA West Volunteers" with "CBA
Speakers" rather than erasing the word.

## Label and identifier are allowed to disagree

The Speaker Requests page reads its number from the registered metric
`opportunities` and says so on screen, next to the renamed heading. The
`canonical_name` and `owning_query` are untouched: they are the binding that
makes the number traceable to the query that owns it (ADR-0011 rules 3–4). Only
`display_name`, which exists to be read by a person, changed.

The same rule governs everything below.

## Intentional exclusions

### Backend authorization `membership`

Untouched: `membership` / `memberships` / `MembershipResponse`, the
`org_unit_path` ltree, `tenant-iawest` and `iawest.*` unit paths in the
authorization fixtures. The capability policy already states the distinction —
`chapter_membership_dues` is a **product concept**, "never the backend
`membership` record". Renaming an authorization table is authorized by nothing,
and would be a schema change hiding inside a copy change.

The scanner's `membership-dues` rule therefore matches only `dues` and
*chapter* membership. Plain `membership` is never a violation.

### The `ia_west_legacy` product scope and `ia_west_chapter` outreach voice

Both are wire values in a server contract. The first exists **because** CBA is
the other product: deleting the name would delete the distinction the Wave 0
policy is built on. `apps/web/legacy-frontend/src/lib/productScope.ts` is
allowlisted in full for this reason, and `lib/api.ts` is allowlisted for the
`ia-west` rule alone.

### The Member Inquiry / membership-interest narrative

`Dashboard.tsx`, `Pipeline.tsx`, `Volunteers.tsx`, `lib/metrics.ts`,
`FeedbackForm.tsx` and the `pipeline_member_inquiry` metric still say
"Member Inquiry" and "Membership interest".

This is not an oversight and it is not a rename that was missed. CBA does not
*rename* this concept — the capability policy switches it **off**
(`member_inquiry_narrative`, `chapter_membership_dues`), and removing the
surfaces belongs to `CBA-SCOPE-COMPOSITION`. Renaming a gated concept would
disguise a removal as a rename: the stage would keep appearing under a friendly
new name, which is worse for the customer than the old word is. The stored
stage, its migration, and every row already written stay exactly as they are.

### Role labels

`volunteer` and `coordinator` — as stored role strings and as the visible
persona names derived from them — are `CBA-ROLE-PRESENTATION`'s decision
(§4 maps Volunteer → Event Host for the event-requesting role, and Chapter
Admin → Speaker Connector). A copy sweep that also renamed roles would be
changing authorization presentation under cover of a vocabulary change, so this
lane changed only the *surface* name "Connector Dashboard" and left every role
label alone.

### History

Decision records, status reports, plans, and the legacy-baseline citations that
name `Nebiux-Team-IA-West-SmartMatch@bdce024` are outside the scanner's scope.
History is not copy; rewriting it would destroy the provenance the audit trail
depends on.

### Developer-facing API metadata

The FastAPI application description in `services/api/smartmatch_api/main.py`
(mirrored into `contracts/openapi/smartmatch.json`) still reads "IA West
SmartMatch platform API". It is developer-facing, and changing it regenerates a
serialized contract shared with other in-flight lanes. Recorded here rather
than swept.

## Deferred (P2)

* **CPP green/gold branding.** §4 says replace the purple theme "only if quick;
  otherwise defer", and §25 lists it under P2. No theme change was made.
* **Ambiguous institutional wording** — "Board volunteer", "Specialist roster",
  "Event Coordinator" as a job title in body copy. These are neither clearly in
  the §4 table nor clearly out of it; recorded, not redesigned.
* **Rewards wording.** §4 says keep rewards and points. Nothing was hidden or
  reframed.
