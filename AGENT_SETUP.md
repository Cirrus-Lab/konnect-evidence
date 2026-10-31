# Agent setup and operating guide: Konnect-Evidence

Instructions for an AI agent (Claude in Cowork, Claude Code, or a similar agent with a shell) to clone this repository, install it, verify it, and use it on a KiCad design. Follow the steps in order. Commands are given for Windows (PowerShell) and Linux/macOS (bash).

Repository: `https://github.com/Cirrus-Lab/konnect-evidence` (private: the user's GitHub credentials are needed to clone).

---

## 0. What you are installing, and the rules that come with it

Konnect-Evidence is two MCP servers plus skills:

| Part | What it does | Where |
|---|---|---|
| `konnect` MCP server (Rust) | 228 KiCad tools: read, edit and route schematics and boards, run ERC/DRC, export manufacturing files | `crates/` |
| Governance hook inside `konnect` | Classifies every tool call; in a governed design, a design-changing call runs only inside a change window that a person approved | `crates/konnect-core/src/governance/` |
| `edagov` MCP server (Python) | 35 `gov_*` tools: evidence store, inventory, ERC/DRC/ngspice runs with provenance, BOM and manufacturing checks, gates, change-window requests, snapshots, dashboard | `governance/` |
| Skills | How to work: `eda-kicad-cloud-evidence-governance`, `governed-design-editing`, `eda-review-dashboard`, `eda-toolchain-setup`, plus Konnect's own KiCad skills | `skills/`, `crates/konnect/assets/skills/` |

Rules you must follow from the start:

1. **Ask before installing software or changing the user's machine.** Say what you will install and from where; wait for a yes unless the user already asked.
2. **Never approve anything yourself.** Approving gates, change windows, reviews, sign-offs, exceptions, connector actions and role grants is done by the named person on the command line. You may show them the exact command.
3. **Never edit KiCad files directly** (`.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `.kicad_sym`, `.kicad_mod`, library tables) with a shell, text editor or script. Changes go through Konnect tools only.
4. **Never turn governance off to get past a refusal** (`KONNECT_GOVERNANCE=off`) unless the user explicitly tells you to, and then say what that disables.
5. **Never put tokens, passwords or keys** in files, commits, records, prompts or logs.
6. **Report results as scoped evidence.** "ERC completed with these inputs: 0 active violations" is fine; "the board is correct / compliant / manufacturable" is not.

---

## 1. Check prerequisites

Run these and note what is missing.

```powershell
# Windows (PowerShell)
git --version
py --version            # or: python --version  (needs 3.10+)
kicad-cli version       # KiCad 10; default path below if not on PATH
ngspice -v              # optional, for simulation
cargo --version         # only if building konnect from source
protoc --version        # only if building from source
cmake --version         # only if building from source
```

```bash
# Linux / macOS
git --version
python3 --version       # needs 3.10+
kicad-cli version       # macOS: /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
ngspice -v
cargo --version; protoc --version; cmake --version
```

| Requirement | Needed for | Install (ask the user first) |
|---|---|---|
| Git | cloning | Windows: `winget install --id Git.Git -e` · macOS: `xcode-select --install` · Linux: `sudo apt install git` |
| Python 3.10+ | edagov (both servers use it) | Windows: `winget install --id Python.Python.3.12 -e` (provides `py`) · macOS: `brew install python` · Linux: `sudo apt install python3` |
| KiCad 10 | `kicad-cli` (ERC/DRC/exports) and the IPC API (live board tools) | Windows: `winget install --id KiCad.KiCad -e` · macOS: `brew install --cask kicad` · Ubuntu: `sudo add-apt-repository --yes ppa:kicad/kicad-10.0-releases && sudo apt update && sudo apt install --install-recommends kicad` |
| ngspice | simulation runs (optional) | Windows: zip from ngspice.sourceforge.io, set `NGSPICE` to `...\Spice64\bin\ngspice_con.exe` · macOS: `brew install ngspice` · Linux: `sudo apt install ngspice` |
| Rust (rustup) | building `konnect` | `https://rustup.rs`; the repo pins Rust 1.96.0 in `rust-toolchain.toml` and rustup fetches it |
| protoc 3.23+ and CMake | building `konnect` | Windows: `choco install protoc cmake` · macOS: `brew install protobuf cmake` · Ubuntu: `sudo apt install protobuf-compiler libprotobuf-dev cmake` |
| C/C++ compiler | building `konnect` (the NNG library) | Windows: Visual Studio Build Tools with "Desktop development with C++" · macOS: Xcode command-line tools · Linux: `sudo apt install build-essential` |

KiCad: enable **Preferences → Plugins → Enable IPC API** for live board tools.

---

## 2. Clone

The repository is private. Make sure the user is logged in to GitHub on this machine (GitHub CLI `gh auth login`, or Git Credential Manager prompts on first clone). Do not ask the user to paste a token into the chat.

```powershell
# Windows
cd $HOME\CODES          # or another folder the user chooses
git clone https://github.com/Cirrus-Lab/konnect-evidence.git
cd konnect-evidence
```

```bash
# Linux / macOS
cd ~/code && git clone https://github.com/Cirrus-Lab/konnect-evidence.git && cd konnect-evidence
```

Record the commit you cloned: `git rev-parse HEAD`. Everything you report later should name it.

---

## 3. Verify the governance toolkit (no KiCad needed)

```powershell
# Windows
py governance\bin\edagov.py --version
py governance\bin\edagov.py doctor
py -m pip install pytest          # optional, only to run the tests
cd governance; py -m pytest -q; cd ..
```

```bash
# Linux / macOS
python3 governance/bin/edagov.py --version
python3 governance/bin/edagov.py doctor
cd governance && python3 -m pytest -q && cd ..        # needs: pip install pytest
sh governance/examples/buck-demo/build_demo.sh /tmp/edagov-demo   # full documentation-only walkthrough
```

Expected: `edagov 0.1.0`, a doctor report (KiCad and ngspice may show `null` if not installed), and all tests passing (49 at the time of writing). The demo ends with `Audit chain verified.` and writes `/tmp/edagov-demo/dashboard.html`.

The pytest suite and `build_demo.sh` use POSIX shell launchers; on Windows, the `edagov.py` commands above are the supported path (CI runs a Windows smoke test of the change-window protocol).

---

## 4. Get the `konnect` binary

**Important:** binaries from the original Konnect project's releases do **not** contain the governance hook. Use a binary built from this repository.

### Option A: build from source (default)

```powershell
# Windows (Developer PowerShell, so the MSVC compiler is on PATH)
cargo build --release -p konnect
.\target\release\konnect.exe --version
```

```bash
# Linux / macOS
cargo build --release -p konnect
./target/release/konnect --version
```

The first build downloads crates and takes several minutes. If protoc's well-known types are not found, set `PROTOC` to the protoc binary and, for Chocolatey/scoop installs, `PROTOC_INCLUDE` to its `include` folder (see `DEV.md` → Build Requirements).

Put the binary on PATH, or note its full path for step 5:
- Windows: copy `target\release\konnect.exe` to a folder on PATH (for example `%USERPROFILE%\.local\bin`) or use the full path.
- Linux/macOS: `install -m 755 target/release/konnect ~/.local/bin/konnect`.

### Option B: the fork's own release

Only if the repository's Releases page has a release built from this fork (tag on this repo, produced by `.github/workflows/release.yml`). Check the release notes name a commit of this repository.

### Verify governance is in the binary

After the MCP server is connected (step 5), call Konnect's always-visible `get_installation_info` tool and confirm the build commit is a commit of this repository, not upstream `c7e87cd` or earlier.

---

## 5. Connect the MCP servers

### Option A: as a Claude plugin (Claude Code or Cowork)

```
/plugin install konnect-evidence --marketplace Cirrus-Lab/konnect-evidence
```

The plugin's `.mcp.json` starts:
- `konnect` (expects `konnect` on PATH) with `KONNECT_GOVERNANCE=auto` and `KONNECT_EDAGOV=${CLAUDE_PLUGIN_ROOT}/governance/bin/edagov.py`;
- `edagov` with `${EDAGOV_PYTHON:-python3} ${CLAUDE_PLUGIN_ROOT}/governance/bin/edagov-mcp.py`.

On Windows set `EDAGOV_PYTHON=py` in the user's environment before starting the client (or edit the plugin's `.mcp.json` to use `py`), and make sure `py` can run Python 3.10+. Restart the client after changing environment variables.

If the organization blocks plugin installs, use option B.

### Option B: manual MCP configuration

Use absolute paths. Replace `<REPO>` with the clone path and `<DESIGN>` with the design repository the user will work on.

Claude Code (project or user `.mcp.json`), Windows example:

```json
{
  "mcpServers": {
    "konnect": {
      "command": "C:\\Users\\<you>\\.local\\bin\\konnect.exe",
      "args": [],
      "env": {
        "KONNECT_GOVERNANCE": "auto",
        "KONNECT_EDAGOV": "<REPO>\\governance\\bin\\edagov.py",
        "KONNECT_PYTHON": "py",
        "KONNECT_GOVERNANCE_ROOT": "<DESIGN>",
        "EDAGOV_ACTOR": "<user email>"
      }
    },
    "edagov": {
      "command": "py",
      "args": ["<REPO>\\governance\\bin\\edagov-mcp.py"],
      "env": {
        "EDAGOV_ROOT": "<DESIGN>",
        "EDAGOV_ACTOR": "<user email>"
      }
    }
  }
}
```

Linux/macOS: same shape with `"command": "/home/<you>/.local/bin/konnect"`, `"KONNECT_PYTHON": "python3"`, and `"command": "python3"` for edagov.

Claude Desktop uses the same `mcpServers` block in its `claude_desktop_config.json`. Claude Code CLI alternative:

```bash
claude mcp add konnect -e KONNECT_GOVERNANCE=auto -e KONNECT_EDAGOV=<REPO>/governance/bin/edagov.py -- /path/to/konnect
claude mcp add edagov -e EDAGOV_ROOT=<DESIGN> -- python3 <REPO>/governance/bin/edagov-mcp.py
```

Optional: `konnect init --client claude` installs Konnect's skills and the governance skills into `~/.claude/skills` for clients that don't load the plugin. It overwrites differing files.

### Check both servers

- `gov_doctor` → shows the edagov version, `kicad_cli`/`ngspice` paths, the design root, and whether a store exists.
- `list_toolboxes` (Konnect) → lists 21 toolsets.
- `get_installation_info` (Konnect) → build commit of this repository.

---

## 6. Put a design under governance (once per design)

A design is governed when its repository contains `.edagov/` (the evidence store). Setting it up assigns people to roles, so **the user (or their lead) runs the init command, not you**. Show them this command, filled in with their details:

```bash
python3 <REPO>/governance/bin/edagov.py --root <DESIGN> init \
  --product PRD-XXX --design DES-XXX --board PCB-XXX --revision A --variant default \
  --authority owner@company.com --standard "IPC-2221B (2012)" \
  --grant designer@company.com=contributor \
  --grant reviewer@company.com=design_reviewer \
  --grant supply@company.com=supply_reviewer \
  --grant fab@company.com=manufacturing_reviewer \
  --grant lead@company.com=release_approver \
  --grant admin@company.com=connector_admin
```

(Windows: `py <REPO>\governance\bin\edagov.py ...` with the same arguments.)

You may call `gov_init` to create a store without roles; then every action is denied until the user grants roles with `edagov roles grant <email> <role>` (run by a release approver).

Commit `.edagov/` with the design. It is the evidence and is reviewed like code. Copy `governance/ci/design-repo/.github/` into the design repository to run the gates in CI (edit `EDAGOV_REPO`, `EDAGOV_REF`, `KICAD_PROJECT` in the workflow).

Smoke-test governance on the bundled demo, never on the user's design:

1. Copy `governance/examples/buck-demo/kicad` to a scratch folder and have a store initialised there (as above, with your user's email as contributor and another email as design_reviewer).
2. Call Konnect `add_no_connect` with `{"schematic": "<scratch>/kicad/power.kicad_sch", "x": 100, "y": 100}`.
3. Expected: an error of kind `plan_blocked` saying no approved change window covers the tool. That proves the hook is active. If the call succeeds instead, governance is not active: check `KONNECT_GOVERNANCE`, the store path, and that the binary was built from this repository.

---

## 7. How to work (every session)

Read the skills before acting: `governed-design-editing` for any design change, `eda-kicad-cloud-evidence-governance` for evidence, gates and reporting.

### Start
1. `gov_status`: design identity, your actor and roles, open windows, pending approvals.
2. `gov_gates`: where the design stands; `gov_explain <gate>` for details.

### Inspect (never blocked)
Konnect read tools (`list_*`, `get_*`, `find_*`, `query_*`, `search_*`), `run_erc`, `run_drc`, audits, and dry runs of apply-mode tools. Check results from Konnect are saved automatically as unreviewed evidence (`konnect:<tool>` tags).

### Change the design
1. Plan with read tools and dry runs.
2. `gov_window_request` with the smallest scope: toolsets (e.g. `sch_wiring`), `tool:<name>` entries, file globs relative to the repo root, a one-sentence reason, the issue ID, hours and a call budget.
3. Tell the user the window ID and the approval command for a reviewer who is not the requester: `edagov konnect window approve WIN-…`. Wait for confirmation; check with `gov_window_status`.
4. Make the edits with Konnect tools.
5. If a call returns `plan_blocked` with a governance reason, stop. Request a new window for what is missing, or report the blocker. Never retry through another tool or a file edit.
6. `gov_window_close`, then `gov_ledger` and report which files changed.
7. Re-run gate evidence (your earlier ERC/DRC/simulation results are now stale): `gov_run_check` for `erc` and `drc` and `gov_spice_run`, each with the user's authorization reason. Execution never happens without that reason.
8. `gov_gates` and `gov_pending_human_actions`, then tell the user which reviews or approvals are needed and the exact commands.

### Other evidence work
| Task | Tool |
|---|---|
| Project inventory (files, versions, libraries, outline, stackup) | `gov_inventory` |
| Record requirements, blocks, decisions, assumptions, evidence | `gov_record_requirement`, `gov_record_block`, `gov_record_decision`, `gov_record_assumption`, `gov_record_evidence` |
| Ingest existing reports or logs (documentation-only) | `gov_ingest_report`, `gov_ingest_spice` |
| BOM check | `gov_ingest_bom` |
| Manufacturing outputs and manifest | `gov_export` (authorized), then `gov_manifest`, `gov_dfm_finding` |
| GitHub PR state (read-only) | `gov_ingest_github` |
| Issues | `gov_issue_open` |
| Connector actions (publish/purchase/release/delete) | `gov_connector_propose` → a person approves → `gov_connector_check` → execute → `gov_connector_outcome` |
| Review outputs | `gov_dashboard`, `gov_snapshot` (needs a reviewer/approver/auditor identity) |
| Before sending any summary or PR text | `gov_lint_claims`, `gov_scan_secrets` |
| Integrity | `gov_audit_verify` |

### Report
Use the response contract from `skills/eda-kicad-cloud-evidence-governance/SKILL.md`: scope (documentation-only vs executed), design identity, evidence index with record IDs, findings, open issues, exceptions, decision per gate, caveats and sign-off limits.

---

## 8. Configuration reference

| Variable | Read by | Meaning |
|---|---|---|
| `KONNECT_GOVERNANCE` | konnect | `auto` (default): govern designs that have `.edagov/`; `enforce`: also refuse design writes that no store covers; `audit`: record but never refuse; `off`: upstream behaviour |
| `KONNECT_GOVERNANCE_ROOT` | konnect | design repo to govern when a tool call has no path argument (live board tools) |
| `KONNECT_EDAGOV` | konnect | edagov launcher path; a `.py` path runs through `KONNECT_PYTHON` |
| `KONNECT_PYTHON` | konnect | Python for `.py` launchers (default `py` on Windows, `python3` elsewhere) |
| `EDAGOV_ROOT` | edagov | design repository holding `.edagov/` |
| `EDAGOV_ACTOR` | both | person the work is attributed to (email); falls back to git `user.email` |
| `EDAGOV_EXECUTION` | edagov | `allow:<reason>` authorizes execution in CI only |
| `KICAD_CLI`, `NGSPICE` | edagov | tool paths when not on PATH |
| `EDAGOV_PYTHON` | plugin `.mcp.json` | Python command for the edagov server (`py` on Windows) |

Design policy lives in `<DESIGN>/.edagov/policy.json` (gates, freshness windows, `governance` section: approver roles, self-approval, window limits, evidence-capture tools). Change it through a PR.

---

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `plan_blocked` … "no approved, unexpired change window covers" | Request a window and have a reviewer approve it. |
| `plan_blocked` … "call budget exhausted" / "outside the window's file scope" | Request a new window covering exactly what is missing. |
| `plan_blocked` … "revision … is released" | The revision is frozen; the user moves to a new revision (`edagov revision <next> --reason …`). |
| `plan_blocked` … "has no role permitting" | `EDAGOV_ACTOR` is wrong or has no role; the user fixes the actor or a release approver grants a role. |
| `plan_blocked` … "governance check could not run" | Konnect cannot start edagov: check `KONNECT_EDAGOV` path, `KONNECT_PYTHON` (`py --version` on Windows), and run `py governance\bin\edagov.py doctor`. |
| Design writes succeed in a governed design | Governance inactive: binary not from this repo, `KONNECT_GOVERNANCE=off`, or the call had no path and `KONNECT_GOVERNANCE_ROOT` is unset. |
| `gov_*` tools missing | edagov server failed to start: wrong Python command (`EDAGOV_PYTHON`), or wrong path to `edagov-mcp.py`. |
| Live board tools fail | KiCad not running, board not open, or IPC API disabled. |
| Gates say "design files changed since this run" | Expected after edits: re-run ERC/DRC/simulation. |
| `cargo build` fails on `google/protobuf/any.proto` | Install `libprotobuf-dev` (Linux) or set `PROTOC_INCLUDE` (Windows/Chocolatey). |
| `cargo build` fails in `nng-sys` | Install CMake and a C compiler (Windows: VS Build Tools, Developer PowerShell). Under Git Bash a fresh target dir also fails; build from PowerShell. |
| `LNK1104` on `konnect.exe` (Windows) | Target dir is inside a Google Drive/OneDrive folder, or the old binary is running. Build to `CARGO_TARGET_DIR` outside synced folders; rename the running exe before copying the new one. |
| `check_kicad_ui` says `not_configured` though KiCad runs (Windows) | KiCad API off (`kicad_common.json` → `api.enable_server` false; the Python interpreter field is a different setting), or Konnect started before the API was enabled. Enable it, then restart the MCP client. The endpoint is the named pipe `\\.\pipe\<TEMP>\kicad\api.sock`. |
| `update_pcb_from_schematic` refused: root `.kicad_sch` "outside the window's file scope" | Governance counts every path argument as a target; include the root schematic in the window's `files`. |
| Sync dry run: "custom-shape pads are not supported" | Swap that footprint for its plain-pad variant via a governed schematic edit, or have a person place it with KiCad's own Update PCB (F8). |
| Evidence hashes break after checkout (Windows) | `core.autocrlf` rewrote design files. Add `.gitattributes` with `* -text` to the design repo and `git add --renormalize .`. |

---

## 10. Status and limits (as of 2026-10-31)

- Verified: governance toolkit and MCP server (49 Python tests), Rust governance core (unit tests and clippy), Rust-to-edagov end-to-end protocol, plugin manifest validation.
- Pending: the first full workspace build (`cargo check/test/clippy` across Windows/macOS/Linux) runs in this repository's GitHub Actions on push; real KiCad 10 and ngspice runs are in `.github/workflows/governance-real-tools.yml`. Check the latest Actions results before relying on a build, and tell the user if they are red.
- Upstream Konnect is archived (development moved to the closed-source Konnect-EDA); this fork is maintained independently under AGPL-3.0. See `FORK_NOTICE.md`.
- Documentation-only evidence shows a process was followed and checks produced stated results. It does not prove circuit function, compliance, manufacturability, authenticity, SI/PI, thermal or EMC adequacy, safety or reliability.
