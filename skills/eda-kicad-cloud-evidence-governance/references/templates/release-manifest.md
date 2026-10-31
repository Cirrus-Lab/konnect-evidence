# Release manifest — {{board_id}} rev {{revision}} ({{variant}})

Package: {{MFG-…}} · built {{timestamp}} · completeness: {{complete | incomplete | conflict}}
Origin / coordinate convention: {{…}} · Units: {{mm}} · Supplier assumptions: {{…}}

| File | Kind | Format | FileFunction | Units | Declared rev | SHA-256 |
|---|---|---|---|---|---|---|
| {{name}} | gerber | Gerber X2 46 | Copper,L1,Top | mm | B | {{sha256:…}} |

## Consistency findings
| Severity | Finding | Next action |
|---|---|---|

## DFM / DFA
| ID | Rule | Finding | Disposition | Rationale · approver |
|---|---|---|---|---|

Rule set / tool / version: {{…}} · Fabricator capability reference: {{…}}

## Sign-offs (separate roles)
| Role | State | Actor | Date | Note |
|---|---|---|---|---|
| design_owner | | | | |
| fabrication_dfm | | | | |
| assembly_dfa | | | | |
| release_control | | | | |
Plotted-view review: {{state, reviewer, date}}

## Limitations
- Gerber plus drill carries image and hole data, not complete stackup, material or design intent.
- This manifest does not prove manufacturability, solderability or assembly quality.
