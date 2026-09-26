<role>Read-only CBA recon agent — R-ROLES.</role>
<mission>Report current repository behavior against `docs/product/cba-smart-match-customer-requirements.md` §§2–4 and §25 terminology/auth P0 items. Make no code or documentation changes.</mission>

<customer_mapping>
- §2: Student, Event Host, Speaker Connector, Speaker.
- §3: one standard login, backend-assigned roles, no portal or role picker.
- §4: CBA terminology throughout UI, documentation, fixtures, and seed/demo data where applicable.
- §25 P0: all terminology renames, removal of membership/dues references, one login, backend role assignment.
</customer_mapping>

<constraints>
- Read files only; cite repository path and current one-based line range for every claim.
- Map every finding to §25 P0/P1/P2 where applicable.
- Flag customer §20 scope conflicts.
- Recommend exactly one disposition per finding: preserve | gate | build new | defer OQ.
- Distinguish stable database role strings from customer-facing labels and permissions.
</constraints>

<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md
2. services/api/smartmatch_api/routers/auth.py
3. docs/decisions/pilot-login-decision-2026-09-04.md
4. services/api/smartmatch_api/routers/portals.py
5. python/smartmatch_authz/smartmatch_authz/policy.py
6. tools/seed_pilot_logins.py
7. apps/web/legacy-frontend/src/app/pages/LoginPage.tsx
8. apps/web/legacy-frontend/src/app/routes.tsx
9. apps/web/legacy-frontend/src/app/components/PortalGate.tsx
10. apps/web/legacy-frontend/src/app/hooks/usePortalAccess.tsx
11. apps/web/legacy-frontend/src/app/components/Layout.tsx
12. tests/unit/test_frontend_auth_contract.py
</read_first>

<output_sections>
1. File inventory (path | one-line role)
2. Current behavior (bullet per capability)
3. Gap table (requirement | today | gap severity P0/P1/P2 | disposition)
4. Tests to add or extend (exact paths)
5. Suggested branch and implementation fence
6. Gate recommendation for anything CBA must hide or refuse
</output_sections>
