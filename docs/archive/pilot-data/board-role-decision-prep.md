# `board_role` decision prep (Dr. Wang)

**Status:** holding position in `columns.yaml` — **no schema commitment**.  
**Classification:** human-decision-required (plan §5.5).

## Question

Is `board_role` intrinsic to a **professional**, or scoped to that person's
**relationship with one unit/chapter**?

## Evidence in repository

| Source | How `board_role` appears |
|---|---|
| `columns.yaml` | optional on `professionals` — holding position |
| `mockData.ts` `Specialist` | flat field on professional (orphaned frontend) |
| Worker `validate_columns` | not wired — `required=(), optional=()` |

Moving the field later is a **schema change**, not a rename.

## Sample export A — flat professional field

One row per person; role travels with the person across units.

```csv
name,metro_region,board_role,company
Jordan Lee,LA County,Board Member,Acme Robotics
```

Same person listed once; if they hold different roles at two chapters, the export
cannot express both without duplication or collision.

## Sample export B — unit-relationship record

Person appears once; roles are per `(person, unit)` with optional effective dates.

```csv
name,metro_region,company
Jordan Lee,LA County,Acme Robotics
```

```csv
professional_key,unit_path,board_role,effective_from,effective_to
jordan-lee,iawest.cpp,Board Member,2025-01-01,
jordan-lee,iawest.irvine,Advisory Council,2024-06-01,2025-12-31
```

## Schema shapes (draft — pick one after workshop)

### Flat (current holding position)

- Keep `board_role` in `professionals.optional` in `columns.yaml`.
- Wire worker validation when decision is recorded.

### Relationship-scoped

- Remove `board_role` from professional optional list.
- New table e.g. `professional_unit_relationship` with composite
  `(tenant_id, professional_id, unit_id)` + `board_role` + effective dates.
- Expand-phase migration + tenant-isolation tests.

## Workshop outputs

- [ ] Written choice: flat vs relationship.
- [ ] If relationship: multiplicity rules and effective-date semantics.
- [ ] Updated `columns.yaml`, fixtures, and (after wiring) worker args.
- [ ] Fixtures that reject the discarded interpretation.

## Do not build yet

- No migration choosing the relationship table.
- No worker `validate_columns` wiring until Dr. Wang answers (plan Wave C §2).

## References

- `docs/pilot-data/columns.yaml` (`open_questions` first item)
- `docs/pilot-data/README.md`
