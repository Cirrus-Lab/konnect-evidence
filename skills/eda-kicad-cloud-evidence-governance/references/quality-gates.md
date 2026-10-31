# Quality gates, claim language and sign-off limits

Gates progress in order. Each gate has entry criteria (its checks), required evidence, a result state, blockers, exceptions, reviewer role and a next action. The default checks live in `.edagov/policy.json`; edit that file through a PR, never in place.

## Gates and default checks

| Gate | Checks (policy names) | Approver role |
|---|---|---|
| requirements | requirements_complete, assumptions_owned, no_blocking_issues | design_reviewer or release_approver |
| architecture | requirements_allocated, blocks_owned, no_blocking_issues | design_reviewer or release_approver |
| schematic_library | run_clean:erc, library_provenance, no_blocking_issues | design_reviewer |
| simulation | simulation_qualified, no_blocking_issues | design_reviewer |
| pcb | run_clean:drc, drc_parity_checked, evidence_tag:{stackup, pi_analysis, si_analysis, thermal_analysis, emc_plan}, no_blocking_issues | design_reviewer |
| supply | bom_present, bom_lines_valid, no_blocking_issues | supply_reviewer |
| release | manifest_complete, manifest_hashes_verify, dfm_dispositioned, prior_gates_approved, no_blocking_issues | release_approver |
| change | change_impact_recorded, no_blocking_issues (not applicable on the first revision) | design_reviewer or release_approver |

What each check needs:
- **requirements_complete**: at least one requirement; no `unmet`; acceptance must be measurable (a number or exact standard edition, not "compliant"/"ready"/"TBD").
- **run_clean:erc / drc**: latest run for the current revision, fresh, bound to input hashes, result `clean`, or `violations` covered by an exception naming that run ID.
- **drc_parity_checked**: DRC ran with `--schematic-parity`.
- **library_provenance**: inventory exists; global libraries are pinned (`--library-release`); every project library asset has provenance and license (`edagov record library`).
- **simulation_qualified**: every head run (not superseded by a retry) is clean, converged_with_warnings, or altered_settings with justification; it has validation data and a complete netlist manifest. Failed attempts stay on record.
- **evidence_tag:X**: a tagged artifact or run exists, is fresh, and has a named reviewer.
- **bom_lines_valid**: no BOM line with a blocking finding.
- **manifest_complete / manifest_hashes_verify**: the latest package is complete and every file still matches its hash.
- **dfm_dispositioned**: no open DFM/DFA finding, plotted-view review approved, and all four sign-offs approved (design owner, fabrication/DFM, assembly/DFA, release control).
- **no_blocking_issues**: no open/contained issue of severity in `issue_blocking_severities` affecting the gate (or all gates).

Mark a check not applicable only with a rationale:
```json
"overrides": {"pcb": {"evidence_tag:si_analysis": {"not_applicable": "No net faster than 10 MHz edge rate; ADR-0012"}}}
```

## State rules

- Automation produces `not_started` (all missing), `in_progress` (some missing), `ready_for_review` (all pass), or `blocked` (any fail).
- `approved` requires `edagov approve <gate> --decision approved` by a permitted role while automation shows `ready_for_review`.
- `approved_with_exception` requires exception IDs (`edagov exception …`) and is allowed even when automation is blocked.
- An approval stores the **evidence fingerprint** (hash of every input ID the checks used). If evidence changes afterwards, the gate falls back and the approval is reported stale, the same way GitHub dismisses a review on a new diff.
- "Accepted" means a named authority accepted the stated risk. It does not mean the risk disappeared.

## Claim language

Use scoped statements tied to inputs, policy and evidence IDs:

| Do write | Never write (without the evidence named) |
|---|---|
| "ERC completed with these inputs (RUN-…): 0 active violations, 1 excluded." | "The schematic is correct / functional." |
| "Simulation RUN-… converged under reltol=1e-3, gear; validated against hand calc ±10%." | "Simulation proves the loop is stable." | <!-- claims:example -->
| "DFM review under rule set X found no recorded violation." | "The board is manufacturable." |
| "Part is production-approved as an alternate for revisions B–C (equivalence matrix EQ-…)." | "Drop-in replacement." | <!-- claims:example -->
| "Pre-compliance scan per CISPR 32:2015 Class B setup showed 6 dB margin at 150 kHz–30 MHz." | "EMC compliant / EMC ready / CE certified." | <!-- claims:example -->
| "Tj estimate 104 °C from analysis ART-…, not measured." | "Thermally adequate." |

`edagov lint-claims <files>` flags the prohibited forms unless the sentence is negated, or carries scoping language and an evidence reference. Documentation that quotes prohibited wording as an example marks the line with `<!-- claims:example -->`.

## Sign-off limits

State these in every sign-off. Documentation-only evidence shows that a process was followed and that stated checks produced stated results. It cannot by itself prove circuit function, production yield, component authenticity, electrical equivalence, controlled impedance, PI/SI adequacy, thermal compliance, EMC/regulatory compliance, safety, reliability, or long-term availability.

- ERC/DRC do not replace engineering review, simulation, SI/PI analysis, thermal or current assessment, manufacturing review, inspection, or qualification.
- Simulation convergence is not physical validation.
- A 3D model is not proof of assembly or mechanical correctness.
- Gerber is not a complete manufacturing intent model.
- A GitHub approval is not architectural correctness.
- MCP support is not authorization.

Every sign-off states claim scope, evidence, assumptions, unresolved issues, applicable standards and editions, reviewer identity and date, and what remains unverified.
