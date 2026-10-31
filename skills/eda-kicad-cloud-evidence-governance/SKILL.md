---
name: eda-kicad-cloud-evidence-governance
description: Governs electronics-design evidence from requirements through KiCad schematic/PCB edits made with Konnect, ERC/DRC, SPICE/ngspice simulation, BOM sourcing, Gerber/IPC-2581/ODB++ release, GitHub review and MCP/cloud connectors, using the bundled edagov toolkit and its gov_* MCP tools. Use when the user asks to review, check, release, sign off, trace or audit a KiCad design; run or interpret ERC/DRC or simulations; check a BOM, alternates or lifecycle; build a manufacturing package; set up Gitflow/GitHub review gates; govern connector actions; or produce an engineering evidence record or dashboard.
---

# EDA/KiCad Evidence Governance

Treat an electronic design as a controlled evidence set, not a board file. Konnect edits the design; edagov captures, reviews, explains and governs the evidence. Prefer explicit evidence over inference. Never claim an action happened unless it was authorized, performed and recorded.

## Locate the tools

Two MCP servers ship with this plugin:
- **konnect**: inspects and edits KiCad schematics, boards and libraries (228 tools in on-demand toolsets). In a governed design every design write runs only inside an approved change window.
- **edagov**: the `gov_*` evidence tools. Prefer them over the CLI; `gov_doctor` checks the setup.

Human decisions stay on the CLI and are run by the named person, never by you: gate approvals, reviews, sign-offs, exceptions, role grants, change-window approvals and connector approvals. The CLI is `edagov` on PATH or `<plugin-root>/governance/bin/edagov.py` (run with `python3`, or `py` on Windows); the plugin root is two directories above this skill's base directory. `gov_pending_human_actions` lists who must run which command.

Set `EDAGOV_ACTOR` to the person the work is done for (their email); otherwise git's `user.email` is used. Roles live in `.edagov/roles.json` and are deny-by-default. Never grant yourself reviewer or approver roles. If `kicad-cli`, `ngspice` or the Konnect binary is missing, follow the `eda-toolchain-setup` skill.

## Hard rules

1. **Authorization boundary.** Default to documentation-only. Execute `kicad-cli` or `ngspice` (`edagov run`, `export`, `spice run`) only after the user authorizes it for this task, and pass their reason in `--authorize "..."`. Otherwise ingest existing reports (`edagov ingest`).
2. **Design changes go through Konnect only.** Change schematics, boards, libraries and rules only with Konnect tools inside an approved change window (see "Edit the design through Konnect"). Never edit KiCad files with a shell, a text editor or another tool in a governed design: that bypasses the ledger. Never pass `--save-board`. Work on a branch and open a PR.
3. **Scoped claims only.** Write "ERC completed with these inputs…", never "the circuit works". Run `edagov lint-claims` on every summary, PR body or report before delivering it. See `references/quality-gates.md`.
4. **Keep states distinct.** Never collapse missing, not_checked, not_applicable, stale, partial, failed, blocked, approved and approved_with_exception. Never show an unavailable source as passing.
5. **Humans approve.** Automation reaches at most `ready_for_review`. Approvals come from `edagov approve` / `review` / `signoff` run as the named reviewer. Do not run them as yourself on someone's behalf.
6. **Secrets.** Never put tokens, keys or credential payloads in prompts, records, logs, files or artifacts. Record only logical secret names. Run `edagov scan-secrets` before publishing anything.
7. **Conflicts are preserved.** When sources disagree (exit code vs report, revisions across outputs, two spec versions), record the conflict and escalate. Do not pick a winner silently.

## Workflow

Follow these steps in order. Skip a step only by recording why it is not applicable.

### 1. Scope and claim boundary
State the intended outcome, audience, design identity (product, design, board, assembly, revision, variant), requested and prohibited actions, and whether the task is documentation-only. If no store exists, initialise one:
```
edagov init --product PRD-X --design DES-X --board PCB-X --revision B --variant default \
  --authority owner@example.com --standard "IPC-2221B (2012)" --grant owner@example.com=contributor ...
```
Ask for exact standard editions; "IPC compliant" or "EMC ready" is not a requirement.

### 2. Inventory sources and versions
`edagov inventory --project <kicad-folder> [--library-release "<tag/commit>"]` records every file hash, the sheet hierarchy, library tables, KiCad generator versions, Edge.Cuts closure, stackup presence and hidden power pins. Record source URLs, retrieval dates and tool versions for anything else consulted. Read `references/kicad-project-and-library.md`.

### 3. Build the design-level record
Record requirements, architecture blocks, decisions and assumptions with stable IDs:
`edagov record requirement|block|decision|assumption|evidence|library ...`. Every requirement needs a verification method and a measurable acceptance threshold. Read `references/evidence-schema.md`.

### Edit the design through Konnect

When the user asks for a design change in a governed design (one with `.edagov/`):
1. Inspect and plan first with Konnect's read and dry-run tools (dry runs are never blocked).
2. Request the smallest window that fits: `gov_window_request` with toolsets (e.g. `sch_wiring`), `tool:<name>` entries, optional file globs, a reason, the issue ID, hours and a call budget. Tell the user who must approve it and the exact command (`edagov konnect window approve WIN-…`, run by a design_reviewer or release_approver other than the requester).
3. After approval, make the edits with Konnect. A refusal whose error kind is `plan_blocked` with a governance reason means stop: report it, and never route around it with another tool or a direct file edit.
4. Close the window with `gov_window_close`, then read `gov_ledger` to report exactly which files changed.
5. Edits make earlier ERC/DRC/simulation evidence stale (its input hashes no longer match). Re-run the checks with `gov_run_check` and `gov_spice_run` so the gates have fresh evidence. Konnect's own `run_erc`/`run_drc`/audit results are captured automatically as unreviewed evidence (`konnect:<tool>` tags); they inform reviewers but do not satisfy gates on their own.
6. Re-evaluate with `gov_gates`. Read `references/konnect-integration.md`.

### 4. Apply the review gates in order
Gates: requirements → architecture → schematic_library → simulation → pcb → supply → release → change. Evaluate with `edagov gates`. Explain any gate with `edagov explain <gate>` (rule, inputs, timestamp, result, missing evidence, next action). Read `references/quality-gates.md`.

### 5. Capture tool-specific evidence
- **ERC/DRC:** `edagov run erc|drc --project … --authorize "…"` or `edagov ingest erc|drc report.json --project …`. Use JSON reports. DRC runs with schematic parity by default. The toolkit cross-checks the exit code (KiCad 10 documents 0 = none, 5 = violations) against the parsed report and records `conflict` on disagreement.
- **Simulation:** `edagov spice manifest deck.cir` first. Then `edagov spice run deck.cir --authorize …` or `ingest spice deck.cir --log …`. Keep failed runs. Retry with `--retry-of RUN-…` and justify any loosened tolerance with `--justification`. Attach `--validation` (data and acceptance criteria). Read `references/spice-validation.md`.
- **PCB integrity:** attach stackup, PI, SI, thermal and EMC evidence with `edagov record evidence --tag stackup|pi_analysis|si_analysis|thermal_analysis|emc_plan`. Mark a topic not applicable only through a policy override with a rationale. Read `references/pcb-integrity.md`.
- **BOM:** `edagov ingest bom bom.csv --project …`. Read `references/bom-sourcing.md`.
- **Manufacturing:** `edagov export gerbers|drill|pos|bom|ipc2581|odb … --authorize …` (KiCad 10 supports `--variant` on gerbers/ipc2581/odb/step), then `edagov manifest --outputs <dir>`. Record DFM/DFA findings with `edagov dfm add`, plotted-view review with `edagov dfm plotted-view`, and the four separate sign-offs with `edagov signoff`. Read `references/manufacturing-release.md`.

### 6. Control claims
Use the scoped wording in `references/quality-gates.md` §Claim language. Lint every outgoing text: `edagov lint-claims file.md`.

### 7. Govern connector actions
Before any MCP/cloud/GitHub write, register the connector (connector_admin), then `edagov connector propose --verb publish|purchase|release|delete|create|change …`. Show the printed proposal (exact inputs, revision, side effects, compensation) to the user. Execute only when `edagov connector check --id ACT-…` says ALLOWED. Then record the outcome with evidence via `edagov connector outcome`. Never infer success. Read `references/mcp-safe-connectors.md`.

### 8. Make execution reproducible
Executed runs automatically capture command, cwd, tool version, platform, locale/TZ, input hashes, logs, output hashes and an unsigned SLSA-v1 provenance statement. State the reproducibility level (default: exact rerun, never bit-for-bit for KiCad outputs). For cloud or CI execution read `references/cloud-reproducibility.md`.

### 9. Reconcile and report
Run `edagov gates --persist`, `edagov snapshot --out snapshots` (as a reviewer or auditor) and `edagov dashboard --out dashboard.html`. Reconcile requirements, artifacts, reports, BOM, outputs, GitHub references and approvals to one identity/revision/variant. Sync PRs read-only with `edagov ingest github owner/repo N`. Read `references/git-review-traceability.md` and `references/dashboard-review-ux.md`.

## Response contract

Every response produced under this skill contains, in this order (fill from the templates in `references/templates/`):
- **Scope**: what was requested and what was not done (state documentation-only vs executed).
- **Design identity**: product/design/board/assembly, revision, variant, release state.
- **Evidence index**: record IDs, hashes, tool versions, dates, links.
- **Findings**: concise scoped claims, with numbered citations `[n]` near external facts.
- **Open issues**: owner, severity, affected claim, due/trigger, next action.
- **Exceptions**: rationale, approver, review trigger, limitations.
- **Decision**: approved, approved_with_exception, blocked, rejected, not_checked, or not_applicable, per gate.
- **Caveats**: sign-off limits and unverified areas (`references/quality-gates.md` §Sign-off limits).

Documents end with a References section in `[n]: URL "Title"` form with stable numbering. Report absolute paths of files you create. When an operation is not authorized or cannot be verified, stop at the plan boundary and name the blocker.

## Before finishing, verify

1. `edagov scan-secrets` is clean on everything delivered.
2. No mutable tag is presented as an immutable reproducibility guarantee.
3. Every external fact has a nearby citation, and `edagov lint-claims` is clean.
4. Every KiCad, simulator, library, manufacturing, GitHub, MCP and cloud claim names its version.
5. Every pass/approval claim names inputs, policy, evidence, reviewer and limitations.
6. ERC/DRC and simulation are never described as functional or physical proof.
7. Alternates, lifecycle data and file formats are not treated as self-validating.
8. Consequential actions have explicit human approval and a compensation path.
9. Failure, stale, partial, unavailable, unauthorized and unknown states stay visible.
10. `gov_audit_verify` passes (audit chain and Konnect call ledger).

## Reference map

| Need | Read |
|---|---|
| Entities, IDs, states | `references/evidence-schema.md` |
| Gates, claim language, sign-off limits | `references/quality-gates.md` |
| KiCad project, ERC/DRC, libraries | `references/kicad-project-and-library.md` |
| SPICE dialects, convergence, validation | `references/spice-validation.md` |
| Stackup, SI/PI, thermal, EMC | `references/pcb-integrity.md` |
| Gerber/X2/Job, IPC-2581, ODB++, DFM | `references/manufacturing-release.md` |
| BOM, lifecycle, alternates, counterfeit control | `references/bom-sourcing.md` |
| Cloud runs, secrets, provenance | `references/cloud-reproducibility.md` |
| MCP/connector safety | `references/mcp-safe-connectors.md` |
| Gitflow, GitHub reviews, CI gates | `references/git-review-traceability.md` |
| Dashboard model and accessibility | `references/dashboard-review-ux.md` |
| Konnect integration: effects, windows, ledger, modes | `references/konnect-integration.md` |
| edagov command reference | `references/edagov-cli.md` |
| Response templates | `references/templates/` (design-record, evidence-index, release-manifest, issue-exception, simulation-run, review-decision) |
| Sources | `references/source-register.md` |
