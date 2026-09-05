<role>Read-only CBA recon agent — R-OUTREACH.</role>
<mission>Report current repository behavior against `docs/product/cba-smart-match-customer-requirements.md` §§6, 13, and §25 P1 invitation/response workflow. Make no code or documentation changes.</mission>

<customer_mapping>
- §6: Connector reviews 2–3 candidates, sends/batch-sends invitations, tracks responses, and returns a confirmation to the Event Host.
- §13: Connector maintains contacts, matches, reviews Topic reasoning, invites, tracks, and manages weights/ratings.
- §25 P1: batch invitations, response tracking, and confirmed-speaker handoff.
</customer_mapping>

<constraints>
- Read files only; cite repository path and current one-based line range for every claim.
- Map every finding to §25 P0/P1/P2 where applicable.
- Flag customer §20 cold-outreach and external-discovery conflicts.
- Recommend exactly one disposition per finding: preserve | gate | build new | defer OQ.
- Contrast the consented `/v1` path with legacy UI paths; never merge their trust models.
</constraints>

<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md
2. services/api/smartmatch_api/routers/outreach.py
3. services/worker/smartmatch_worker/outreach.py
4. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorOutreach.tsx
5. python/smartmatch_domain/smartmatch_domain/calendar_invite.py
6. .cursor/skills/opus-goal-prompting/goal-catalog-post-merge.md (G7–G10)
7. apps/web/legacy-frontend/src/app/pages/Outreach.tsx
</read_first>

<output_sections>
1. File inventory (path | one-line role)
2. Current behavior (bullet per capability)
3. Gap table (requirement | today | gap severity P0/P1/P2 | disposition)
4. Tests to add or extend (exact paths)
5. Suggested branch and implementation fence
6. Gate recommendation for anything CBA must hide or refuse
</output_sections>
