# Evidence governance in Konnect-Evidence

This fork connects two systems:

- **Konnect** (Rust MCP server): reads and edits KiCad schematics, boards, libraries and rules; runs ERC/DRC, exports and audits.
- **edagov** (`governance/`, Python): the evidence store kept beside the design (`.edagov/`): requirements, runs with provenance, BOM and manufacturing records, gates, approvals, audit chain, snapshots and dashboard.

The design-level guide for agents is `skills/eda-kicad-cloud-evidence-governance/references/konnect-integration.md`. This page covers architecture and maintenance.

## Architecture

```
            ┌────────────── Claude (Cowork / Claude Code) ──────────────┐
            │  skills: konnect, kicad-*, eda-kicad-cloud-evidence-…,    │
            │          governed-design-editing, eda-review-dashboard,   │
            │          eda-toolchain-setup                              │
            └──────────────┬───────────────────────────┬────────────────┘
                 MCP stdio │                           │ MCP stdio
          ┌────────────────▼──────────────┐  ┌─────────▼─────────────────┐
          │ konnect (Rust)                │  │ edagov MCP (Python)       │
          │ dispatch_tool                 │  │ 35 gov_* tools            │
          │  ├ schema validation          │  │ (no approval tools)       │
          │  ├ governance::pre_call ──────┼──┼─► edagov konnect authorize│
          │  ├ handler (KiCad IPC / files)│  │                           │
          │  └ governance::post_call ─────┼──┼─► edagov konnect record   │
          └────────────────┬──────────────┘  └─────────┬─────────────────┘
                           │                           │
                     KiCad 10 (IPC, kicad-cli)    .edagov/ store in the design repo
                                                  (records, audit.jsonl, konnect/calls.jsonl,
                                                   runs/, policy.json, roles.json)
            Humans: edagov CLI for approvals, reviews, sign-offs, roles, window approvals
```

### Rust side (`crates/konnect-core/src/governance/`)

| File | Role | Dependencies |
|---|---|---|
| `effects.rs` | `TABLE` classifies all 228 registered tools; argument-dependent rules for apply-mode tools; `CAPTURE_EVIDENCE` list | std only |
| `bridge.rs` | `KONNECT_GOVERNANCE` modes, store discovery, edagov process runner (timeout, stdin, `.py` launcher), `key=value` decision protocol | std only |
| `mod.rs` | `pre_call` / `post_call` used by `mcp::handler::dispatch_tool`; refusals are `ToolErrorKind::PlanBlocked` with operation `governance:<tool>` | serde_json, tokio, tracing |

Tests: `effects.rs` and `bridge.rs` unit tests; `mod.rs` tests that every registered tool is classified and no stale entries exist, path collection, refusal kind, and that ungoverned reads proceed untouched.

Upstream behaviour is preserved: with no `.edagov/` store above a call's paths (and `KONNECT_GOVERNANCE_ROOT` unset) the default `auto` mode lets every call through without spawning anything, so upstream tests and ungoverned projects are unaffected. `KONNECT_GOVERNANCE=off` disables the hooks entirely.

### Python side (`governance/src/edagov/`)

| Module | Role |
|---|---|
| `governance.py` | change windows (request / approve / close), `authorize`, `record`, hash-chained call ledger, evidence capture |
| `mcp_server.py` | stdio MCP server, 35 `gov_*` tools; stdout protected from library prints |
| `gates.py` | gate checks now also fail when the input hashes of ERC/DRC runs, simulations or tagged evidence no longer match the files |
| others | the original edagov toolkit (store, audit, inventory, KiCad/ngspice runners, BOM, manifest, GitHub sync, connectors, snapshots, dashboard) |

## Maintenance rules

- **New upstream-style tool**: add it to `effects::TABLE`. `every_registered_tool_is_classified` fails until you do; unclassified tools are treated as design writes at runtime.
- **New check tool whose result is worth keeping**: add it to `effects::CAPTURE_EVIDENCE` and to `governance.capture_evidence_tools` in edagov's default policy (`governance/src/edagov/policy.py`).
- **Protocol between the two sides** is the `edagov konnect authorize|record --format kv` command line; keep it backward compatible (`decision=` is the only required key).
- Keep governance skills out of `crates/konnect/assets/`: the asset tests reject snake_case words that are not Konnect tools. They live in `skills/` and are bundled by `manifest.rs`.

## Verification status (2026-10-31)

| Item | Status |
|---|---|
| edagov + governance + MCP server | 51 Python tests (`cd governance && python -m pytest`), run in CI on Linux, macOS and Windows with Python 3.10 and 3.13; the POSIX demo walkthrough is skipped on Windows |
| `effects.rs`, `bridge.rs` | 11 unit tests pass and clippy (`-D warnings`) is clean, compiled with rustc outside the workspace |
| Rust bridge ↔ edagov | End-to-end harness: deny without window → allow inside approved window → changed files recorded → evidence captured → missing launcher is an error |
| `mod.rs` and the `handler.rs` hook | Type-checked against stand-in types only. The full workspace (`cargo check/test/clippy`) could not be built in the authoring environment (no crates.io access); it runs in `.github/workflows/ci.yml` on the first push |
| Real KiCad / ngspice execution | Not run here; `.github/workflows/governance-real-tools.yml` runs edagov against KiCad 10 and ngspice; upstream `e2e-kicad.yml` covers Konnect itself |
