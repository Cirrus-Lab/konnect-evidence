## Design change

- Issue: #<!-- id -->
- Design / board / revision / variant: <!-- DES-… / PCB-… / B / default -->
- Gitflow lane: <!-- feature/* → develop | release/* → main+develop | hotfix/* → main+develop -->
- Purpose:
- Affected artifacts: <!-- schematic sheets, board, libraries, BOM lines, fab outputs, .edagov/policy.json -->
- Risk: <!-- low / medium / high, and why -->

## Evidence (record IDs)

| Evidence | Record ID | Executed or ingested | Result |
|---|---|---|---|
| ERC | RUN-… | | |
| DRC (with schematic parity) | RUN-… | | |
| Simulation | RUN-… | | |
| BOM | BOM-… | | |
| Manifest | MFG-… | | |

## Open issues and exceptions

- ISS-… / EXC-…

## Release impact

<!-- what changes for fabrication/assembly; which gates must be re-reviewed -->

## Claim checklist

- [ ] Every statement is scoped to inputs, policy and evidence IDs (`edagov lint-claims` passes on this description)
- [ ] No ERC/DRC or simulation result is described as functional, compliance or manufacturing proof
- [ ] No secrets, tokens or credential payloads in the diff or evidence (`edagov scan-secrets` passes)
- [ ] Linked issues: I know whether they auto-close (only when merging into the default branch)
