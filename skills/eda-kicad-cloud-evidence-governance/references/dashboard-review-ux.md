# Review dashboard model and accessibility

`edagov dashboard --out dashboard.html` writes one static, self-contained HTML file from the evidence store. It answers one question: what design revision is under review, what evidence exists, what is blocked, who must act, and what remains unverified before release [1]. It is a decision and navigation surface, not a KiCad file inspector, and it never mutates anything.

## Screens

| Key | Screen | Content |
|---|---|---|
| A | Overview | identity, gate rail (linear, ordered), blocked gates, open high/critical issues, missing and stale evidence, next actions, legend |
| B | Requirements | coverage by verification method (table is the chart's text alternative), requirements, blocks, decisions/assumptions, **Trace** (highlights linked blocks, runs, issues, approvals) |
| C | Design evidence | ERC and inventory cards, simulation runs (failed attempts and retry chain), DRC card, PCB analysis evidence by topic |
| D | BOM & supply | blocking/warning counts, lines with lifecycle, evidence age, source, alternate state (unsupported claims shown as such), findings |
| E | Manufacturing release | package identity, release steps (manifest, plotted view, four sign-offs), consistency findings, manifest with hashes, DFM/DFA dispositions, limitations |
| F | Review | gate decisions with stale-approval notes, issues, exceptions, reviews, GitHub PRs (lane, sync, current-diff approvals, blocking checks, linked vs auto-closing issues), revision comparison |
| G | Connectors & audit | connector registry (protocol version, transport, scopes, trust, sync, last error with correlation ID), connector actions, audit events and hash-chain status |

Every screen header carries product, board, design, revision, variant, assembly, release state and generation time. A banner states the execution mode: documentation-only unless runs were executed, and which connectors are verified. Filters (search, owner, severity, freshness) persist across screens. Each status badge opens a detail drawer with state, severity, timestamp, owner, source, freshness, next action, claim scope, limitations, linked evidence and the full record. Gate badges open **Explain status**: the deterministic rule/inputs/result text from `edagov explain`.

Actions are non-mutating: the page shows the exact `edagov` command (with a Copy button) to record a decision, escalate or compare revisions. Acknowledging never changes technical state.

## Status language

- Tones: complete (✓), accepted with exception (◆, double border), needs action (●), attention (▲, dashed border), blocking (■, square corners), not started / not applicable (○, dotted border). Color is never the only cue: glyph, border style, shape and text label always accompany it [2].
- Missing, stale, not checked, not applicable, partial, failed, blocked, approved and approved-with-exception are always distinct.
- Badges and graphical state indicators use token colors chosen for at least 3:1 contrast against adjacent colors in both light and dark themes [3].

## Accessibility behaviour

- Tabs are a `role="tablist"` with arrow/Home/End keys; each screen is addressable by hash (`#overview`, `#requirements`, `#evidence`, `#bom`, `#release`, `#review`, `#admin`).
- Status changes (filters applied, trace set, drawer opened, command copied) are announced through a polite live region without moving focus [4].
- The drawer moves focus to its Close button, closes on Escape, and returns focus to the trigger.
- Every chart has a table equivalent; tables have captions and scoped headers; wide tables scroll inside their own container.
- Visible focus rings, `prefers-reduced-motion` respected, layout works at 400 px width.
- Progress/step indicators are used only for the linear gate sequence and the release sign-off sequence [5].

## Failure and uncertainty

Connector and GitHub records show `loading`, `empty`, `not_configured`, `stale`, `partial`, `unavailable`, `unauthorized`, `conflict`, `invalid`, `timeout`, `queued/retrying` or `dead_lettered` with source, timestamp, correlation ID and whether displayed status is provisional. An unavailable source is never shown as a pass.

## Publishing

For a Claude artifact use `edagov dashboard --fragment --out page.html` (no `<html>`/`<head>` wrapper) and publish that file. Run `edagov scan-secrets page.html` first. For review records prefer `edagov snapshot`, which embeds a dashboard together with the frozen manifest, filters, hashes and caveats.

## References

[1]: https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/ "Grafana Dashboard Best Practices"
[2]: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html "WCAG 2.2 Use of Color"
[3]: https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html "WCAG 2.2 Non-text Contrast"
[4]: https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html "WCAG 2.2 Status Messages"
[5]: https://designsystem.digital.gov/components/step-indicator/ "USWDS Step Indicator"
