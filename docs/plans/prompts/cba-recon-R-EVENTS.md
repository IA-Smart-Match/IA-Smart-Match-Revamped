<role>Read-only CBA recon agent — R-EVENTS.</role>
<mission>Report current repository behavior against `docs/product/cba-smart-match-customer-requirements.md` §§12, 15, and §25 event/calendar items. Make no code or documentation changes.</mission>

<customer_mapping>
- §12: Event Host creates a physical or virtual Speaker Request with details, topic, location, and multi-select industries/roles.
- §15: students browse/register/add calendar/attend/rate; month calendar remains at the bottom of Events.
- §25 P0: Event Host event creation and the calendar placement requirement.
</customer_mapping>

<constraints>
- Read files only; cite repository path and current one-based line range for every claim.
- Map every finding to §25 P0/P1/P2 where applicable.
- Flag customer §20 external-discovery conflicts.
- Recommend exactly one disposition per finding: preserve | gate | build new | defer OQ.
- Do not propose a UI event-creation success state without a durable API command/write path.
- Treat the customer’s newer §15 placement as authoritative: preserve browse/agenda content and place the month calendar at the bottom of the Student Events page. Do not recommend replacing the page with a calendar-only view.
</constraints>

<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md
2. services/api/smartmatch_api/routers/events.py
3. db/migrations/versions/0017_event_persistence.py
4. python/smartmatch_domain/smartmatch_domain/ingest.py
5. apps/web/legacy-frontend/src/app/pages/Calendar.tsx
6. apps/web/legacy-frontend/src/app/pages/student/StudentEvents.tsx
7. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorEvents.tsx
8. python/smartmatch_domain/smartmatch_domain/calendar_invite.py
9. tests/unit/test_calendar_invite_wiring.py
10. tests/golden/test_calendar_invite_golden.py
11. docs/plans/frontend-broken-buttons.md
12. apps/web/legacy-frontend/src/app/pages/Opportunities.tsx
</read_first>

<output_sections>
1. File inventory (path | one-line role)
2. Current behavior (bullet per capability)
3. Gap table (requirement | today | gap severity P0/P1/P2 | disposition)
4. Tests to add or extend (exact paths)
5. Suggested branch and implementation fence
6. Gate recommendation for anything CBA must hide or refuse
</output_sections>
