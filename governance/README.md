# governance/ — edagov

The evidence-governance half of Konnect-Evidence. Python 3.10+, standard library only.

- `src/edagov/` — evidence store, audit chain, KiCad/ngspice runners with provenance, BOM and manufacturing checks, gates, GitHub sync, connector governance, snapshots, dashboard, **`governance.py`** (Konnect change windows, authorize/record, call ledger) and **`mcp_server.py`** (`gov_*` MCP tools).
- `bin/` — launchers: `edagov`, `edagov-mcp` (POSIX); `edagov.py`, `edagov-mcp.py` (any OS); `.cmd` variants.
- `tests/` — `python -m pytest` (uses fake `kicad-cli`/`ngspice` in `tests/fakes`).
- `examples/buck-demo/` — a 12 V → 3.3 V design with reports, BOM, SPICE decks, X2 Gerbers; `build_demo.sh` walks the full workflow.
- `ci/design-repo/` — GitHub Actions gate workflow, PR template, CODEOWNERS and issue template to copy into a design repository.

How Konnect calls it: `../docs/EVIDENCE_GOVERNANCE.md`. Agent-facing guidance: `../skills/`.

edagov was first published by HWIT under the MIT license (`LICENSE-MIT-edagov`); inside this repository it is part of an AGPL-3.0 combined work (`../LICENSE`, `../FORK_NOTICE.md`).
