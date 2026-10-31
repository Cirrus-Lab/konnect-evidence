# edagov command reference

Generated from the CLI parser (`edagov <command> -h` shows the same). Run as `edagov` (installed), `governance/bin/edagov` (POSIX) or `python governance/bin/edagov.py` (any OS). Global options: `--root DIR` (or `EDAGOV_ROOT`), `--json`.

Agents normally use the equivalent `gov_*` MCP tools; the CLI is where people record decisions (approve, review, signoff, exception, roles, konnect window approve, connector approve).

Exit codes: 0 ok · 1 error · 2 permission denied / not authorized · 3 gate blocked (with `--fail-on-blocked`), incomplete inventory/manifest, broken ledger, or lint/scan findings · 4 tool missing.

Environment: `EDAGOV_ACTOR` (who is acting), `EDAGOV_EXECUTION=allow:<reason>` (CI-wide execution authorization), `KICAD_CLI`, `NGSPICE` (tool paths), `EDAGOV_NOW` (fixed timestamp for reproducible tests), `GITHUB_TOKEN`/`GH_TOKEN` (read-only sync; never stored).

## `edagov doctor`

```
edagov doctor [-h]
```

## `edagov init`

```
edagov init [-h] --product PRODUCT --design DESIGN --board BOARD
                   --revision REVISION [--variant VARIANT]
                   [--assembly ASSEMBLY] [--authority AUTHORITY]
                   [--repository REPOSITORY] [--standard STANDARD]
                   [--grant GRANT]
```

## `edagov roles`

```
edagov roles [-h] {show,grant,revoke} [actor] [role]
```

## `edagov revision`

```
edagov revision [-h] [--variant VARIANT] --reason REASON revision
```

## `edagov inventory`

```
edagov inventory [-h] --project PROJECT
                        [--library-release LIBRARY_RELEASE]
```

## `edagov run`

```
edagov run [-h] --project PROJECT [--authorize AUTHORIZE]
                  [--severity {error,warning,exclusions,all}] [--no-parity]
                  [--refill-zones]
                  {erc,drc}
```

## `edagov export`

```
edagov export [-h] --project PROJECT --out OUT [--authorize AUTHORIZE]
                     [--variant VARIANT] [--extra ...]
                     {bom,drill,gerbers,ipc2581,netlist,odb,pos,spice_netlist,step}
```

## `edagov spice`

```
edagov spice [-h] [--authorize AUTHORIZE] [--retry-of RETRY_OF]
                    [--validation VALIDATION] [--justification JUSTIFICATION]
                    {manifest,run} netlist
```

## `edagov ingest`

```
edagov ingest [-h] [--project PROJECT] [--log LOG]
                     [--simulator SIMULATOR] [--tool-version TOOL_VERSION]
                     [--exit-code EXIT_CODE] [--retry-of RETRY_OF]
                     [--validation VALIDATION] [--justification JUSTIFICATION]
                     [--from-json FROM_JSON]
                     {erc,drc,spice,bom,github} path [number]
```

## `edagov manifest`

```
edagov manifest [-h] --outputs OUTPUTS [--variant VARIANT]
                       [--origin ORIGIN]
                       [--supplier-assumption SUPPLIER_ASSUMPTION]
```

## `edagov dfm`

```
edagov dfm [-h] [--rule RULE] [--description DESCRIPTION] [--tool TOOL]
                  [--disposition {open,corrected,accepted,waived}]
                  [--rationale RATIONALE] [--approver APPROVER]
                  [--decision {approved,requested_changes,in_progress}]
                  [--note NOTE]
                  {add,plotted-view} package
```

## `edagov signoff`

```
edagov signoff [-h] --decision {approved,requested_changes,blocked}
                      [--note NOTE]
                      package
                      {design_owner,fabrication_dfm,assembly_dfa,release_control}
```

## `edagov record`

```
edagov record [-h] [--id ID] [--text TEXT] [--source SOURCE]
                     [--owner OWNER] [--priority PRIORITY] [--method METHOD]
                     [--acceptance ACCEPTANCE] [--status STATUS]
                     [--conditions CONDITIONS] [--standard STANDARD]
                     [--name NAME] [--purpose PURPOSE] [--interface INTERFACE]
                     [--allocate ALLOCATE] [--title TITLE]
                     [--rationale RATIONALE] [--alternative ALTERNATIVE]
                     [--consequences CONSEQUENCES] [--tag TAG]
                     [--review-condition REVIEW_CONDITION] [--path PATH]
                     [--artifact-kind ARTIFACT_KIND] [--claim CLAIM]
                     [--license LICENSE]
                     {requirement,block,decision,assumption,evidence,library}
```

## `edagov issue`

```
edagov issue [-h] [--id ID] [--severity {low,medium,high,critical}]
                    [--owner OWNER] [--affected AFFECTED] [--gate GATE]
                    [--due DUE] [--containment CONTAINMENT]
                    [--external EXTERNAL] [--disposition DISPOSITION]
                    [--evidence EVIDENCE]
                    {open,close} [title]
```

## `edagov exception`

```
edagov exception [-h] [--id ID] --rationale RATIONALE --affects AFFECTS
                        --review-trigger REVIEW_TRIGGER
                        [--limitation LIMITATION]
                        title
```

## `edagov review`

```
edagov review [-h]
                     --state {approved,requested_changes,in_progress,abstained,blocked}
                     --role {design_reviewer,supply_reviewer,manufacturing_reviewer,release_approver}
                     [--comments COMMENTS] [--request REQUEST]
                     target
```

## `edagov gates`

```
edagov gates [-h] [--persist] [--fail-on-blocked]
```

## `edagov explain`

```
edagov explain [-h]
                      {requirements,architecture,schematic_library,simulation,pcb,supply,release,change}
```

## `edagov approve`

```
edagov approve [-h]
                      --decision {approved,approved_with_exception,rejected}
                      [--note NOTE] [--exception EXCEPTION]
                      {requirements,architecture,schematic_library,simulation,pcb,supply,release,change}
```

## `edagov connector`

```
edagov connector [-h] [--id ID] [--provider PROVIDER]
                        [--protocol PROTOCOL]
                        [--protocol-version PROTOCOL_VERSION]
                        [--transport {stdio,streamable-http,http,https,sse}]
                        [--endpoint ENDPOINT] [--scope SCOPE]
                        [--data-class DATA_CLASS]
                        [--trust-tier {untrusted,verified_read,verified_write}]
                        [--secret-ref SECRET_REF] [--state STATE]
                        [--error ERROR] [--correlation CORRELATION]
                        [--verb {read,create,change,publish,purchase,release,delete}]
                        [--target TARGET] [--input INPUT]
                        [--side-effect SIDE_EFFECT] [--reversible]
                        [--compensation COMPENSATION] [--dry-run-available]
                        [--decision {approved,rejected}] [--note NOTE]
                        [--result {success,failed,unknown,compensated,dead_lettered}]
                        [--evidence EVIDENCE] [--external-id EXTERNAL_ID]
                        {register,sync,propose,approve,check,outcome}
```

## `edagov lint-claims`

```
edagov lint-claims [-h] paths [paths ...]
```

## `edagov scan-secrets`

```
edagov scan-secrets [-h] paths [paths ...]
```

## `edagov snapshot`

```
edagov snapshot [-h] [--out OUT] [--revision REVISION] [--owner OWNER]
                       [--severity SEVERITY] [--type TYPE]
```

## `edagov diff`

```
edagov diff [-h] [--dashboard DASHBOARD] before after
```

## `edagov dashboard`

```
edagov dashboard [-h] [--out OUT] [--fragment]
```

## `edagov audit`

```
edagov audit [-h] [--limit LIMIT] {verify,log}
```

## `edagov status`

```
edagov status [-h]
```

## `edagov konnect`

```
edagov konnect [-h] {window,authorize,record,ledger} ...
```

## `edagov konnect window`

```
edagov konnect window [-h] [--scope SCOPE] [--reason REASON]
                             [--issue ISSUE] [--branch BRANCH] [--hours HOURS]
                             [--max-calls MAX_CALLS] [--files FILES]
                             [--decision {approved,rejected}] [--note NOTE]
                             {request,approve,close,status} [id]
```

## `edagov konnect authorize`

```
edagov konnect authorize [-h] --tool TOOL [--toolset TOOLSET]
                                --effect EFFECT --call-id CALL_ID
                                [--path PATH] [--format {kv,json}]
                                [--audit-only]
```

## `edagov konnect record`

```
edagov konnect record [-h] --tool TOOL [--toolset TOOLSET]
                             --effect EFFECT --call-id CALL_ID [--path PATH]
                             --status {ok,error} [--capture]
                             [--format {kv,json}]
```

## `edagov konnect ledger`

```
edagov konnect ledger [-h] [--limit LIMIT] [--verify]
```

## `edagov mcp`

```
edagov mcp [-h]
```
