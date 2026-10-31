# Manufacturing outputs and release package

A manufacturing release is a controlled, revision-consistent evidence package, not a folder of plots.

## Formats

- **Gerber + NC drill** carry image and hole data. Gerber alone does not carry complete stackup, materials, design intent or netlist [1][2].
- **Gerber X2** adds attributes (`%TF.FileFunction`, `%TF.ProjectId,<name>,<guid>,<rev>`, `%TF.GenerationSoftware`, `%TF.CreationDate`, `%TF.SameCoordinates`) [1]. The **Gerber job file** (`.gbrjob`) lists files, layer count, thickness and material stackup.
- **IPC-2581** and **ODB++** carry richer manufacturing intent; record exporter and version and confirm the recipient accepts it [2][3].

## Generating outputs (KiCad 10)

Run only with authorization; edagov records command, version and output hashes [4]:
```
edagov export gerbers --project kicad --out fab --authorize "…" [--variant NAME]
edagov export drill   --project kicad --out fab --authorize "…"      # adds --generate-map --map-format gerberx2
edagov export pos     --project kicad --out fab --authorize "…"      # csv, mm, both sides
edagov export bom     --project kicad --out fab --authorize "…"
edagov export ipc2581 --project kicad --out fab --authorize "…" [--variant NAME]
edagov export odb     --project kicad --out fab --authorize "…" [--variant NAME]
```
KiCad 10 documents `--variant` for gerbers, ipc2581, odb, step, pdf, dxf and 3D exports, not for drill or pos; edagov records a limitation if a variant is requested where it is not documented. Set the title-block revision so X2 and job files carry it.

## Package content

Fabrication: Gerber layers, drill/route files and drill chart, controlled fabrication drawing and notes, outline, layer count/stackup/materials/thickness/copper/finish/mask/legend, tolerances, slots/cutouts, impedance and coupon requirements, panel/tooling, product class, special processes.
Assembly: revision-matched BOM, placement/centroid, paste where applicable, top/bottom assembly drawings, polarity/orientation, connectors/heatsinks/hardware, labels, no-pop and hand-assembly notes, variants [5].

## Manifest

`edagov manifest --outputs fab --origin "<origin convention>" --supplier-assumption "<…>"` records per file: name, kind, format/version, file function, units, generated timestamp, generator, declared project revision, variant, origin, SHA-256. It then reconciles:
- required kinds (`gerber`, `drill`, `position`, `bom`) and required FileFunctions from `policy.json` (default 2-layer set: Copper L1/L2, Soldermask Top/Bot, Legend Top, Profile);
- one project revision across all files, equal to the design identity (else `conflict`);
- units, generator version and `SameCoordinates` consistency;
- files the job file lists but the package lacks;
- placement references versus BOM references for the revision (DNP excluded).

`edagov` re-hashes files at gate evaluation and at sign-off. If any file changed, the manifest no longer verifies and prior sign-offs do not carry over.

## DFM/DFA and sign-off

Sign-off names the rule set, tool and version, fabricator/assembler capabilities, minimum trace/space, annular rings and drills, copper-to-edge, mask slivers, courtyard/clearance, thermal and assembly access, fiducials, panelization and test access.

- Record each finding: `edagov dfm add MFG-… --rule … --description … --disposition open|corrected|accepted|waived --rationale … [--approver …]`. Accepted or waived needs rationale and approver.
- Record plotted-view review: `edagov dfm plotted-view MFG-… --decision approved --note "Gerber viewer review of all layers"`.
- Collect four separate sign-offs: `edagov signoff MFG-… design_owner|fabrication_dfm|assembly_dfa|release_control --decision approved`. Each maps to a different role.

Documentation cannot prove physical manufacturability, solderability, process capability or assembly quality without supplier feedback and inspection or test [1][5].

## Troubleshooting

Manufacturing mismatch: compare IDs, revisions, variants, origin, units and reference sets and the manifest hashes; inspect Gerber, drill and assembly views; check supplier capability assumptions.

## References

[1]: https://www.ucamco.com/en/gerber "The Gerber Format"
[2]: https://www.ipc2581.com/history/ "IPC-2581 History and Data Exchange"
[3]: https://www.siemens.com/en-us/products/pcb/odb-plus-plus/ "Siemens ODB++"
[4]: https://docs.kicad.org/10.0/en/cli/cli.html "KiCad 10.0 Command-Line Interface"
[5]: https://www.protoexpress.com/kb/fabrication-assembly-files/ "Fabrication and Assembly Files"
