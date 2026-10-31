# KiCad project, ERC/DRC and library governance

Version scope: written against KiCad 10.0.0 documentation (retrieved 2026-10-31) [1][2]. Re-check flags with `kicad-cli <cmd> -h` on the installed build and record the version in every run.

## Project structure

A KiCad project is a folder with `<name>.kicad_pro` (JSON settings), a root `<name>.kicad_sch` plus hierarchical sheet files, and `<name>.kicad_pcb`. Native schematic, board and library files are S-expressions [3]. The workflow runs: schematic capture → footprint assignment → ERC → update PCB from schematic → placement/routing → DRC → fabrication outputs [1].

Keep the project folder together. A board opened outside its project can lose project settings (net classes, rule severities, text variables, custom rules).

Controlled files: `.kicad_pro`, all `.kicad_sch`, `.kicad_pcb`, `sym-lib-table`, `fp-lib-table`, project libraries (`.kicad_sym`, `.pretty/*.kicad_mod`, 3D models), `.kicad_dru` custom rules, `.kicad_wks` worksheets, `.kicad_jobset`.
Usually local-only: `.kicad_prl`, `fp-info-cache`, `*.lck`, `*-backups/`. Excluding them is acceptable only after confirming they are not needed to reproduce the design.

`edagov inventory --project <dir>` records all of this read-only:
- every file with kind, hash and controlled/local-only distribution;
- the sheet hierarchy (missing sheet files block);
- `generator_version` of each file, flagging version skew (files written by a newer KiCad should not be assumed to open in an older one);
- library tables, flagging project libraries that do not exist and dependencies on global tables or path variables (`${KICAD10_*}`);
- symbols without footprints, hidden power-input pins (implicit nets; supported for compatibility, not recommended for new designs);
- board stackup presence, copper layers, zones, footprints without 3D model references;
- Edge.Cuts outline closure from segment endpoints (closed / open / absent / unknown).

Pin the library release with `--library-release "<tag or commit>"` and record project library provenance with `edagov record library --path lib/x.kicad_sym --source "<datasheet/repo@tag>" --license "<license>"`.

## ERC

ERC is a rule-based consistency check (unconnected pins, conflicting or undriven connections). It cannot show the circuit works. No-connect flags document intentional non-connections. `PWR_FLAG` or a real power-output pin satisfies power-driver checks when electrically justified [1][4].

Command (KiCad 10):
```
kicad-cli sch erc --format json --units mm --severity-error --severity-warning \
  --exit-code-violations --output erc.json <root>.kicad_sch
```
`edagov run erc --project <dir> --authorize "…"` builds exactly this and binds the run to the hashes of the project, all sheets, the board, rules and library tables.

## DRC

DRC checks board constraints, net classes, keepouts/rule areas and custom rules. Custom rules apply only when they parse without errors; keep the rule file and its syntax result. A malformed Edge.Cuts outline disables parts of DRC [1].

```
kicad-cli pcb drc --format json --units mm --severity-error --severity-warning \
  --schematic-parity --exit-code-violations --output drc.json <name>.kicad_pcb
```
`--refill-zones` refills zones in memory before checking; edagov records the zone state either way and never passes `--save-board`.

## Exit codes and reports

KiCad 10 docs: with `--exit-code-violations`, exit 0 means no violations and 5 means violations exist [2]. One third-party CLI reference states 2 [5]; treat that as unverified. edagov records the raw code and compares it with the parsed report:

| Exit | Active violations in report | Result class |
|---|---|---|
| 0 | 0 | clean |
| 5 | >0 | violations |
| 0 | >0 | conflict |
| 5 | 0 | conflict (excluded items may be counted) |
| other | any | tool_error |

JSON report fields (from KiCad's `rc_json_schema.h`) [6]:
- common: `$schema`, `source`, `date`, `kicad_version`, `coordinate_units`, `included_severities`, `ignored_checks[{key, description}]`;
- ERC: `sheets[{uuid_path, path, violations[]}]`;
- DRC: `violations[]`, `unconnected_items[]`, `schematic_parity[]`;
- violation: `type`, `description`, `severity`, `items[{uuid, description, pos{x,y}}]`, and `excluded` + `comment` when excluded.

Record severity configuration, exclusions (each with rationale and reviewer), ignored checks (each disables a check and needs exceptional justification), zone refill state, parity, stackup, net classes, custom rules, library revisions and paths.

## Library governance

Symbols, footprints, 3D models and simulation models are distinct governed asset classes. For each asset record: stable ID, repository path, tag/commit, KiCad format version, datasheet/manufacturer evidence, pin and pad data, dimensions, courtyard/keepout intent, model filename and alignment, license, automated check output, visual review, reviewer/date, status, exceptions, supersession [7][8].

- Official KiCad libraries use separate repositories for symbols, footprints, 3D models and model sources; contributions go through focused merge requests with datasheet evidence and librarian review [7].
- The KiCad Library Conventions (KLC) are guidance with possible approved exceptions; a datasheet normally takes priority over a convention [8]. KLC scripts do not replace electrical, dimensional, provenance or manufacturability review.
- Path-variable conventions change between releases (for example `KICAD9_3DMODEL_DIR` → `KICAD10_3DMODEL_DIR`). Bind library policy to a target release.
- Distinguish fully specified symbols (valid `library:footprint`) from generic symbols whose footprint is intentionally blank.
- A non-virtual footprint should carry a 3D reference under KLC even if the model file is missing. A missing model is a documented state, not automatically an invalid footprint [8].

## Troubleshooting

- **Missing settings or libraries on open:** restore the project folder, tables, path variables, local libraries and exact version; record limitations if validating outside the project.
- **ERC power-driver or unconnected errors:** check pin electrical types, intentional no-connects, power flags, hidden power pins and hierarchy. Document the exception; do not silence it.
- **DRC unexpectedly incomplete:** check Edge.Cuts closure, rule syntax, board setup, zone refill and severity policy.

## References

[1]: https://docs.kicad.org/10.0/en/introduction/introduction.html "KiCad 10 Introduction"
[2]: https://docs.kicad.org/10.0/en/cli/cli.html "KiCad 10.0 Command-Line Interface"
[3]: https://dev-docs.kicad.org/en/file-formats/ "KiCad Developer File Formats"
[4]: https://docs.kicad.org/9.0/en/eeschema/eeschema.html "KiCad Schematic Editor"
[5]: https://www.mintlify.com/KiCad/kicad-source-mirror/api/cli-reference "Third-party CLI reference (unverified exit code claim)"
[6]: https://docs.kicad.org/doxygen/rc__json__schema_8h_source.html "KiCad rc_json_schema.h"
[7]: https://www.kicad.org/libraries/contribute/ "KiCad Library Contribution Guide"
[8]: https://klc.kicad.org/ "KiCad Library Conventions"
