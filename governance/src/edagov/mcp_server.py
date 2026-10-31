"""edagov governance MCP server (stdio, JSON-RPC 2.0, standard library only).

Runs beside Konnect. Konnect edits the design; this server gives the agent the
evidence side: inventory, authorized ERC/DRC/ngspice runs, ingestion, BOM and
manifest checks, gates and explanations, change-window requests, connector
proposals, snapshots and the dashboard.

Human decisions are deliberately NOT exposed as tools: approving gates or
change windows, reviews, sign-offs, exceptions, role grants and connector
approvals stay on the `edagov` CLI, run by the named person. `gov_pending_human_actions`
lists the exact commands they need to run.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback

from . import (__version__, bom, claims, connectors, gates, github, governance, inventory as inv_mod, kicad,
               manufacturing, records, snapshot, spice)
from .store import Store

SUPPORTED_PROTOCOLS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "edagov", "title": "EDA evidence governance", "version": __version__}

S = {"type": "string"}
B = {"type": "boolean"}
I = {"type": "integer"}
ROOT = {"type": "string", "description": "Design repository root holding .edagov/ (default: EDAGOV_ROOT or cwd)"}


def obj(props: dict, required=()):
    p = dict(props)
    p["root"] = ROOT
    return {"type": "object", "properties": p, "required": list(required), "additionalProperties": False}


def _root(args):
    return args.get("root") or os.environ.get("EDAGOV_ROOT") or os.getcwd()


def _st(args):
    return Store(_root(args))


def _brief(rec):
    return {k: rec.get(k) for k in ("id", "type", "state", "result_class", "severity", "claim_scope", "next_action",
                                    "limitations", "counts", "completeness", "window_state", "expires_at") if rec.get(k) is not None}


# ------------------------------------------------------------------ handlers
def h_status(a):
    st = _st(a)
    return {"governance": governance.status(st),
            "gates": [{k: e[k] for k in ("gate", "state", "automation_state", "next_action")} for e in gates.evaluate_all(st)]}


def h_doctor(a):
    return {"edagov": __version__, "kicad_cli": kicad.locate_cli(), "ngspice": spice.locate_ngspice(),
            "root": _root(a), "store": os.path.isdir(os.path.join(_root(a), ".edagov")),
            "actor": os.environ.get("EDAGOV_ACTOR")}


def h_init(a):
    st = Store.init(_root(a), product_id=a["product"], design_id=a["design"], board_id=a["board"], revision=a["revision"],
                    variant=a.get("variant", "default"), design_authority=a.get("authority", "unassigned"),
                    standards=a.get("standards"), owner=a.get("authority", "unassigned"))
    return {"store": str(st.dir), "identity": st.identity,
            "next_action": "Roles are empty (deny-by-default). A person grants them with the CLI: "
                           "edagov roles grant <email> contributor | design_reviewer | supply_reviewer | "
                           "manufacturing_reviewer | release_approver | connector_admin"}


def h_inventory(a):
    from .cli import cmd_inventory
    import argparse
    ns = argparse.Namespace(root=_root(a), project=a["project"], library_release=a.get("library_release"), json=False)
    rc = cmd_inventory(ns)
    st = _st(a)
    inv = [x for x in st.list("artifact") if x.get("report_kind") == "inventory"]
    latest = sorted(inv, key=lambda x: x.get("updated_at", ""))[-1] if inv else {}
    return {"complete": rc == 0, "inventory": _brief(latest), "findings": latest.get("findings", [])}


def h_run_check(a):
    return _brief(kicad.run_check(_st(a), a["kind"], a["project"], authorize=a.get("authorize"),
                                  parity=not a.get("no_parity", False)))


def h_export(a):
    rec = kicad.run_export(_st(a), a["kind"], a["project"], a["out"], authorize=a.get("authorize"), variant=a.get("variant"))
    return {**_brief(rec), "outputs": rec.get("outputs")}


def h_ingest_report(a):
    return _brief(kicad.ingest_report(_st(a), a["kind"], a["report"], a.get("project")))


def h_spice_manifest(a):
    return spice.manifest(a["netlist"])


def h_spice_run(a):
    return _brief(spice.run_ngspice(_st(a), a["netlist"], authorize=a.get("authorize"), retry_of=a.get("retry_of"),
                                    validation=a.get("validation"), justification=a.get("justification")))


def h_ingest_spice(a):
    return _brief(spice.ingest_log(_st(a), a["netlist"], a["log"], simulator=a.get("simulator", "ngspice"),
                                   version=a.get("tool_version"), exit_code=a.get("exit_code"), retry_of=a.get("retry_of"),
                                   validation=a.get("validation"), justification=a.get("justification")))


def h_ingest_bom(a):
    syms = inv_mod.inventory(a["project"])["symbols"] if a.get("project") else None
    res = bom.ingest_csv(_st(a), a["csv"], cross_check_symbols=syms)
    return {"lines": len(res["lines"]), "blocking_lines": res["blocking_lines"], "cross_check": res["cross_check"],
            "unmapped_required_columns": res["unmapped_required_columns"],
            "blocking": [{"id": l["id"], "findings": [f["message"] for f in l["findings"] if f["severity"] == "blocking"]}
                         for l in res["lines"] if l["severity"] == "blocking"]}


def h_ingest_github(a):
    rec = github.sync(_st(a), a["repo"], int(a["number"]))
    return {**_brief(rec), "sync_state": rec["sync_state"], "approvals_state": rec.get("approvals_state"),
            "blocking_checks": rec.get("blocking_checks"), "issue_links": rec.get("issue_links")}


def h_requirement(a):
    return _brief(records.requirement(_st(a), a.get("id"), a["text"], source=a["source"], owner=a["owner"],
                                      priority=a.get("priority", "medium"), method=a["method"], acceptance=a["acceptance"],
                                      status=a.get("status", "draft"), conditions=a.get("conditions"), standard=a.get("standard")))


def h_block(a):
    return _brief(records.block(_st(a), a.get("id"), a["name"], purpose=a["purpose"], owner=a["owner"],
                                interfaces=a.get("interfaces", []), allocated=a.get("allocated_requirements", [])))


def h_decision(a):
    return _brief(records.decision(_st(a), a["title"], rationale=a["rationale"], alternatives=a.get("alternatives", []),
                                   consequences=a["consequences"], tags=a.get("tags", []), did=a.get("id")))


def h_assumption(a):
    return _brief(records.assumption(_st(a), a["text"], owner=a["owner"], review_condition=a["review_condition"], aid=a.get("id")))


def h_evidence(a):
    return _brief(records.evidence(_st(a), a["path"], kind=a.get("artifact_kind", "report"), tags=a.get("tags", []),
                                   owner=a["owner"], claim_scope=a["claim"], aid=a.get("id"), standard=a.get("standard"),
                                   method=a.get("method")))


def h_issue(a):
    return _brief(records.issue(_st(a), a["title"], severity=a["severity"], owner=a["owner"], affected=a.get("affected", []),
                                gates=a.get("gates"), due=a.get("due"), containment=a.get("containment"), iid=a.get("id")))


def h_gates(a):
    evs = gates.evaluate_all(_st(a), persist=a.get("persist", False))
    return [{k: e[k] for k in ("gate", "state", "automation_state", "blocking", "missing_evidence", "next_action", "approval_note")}
            for e in evs]


def h_explain(a):
    return gates.evaluate_gate(_st(a), a["gate"])["explanation"]


def h_manifest(a):
    rec = manufacturing.build(_st(a), a["outputs"], variant=a.get("variant"),
                              origin=a.get("origin", "unknown — record drill/placement origin"),
                              supplier_assumptions=a.get("supplier_assumptions"))
    return {**_brief(rec), "files": len(rec["files"]), "findings": rec["consistency_findings"]}


def h_dfm(a):
    if a["disposition"] not in ("open", "corrected"):
        raise ValueError("agents may record open or corrected findings; accepted/waived needs a named approver via the CLI")
    return _brief(manufacturing.add_dfm_finding(_st(a), a["package"], rule=a["rule"], description=a["description"],
                                                disposition=a["disposition"], rationale=a.get("rationale", ""), tool=a.get("tool")))


def h_snapshot(a):
    filters = {k: a[k] for k in ("revision", "owner", "severity") if a.get(k)}
    res = snapshot.build(_st(a), a.get("out") or os.path.join(_root(a), "snapshots"), filters=filters)
    return {"zip": res["zip"], "records": len(res["manifest"]["records"]), "redactions": len(res["manifest"]["redactions"]),
            "audit_chain_verified": res["manifest"]["audit_chain"]["verified"]}


def h_dashboard(a):
    from .dashboard import render
    out = a.get("out") or os.path.join(_root(a), "dashboard.html")
    return {"dashboard": str(render(_st(a), out, standalone=not a.get("fragment", False)))}


def h_lint(a):
    hits = claims.lint_claims(a["text"])
    return {"clean": not hits, "findings": hits}


def h_scan(a):
    hits = claims.scan_paths(a["paths"])
    return {"clean": not hits, "findings": hits}


def h_window_request(a):
    return _brief(governance.request_window(_st(a), scope=a["scope"], reason=a["reason"], issue=a.get("issue"),
                                            hours=a.get("hours", 8), max_calls=a.get("max_calls", 500),
                                            files=a.get("files"), branch=a.get("branch")))


def h_window_status(a):
    return governance.status(_st(a))


def h_window_close(a):
    return _brief(governance.close_window(_st(a), a["id"], reason=a.get("reason", "")))


def h_propose(a):
    rec = connectors.propose(_st(a), connector_id=a["connector"], action=a["action"], target=a["target"],
                             inputs=a.get("inputs", {}), side_effects=a.get("side_effects", []),
                             reversible=a.get("reversible", False), compensation=a.get("compensation"),
                             dry_run_available=a.get("dry_run_available", False))
    return {"proposal": connectors.render_proposal(rec), "id": rec["id"], "requires_human_approval": rec["requires_human_approval"]}


def h_check(a):
    ok, why = connectors.check(_st(a), a["id"])
    return {"allowed": ok, "reason": why}


def h_outcome(a):
    return _brief(connectors.record_outcome(_st(a), a["id"], result=a["result"], evidence=a.get("evidence", ""),
                                            external_id=a.get("external_id"), error=a.get("error")))


def h_ledger(a):
    led = governance.Ledger(_st(a))
    ok, problems = led.verify()
    return {"verified": ok, "problems": problems, "entries": led.entries()[-int(a.get("limit", 30)):]}


def h_audit(a):
    st = _st(a)
    ok, problems = st.audit.verify()
    lok, lproblems = governance.Ledger(st).verify()
    return {"audit_chain_verified": ok, "audit_problems": problems, "konnect_ledger_verified": lok, "ledger_problems": lproblems}


def h_pending(a):
    st = _st(a)
    out = []
    for w in governance.windows(st):
        if w["window_state"] == "requested":
            out.append({"who": "design_reviewer or release_approver (not the requester)",
                        "command": f"edagov konnect window approve {w['id']}", "why": w["reason"]})
    for e in gates.evaluate_all(st):
        if e["state"] == "ready_for_review":
            out.append({"who": f"approver for gate {e['gate']}", "command": f"edagov approve {e['gate']} --decision approved --note \"...\"",
                        "why": "automation shows ready_for_review"})
    for c in st.list("connector_action"):
        if c.get("action_state") == "proposed":
            out.append({"who": "release_approver (not the proposer)", "command": f"edagov connector approve --id {c['id']}",
                        "why": f"{c['action']} → {c['target']}"})
    for p in st.list("manufacturing_package"):
        for role, s in (p.get("signoffs") or {}).items():
            if s.get("state") != "approved":
                out.append({"who": role, "command": f"edagov signoff {p['id']} {role} --decision approved", "why": "release sign-off"})
    for r in st.list("artifact") + st.list("run"):
        if r.get("tags") and not r.get("reviewer") and not r.get("superseded"):
            out.append({"who": "design_reviewer", "command": f"edagov review {r['id']} --role design_reviewer --state approved",
                        "why": f"evidence {r.get('tags')} awaiting review"})
    return out


# ------------------------------------------------------------------ catalog
TOOLS = {
    "gov_status": ("Governance overview: design identity, actor roles, change windows, ledger integrity and gate states.", obj({}), h_status),
    "gov_doctor": ("Toolchain and store check: kicad-cli, ngspice, store presence, acting identity.", obj({}), h_doctor),
    "gov_init": ("Initialise an evidence store for a design. Roles start empty; a person grants them via the CLI.",
                 obj({"product": S, "design": S, "board": S, "revision": S, "variant": S, "authority": S,
                      "standards": {"type": "array", "items": S}}, ["product", "design", "board", "revision"]), h_init),
    "gov_inventory": ("Read-only KiCad project inventory: files and hashes, sheets, libraries, versions, Edge.Cuts, stackup.",
                      obj({"project": S, "library_release": S}, ["project"]), h_inventory),
    "gov_run_check": ("Execute ERC or DRC with kicad-cli and record provenance. Requires an authorization reason from the user.",
                      obj({"kind": {"type": "string", "enum": ["erc", "drc"]}, "project": S, "authorize": S, "no_parity": B},
                          ["kind", "project", "authorize"]), h_run_check),
    "gov_export": ("Generate fabrication/assembly outputs with kicad-cli (gerbers, drill, pos, bom, netlist, ipc2581, odb, step) with provenance.",
                   obj({"kind": {"type": "string", "enum": sorted(kicad.EXPORTS)}, "project": S, "out": S, "authorize": S, "variant": S},
                       ["kind", "project", "out", "authorize"]), h_export),
    "gov_ingest_report": ("Documentation-only: record an existing ERC/DRC report (JSON preferred).",
                          obj({"kind": {"type": "string", "enum": ["erc", "drc"]}, "report": S, "project": S}, ["kind", "report"]), h_ingest_report),
    "gov_spice_manifest": ("Check a SPICE netlist: includes, ground, analyses, options, subcircuit pin counts.", obj({"netlist": S}, ["netlist"]), h_spice_manifest),
    "gov_spice_run": ("Run ngspice in batch mode with provenance; keep failures; link retries.",
                      obj({"netlist": S, "authorize": S, "retry_of": S, "validation": S, "justification": S}, ["netlist", "authorize"]), h_spice_run),
    "gov_ingest_spice": ("Documentation-only: record an existing simulator log against its netlist.",
                         obj({"netlist": S, "log": S, "simulator": S, "tool_version": S, "exit_code": I, "retry_of": S,
                              "validation": S, "justification": S}, ["netlist", "log"]), h_ingest_spice),
    "gov_ingest_bom": ("Ingest a BOM CSV and check exact MPNs, lifecycle evidence, alternates and sources; cross-check the schematic.",
                       obj({"csv": S, "project": S}, ["csv"]), h_ingest_bom),
    "gov_ingest_github": ("Read-only sync of a GitHub pull request: current-diff approvals, required checks, Gitflow lane, issue links.",
                          obj({"repo": S, "number": I}, ["repo", "number"]), h_ingest_github),
    "gov_record_requirement": ("Record a requirement with a verification method and measurable acceptance.",
                               obj({"id": S, "text": S, "source": S, "owner": S, "priority": S,
                                    "method": {"type": "string", "enum": ["inspection", "analysis", "simulation", "test", "demonstration", "supplier_confirmation", "review"]},
                                    "acceptance": S, "status": S, "conditions": S, "standard": S},
                                   ["text", "source", "owner", "method", "acceptance"]), h_requirement),
    "gov_record_block": ("Record an architecture block and the requirements allocated to it.",
                         obj({"id": S, "name": S, "purpose": S, "owner": S, "interfaces": {"type": "array", "items": S},
                              "allocated_requirements": {"type": "array", "items": S}}, ["name", "purpose", "owner"]), h_block),
    "gov_record_decision": ("Record a design decision with rationale, alternatives and consequences.",
                            obj({"id": S, "title": S, "rationale": S, "alternatives": {"type": "array", "items": S}, "consequences": S,
                                 "tags": {"type": "array", "items": S}}, ["title", "rationale", "consequences"]), h_decision),
    "gov_record_assumption": ("Record an assumption with an owner and a review condition.",
                              obj({"id": S, "text": S, "owner": S, "review_condition": S}, ["text", "owner", "review_condition"]), h_assumption),
    "gov_record_evidence": ("Attach evidence (file or URL) with tags such as stackup, pi_analysis, si_analysis, thermal_analysis, emc_plan.",
                            obj({"id": S, "path": S, "artifact_kind": S, "tags": {"type": "array", "items": S}, "owner": S, "claim": S,
                                 "standard": S, "method": S}, ["path", "owner", "claim"]), h_evidence),
    "gov_issue_open": ("Open an engineering issue with owner, severity, affected records and gates.",
                       obj({"id": S, "title": S, "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "owner": S,
                            "affected": {"type": "array", "items": S}, "gates": {"type": "array", "items": S}, "due": S, "containment": S},
                           ["title", "severity", "owner"]), h_issue),
    "gov_gates": ("Evaluate all eight gates. Automation reaches at most ready_for_review.", obj({"persist": B}), h_gates),
    "gov_explain": ("Deterministic explanation of one gate: rule, inputs, results, missing evidence, next action.",
                    obj({"gate": {"type": "string", "enum": list(gates.GATE_ORDER)}}, ["gate"]), h_explain),
    "gov_manifest": ("Build the hashed manufacturing manifest and reconcile revisions, units and references.",
                     obj({"outputs": S, "variant": S, "origin": S, "supplier_assumptions": {"type": "array", "items": S}}, ["outputs"]), h_manifest),
    "gov_dfm_finding": ("Record a DFM/DFA finding as open or corrected (accepted/waived needs a named approver via the CLI).",
                        obj({"package": S, "rule": S, "description": S, "disposition": {"type": "string", "enum": ["open", "corrected"]},
                             "rationale": S, "tool": S}, ["package", "rule", "description", "disposition"]), h_dfm),
    "gov_snapshot": ("Export a read-only review snapshot (needs a reviewer, approver or auditor identity).",
                     obj({"out": S, "revision": S, "owner": S, "severity": S}), h_snapshot),
    "gov_dashboard": ("Render the static review dashboard.", obj({"out": S, "fragment": B}), h_dashboard),
    "gov_lint_claims": ("Flag unscoped claims (compliant, manufacturable, drop-in, ...) in text before it is sent.", obj({"text": S}, ["text"]), h_lint),
    "gov_scan_secrets": ("Scan files or folders for credential-shaped content.", obj({"paths": {"type": "array", "items": S}}, ["paths"]), h_scan),
    "gov_window_request": ("Request a design change window so Konnect may edit the design. A different person must approve it.",
                           obj({"scope": {"type": "array", "items": S, "description": "toolsets (e.g. sch_wiring), tool:<name>, or *"},
                                "reason": S, "issue": S, "hours": {"type": "number"}, "max_calls": I,
                                "files": {"type": "array", "items": S, "description": "globs relative to the repo root"}, "branch": S},
                               ["scope", "reason"]), h_window_request),
    "gov_window_status": ("Show change windows, active scope, calls used, and pending approvals.", obj({}), h_window_status),
    "gov_window_close": ("Close a change window when the edit session is done.", obj({"id": S, "reason": S}, ["id"]), h_window_close),
    "gov_connector_propose": ("Propose a consequential connector action (publish/purchase/release/delete/create/change) for human approval.",
                              obj({"connector": S, "action": {"type": "string", "enum": ["read", "create", "change", "publish", "purchase", "release", "delete"]},
                                   "target": S, "inputs": {"type": "object", "additionalProperties": S},
                                   "side_effects": {"type": "array", "items": S}, "reversible": B, "compensation": S, "dry_run_available": B},
                                  ["connector", "action", "target"]), h_propose),
    "gov_connector_check": ("Check whether an approved connector action may execute now (call immediately before executing).",
                            obj({"id": S}, ["id"]), h_check),
    "gov_connector_outcome": ("Record the outcome of an executed connector action with evidence; success without evidence is refused.",
                              obj({"id": S, "result": {"type": "string", "enum": ["success", "failed", "unknown", "compensated", "dead_lettered"]},
                                   "evidence": S, "external_id": S, "error": S}, ["id", "result"]), h_outcome),
    "gov_ledger": ("Show the Konnect call ledger: authorizations, denials, changed files, captured evidence.", obj({"limit": I}), h_ledger),
    "gov_audit_verify": ("Verify the audit chain and the Konnect call ledger.", obj({}), h_audit),
    "gov_pending_human_actions": ("List decisions only a person can make, with the exact CLI command and who must run it.", obj({}), h_pending),
}


def tool_list():
    return [{"name": n, "description": d, "inputSchema": schema} for n, (d, schema, _) in TOOLS.items()]


def call(name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Unknown tool {name}"}], "isError": True}
    schema = TOOLS[name][1]
    missing = [k for k in schema.get("required", []) if k not in args]
    unknown = [k for k in args if k not in schema["properties"]]
    if missing or unknown:
        msg = (f"missing required: {missing}. " if missing else "") + (f"unknown arguments: {unknown}" if unknown else "")
        return {"content": [{"type": "text", "text": msg.strip()}], "isError": True}
    try:
        # Never let library code print onto the protocol stream.
        with contextlib.redirect_stdout(io.StringIO()):
            res = TOOLS[name][2](args)
        text = res if isinstance(res, str) else json.dumps(res, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:  # noqa: BLE001 — every failure goes back to the client as a tool error
        kind = type(e).__name__
        return {"content": [{"type": "text", "text": f"{kind}: {e}"}], "isError": True}


def handle(msg: dict) -> dict | None:
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if mid is None:  # notification
        return None
    try:
        if method == "initialize":
            req = params.get("protocolVersion")
            ver = req if req in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[2]
            result = {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO,
                      "instructions": ("Evidence and governance for KiCad designs edited through Konnect. Request a change "
                                       "window (gov_window_request) before editing; a person approves it. Never present "
                                       "automated results as approvals.")}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tool_list()}
        elif method == "tools/call":
            result = call(params.get("name", ""), params.get("arguments") or {})
        elif method in ("resources/list",):
            result = {"resources": []}
        elif method in ("prompts/list",):
            result = {"prompts": []}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if isinstance(msg, list):
                resp = [r for r in (handle(m) for m in msg) if r is not None] or None
            else:
                resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(serve())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:  # pragma: no cover
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
