# Review decision — gate {{gate}} for {{design_id}} rev {{revision}} ({{variant}})

| Field | Value |
|---|---|
| Decision | approved / approved_with_exception / rejected / requested_changes |
| Reviewer · role · identity verified? | |
| Date | |
| Evidence fingerprint at decision | {{sha256:…}} |
| Evidence reviewed | {{record IDs}} |
| Exceptions relied on | {{EXC-…}} |
| Unresolved issues | {{ISS-…}} |
| Applicable standards (editions) | |

## Explanation at decision time
```
{{output of: edagov explain <gate>}}
```

## Scope and limits
- Claim scope: {{…}}
- Not verified: {{…}}
- This approval is bound to the evidence above; if any of it changes the approval becomes stale and needs re-review.

Command: `edagov approve {{gate}} --decision approved --note "…"` (run as the reviewer)
