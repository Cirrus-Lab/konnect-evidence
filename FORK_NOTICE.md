# Fork notice

**Konnect-Evidence** is a modified version of Konnect.

- Upstream: https://github.com/mixelpixx/Konnect, commit `c7e87cd8a7d440bfd6912025bc4370c7ebc00a00` (2026-10-24).
- Upstream license: GNU Affero General Public License v3.0 only (`LICENSE`). This fork is distributed under the same license.
- Modified by HWIT, starting 2026-10-31.

## Upstream status

The upstream README announces that the repository is archived at the end of 2026-10-25 and that development continues as Konnect-EDA, a commercial, closed-source product. Releases already published remain available under the AGPL-3.0. Consequences for this fork:

- Fixes and features from Konnect-EDA will not flow into this fork; it is maintained independently.
- The AGPL-3.0 terms still apply to everything derived from Konnect here. Konnect's dual-licensing (COMMERCIAL.md) was offered by the upstream copyright holders; it does not grant rights to this fork's modifications.

## What changed (AGPL §5(a) notice)

Added:
- `crates/konnect-core/src/governance/` (effect classification of every tool, edagov bridge, dispatch hooks) — 2026-10-31.
- `governance/` — the edagov evidence-governance toolkit, MCP server, tests, example design and CI templates. edagov was first written by HWIT under the MIT license (`governance/LICENSE-MIT-edagov`); as part of this combined work it is conveyed under the AGPL-3.0.
- `skills/` (four governance skills), `.claude-plugin/`, `.mcp.json`, `docs/EVIDENCE_GOVERNANCE.md`, this notice — 2026-10-31.

Modified:
- `crates/konnect-core/src/lib.rs` — declares the `governance` module.
- `crates/konnect-core/src/mcp/handler.rs` — `dispatch_tool` calls `governance::pre_call` before a domain tool handler and `governance::post_call` after it.
- `crates/konnect/src/manifest.rs` — `konnect init` also installs the four governance skills.
- `crates/konnect/assets/skills/konnect/SKILL.md` — "Evidence Governance" section.
- `README.md` — fork section at the top.
- `.github/workflows/ci.yml` — governance (Python) test job.

## AGPL obligations in practice

- If you distribute binaries of this fork, provide the corresponding source (this repository at the matching commit).
- If you let others use a modified version over a network (for example a hosted MCP endpoint), offer them the source of that version (AGPL §13).
- Keep this notice and `LICENSE` with the code.

This notice is a summary, not legal advice; read `LICENSE` for the terms.
