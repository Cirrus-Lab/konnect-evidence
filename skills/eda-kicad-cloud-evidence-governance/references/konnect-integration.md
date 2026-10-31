# Konnect integration

How the Konnect MCP server and the edagov evidence store work together in this fork. Implementation: `crates/konnect-core/src/governance/` (Rust) and `governance/src/edagov/governance.py` (Python).

## Call flow

```
Claude ──tools/call──► Konnect dispatch
                        │ 1. schema validation (upstream)
                        │ 2. governance::pre_call   ── classify effect
                        │      design_write in a governed design?
                        │        └─► edagov konnect authorize ── allow / deny (+ pre-hashes, ledger, audit)
                        │ 3. tool handler (only on allow)
                        │ 4. governance::post_call  ── edagov konnect record
                        │                               (post-hashes, changed files, evidence capture, audit)
                        ▼
                      result (or a plan_blocked refusal naming the reason and next action)
```

A design is **governed** when `.edagov/design.json` exists at or above a path argument of the call, or at `KONNECT_GOVERNANCE_ROOT`. Live-IPC tools that take no path (for example moving a footprint on the open board) are governed only through `KONNECT_GOVERNANCE_ROOT`; the plugin's MCP configuration should set it to the design repository.

## Effects

Every one of Konnect's 228 tools is classified in `effects.rs`; a test fails if a registered tool is missing, and an unknown tool is treated as a design write.

| Effect | Examples | Governance |
|---|---|---|
| read | list/get/query/search tools, `run_erc`, `run_drc`, audits, `score_placement` | none; check results are captured as unreviewed evidence |
| plan | `plan_specctra_ses_import`, dry runs of apply-mode tools | none |
| ui | `launch_kicad_ui`, `open_schematic_viewer`, editor selection | none |
| output | exports, renders, netlists, `snapshot_project`, `route_specctra_dsn` | allowed for permitted actors; recorded with output hashes |
| config_write | `save_user_config`, `save_project_config`, `add_design_rule` | allowed for permitted actors; recorded |
| external | `download_jlcpcb_database`, `get_datasheet_url` | allowed for permitted actors; recorded |
| design_write | schematic, board, project, library, rules and netclass mutations, `apply_template`, `enrich_datasheets` | requires an approved change window; recorded with before/after hashes |

Apply-mode tools are classified from their arguments, matching each handler's own default: `update_pcb_from_schematic`, `update_footprints_from_library`, `repair_corrupted_footprints`, `place_decoupling_caps`, `auto_place_from_schematic`, `refine_placement_force_directed` plan unless `dry_run` is false; `fix_connectivity`, `delete_graphics`, `rename_project` write unless `dry_run` is true; `plan_bga_fanout` writes only with `apply: true`; `set_placed_footprint_models` reads only in `mode: "inspect"`.

## Change windows

| Step | Who | How |
|---|---|---|
| Request | contributor (the agent, acting for the user) | `gov_window_request` / `edagov konnect window request --scope sch_wiring --scope tool:add_power_symbol --files 'hw/kicad/*.kicad_sch' --reason "…" --issue ISS-12 --hours 4 --max-calls 200` |
| Approve or reject | design_reviewer or release_approver, not the requester (policy `governance.window_approver_roles`, `allow_self_approved_windows`) | `edagov konnect window approve WIN-… [--decision rejected] --note "…"` |
| Use | Konnect | each design write must match: approved, unexpired, same design revision, scope covers the toolset or `tool:<name>` (or `*`), call budget left, every target path inside the repo and matching the file globs |
| Close | requester or approver | `gov_window_close` / `edagov konnect window close WIN-…` |

Other refusals: the actor has no role permitting changes; the target file is outside the governed repository; the revision is `released` (move to a new revision first). Limits come from `.edagov/policy.json` → `governance` (`max_window_hours`, `max_window_calls`).

## Records

- **Call ledger** `.edagov/konnect/calls.jsonl`: hash-chained entries for every authorization (allow, deny, would-deny in audit mode) and completion: tool, toolset, effect, window, actor, revision, paths, pre/post hashes, changed files, captured evidence. Each entry's hash is also stored in the main audit chain. Verify with `gov_audit_verify` or `edagov konnect ledger --verify`.
- **Captured evidence**: successful results of the check tools listed in policy `governance.capture_evidence_tools` (ERC, DRC, design-review audits, validation and connectivity checks) become `artifact` records tagged `konnect:<tool>`, unreviewed, with a claim scope that says they are automated results.
- **Staleness**: gates compare the input hashes stored with ERC/DRC runs, simulations and tagged evidence against the current files. After a Konnect edit those checks fail with "design files changed since this run" until re-run.

## Modes and environment

| Variable | Meaning |
|---|---|
| `KONNECT_GOVERNANCE` | `auto` (default): govern designs that have a store; `enforce`: also refuse design writes no store covers; `audit`: never refuse, record would-deny decisions; `off`: upstream behaviour |
| `KONNECT_GOVERNANCE_ROOT` | design repository to govern when a call has no path argument |
| `KONNECT_EDAGOV` | edagov launcher; a `.py` path runs through `KONNECT_PYTHON` (default `py` on Windows, `python3` elsewhere) |
| `KONNECT_EDAGOV_ARGS` | extra leading arguments for the launcher |
| `EDAGOV_ACTOR` | identity recorded for calls (else git `user.email`); recorded as unverified unless a verified integration sets `EDAGOV_ACTOR_VERIFIED_BY` |

Fail-closed rule (same contract as Konnect's own gates: a check that did not run is never a pass): in `auto` and `enforce`, a governed design write is refused if edagov cannot be started, times out (60 s), exits non-zero or returns no decision. Recording failures after a call are logged as warnings and do not undo the call.
