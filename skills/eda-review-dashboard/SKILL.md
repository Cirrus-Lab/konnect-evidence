---
name: eda-review-dashboard
description: Renders, publishes and compares the read-only EDA engineering review dashboard and review snapshots from an edagov evidence store (gate status, requirements trace, ERC/DRC and simulation evidence, BOM risk, manufacturing release, reviews, GitHub sync, connectors and audit). Use when the user asks to see the design status, show the dashboard, export a review snapshot or evidence pack, compare two revisions, or share the review state with their team.
---

# EDA review dashboard and snapshots

The dashboard is a decision and navigation surface. It shows what revision is under review, what evidence exists, what is blocked, who must act and what is unverified. It never mutates anything and never claims live data.

Use the `gov_*` tools of the edagov MCP server (`gov_gates`, `gov_explain`, `gov_dashboard`, `gov_snapshot`). The CLI equivalent is `edagov` on PATH or `<plugin-root>/governance/bin/edagov.py` (the plugin root is two directories above this skill's base directory). Set `EDAGOV_ROOT` to the design repository.

## Show current status

1. `gov_gates` for the gate states; `gov_explain` for one gate's rule, inputs and next action.
2. `gov_dashboard` (or `edagov dashboard --out dashboard.html`) writes a standalone page. To publish it as a Claude artifact, render with `--fragment` (no `<html>`/`<head>` wrapper), run `edagov scan-secrets` on the file, then publish that file. Describe what the page shows in one sentence; do not restate every gate.
3. Point out the top blocking reasons and next actions from the Overview, with record IDs.

## Export a review snapshot

Run as a reviewer, release approver or auditor (viewers cannot export):
```
edagov snapshot --out snapshots [--revision B] [--owner …] [--severity blocking] [--type run --type bom_line]
```
The zip contains `manifest.json` (identity, filters, every record ID/version/hash, gate explanations, audit-chain verification, redactions, caveats), the records (secret-shaped content redacted) and an embedded `dashboard.html`. Deliver the zip as a file and say which filters were applied.

## Compare revisions

Take a snapshot at each revision (or before/after a change), then:
```
edagov diff snapshots/<A>.zip snapshots/<B>.zip --dashboard compare.html
```
Report added, removed, changed and superseded records, gate state changes and unresolved issues. Do not open raw KiCad files to infer differences.

## Rules

- Keep the banner's execution-mode statement intact: "documentation-only" unless runs were executed, and only connectors marked verified count as live.
- Never edit the generated HTML to change a state. Fix the evidence, re-evaluate, and re-render.
- If the audit chain or the Konnect call ledger fails verification (`gov_audit_verify`), say so first; the dashboard shows the audit state on the banner and on screen G.
- Accessibility behaviour (non-color status cues, keyboard tabs, live announcements, table alternatives) is described in `../eda-kicad-cloud-evidence-governance/references/dashboard-review-ux.md`.
