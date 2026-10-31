# Issue / exception entry

## Issue {{ISS-…}}
| Field | Value |
|---|---|
| Title | |
| Severity | low / medium / high / critical |
| State | open / contained / accepted / closed / superseded |
| Owner | |
| Affected records | {{RUN-…, BOM-…}} |
| Gates | {{pcb, supply}} |
| Due / trigger | |
| Containment | |
| Disposition | |
| Closure evidence | {{record IDs / links}} |
| External ref | {{owner/repo#N}} |

Command: `edagov issue open "<title>" --severity high --owner <who> --affected <ID> --gate <gate> --due <date>`

## Exception {{EXC-…}}
| Field | Value |
|---|---|
| Title | |
| Rationale | |
| Affected claims (record IDs) | |
| Approver (named authority) · date | |
| Review trigger / expiry | |
| Limitations that remain | |

"Accepted" means a named authority accepted the stated risk. It does not mean the risk disappeared.
Command: `edagov exception "<title>" --rationale "…" --affects <ID> --review-trigger "<event/date>"`
