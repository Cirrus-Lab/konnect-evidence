# Source register

Retrieval date for all entries: 2026-10-31 unless noted. "Applicability" says what the source may and may not be used to support. Re-verify version-specific items before relying on them for a new release.

| # | Title | URL | Version / date | Applicability caveat |
|---|---|---|---|---|
| 1 | KiCad 10.0 Command-Line Interface | https://docs.kicad.org/10.0/en/cli/cli.html | KiCad 10.0.0 manual (doc rev 28b5f9b0) | Flags and exit codes (0/5) for kicad-cli; re-check `-h` on the installed build |
| 2 | KiCad 10 Introduction | https://docs.kicad.org/10.0/en/introduction/introduction.html | KiCad 10.0 | Project workflow and file roles |
| 3 | KiCad rc_json_schema.h | https://docs.kicad.org/doxygen/rc__json__schema_8h_source.html | master doxygen | ERC/DRC JSON field names; may change between releases |
| 4 | KiCad Developer File Formats | https://dev-docs.kicad.org/en/file-formats/ | current | S-expression file formats |
| 5 | KiCad Schematic Editor | https://docs.kicad.org/9.0/en/eeschema/eeschema.html | KiCad 9.0 | ERC concepts; check KiCad 10 page for changes |
| 6 | KiCad Library Contribution Guide | https://www.kicad.org/libraries/contribute/ | current | Library repository and review process |
| 7 | KiCad Library Conventions (KLC) | https://klc.kicad.org/ | current | Guidance with exceptions; datasheet takes priority |
| 8 | Third-party kicad-cli reference | https://www.mintlify.com/KiCad/kicad-source-mirror/api/cli-reference | unknown | Conflicts with [1] on violation exit code (claims 2); not authoritative |
| 9 | SPICE3 User Guide (Berkeley) | https://www2.eecs.berkeley.edu/Pubs/TechRpts/1989/1220.html | 1989 | Historical language baseline only |
| 10 | ngspice User Manual | https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml | current | Analyses, options and defaults |
| 11 | ngspice(1) manual page | https://man.archlinux.org/man/ngspice.1.en | Arch package | Batch-mode command-line options |
| 12 | LTspice: How to Import Third-Party Models | https://www.analog.com/en/resources/technical-articles/ltspice-how-to-import-third-party-models.html | ADI article | LTspice model/pin mapping |
| 13 | High-Speed PCB Layout (ADI) | https://www.analog.com/en/resources/analog-dialogue/articles/high-speed-printed-circuit-board-layout.html | ADI article | Return paths, reference planes; not numeric rules for a given interface |
| 14 | High-Speed PCB Design Guidelines (TI SCAA082) | https://www.ti.com/lit/pdf/scaa082 | TI app note | Stackup and routing guidance |
| 15 | Power Integrity Analysis (TI SWPA222A) | https://www.ti.com/lit/an/swpa222a/swpa222a.pdf | rev A | PDN method; margins are example-specific |
| 16 | Thermal Design by Insight (TI SZZA009) | https://www.ti.com/lit/pdf/szza009 | TI app note | Heat paths; θJA limits |
| 17 | EMI/EMC and PCB Design (TI SNVA419) | https://www.ti.com/lit/pdf/snva419 | TI app note | Source–path–victim approach |
| 18 | The Gerber Format (Ucamco) | https://www.ucamco.com/en/gerber | current spec page | Gerber, X2 attributes, job file |
| 19 | IPC-2581 History | https://www.ipc2581.com/history/ | consortium page | Format scope; recipient support must be confirmed |
| 20 | Siemens ODB++ | https://www.siemens.com/en-us/products/pcb/odb-plus-plus/ | vendor page | Format scope |
| 21 | Fabrication and Assembly Files (Sierra Circuits) | https://www.protoexpress.com/kb/fabrication-assembly-files/ | vendor KB | Package checklist; supplier-specific |
| 22 | IEC 62402:2019 | https://webstore.iec.ch/en/publication/59531 | 2019 edition | Obsolescence framework, not a guarantee |
| 23 | DigiKey Counterfeit Control Plan | https://www.digikey.com/-/media/PDF/Sitemap/DigiKey-Counterfeit-Control-Plan.pdf | distributor policy | One distributor's controls |
| 24 | MCP Architecture | https://modelcontextprotocol.io/specification/2026-07-28/architecture | 2026-07-28 | Roles and connection model |
| 25 | MCP Authorization | https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization | 2026-07-28 | OAuth/OIDC requirements |
| 26 | MCP Tools | https://modelcontextprotocol.io/specification/2026-07-28/server/tools | 2026-07-28 | Tool safety responsibilities |
| 27 | MCP Transports | https://modelcontextprotocol.io/specification/2025-06-18/basic/transports | 2025-06-18 | Older version than 24–26: recorded conflict |
| 28 | MCP specification release 2026-07-28 | https://github.com/modelcontextprotocol/specification/releases/tag/2026-07-28 | release tag | Stateless core changes |
| 29 | AWS Event-Driven Architecture | https://aws.amazon.com/what-is/eda/ | vendor overview | Delivery-semantics caveats |
| 30 | SLSA Build Provenance v1.2 | https://slsa.dev/spec/v1.2/build-provenance | v1.2 | Provenance predicate shape |
| 31 | Kubernetes Persistent Volumes | https://kubernetes.io/docs/concepts/storage/persistent-volumes/ | current | Storage lifecycle |
| 32 | Kubernetes Secrets | https://kubernetes.io/docs/concepts/configuration/secret/ | current | etcd unencrypted by default |
| 33 | Docker Build Best Practices | https://docs.docker.com/build/building/best-practices/ | current | Digest pinning |
| 34 | Deterministic Build Systems | https://reproducible-builds.org/docs/deterministic-build-systems/ | current | Determinism sources |
| 35 | Google Cloud Workload Identity Federation | https://cloud.google.com/iam/docs/workload-identity-federation | current | Short-lived credentials |
| 36 | OWASP Secrets Management Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html | current | Secret handling |
| 37 | A Successful Git Branching Model | https://nvie.com/posts/a-successful-git-branching-model/ | 2010 (+note) | Gitflow lanes |
| 38 | gitflow-avh | https://github.com/petervanderdoes/gitflow-avh | archived | Tooling convention |
| 39 | Atlassian Gitflow Workflow | https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow | current | Trade-offs |
| 40 | Git Workflows | https://git-scm.com/docs/gitworkflows | current | Topic branches |
| 41 | GitHub Protected Branches | https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches | current | Review and check enforcement |
| 42 | GitHub Linking PRs to Issues | https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue | current | Default-branch auto-close |
| 43 | GitHub Projects | https://docs.github.com/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects | current | Project fields and views |
| 44 | GitHub REST API: pulls, reviews, check runs, branch protection | https://docs.github.com/en/rest | API version 2022-11-28 | Read-only sync endpoints |
| 45 | Grafana Dashboard Best Practices | https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/ | current | Dashboard purpose and drill-down |
| 46 | WCAG 2.2 Use of Color | https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html | WCAG 2.2 | Color not sole cue |
| 47 | WCAG 2.2 Non-text Contrast | https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html | WCAG 2.2 | 3:1 for graphical objects |
| 48 | WCAG 2.2 Status Messages | https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html | WCAG 2.2 | Live announcements |
| 49 | USWDS Step Indicator | https://designsystem.digital.gov/components/step-indicator/ | current | Linear flows only |
| 50 | IPC Document Revision Table | https://www.ipc.org/ipc-document-revision-table | current | Exact standard editions |
| 51 | KiCad PPA (kicad-10.0-releases) | https://launchpad.net/~kicad/+archive/ubuntu/kicad-10.0-releases | PPA | CI installation; versions move |
