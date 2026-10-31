# Simulation run {{RUN-…}}

| Field | Value |
|---|---|
| Deck / netlist | {{path}} · {{sha256:…}} |
| Included models | {{file — vendor/rev — license — encrypted?}} |
| Simulator · version · platform | {{ngspice-44.2 · Linux x86_64}} |
| Executed by edagov? | {{yes (provenance path) | ingested log}} |
| Analyses | {{.ac dec 50 10 1meg}} |
| Options vs defaults | {{reltol=3e-3 (loosened), method=gear}} |
| Temperatures / parameters / ICs | |
| Pin map check | {{all X instances match .subckt pin counts}} |
| Result class | {{clean | converged_with_warnings | altered_settings | failed}} |
| Retry of · changed settings | {{RUN-… · reltol, method}} |
| Justification for changed settings | |
| Validation data and acceptance criteria | |
| Model validity range | |
| Warnings / failure lines | |
| Reviewer · date | |

Claim scope: {{simulator}} run classified {{class}} for {{analyses}} under {{options}}. Convergence means the numerical stopping criteria were met; it is not hardware validation.
