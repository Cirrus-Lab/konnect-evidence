"""edagov command-line interface.

Exit codes: 0 ok · 1 error · 2 permission denied / not authorized · 3 gate blocked
(with --fail-on-blocked) or findings present (lint/scan) · 4 tool missing.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from . import (bom, claims, connectors, executor, gates, github, inventory as inv_mod, kicad, manufacturing,
               permissions, records, snapshot, spice)
from .dashboard import render
from . import governance
from .store import Store, StoreError, dumps
from .util import file_hash, new_id, now_iso, write_json


def _store(a) -> Store:
    return Store(a.root)


def out(obj, a=None):
    if a is not None and getattr(a, "json", False):
        print(dumps(obj))
    elif isinstance(obj, str):
        print(obj)
    else:
        print(dumps(obj))


def brief(rec: dict) -> str:
    keys = ("id", "type", "state", "result_class", "severity", "next_action")
    return " | ".join(f"{k}={rec.get(k)}" for k in keys if rec.get(k) is not None)


# ------------------------------------------------------------------ commands
def cmd_doctor(a):
    def ver(cmd):
        exe = shutil.which(cmd[0]) if os.path.sep not in cmd[0] else cmd[0]
        if not exe:
            return None
        try:
            r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=30)
            return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else exe
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"
    cli = kicad.locate_cli()
    ng = spice.locate_ngspice()
    report = {
        "edagov": __version__, "python": platform.python_version(), "platform": platform.platform(),
        "kicad_cli": {"path": cli, "version": ver([cli, "version"]) if cli else None},
        "ngspice": {"path": ng, "version": ver([ng, "-v"]) if ng else None},
        "git": ver(["git", "--version"]), "gh": ver(["gh", "--version"]),
        "execution_env": os.environ.get("EDAGOV_EXECUTION"), "actor": permissions.current_actor()[0],
    }
    report["ready_for_execution"] = bool(cli)
    report["notes"] = []
    if not cli:
        report["notes"].append("kicad-cli missing: install KiCad 10 (see skills/eda-toolchain-setup) or set KICAD_CLI. "
                               "Documentation-only ingestion still works.")
    if not ng:
        report["notes"].append("ngspice missing: simulation runs cannot execute; logs can still be ingested.")
    out(report)
    return 0


def cmd_init(a):
    roles = {"actors": {}}
    for g in a.grant or []:
        actor, _, role = g.rpartition("=")
        if role not in permissions.POLICY["read"] and role not in ("connector_admin", "auditor"):
            raise SystemExit(f"unknown role {role}")
        roles["actors"].setdefault(actor, []).append(role)
    st = Store.init(a.root, product_id=a.product, design_id=a.design, board_id=a.board, revision=a.revision,
                    variant=a.variant, assembly_id=a.assembly, design_authority=a.authority, repository=a.repository,
                    standards=a.standard, owner=a.authority, roles=roles)
    out(f"Initialised evidence store at {st.dir}\n" + dumps(st.identity))
    return 0


def cmd_roles(a):
    st = _store(a)
    if a.action == "show":
        out(st.roles_doc)
        return 0
    actor_, verified, _ = st.check("approve_release")
    doc = st.roles_doc
    roles = doc.setdefault("actors", {}).setdefault(a.actor, [])
    before = json.loads(json.dumps(doc))
    if a.action == "grant" and a.role not in roles:
        roles.append(a.role)
    if a.action == "revoke" and a.role in roles:
        roles.remove(a.role)
    write_json(st.dir / "roles.json", doc)
    st.audit.append(actor=actor_, actor_verified=verified, action=f"roles.{a.action}", object_type="permission",
                    object_id=a.actor, before=before, after=doc, reason=f"{a.action} {a.role}")
    out(doc)
    return 0


def cmd_revision(a):
    st = _store(a)
    before = st.identity
    ident = st.set_revision(a.revision, a.variant, reason=a.reason)
    ident = dict(ident, previous_revision=before["revision"])
    write_json(st.dir / "design.json", ident)
    out(ident)
    return 0


def cmd_inventory(a):
    st = _store(a)
    st.check("record_evidence")
    inv = inv_mod.inventory(a.project)
    ident = st.identity
    run_id = new_id("run")
    rdir = st.run_dir(run_id)
    write_json(rdir / "inventory.json", inv)
    rec = {
        "type": "artifact", "id": new_id("artifact", f"inventory-{ident['revision']}"), "kind": "report",
        "report_kind": "inventory", "path": str(rdir / "inventory.json"), "hash": file_hash(rdir / "inventory.json"),
        "source_revision": inv["git"].get("commit") or "untracked", "owner": ident.get("design_authority"),
        "project_dir": inv["project_dir"], "project_file": inv.get("project_file"),
        "kicad_generator_versions": inv.get("kicad_generator_versions"), "sheet_count": len(inv.get("sheets", [])),
        "symbol_count": len([s for s in inv.get("symbols", []) if not s.get("power_symbol")]),
        "board_summary": {k: v for k, v in (inv.get("board") or {}).items() if k not in ("footprints", "models")},
        "findings": inv["findings"], "complete": inv["complete"], "local_only_files": inv.get("local_only_files"),
        "library_release_pinned": a.library_release,
        "state": "ready_for_review" if inv["complete"] else "blocked",
        "severity": "blocking" if not inv["complete"] else ("attention" if inv["findings"] else "info"),
        "timestamp": now_iso(), "source": "edagov inventory (read-only)", "linked_evidence": [inv["project_dir"]],
        "next_action": next((f["next_action"] for f in inv["findings"] if f["severity"] == "blocking"),
                            inv["findings"][0]["next_action"] if inv["findings"] else "Design reviewer checks inventory."),
        "claim_scope": "Inventory records structure, versions and hashes. It does not infer electrical meaning.",
    }
    st.put(rec, reason="project inventory")
    ctrl = {"project", "schematic", "pcb", "rules", "configuration", "symbol_library", "footprint_library", "jobset", "worksheet"}
    n = 0
    for f in inv["files"]:
        if f["kind"] in ctrl and f["distribution"] == "controlled":
            st.put({"type": "artifact", "id": new_id("artifact", f"{f['path']}-{ident['revision']}"), "kind": f["kind"],
                    "path": f["path"], "hash": f["hash"], "source_revision": rec["source_revision"],
                    "owner": ident.get("design_authority"), "bytes": f["bytes"],
                    "provenance": "project-local" if f["kind"] in ("symbol_library", "footprint_library") else None,
                    "license": None}, reason="inventory file")
            n += 1
    if getattr(a, "json", False):
        out(inv, a)
    else:
        print(f"Inventory of {inv['project_dir']}: {len(inv['files'])} files, {n} controlled artifacts recorded, "
              f"complete={inv['complete']}")
        for f in inv["findings"]:
            print(f"  [{f['severity']:>9}] {f['message']}\n              → {f['next_action']}")
    return 0 if inv["complete"] else 3


def cmd_run(a):
    st = _store(a)
    rec = kicad.run_check(st, a.kind, a.project, authorize=a.authorize, severities=a.severity or ["error", "warning"],
                          parity=not a.no_parity, refill_zones=a.refill_zones)
    out(rec if getattr(a, "json", False) else brief(rec) + "\n" + rec["claim_scope"])
    return 0


def cmd_export(a):
    st = _store(a)
    rec = kicad.run_export(st, a.kind, a.project, a.out, authorize=a.authorize, variant=a.variant, extra=a.extra)
    out(rec if getattr(a, "json", False) else brief(rec) + f"\n{len(rec.get('outputs', []))} output file(s)")
    return 0 if rec["result_class"] == "clean" else 1


def cmd_spice(a):
    st = _store(a)
    if a.action == "manifest":
        out(spice.manifest(a.netlist))
        return 0
    rec = spice.run_ngspice(st, a.netlist, authorize=a.authorize, retry_of=a.retry_of, validation=a.validation,
                            justification=a.justification)
    out(rec if getattr(a, "json", False) else brief(rec) + "\n" + rec["claim_scope"])
    return 0


def cmd_ingest(a):
    st = _store(a)
    if a.what in ("erc", "drc"):
        rec = kicad.ingest_report(st, a.what, a.path, a.project, tool_version_hint=a.tool_version)
        out(brief(rec) + "\n" + rec["claim_scope"])
    elif a.what == "spice":
        rec = spice.ingest_log(st, a.path, a.log, simulator=a.simulator, version=a.tool_version, exit_code=a.exit_code,
                               retry_of=a.retry_of, validation=a.validation, justification=a.justification)
        out(brief(rec))
    elif a.what == "bom":
        syms = inv_mod.inventory(a.project)["symbols"] if a.project else None
        res = bom.ingest_csv(st, a.path, cross_check_symbols=syms)
        print(f"{len(res['lines'])} BOM line(s), {res['blocking_lines']} blocking")
        if res["unmapped_required_columns"]:
            print(f"  unmapped required columns: {res['unmapped_required_columns']}")
        if res["cross_check"]:
            print(f"  schematic cross-check: {res['cross_check']}")
    elif a.what == "github":
        rec = github.sync(st, a.path, int(a.number), from_json=a.from_json)
        out(brief(rec) + f"\nsync_state={rec['sync_state']} approvals={rec.get('approvals_state')}")
    return 0


def cmd_manifest(a):
    st = _store(a)
    rec = manufacturing.build(st, a.outputs, variant=a.variant, origin=a.origin, supplier_assumptions=a.supplier_assumption)
    print(f"{rec['id']}: {len(rec['files'])} file(s), completeness={rec['completeness']}")
    for f in rec["consistency_findings"]:
        print(f"  [{f['severity']:>9}] {f['message']}")
    return 0 if rec["completeness"] == "complete" else 3


def cmd_dfm(a):
    st = _store(a)
    if a.action == "add":
        rec = manufacturing.add_dfm_finding(st, a.package, rule=a.rule, description=a.description,
                                            disposition=a.disposition, rationale=a.rationale or "", approver=a.approver, tool=a.tool)
    else:
        st.check("review:manufacturing")
        pkg = dict(st.get("manufacturing_package", a.package))
        pkg["plotted_view_review"] = a.decision
        pkg["plotted_view_note"] = a.note
        rec = st.put(pkg, action="review:manufacturing", reason=f"plotted-view review {a.decision}")
    out(brief(rec))
    return 0


def cmd_signoff(a):
    rec = manufacturing.signoff(_store(a), a.package, a.role, a.decision, a.note or "")
    out(brief(rec) + f"\nsignoffs={ {k: v['state'] for k, v in rec['signoffs'].items()} }")
    return 0


def cmd_record(a):
    st = _store(a)
    k = a.kind
    if k == "requirement":
        rec = records.requirement(st, a.id, a.text, source=a.source, owner=a.owner, priority=a.priority, method=a.method,
                                  acceptance=a.acceptance, status=a.status, conditions=a.conditions, standard=a.standard)
    elif k == "block":
        rec = records.block(st, a.id, a.name, purpose=a.purpose, owner=a.owner, interfaces=a.interface or [],
                            allocated=a.allocate or [])
    elif k == "decision":
        rec = records.decision(st, a.title, rationale=a.rationale, alternatives=a.alternative or [],
                               consequences=a.consequences, tags=a.tag or [], did=a.id)
    elif k == "assumption":
        rec = records.assumption(st, a.text, owner=a.owner, review_condition=a.review_condition, aid=a.id)
    elif k == "library":
        rec = records.library(st, a.path, provenance=a.source, license=a.license, reviewer_note=a.rationale)
    elif k == "evidence":
        rec = records.evidence(st, a.path, kind=a.artifact_kind, tags=a.tag or [], owner=a.owner, claim_scope=a.claim,
                               aid=a.id, standard=a.standard, method=a.method)
    out(brief(rec))
    return 0


def cmd_issue(a):
    st = _store(a)
    if a.action == "open":
        rec = records.issue(st, a.title, severity=a.severity, owner=a.owner, affected=a.affected or [], gates=a.gate,
                            due=a.due, containment=a.containment, iid=a.id, external=a.external)
    else:
        rec = records.close_issue(st, a.id, disposition=a.disposition, closure_evidence=a.evidence or [])
    out(brief(rec))
    return 0


def cmd_exception(a):
    rec = records.exception(_store(a), a.title, rationale=a.rationale, affected_claims=a.affects,
                            review_trigger=a.review_trigger, limitations=a.limitation, eid=a.id)
    out(brief(rec))
    return 0


def cmd_review(a):
    rec = records.review(_store(a), a.target, state=a.state, role=a.role, comments=a.comments or "",
                         requested_changes=a.request)
    out(brief(rec))
    return 0


def cmd_gates(a):
    st = _store(a)
    evs = gates.evaluate_all(st, persist=a.persist)
    if getattr(a, "json", False):
        out(evs, a)
    else:
        for e in evs:
            print(f"{e['gate']:<18} {e['state']:<24} auto={e['automation_state']:<17} next: {e['next_action'] or '-'}")
    if a.fail_on_blocked and any(e["state"] in ("blocked", "rejected") for e in evs):
        return 3
    return 0


def cmd_explain(a):
    ev = gates.evaluate_gate(_store(a), a.gate)
    out(ev if getattr(a, "json", False) else ev["explanation"], a)
    return 0


def cmd_approve(a):
    rec = gates.approve(_store(a), a.gate, a.decision, note=a.note or "", exceptions=a.exception)
    out(brief(rec) + f"\nbound to evidence fingerprint {rec['evidence_fingerprint']}")
    return 0


def cmd_connector(a):
    st = _store(a)
    if a.action == "register":
        rec = connectors.register(st, provider=a.provider, protocol=a.protocol, protocol_version=a.protocol_version,
                                  transport=a.transport, endpoint=a.endpoint, scopes=a.scope or [],
                                  data_classes=a.data_class or [], trust_tier=a.trust_tier, secret_ref=a.secret_ref, cid=a.id)
    elif a.action == "sync":
        rec = connectors.record_sync(st, a.id, state=a.state, error=a.error, correlation=a.correlation)
    elif a.action == "propose":
        inputs = dict(kv.split("=", 1) for kv in (a.input or []))
        rec = connectors.propose(st, connector_id=a.id, action=a.verb, target=a.target, inputs=inputs,
                                 side_effects=a.side_effect or [], reversible=a.reversible, compensation=a.compensation,
                                 dry_run_available=a.dry_run_available)
        print(connectors.render_proposal(rec))
        return 0
    elif a.action == "approve":
        rec = connectors.approve(st, a.id, decision=a.decision, note=a.note or "")
    elif a.action == "check":
        ok, why = connectors.check(st, a.id)
        print(("ALLOWED: " if ok else "NOT ALLOWED: ") + why)
        return 0 if ok else 2
    elif a.action == "outcome":
        rec = connectors.record_outcome(st, a.id, result=a.result, evidence=a.evidence or "", external_id=a.external_id,
                                        error=a.error)
    out(brief(rec))
    return 0


def cmd_lint(a):
    hits = []
    for p in a.paths:
        for h in claims.lint_claims(Path(p).read_text(encoding="utf-8", errors="replace")):
            hits.append({"file": p, **h})
    out(hits if hits else "No unscoped claims found.")
    return 3 if hits else 0


def cmd_scan(a):
    hits = claims.scan_paths(a.paths)
    out(hits if hits else "No credential-shaped content found.")
    return 3 if hits else 0


def cmd_snapshot(a):
    st = _store(a)
    filters = {k: v for k, v in {"revision": a.revision, "owner": a.owner, "severity": a.severity,
                                 "types": a.type}.items() if v}
    res = snapshot.build(st, a.out, filters=filters)
    print(f"Snapshot: {res['zip']}\nRecords: {len(res['manifest']['records'])}  "
          f"Redactions: {len(res['manifest']['redactions'])}  Audit chain verified: {res['manifest']['audit_chain']['verified']}")
    return 0


def cmd_diff(a):
    d = snapshot.compare(snapshot.load(a.before), snapshot.load(a.after))
    if a.dashboard:
        st = _store(a)
        render(st, a.dashboard, diff=d)
        print(f"Dashboard with comparison: {a.dashboard}")
    out(d)
    return 0


def cmd_dashboard(a):
    st = _store(a)
    p = render(st, a.out, standalone=not a.fragment)
    print(f"Dashboard written to {p}")
    return 0


def cmd_audit(a):
    st = _store(a)
    if a.action == "verify":
        ok, problems = st.audit.verify()
        print("Audit chain verified." if ok else "AUDIT CHAIN BROKEN:\n  " + "\n  ".join(problems))
        return 0 if ok else 3
    evs = st.audit.events()[-a.limit:]
    for e in evs:
        print(f"{e['timestamp']}  {e['actor']:<28} {e['action']:<28} {e['object_id']:<40} {e['result']}")
    return 0


def cmd_status(a):
    st = _store(a)
    ident = st.identity
    evs = gates.evaluate_all(st)
    recs = st.all_records()
    print(f"{ident['product_id']} / {ident['design_id']} board {ident['board_id']} rev {ident['revision']} "
          f"variant {ident['variant']} — {ident['release_state']}")
    print("Records: " + ", ".join(f"{k}={len(v)}" for k, v in recs.items()))
    for e in evs:
        print(f"  {e['gate']:<18} {e['state']}")
    open_issues = [i for i in recs.get("issue", []) if i.get("state") in ("open", "contained")]
    print(f"Open issues: {len(open_issues)}")
    return 0


def cmd_konnect(a):
    st = _store(a)
    if a.kaction == "window":
        if a.waction == "request":
            rec = governance.request_window(st, scope=[x for s in a.scope for x in s.split(",") if x],
                                            reason=a.reason or "", issue=a.issue, hours=a.hours, max_calls=a.max_calls,
                                            files=a.files, branch=a.branch)
            out(brief(rec) + f"\nscope={rec['scope']} files={rec['files'] or 'any'} hours={rec['hours']} calls={rec['max_calls']}")
        elif a.waction == "approve":
            rec = governance.approve_window(st, a.id, decision=a.decision, note=a.note or "")
            out(brief(rec) + f"\nexpires_at={rec['expires_at']}")
        elif a.waction == "close":
            out(brief(governance.close_window(st, a.id, reason=a.reason or "")))
        else:
            out(governance.status(st))
        return 0
    if a.kaction == "authorize":
        res = governance.authorize(st, tool=a.tool, toolset=a.toolset, effect=a.effect, call_id=a.call_id,
                                   paths=a.path or [], audit_only=a.audit_only)
        if a.format == "kv":
            for k in ("decision", "window", "effect", "actor", "reason", "next_action"):
                v = res.get(k)
                print(f"{k}={'' if v is None else str(v).replace(chr(10), ' ')}")
        else:
            out(res)
        return 0
    if a.kaction == "record":
        text = sys.stdin.read() if a.capture else None
        res = governance.record(st, call_id=a.call_id, tool=a.tool, toolset=a.toolset, effect=a.effect,
                                status=a.status, paths=a.path or [], result_text=text, capture=a.capture)
        if a.format == "kv":
            print(f"changed_files={len(res['changed_files'])}")
            print(f"evidence={res['evidence'] or ''}")
            print(f"note={res.get('note', '')}")
        else:
            out(res)
        return 0
    if a.kaction == "ledger":
        led = governance.Ledger(st)
        if a.verify:
            ok, problems = led.verify()
            print("Konnect call ledger verified." if ok else "LEDGER BROKEN:\n  " + "\n  ".join(problems))
            return 0 if ok else 3
        for e in led.entries()[-a.limit:]:
            print(f"{e['timestamp']} {e['phase']:<9} {e.get('decision', e.get('status', '')):<6} {e['tool']:<32} "
                  f"{e.get('effect', ''):<12} {e.get('window') or '-':<16} {e.get('reason', '') or ', '.join(e.get('changed_files', []))[:80]}")
        return 0
    return 1


def cmd_mcp(a):
    from .mcp_server import serve
    return serve()


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edagov", description="EDA/KiCad evidence governance toolkit")
    p.add_argument("--root", default=os.environ.get("EDAGOV_ROOT", "."), help="design repository root (holds .edagov/)")
    p.add_argument("--json", action="store_true", help="JSON output where supported")
    p.add_argument("--version", action="version", version=f"edagov {__version__}")
    s = p.add_subparsers(dest="cmd", required=True)

    s.add_parser("doctor", help="check toolchain availability and versions").set_defaults(fn=cmd_doctor)

    x = s.add_parser("init", help="initialise the evidence store for a design")
    x.add_argument("--product", required=True); x.add_argument("--design", required=True)
    x.add_argument("--board", required=True); x.add_argument("--revision", required=True)
    x.add_argument("--variant", default="default"); x.add_argument("--assembly")
    x.add_argument("--authority", default="unassigned", help="design authority / owner")
    x.add_argument("--repository"); x.add_argument("--standard", action="append", help="exact standard edition")
    x.add_argument("--grant", action="append", help="actor=role (repeatable)")
    x.set_defaults(fn=cmd_init)

    x = s.add_parser("roles", help="show/grant/revoke roles (deny by default)")
    x.add_argument("action", choices=["show", "grant", "revoke"]); x.add_argument("actor", nargs="?"); x.add_argument("role", nargs="?")
    x.set_defaults(fn=cmd_roles)

    x = s.add_parser("revision", help="move the design identity to a new revision/variant")
    x.add_argument("revision"); x.add_argument("--variant"); x.add_argument("--reason", required=True)
    x.set_defaults(fn=cmd_revision)

    x = s.add_parser("inventory", help="read-only KiCad project inventory")
    x.add_argument("--project", required=True); x.add_argument("--library-release", help="KiCad library tag/commit in use")
    x.set_defaults(fn=cmd_inventory)

    x = s.add_parser("run", help="execute ERC/DRC with kicad-cli (requires --authorize)")
    x.add_argument("kind", choices=["erc", "drc"]); x.add_argument("--project", required=True)
    x.add_argument("--authorize", help="reason this execution is authorized")
    x.add_argument("--severity", action="append", choices=["error", "warning", "exclusions", "all"])
    x.add_argument("--no-parity", action="store_true"); x.add_argument("--refill-zones", action="store_true")
    x.set_defaults(fn=cmd_run)

    x = s.add_parser("export", help="generate fab/assembly outputs with kicad-cli (requires --authorize)")
    x.add_argument("kind", choices=sorted(kicad.EXPORTS)); x.add_argument("--project", required=True)
    x.add_argument("--out", required=True); x.add_argument("--authorize"); x.add_argument("--variant")
    x.add_argument("--extra", nargs=argparse.REMAINDER, help="extra kicad-cli flags")
    x.set_defaults(fn=cmd_export)

    x = s.add_parser("spice", help="netlist manifest or ngspice run")
    x.add_argument("action", choices=["manifest", "run"]); x.add_argument("netlist")
    x.add_argument("--authorize"); x.add_argument("--retry-of"); x.add_argument("--validation")
    x.add_argument("--justification", help="why loosened solver settings keep the run qualified")
    x.set_defaults(fn=cmd_spice)

    x = s.add_parser("ingest", help="documentation-only: record existing reports/logs/BOM/GitHub state")
    x.add_argument("what", choices=["erc", "drc", "spice", "bom", "github"])
    x.add_argument("path", help="report / netlist / BOM CSV / owner/repo")
    x.add_argument("number", nargs="?", help="PR number (github)")
    x.add_argument("--project"); x.add_argument("--log", help="simulator log (spice)")
    x.add_argument("--simulator", default="ngspice"); x.add_argument("--tool-version"); x.add_argument("--exit-code", type=int)
    x.add_argument("--retry-of"); x.add_argument("--validation"); x.add_argument("--justification")
    x.add_argument("--from-json", help="offline GitHub fixture")
    x.set_defaults(fn=cmd_ingest)

    x = s.add_parser("manifest", help="build the hashed manufacturing release manifest")
    x.add_argument("--outputs", required=True); x.add_argument("--variant")
    x.add_argument("--origin", default="unknown — record drill/placement origin")
    x.add_argument("--supplier-assumption", action="append")
    x.set_defaults(fn=cmd_manifest)

    x = s.add_parser("dfm", help="DFM/DFA findings and plotted-view review")
    x.add_argument("action", choices=["add", "plotted-view"]); x.add_argument("package")
    x.add_argument("--rule"); x.add_argument("--description"); x.add_argument("--tool")
    x.add_argument("--disposition", choices=["open", "corrected", "accepted", "waived"])
    x.add_argument("--rationale"); x.add_argument("--approver")
    x.add_argument("--decision", choices=["approved", "requested_changes", "in_progress"]); x.add_argument("--note")
    x.set_defaults(fn=cmd_dfm)

    x = s.add_parser("signoff", help="separate design/fab/assembly/release sign-offs")
    x.add_argument("package"); x.add_argument("role", choices=list(manufacturing.SIGNOFF_ROLES))
    x.add_argument("--decision", required=True, choices=["approved", "requested_changes", "blocked"]); x.add_argument("--note")
    x.set_defaults(fn=cmd_signoff)

    x = s.add_parser("record", help="record requirements, blocks, decisions, assumptions, evidence")
    x.add_argument("kind", choices=["requirement", "block", "decision", "assumption", "evidence", "library"])
    x.add_argument("--id"); x.add_argument("--text"); x.add_argument("--source"); x.add_argument("--owner")
    x.add_argument("--priority", default="medium"); x.add_argument("--method"); x.add_argument("--acceptance")
    x.add_argument("--status", default="draft"); x.add_argument("--conditions"); x.add_argument("--standard")
    x.add_argument("--name"); x.add_argument("--purpose"); x.add_argument("--interface", action="append")
    x.add_argument("--allocate", action="append"); x.add_argument("--title"); x.add_argument("--rationale")
    x.add_argument("--alternative", action="append"); x.add_argument("--consequences"); x.add_argument("--tag", action="append")
    x.add_argument("--review-condition"); x.add_argument("--path"); x.add_argument("--artifact-kind", default="report")
    x.add_argument("--claim", help="scoped claim the evidence supports")
    x.add_argument("--license", help="library license (record library)")
    x.set_defaults(fn=cmd_record)

    x = s.add_parser("issue", help="open/close issues")
    x.add_argument("action", choices=["open", "close"]); x.add_argument("title", nargs="?")
    x.add_argument("--id"); x.add_argument("--severity", choices=["low", "medium", "high", "critical"])
    x.add_argument("--owner"); x.add_argument("--affected", action="append"); x.add_argument("--gate", action="append")
    x.add_argument("--due"); x.add_argument("--containment"); x.add_argument("--external")
    x.add_argument("--disposition"); x.add_argument("--evidence", action="append")
    x.set_defaults(fn=cmd_issue)

    x = s.add_parser("exception", help="record an accepted exception (named authority)")
    x.add_argument("title"); x.add_argument("--id"); x.add_argument("--rationale", required=True)
    x.add_argument("--affects", action="append", required=True, help="record IDs whose claims this covers")
    x.add_argument("--review-trigger", required=True); x.add_argument("--limitation", action="append")
    x.set_defaults(fn=cmd_exception)

    x = s.add_parser("review", help="record a review decision on a record")
    x.add_argument("target"); x.add_argument("--state", required=True, choices=["approved", "requested_changes", "in_progress", "abstained", "blocked"])
    x.add_argument("--role", required=True, choices=["design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver"])
    x.add_argument("--comments"); x.add_argument("--request", action="append")
    x.set_defaults(fn=cmd_review)

    x = s.add_parser("gates", help="evaluate all gates")
    x.add_argument("--persist", action="store_true"); x.add_argument("--fail-on-blocked", action="store_true")
    x.set_defaults(fn=cmd_gates)

    x = s.add_parser("explain", help="deterministic explanation of one gate")
    x.add_argument("gate", choices=gates.GATE_ORDER); x.set_defaults(fn=cmd_explain)

    x = s.add_parser("approve", help="record a human gate decision")
    x.add_argument("gate", choices=gates.GATE_ORDER)
    x.add_argument("--decision", required=True, choices=["approved", "approved_with_exception", "rejected"])
    x.add_argument("--note"); x.add_argument("--exception", action="append")
    x.set_defaults(fn=cmd_approve)

    x = s.add_parser("connector", help="connector registry and governed actions")
    x.add_argument("action", choices=["register", "sync", "propose", "approve", "check", "outcome"])
    x.add_argument("--id"); x.add_argument("--provider"); x.add_argument("--protocol", default="mcp")
    x.add_argument("--protocol-version"); x.add_argument("--transport", choices=["stdio", "streamable-http", "http", "https", "sse"])
    x.add_argument("--endpoint"); x.add_argument("--scope", action="append"); x.add_argument("--data-class", action="append")
    x.add_argument("--trust-tier", default="untrusted", choices=["untrusted", "verified_read", "verified_write"])
    x.add_argument("--secret-ref", help="logical secret name only, never the value")
    x.add_argument("--state"); x.add_argument("--error"); x.add_argument("--correlation")
    x.add_argument("--verb", choices=["read", "create", "change", "publish", "purchase", "release", "delete"])
    x.add_argument("--target"); x.add_argument("--input", action="append", help="key=value")
    x.add_argument("--side-effect", action="append"); x.add_argument("--reversible", action="store_true")
    x.add_argument("--compensation"); x.add_argument("--dry-run-available", action="store_true")
    x.add_argument("--decision", default="approved", choices=["approved", "rejected"]); x.add_argument("--note")
    x.add_argument("--result", choices=["success", "failed", "unknown", "compensated", "dead_lettered"])
    x.add_argument("--evidence"); x.add_argument("--external-id")
    x.set_defaults(fn=cmd_connector)

    x = s.add_parser("lint-claims", help="flag unscoped compliance/function/manufacturability claims")
    x.add_argument("paths", nargs="+"); x.set_defaults(fn=cmd_lint)

    x = s.add_parser("scan-secrets", help="flag credential-shaped content")
    x.add_argument("paths", nargs="+"); x.set_defaults(fn=cmd_scan)

    x = s.add_parser("snapshot", help="export a read-only review snapshot")
    x.add_argument("--out", default="snapshots"); x.add_argument("--revision"); x.add_argument("--owner")
    x.add_argument("--severity"); x.add_argument("--type", action="append")
    x.set_defaults(fn=cmd_snapshot)

    x = s.add_parser("diff", help="compare two snapshots")
    x.add_argument("before"); x.add_argument("after"); x.add_argument("--dashboard")
    x.set_defaults(fn=cmd_diff)

    x = s.add_parser("dashboard", help="render the static review dashboard")
    x.add_argument("--out", default="dashboard.html"); x.add_argument("--fragment", action="store_true",
                                                                      help="omit <html>/<head> wrapper (for artifact hosts)")
    x.set_defaults(fn=cmd_dashboard)

    x = s.add_parser("audit", help="verify or list the audit chain")
    x.add_argument("action", choices=["verify", "log"]); x.add_argument("--limit", type=int, default=50)
    x.set_defaults(fn=cmd_audit)

    s.add_parser("status", help="one-screen summary").set_defaults(fn=cmd_status)

    k = s.add_parser("konnect", help="governance of Konnect MCP tool calls (change windows, authorize, record, ledger)")
    ks = k.add_subparsers(dest="kaction", required=True)
    w = ks.add_parser("window", help="request/approve/close/status of design change windows")
    w.add_argument("waction", choices=["request", "approve", "close", "status"])
    w.add_argument("id", nargs="?", help="window ID (approve/close)")
    w.add_argument("--scope", action="append", default=[], help="toolset, tool:<name> or * (comma-separated, repeatable)")
    w.add_argument("--reason"); w.add_argument("--issue"); w.add_argument("--branch")
    w.add_argument("--hours", type=float, default=8); w.add_argument("--max-calls", type=int, default=500)
    w.add_argument("--files", action="append", help="glob relative to the repo root (repeatable)")
    w.add_argument("--decision", default="approved", choices=["approved", "rejected"]); w.add_argument("--note")
    au = ks.add_parser("authorize", help="(called by Konnect) decide whether a tool call may run")
    for x in (au,):
        x.add_argument("--tool", required=True); x.add_argument("--toolset"); x.add_argument("--effect", required=True)
        x.add_argument("--call-id", required=True); x.add_argument("--path", action="append")
        x.add_argument("--format", choices=["kv", "json"], default="json")
    au.add_argument("--audit-only", action="store_true")
    rc = ks.add_parser("record", help="(called by Konnect) record a completed tool call")
    rc.add_argument("--tool", required=True); rc.add_argument("--toolset"); rc.add_argument("--effect", required=True)
    rc.add_argument("--call-id", required=True); rc.add_argument("--path", action="append")
    rc.add_argument("--status", required=True, choices=["ok", "error"])
    rc.add_argument("--capture", action="store_true", help="read the tool result from stdin and capture it as evidence")
    rc.add_argument("--format", choices=["kv", "json"], default="json")
    lg = ks.add_parser("ledger", help="show or verify the Konnect call ledger")
    lg.add_argument("--limit", type=int, default=50); lg.add_argument("--verify", action="store_true")
    k.set_defaults(fn=cmd_konnect)

    s.add_parser("mcp", help="run the edagov governance MCP server on stdio").set_defaults(fn=cmd_mcp)
    return p


def main(argv=None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    try:
        return a.fn(a) or 0
    except (permissions.PermissionDenied, executor.NotAuthorized, PermissionError) as e:
        print(f"DENIED: {e}", file=sys.stderr)
        return 2
    except executor.ToolMissing as e:
        print(f"TOOL MISSING: {e}", file=sys.stderr)
        return 4
    except (StoreError, ValueError, FileNotFoundError, KeyError) as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
