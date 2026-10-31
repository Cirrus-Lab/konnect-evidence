---
name: eda-toolchain-setup
description: Installs and verifies the EDA agent toolchain, the Konnect MCP server binary, KiCad 10 (kicad-cli and IPC API), ngspice and Python for edagov, on Linux, macOS or Windows, and records the exact versions. Use when gov_doctor or edagov doctor reports something missing, when the konnect or edagov MCP server does not start, when the user asks to set up KiCad, ngspice, Konnect or the EDA agent environment, or before the first authorized ERC/DRC, export or simulation run on a new machine or CI runner.
---

# EDA toolchain setup

Install only what the user agreed to. Installing software changes their machine, so say what you will install and from where, and wait for a yes unless they already asked for it. Never use `sudo` or an installer silently.

## 1. Check what exists

Call `gov_doctor`, or run `<plugin-root>/governance/bin/edagov.py doctor` with Python (the plugin root is two directories above this skill's base directory). It reports Python, `kicad-cli`, `ngspice`, `git` and `gh` paths and versions. Python 3.10+ is the only hard requirement for documentation-only work.

## 2. Install KiCad 10 (provides kicad-cli)

Use the official channels from kicad.org [1]. The latest stable in this plugin's research window was 10.0.7 (2026-10-07) [2]; prefer the newest 10.0.x the channel offers and record it.

| Platform | Command |
|---|---|
| Ubuntu / Debian derivatives | `sudo add-apt-repository --yes ppa:kicad/kicad-10.0-releases && sudo apt update && sudo apt install --install-recommends kicad` |
| Other Linux | Flatpak: `flatpak install --user flathub org.kicad.KiCad` then use `flatpak run --command=kicad-cli org.kicad.KiCad` (set `KICAD_CLI` to a wrapper script) |
| macOS | `brew install --cask kicad` (kicad-cli at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`) or the DMG from kicad.org |
| Windows | `winget install --id KiCad.KiCad -e` (kicad-cli at `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`) |

If the binary is not on PATH, set `KICAD_CLI` to its full path. In a headless container kicad-cli runs without a display; if it complains about a display, retry under `xvfb-run`.

## 3. Install the Konnect binary

The `konnect` MCP server is this repository's Rust workspace (fork of Konnect with evidence governance). Either:
- download the release binary for the platform from the fork's GitHub Releases and put `konnect` (`konnect.exe` on Windows) on PATH; or
- build it: install Rust (rustup) and `protoc` 3.23+, then run `cargo build --release -p konnect` in the plugin root and use `target/release/konnect`.

Enable KiCad's IPC API (Preferences → Plugins → Enable IPC API) for live board tools. Run `konnect status` to confirm the build and `konnect init --client claude` only if you also want Konnect's skills installed outside this plugin.

Making the IPC API work on Windows:

- **Which setting.** The Plugins page also has a Python interpreter field, which does not enable the API. Confirm the API itself is on: `%APPDATA%\kicad\10.0\kicad_common.json` must contain `"api": {"enable_server": true}`.
- **What the endpoint is.** It is a named pipe, `\\.\pipe\<TEMP>\kicad\api.sock`, and no file exists at that path. List KiCad's pipe with `[System.IO.Directory]::GetFiles('\\.\pipe\') | Where-Object { $_ -match 'kicad' }`.
- **Restart after enabling.** Konnect looks for the endpoint once, at startup. After enabling the API, restart the MCP client (or reconnect the `konnect` server); `check_kicad_ui` then reports `ipc_responsive: true`.
- **Retry once after opening the PCB editor.** For a few seconds after the editor opens, live tools can fail with `GetOpenDocuments … AS_UNHANDLED`, because the editor has not finished registering. Retry once before treating it as a configuration fault.

Building from source on Windows:

- Build from PowerShell (Developer PowerShell for MSVC). `nng-sys`'s CMake step fails under Git Bash in a fresh target directory.
- Put the target directory outside cloud-synced folders, for example `CARGO_TARGET_DIR=C:\Users\<you>\.cargo-target\konnect`. Google Drive and OneDrive lock build outputs, which fails the link step with `LNK1104`.
- A release build needs several GB free.

The plugin's MCP configuration starts `konnect` with `KONNECT_GOVERNANCE=auto` and `KONNECT_EDAGOV` pointing at the bundled `governance/bin/edagov.py`. On Windows, Python must be reachable as `py` (python.org launcher) or set `KONNECT_PYTHON`. The edagov MCP server starts with `${EDAGOV_PYTHON:-python3}`, and on Windows `python3` is usually the Microsoft Store alias, so set the user environment variable `EDAGOV_PYTHON=py` there. Set `KONNECT_GOVERNANCE_ROOT` to the design repository so live-board tools without a path argument are governed too.

## 4. Install ngspice

| Platform | Command |
|---|---|
| Ubuntu / Debian | `sudo apt install ngspice` |
| Fedora | `sudo dnf install ngspice` |
| macOS | `brew install ngspice` |
| Windows | download the 64-bit zip from ngspice.sourceforge.io and unzip it so that `C:\Spice64\bin\ngspice_con.exe` exists (the build loads its code models from `C:\Spice64`). edagov finds it there, in `C:\Program Files\Spice64` or as `ngspice_con` on PATH; anywhere else, set `NGSPICE` to the full path of `ngspice_con.exe` |

LTspice and commercial simulators are not driven by edagov; run them yourself and ingest the log (`edagov ingest spice`).

## 5. Verify and record

1. Call `gov_doctor` again; `kicad_cli` and `ngspice` must show a path, and the `konnect` server must list its tools.
2. Smoke-test on the bundled demo without touching the user's design:
   `sh <plugin-root>/governance/examples/buck-demo/build_demo.sh /tmp/edagov-demo` (documentation-only; works without KiCad).
3. Record the toolchain in the design repository so later runs are comparable:
   `edagov doctor > toolchain.json`, then
   `edagov record evidence --path toolchain.json --artifact-kind configuration --tag toolchain --owner <user> --claim "Toolchain versions on <host> at <date>"`.

## 6. Supporting tools agents need on the design side

- **Design repository line endings.** edagov records SHA-256 hashes of design files and hash-chains its ledger, and `core.autocrlf=true` (the Git for Windows default) rewrites files on checkout. Before the first commit, add a `.gitattributes` containing `* -text`. If files were already committed, run `git add --renormalize .` and commit again.
- **Reading manufacturer PDF drawings.**
  - Web fetchers often cannot decode compressed PDFs.
  - Land-pattern tables only make sense next to the drawing: extracted text gives values like `.310 (7.87)` but not which edge or pad each letter measures.
  - With the user's consent, install PyMuPDF (`py -m pip install --user pymupdf`) and render the page: `pymupdf.open(pdf)[page].get_pixmap(dpi=200).save("page.png")`.
  - Read dimensions only from the rendered drawing; never estimate a footprint dimension.
- **Python flags on Windows.** `py -I` (isolated mode) also disables the user site-packages, so a `--user` install is invisible to it. Use `py -P` instead: it still keeps the script's directory off `sys.path`, which is what matters when the script reads downloaded files.
- **Sites that refuse automated clients.**
  - keyelco.com returns 403 to fetchers, and mouser.com blocks automated browsers.
  - Do not spoof a browser user agent or otherwise get around a bot check. Ask the user to download the file and point you at it.
  - Opening such a PDF link in the built-in browser shows the user a save dialog; tell them what it is.

## 7. CI runner

The design-repo template `governance/ci/design-repo/.github/workflows/eda-evidence.yml` installs KiCad from the PPA and ngspice from apt on `ubuntu-24.04`, then prints `edagov doctor` into the job log. In the design repository give the CI actor only the `contributor` role. Pin the runner image; PPA packages move, so each run records the installed version.

## Failure handling

- Package source unreachable (proxy, offline): say so plainly, do not try other download routes, and continue in documentation-only mode with `edagov ingest`.
- Version older than 10.0: KiCad 9 CLI is similar but `--variant` and some JSON fields differ. Record the version and note the limitation in every run.

## References

[1]: https://www.kicad.org/download/details/ubuntu/ "KiCad download: Ubuntu"
[2]: https://www.kicad.org/blog/2026/10/KiCad-Version-10.0.8-Release-Candidate-1-Available/ "KiCad 10.0.8 RC1 announcement (notes 10.0.7 stable)"
[3]: https://man.archlinux.org/man/ngspice.1.en "ngspice(1) manual page"
