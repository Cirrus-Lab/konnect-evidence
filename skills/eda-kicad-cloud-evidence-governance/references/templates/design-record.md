# Design record — {{product_id}} / {{design_id}} rev {{revision}} ({{variant}})

> Descriptive template. Fill from `edagov status`, `edagov gates` and the store. Keep record IDs exact.

## Scope
- Requested: {{what the user asked for}}
- Done: {{documentation-only | executed runs RUN-…}}
- Not done / prohibited: {{…}}
- Claim boundary: {{what this record does not infer}}

## Design identity
| Field | Value |
|---|---|
| Product | {{product_id}} |
| Design / board / assembly | {{design_id}} / {{board_id}} / {{assembly_id}} |
| Revision · variant | {{revision}} · {{variant}} |
| Release state | {{release_state}} |
| Design authority | {{design_authority}} |
| Repository · commit | {{repository}} · {{source_revision}} |
| Applicable standards (exact editions) | {{…}} |

## Requirements and architecture
| REQ | Text | Method | Acceptance | Allocated to | Status | Evidence |
|---|---|---|---|---|---|---|
| {{REQ-…}} | | | | {{BLK-…}} | | {{RUN-/ART-…}} |

Decisions: {{ADR-… title — rationale — alternatives — consequences}}
Assumptions: {{ASM-… — owner — review condition}}

## Gate status
| Gate | State | Automation | Approval | Next action |
|---|---|---|---|---|
| requirements … change | | | {{APR-… or —}} | |

## Open issues and exceptions
See `issue-exception.md` entries: {{ISS-…, EXC-…}}

## Decision
{{approved | approved_with_exception | blocked | rejected | not_checked | not_applicable}} — per gate above.

## Caveats
{{Sign-off limits from quality-gates.md, plus unverified areas specific to this design.}}

## References
[1]: {{URL}} "{{Title}}"
