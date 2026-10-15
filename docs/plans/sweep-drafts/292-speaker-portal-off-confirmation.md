> DRAFT — needs Danny decision. Nothing here is decided.

# #292 — SPEAKER_PORTAL off: dated confirmation row

## Verified on this tree (origin/main 122b01b0, checked 2026-10-09)
`Capability.SPEAKER_PORTAL` is `False` in all three scopes in `python/smartmatch_domain/smartmatch_domain/product_scope.py`:

| Scope | Line | Value |
|---|---|---|
| `ProductScope.CBA` (block starts `:270`) | `:292` | False |
| `ProductScope.LEGACY_PILOT` (`:295`) | `:321` | False |
| `ProductScope.CLASS_EXERCISE` (`:341`) | `:357` | False |

Line numbers differ from the issue (284/313/349): all moved +8. Enum member is at `:253`. An import-time assert (`:377-382`) also refuses SPEAKER_PORTAL=True unless `SPEAKER_PORTAL_REQUIRES` capabilities are on in the same scope.

## Context
- Ann 2026-09-15: speaker accounts are "phase two ... I will bring it to Pia and Lisa" (`docs/decisions/stakeholder-correspondence-2026-09.md`, email B). No Pia/Lisa answer recorded.
- Owner decision #2 in that file: "Confirm SPEAKER_PORTAL stays off, and no real Speaker is invited, until Pia and Lisa answer."
- Open gate 3 today: `docs/decisions/INDEX.md:66` "SPEAKER_PORTAL turn-on — T6b-1 C5 rule, pending stakeholder rows".
- Backlog row: `docs/plans/backlog.md:11` (first row).
- This verifies the code flag only. It does not verify that no Speaker was invited; that needs a DB check (not done).

## Proposed row text (for Danny to place; I did NOT edit INDEX.md or backlog.md)
For `docs/decisions/INDEX.md` open gate 3, replace line 66 with:
> 3. SPEAKER_PORTAL turn-on — T6b-1 C5 rule, pending stakeholder rows (Ann/Pia/Lisa). Code flag verified off 2026-10-09: `Capability.SPEAKER_PORTAL` is False in CBA, LEGACY_PILOT and CLASS_EXERCISE (`product_scope.py:292/321/357`). Owner confirmation: <TBD — Danny confirms keep-off and no real Speaker invited>.

For `docs/plans/backlog.md` speaker row, append to Notes:
> 2026-10-09: flag verified False in all three scopes; stays off until Pia and Lisa answer. <TBD — Danny confirms>.

## Open questions
1. Confirm the flag stays off and no real Speaker is invited until Pia/Lisa answer? — Danny.
2. Has any real Speaker been invited on any deployed database? (code check cannot tell) — Danny / ops.
3. Is the dated row wanted in INDEX.md only, backlog only, or both? — Danny.
