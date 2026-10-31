# SPICE/LTspice simulation and validation

## Netlist and model record

A netlist is more than topology: element lines, directives, analyses, included libraries, parameters, initial conditions and simulator options. For ngspice-style decks capture the title line, `.end`, ground node `0` and DC paths to ground [1][3]. For LTspice subcircuits capture the model name, `X` prefix, exact ordered pin map, symbol association and every included `.lib`/model file; a matching filename does not establish compatibility [2].

`edagov spice manifest deck.cir` extracts and checks:
- title, `.end`, a connection to node 0 (`gnd` alias noted);
- `.include`/`.lib` files with hashes (missing files block);
- analyses (`.op .ac .dc .tran .noise .tf …`), `.options`, `.param`, `.temp`, `.ic`/`.nodeset`, saved outputs;
- every `X` instance against its `.subckt` definition (missing definition or pin-count mismatch blocks);
- encrypted/proprietary model markers and LTspice-style syntax hints;
- `.options` loosened beyond ngspice defaults (reltol 1e-3, abstol 1e-12, vntol 1e-6, chgtol 1e-14, gmin 1e-12, trtol 7, itl1 100, itl2 50, itl4 10) [3].

Minimum simulation record: netlist ID and hash; simulator and exact version/build/platform; all source and included files; model vendor/revision/license/encryption status; pin map and ground convention; units and scale factors; temperatures; analysis type, sweeps, sources, initial conditions, saved vectors; solver method, tolerances, timestep limits, integration method/order; warnings and logs; output definitions and hashes; model validity limits; validation data and acceptance criteria; reviewer/date; change history.

## Execution

ngspice batch mode: `ngspice -b -o <log> -r <rawfile> <deck>`; `-v` prints the version [4]. `edagov spice run deck.cir --authorize "…"` freezes a copy of the deck, runs it, keeps log and raw output, and writes provenance. For LTspice or a commercial simulator, run it yourself and ingest: `edagov ingest spice deck.cir --log run.log --simulator ltspice --tool-version "24.1.x" --exit-code N`.

## Run classes

| Class | Meaning |
|---|---|
| clean | log shows no failure or warning, settings at defaults |
| converged_with_warnings | completed with warnings; each needs a disposition |
| altered_settings | completed with loosened solver settings; needs `--justification` and review |
| failed | non-zero exit, aborted analysis, "timestep too small", singular matrix, no convergence, missing model, etc. |

## Scope of claims

- SPICE implementations differ in syntax, device levels, defaults, temperature behaviour, convergence settings and proprietary/encrypted model support [1][3]. Berkeley SPICE3 is a historical baseline, not a guarantee of modern behaviour [1].
- DC operating point treats capacitors as open and inductors as short; AC analysis linearizes around the DC point; transient starts from a DC solution and depends on initial conditions [3]. An AC result is not a large-signal transient result.
- Convergence only means the numerical stopping criteria were met for the chosen equations and settings. It does not show the topology, model, operating region or physical assumptions are right.
- Non-convergence is diagnostic information. Do not hide it by loosening tolerances broadly. Keep the failed run, record what was tried, link the retry with `--retry-of`, and let the reviewer judge whether the final run is still qualified. edagov lists the changed settings between attempts.
- Validate against intended-domain observables: test conditions, uncertainty, parameter and temperature range, acceptance limits, and coverage (device model, subcircuit, assembled circuit, mathematical benchmark). Record this in `--validation`.
- Simulation does not establish hardware compliance, reliability, safety or production behaviour.

## Troubleshooting

- **Parser/model failure:** check dialect, title and `.end`, node 0, include paths, model name, ordered pins, units, unsupported constructs.
- **Non-convergence:** keep the failure; inspect topology, floating nodes, feedback, values, model parameters, initial conditions, tolerances, timestep, integration method and switch ideality (finite edges, hysteresis). Report changed settings and whether the final run remains qualified.

## References

[1]: https://www2.eecs.berkeley.edu/Pubs/TechRpts/1989/1220.html "SPICE3 User Guide (Berkeley report)"
[2]: https://www.analog.com/en/resources/technical-articles/ltspice-how-to-import-third-party-models.html "LTspice: How to Import Third-Party Models"
[3]: https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml "ngspice User Manual"
[4]: https://man.archlinux.org/man/ngspice.1.en "ngspice(1) manual page"
