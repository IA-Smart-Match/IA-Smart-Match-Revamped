# Frontend agent instructions

Before changing anything under `apps/web`, read [`DESIGN.md`](DESIGN.md) completely and treat it as the authoritative frontend design and integration contract.

- Follow the CPP design tokens and component patterns already present in `legacy-frontend`.
- Verify backend wiring against `../../contracts/openapi/smartmatch.json`; never invent an endpoint or response shape from a mockup.
- Preserve authorization, principal/unit cache isolation, provenance, unknown values, and fixture disclosures.
- Do not add hard-coded identities, roles, production-looking records, statistics, or fake successful mutations.
- Run the relevant verification commands listed in `DESIGN.md` before reporting completion.

If an existing screen conflicts with `DESIGN.md`, improve it toward the standard rather than copying the exception. If `DESIGN.md` conflicts with the API contract about data or behavior, the API contract wins and the design document should be corrected in the same change.
