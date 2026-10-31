# PCB stackup, SI/PI, thermal and EMC evidence

Attach evidence with `edagov record evidence --path <file|url> --artifact-kind report --tag <topic> --owner … --claim "<scoped claim>"`. Topics checked by the PCB gate: `stackup`, `pi_analysis`, `si_analysis`, `thermal_analysis`, `emc_plan`. Each needs a named reviewer (`edagov review ART-… --role design_reviewer --state approved`) and must be fresh (`freshness_days.analysis`). Mark a topic not applicable only through a policy override with a rationale.

## Stackup and fabrication definition

Define before routing: layer order, copper weights, dielectric thickness and material, Dk/Df assumptions, finished thickness, plane assignments, impedance targets and tolerances, the fabricator's controlled-impedance method, and coupon requirements. Stackup is an electrical design variable [1][2]. Do not infer impedance from layer count or nominal Dk. The inventory reports whether the board defines a physical stackup; that is presence, not validity.

## Placement and routing

Place by functional flow and critical current/return paths: converters, drivers, loads, decoupling, connectors, sensitive analog/RF, probes, heat spreaders, mechanical interfaces. Record critical locations, keep-in/keep-out zones, critical traces, reference layers, matched-length nets and termination intent [1].

Keep a continuous reference plane next to signals. A split, void or plane change forces return current to detour (more loop inductance, coupling, EMI). When a signal changes reference layers, place stitching vias nearby or record an analyzed alternative [1].

Controlled impedance depends on edge rate and electrical length, not just clock frequency. Record per net: target impedance, topology, discontinuity budget, layer/reference, length/skew limit, termination, and the verification model or measurement. Differential pairs add spacing, skew, reference, via policy and allowed geometry transitions. Numbers come from interface specifications, vendor guides, IBIS/S-parameters or validated analysis.

## Power integrity

Treat the PDN as regulator, planes/traces, vias, capacitors, package and die. Record voltage/current limits, allowed ripple and droop, target impedance versus frequency, capacitor value/voltage/temperature/ESR/ESL, placement and via geometry, and analysis assumptions. PI analysis typically needs schematic, layout, stackup/material data, capacitor S-parameters and a PI tool [3]. Capacitor count is not evidence: capacitors become inductive above self-resonance, and mounting and plane inductance matter. Check power routing for current density, IR drop, temperature rise, via capacity and discontinuities. Do not generalize a vendor example's margin.

## Thermal

Record dissipation per operating mode, maximum ambient, allowed junction/case temperature, copper area/thickness/layers, exposed pad and via pattern, airflow/enclosure, heat sink/contact, nearby sources and the analysis or measurement method. Heat leaves through the package top, exposed pad, PCB copper, vias, inner/bottom copper, convection and radiation [4]. Datasheet θJA belongs to a specific test board; use it for comparison and sanity checks, not as a prediction for this board.

## EMC

Use the source → coupling path → victim model. Minimize high-di/dt loop area, keep noisy currents local, preserve returns, avoid splits under fast signals, separate noisy and sensitive zones, and control connector and cable interfaces. Fast edges carry harmonics far above the clock frequency [1][5]. The EMC plan names standards and limits by edition, ports and cables, enclosure and shield bonding, filter topology and placement, ESD/transient paths, the pre-compliance setup and the final test configuration. Shields, ferrites, filters and partitions do not replace a sound return path.

## Troubleshooting

- **Impedance/EMI concern:** verify fabricated stackup, Dk and tolerances, reference continuity, transitions, geometry, edge rate, return path, cable assumptions and model/measurement evidence.
- **Thermal concern:** check real dissipation, copper and vias, exposed pad, airflow, enclosure, heat sink, nearby sources and boundary conditions; do not substitute θJA.

## References

[1]: https://www.analog.com/en/resources/analog-dialogue/articles/high-speed-printed-circuit-board-layout.html "High-Speed Printed-Circuit Board Layout"
[2]: https://www.ti.com/lit/pdf/scaa082 "High-Speed PCB Design Guidelines"
[3]: https://www.ti.com/lit/an/swpa222a/swpa222a.pdf "Power Integrity Analysis and Design Guidance"
[4]: https://www.ti.com/lit/pdf/szza009 "Thermal Design by Insight, Not Hindsight"
[5]: https://www.ti.com/lit/pdf/snva419 "EMI, EMC, and PCB Design Guidance"
