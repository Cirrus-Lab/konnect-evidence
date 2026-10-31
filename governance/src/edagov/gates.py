"""Gate engine with deterministic "explain status" output (Workflow Guide §12,
Dashboard Spec §7 "Explain status").

Rules:
  * Automation may only assign not_started / in_progress / ready_for_review / blocked.
  * approved / approved_with_exception / rejected come only from an approval
    record by a permitted role, bound to the evidence fingerprint at approval
    time. If the evidence changes afterwards the approval is reported stale
    (like a GitHub review dismissed on a new diff) and the gate falls back.
  * A check is not_applicable only with a rationale in policy overrides.
"""
from __future__ import annotations

from . import manufacturing
from .util import freshness, now_iso, obj_hash
from .vocab import GATES

GATE_ORDER = [g for g, _ in GATES]


def _res(ok, check, detail, missing=None, next_action=None, inputs=None, na=None):
    state = "not_applicable" if na else ("pass" if ok is True else "missing" if ok is None else "fail")
    return {"check": check, "result": state, "detail": detail, "missing": missing or [],
            "next_action": None if ok or na else next_action, "inputs": inputs or [], "rationale": na}


def _latest_run(store, check, revision):
    runs = [r for r in store.list("run", revision=revision) if r.get("check") == check and not r.get("superseded")]
    return sorted(runs, key=lambda r: (r.get("timestamp") or "", r.get("updated_at") or ""))[-1] if runs else None


def inputs_changed(rec) -> list[str]:
    """Absolute input files whose content no longer matches the hash bound to the evidence."""
    from pathlib import Path
    from .util import file_hash
    changed = []
    for inp in rec.get("inputs") or []:
        p = Path(inp.get("path", ""))
        h = inp.get("hash")
        if not p.is_absolute() or not h or not h.startswith("sha256:"):
            continue
        if not p.exists():
            changed.append(f"{p.name} (missing)")
        elif p.is_file() and file_hash(p) != h:
            changed.append(p.name)
    return changed


def _exceptions_for(store, target_id):
    return [e for e in store.list("exception") if target_id in (e.get("affected_claims") or []) and not e.get("superseded")]


def _open_blockers(store, gate, revision, severities):
    out = []
    for i in store.list("issue", revision=revision):
        if i.get("state") in ("open", "contained") and i.get("severity") in severities:
            gates = i.get("gates") or []
            if not gates or gate in gates:
                out.append(i)
    return out


# ---------------------------------------------------------------- checks
def check_requirements_complete(store, rev, policy, gate):
    reqs = store.list("requirement", revision=rev, include_superseded=False)
    if not reqs:
        return _res(None, "requirements_complete", "no requirement records", ["requirement records"],
                    "Capture requirements with verification method and acceptance threshold.")
    unmet = [r["id"] for r in reqs if r.get("status") == "unmet"]
    if unmet:
        return _res(False, "requirements_complete", f"unmet requirements: {unmet}", unmet,
                    "Resolve or formally disposition unmet requirements.", [r["id"] for r in reqs])
    vague = [r["id"] for r in reqs if any(w in (r.get("acceptance") or "").lower() for w in ("compliant", "ready", "tbd"))
             and not any(ch.isdigit() for ch in r.get("acceptance") or "")]
    if vague:
        return _res(False, "requirements_complete", f"acceptance criteria not measurable: {vague}", vague,
                    "Name the exact standard edition / numeric threshold.", [r["id"] for r in reqs])
    return _res(True, "requirements_complete", f"{len(reqs)} requirement(s) with method and acceptance", inputs=[r["id"] for r in reqs])


def check_assumptions_owned(store, rev, policy, gate):
    a = store.list("assumption", revision=rev, include_superseded=False)
    bad = [x["id"] for x in a if not x.get("owner") or not x.get("review_condition")]
    return _res(not bad, "assumptions_owned", f"{len(a)} assumption(s); {len(bad)} without owner/review condition", bad,
                "Give each assumption an owner and expiry/review condition.", [x["id"] for x in a])


def check_requirements_allocated(store, rev, policy, gate):
    reqs = store.list("requirement", revision=rev, include_superseded=False)
    blocks = store.list("architecture_block", revision=rev, include_superseded=False)
    if not blocks:
        return _res(None, "requirements_allocated", "no architecture blocks", ["architecture_block records"],
                    "Record architecture blocks and allocate requirements.")
    allocated = {rid for b in blocks for rid in (b.get("allocated_requirements") or [])}
    un = [r["id"] for r in reqs if r["id"] not in allocated]
    return _res(not un, "requirements_allocated", f"{len(reqs) - len(un)}/{len(reqs)} requirements allocated", un,
                "Allocate each requirement to at least one block.", [b["id"] for b in blocks])


def check_blocks_owned(store, rev, policy, gate):
    blocks = store.list("architecture_block", revision=rev, include_superseded=False)
    bad = [b["id"] for b in blocks if not b.get("owner") or b.get("owner") == "unassigned"]
    return _res(not bad if blocks else None, "blocks_owned", f"{len(blocks)} block(s), {len(bad)} unowned", bad,
                "Assign an owner to every block.", [b["id"] for b in blocks])


def _run_check(store, rev, policy, kind):
    name = f"run_clean:{kind}"
    r = _latest_run(store, kind, rev)
    if not r:
        return _res(None, name, f"no {kind.upper()} run for revision {rev}", [f"{kind} run"],
                    f"Run `edagov run {kind} --authorize ...` or ingest an existing report.")
    fr = freshness(r.get("timestamp"), policy["freshness_days"].get(kind, policy["freshness_days"]["default"]))
    inputs = [r["id"]]
    if fr != "current":
        return _res(False, name, f"{kind.upper()} evidence is {fr} ({r.get('timestamp')})", [r["id"]],
                    f"Re-run {kind.upper()} on the current revision.", inputs)
    if not r.get("inputs"):
        return _res(False, name, f"{r['id']} is not bound to input hashes", [r["id"]],
                    "Re-ingest with the project folder or execute the check.", inputs)
    changed = inputs_changed(r)
    if changed:
        return _res(False, name, f"{r['id']}: design files changed since this run ({changed[:5]})", [r["id"]],
                    f"Re-run {kind.upper()} on the current files.", inputs)
    rc = r.get("result_class")
    if rc == "clean":
        return _res(True, name, f"{r['id']}: clean under recorded policy ({r['source']})", inputs=inputs)
    if rc == "violations":
        exc = _exceptions_for(store, r["id"])
        if exc:
            return _res(True, name, f"{r['id']}: {r['counts'].get('active')} violation(s) covered by exception(s) "
                        f"{[e['id'] for e in exc]}", inputs=inputs + [e["id"] for e in exc])
        return _res(False, name, f"{r['id']}: {r['counts'].get('active')} active violation(s) {r.get('by_type')}", [r["id"]],
                    r.get("next_action"), inputs)
    return _res(False, name, f"{r['id']}: result '{rc}' — {'; '.join(r.get('limitations', [])[-1:])}", [r["id"]],
                r.get("next_action"), inputs)


def check_drc_parity_checked(store, rev, policy, gate):
    r = _latest_run(store, "drc", rev)
    if not r:
        return _res(None, "drc_parity_checked", "no DRC run", ["drc run"], "Run DRC with --schematic-parity.")
    p = (r.get("settings") or {}).get("schematic_parity")
    if p is True:
        return _res(True, "drc_parity_checked", f"{r['id']} ran with schematic parity", inputs=[r["id"]])
    return _res(False, "drc_parity_checked", f"{r['id']}: schematic parity {'unknown' if p is None else 'not checked'}",
                [r["id"]], "Re-run DRC with schematic parity enabled.", [r["id"]])


def check_library_provenance(store, rev, policy, gate):
    libs = [a for a in store.list("artifact", revision=rev)
            if a.get("kind") in ("symbol_library", "footprint_library", "model_3d", "spice_model")]
    inv = [a for a in store.list("artifact", revision=rev) if a.get("kind") == "report" and a.get("report_kind") == "inventory"]
    missing = [a["id"] for a in libs if not a.get("provenance") or not a.get("license")]
    if not libs and not inv:
        return _res(None, "library_provenance", "no library assets or inventory recorded", ["inventory"],
                    "Run `edagov inventory` and record library provenance.")
    if inv:
        latest = sorted(inv, key=lambda a: a.get("updated_at", ""))[-1]
        globals_ = [f for f in latest.get("findings", []) if f["code"].startswith("global_")]
        pinned = latest.get("library_release_pinned")
        if globals_ and not pinned:
            return _res(False, "library_provenance", "symbols/footprints resolve through unpinned global libraries",
                        [latest["id"]], "Record the KiCad library release/commit (`edagov inventory --library-release ...`).",
                        [latest["id"]])
    return _res(not missing, "library_provenance", f"{len(libs)} library asset(s), {len(missing)} without provenance/license",
                missing, "Record repository/tag, license and reviewer for each asset.", [a["id"] for a in libs])


def check_simulation_qualified(store, rev, policy, gate):
    runs = [r for r in store.list("run", revision=rev) if r.get("check") == "simulation" and not r.get("superseded")]
    if not runs:
        return _res(None, "simulation_qualified", "no simulation runs", ["simulation run"],
                    "Run or ingest simulations, or mark the gate not_applicable with rationale.")
    retried = {r.get("retry_of") for r in runs if r.get("retry_of")}
    heads = [r for r in runs if r["id"] not in retried]  # failures that were retried are preserved but not the head
    bad = []
    for r in heads:
        rc = r.get("result_class")
        if rc == "failed":
            bad.append(f"{r['id']}: failed")
        elif rc == "altered_settings" and not r.get("settings_justification"):
            bad.append(f"{r['id']}: loosened settings without justification")
        elif not r.get("validation"):
            bad.append(f"{r['id']}: no validation/acceptance data")
        elif not r.get("manifest", {}).get("complete", False):
            bad.append(f"{r['id']}: netlist manifest incomplete")
        elif inputs_changed(r):
            bad.append(f"{r['id']}: netlist/models changed since the run ({inputs_changed(r)[:3]})")
    return _res(not bad, "simulation_qualified", f"{len(heads)} head run(s); {len(runs) - len(heads)} preserved earlier attempt(s)",
                bad, "Qualify each head run: validation data, justified settings, complete manifest.", [r["id"] for r in runs])


def check_evidence_tag(store, rev, policy, gate, tag):
    name = f"evidence_tag:{tag}"
    items = [a for a in store.list("artifact", revision=rev) + store.list("run", revision=rev)
             if tag in (a.get("tags") or []) and not a.get("superseded")]
    if not items:
        return _res(None, name, f"no evidence tagged '{tag}'", [tag],
                    f"Attach {tag.replace('_', ' ')} evidence (`edagov evidence add --tag {tag} ...`) or mark not applicable with rationale.")
    days = policy["freshness_days"].get("analysis")
    stale = [a["id"] for a in items if freshness(a.get("timestamp") or a.get("updated_at"), days) != "current"
             or inputs_changed(a) or _artifact_file_changed(a)]
    unreviewed = [a["id"] for a in items if not a.get("reviewer")]
    if stale:
        return _res(False, name, f"stale: {stale}", stale, "Refresh the analysis for this revision.", [a["id"] for a in items])
    if unreviewed:
        return _res(False, name, f"not reviewed: {unreviewed}", unreviewed, "Name a reviewer for the analysis.", [a["id"] for a in items])
    return _res(True, name, f"{len(items)} reviewed item(s)", inputs=[a["id"] for a in items])


def _artifact_file_changed(a) -> bool:
    from pathlib import Path
    from .util import file_hash
    p, h = Path(a.get("path", "")), a.get("hash", "")
    return bool(p.is_absolute() and p.is_file() and h.startswith("sha256:") and file_hash(p) != h)


def check_bom_present(store, rev, policy, gate):
    lines = store.list("bom_line", revision=rev, include_superseded=False)
    return _res(True if lines else None, "bom_present", f"{len(lines)} BOM line(s)", [] if lines else ["BOM"],
                "Ingest the revision-matched BOM.", [l["id"] for l in lines])


def check_bom_lines_valid(store, rev, policy, gate):
    lines = store.list("bom_line", revision=rev, include_superseded=False)
    bad = [f"{l['id']}: {l['findings'][0]['message']}" for l in lines if l.get("severity") == "blocking"]
    return _res(not bad if lines else None, "bom_lines_valid", f"{len(bad)} blocking line(s) of {len(lines)}", bad,
                "Fix blocking BOM findings (exact MPN, lifecycle risk, alternate evidence).", [l["id"] for l in lines])


def _latest_pkg(store, rev):
    pk = [p for p in store.list("manufacturing_package", revision=rev) if not p.get("superseded")]
    return sorted(pk, key=lambda p: p.get("updated_at", ""))[-1] if pk else None


def check_manifest_complete(store, rev, policy, gate):
    p = _latest_pkg(store, rev)
    if not p:
        return _res(None, "manifest_complete", "no manufacturing package", ["manufacturing package"], "Run `edagov manifest <outputs>`.")
    blocking = [f["message"] for f in p.get("consistency_findings", []) if f["severity"] == "blocking"]
    return _res(p["completeness"] == "complete", "manifest_complete", f"{p['id']}: {p['completeness']}", blocking,
                "Resolve manifest findings and rebuild.", [p["id"]])


def check_manifest_hashes_verify(store, rev, policy, gate):
    p = _latest_pkg(store, rev)
    if not p:
        return _res(None, "manifest_hashes_verify", "no manufacturing package", ["manufacturing package"], "Build the manifest.")
    ok, problems = manufacturing.verify(p)
    return _res(ok, "manifest_hashes_verify", "all file hashes match" if ok else "; ".join(problems[:5]), problems,
                "Files changed after the manifest: rebuild the manifest and re-review.", [p["id"]])


def check_dfm_dispositioned(store, rev, policy, gate):
    p = _latest_pkg(store, rev)
    if not p:
        return _res(None, "dfm_dispositioned", "no manufacturing package", ["manufacturing package"], "Build the manifest.")
    if not p.get("dfm_findings") and p.get("plotted_view_review") != "approved":
        return _res(None, "dfm_dispositioned", "no DFM/DFA review recorded and plotted views not reviewed",
                    ["DFM/DFA review", "plotted-view review"], "Record DFM/DFA findings (or a clean review) and plotted-view review.", [p["id"]])
    open_ = [f["id"] for f in p.get("dfm_findings", []) if f["disposition"] == "open"]
    signs = [r for r, s in p.get("signoffs", {}).items() if s.get("state") != "approved"]
    missing = open_ + [f"sign-off:{r}" for r in signs]
    if p.get("plotted_view_review") != "approved":
        missing.append("plotted-view review")
    return _res(not missing, "dfm_dispositioned", f"{len(open_)} open finding(s); sign-offs pending {signs}", missing,
                "Disposition findings and collect separate design/fab/assembly/release sign-offs.", [p["id"]])


def check_prior_gates_approved(store, rev, policy, gate):
    idx = GATE_ORDER.index(gate)
    pending = []
    for g in GATE_ORDER[:idx]:
        ev = evaluate_gate(store, g, _shallow=True)
        if ev["state"] not in ("approved", "approved_with_exception", "not_applicable"):
            pending.append(f"{g}:{ev['state']}")
    return _res(not pending, "prior_gates_approved", "all prior gates approved" if not pending else f"pending: {pending}",
                pending, "Approve earlier gates first.")


def check_change_impact_recorded(store, rev, policy, gate):
    ident = store.identity
    prev = ident.get("previous_revision")
    if not prev:
        return _res(True, "change_impact_recorded", "initial revision: no predecessor", na=None)
    dec = [d for d in store.list("decision", revision=rev) if "change_impact" in (d.get("tags") or [])]
    return _res(bool(dec), "change_impact_recorded", f"{len(dec)} change-impact record(s) vs {prev}", [] if dec else ["change impact decision"],
                f"Record impact analysis from {prev} to {rev}: affected requirements, evidence, re-reviews.", [d["id"] for d in dec])


def check_no_blocking_issues(store, rev, policy, gate):
    sev = policy.get("issue_blocking_severities", ["high", "critical"])
    issues = _open_blockers(store, gate, rev, sev)
    return _res(not issues, "no_blocking_issues", f"{len(issues)} open blocking issue(s)", [i["id"] for i in issues],
                "Resolve, contain, or accept (with exception) the blocking issues.", [i["id"] for i in issues])


CHECKS = {
    "requirements_complete": check_requirements_complete,
    "assumptions_owned": check_assumptions_owned,
    "requirements_allocated": check_requirements_allocated,
    "blocks_owned": check_blocks_owned,
    "drc_parity_checked": check_drc_parity_checked,
    "library_provenance": check_library_provenance,
    "simulation_qualified": check_simulation_qualified,
    "bom_present": check_bom_present,
    "bom_lines_valid": check_bom_lines_valid,
    "manifest_complete": check_manifest_complete,
    "manifest_hashes_verify": check_manifest_hashes_verify,
    "dfm_dispositioned": check_dfm_dispositioned,
    "prior_gates_approved": check_prior_gates_approved,
    "change_impact_recorded": check_change_impact_recorded,
    "no_blocking_issues": check_no_blocking_issues,
}


def run_check(store, rev, policy, gate, name):
    ov = policy.get("overrides", {}).get(gate, {}).get(name, {})
    if ov.get("not_applicable"):
        return _res(True, name, "marked not applicable", na=ov["not_applicable"])
    if name.startswith("run_clean:"):
        return _run_check(store, rev, policy, name.split(":", 1)[1])
    if name.startswith("evidence_tag:"):
        return check_evidence_tag(store, rev, policy, gate, name.split(":", 1)[1])
    fn = CHECKS.get(name)
    if not fn:
        return _res(False, name, f"unknown check '{name}' in policy", [name], "Fix the gate policy.")
    return fn(store, rev, policy, gate)


def evidence_fingerprint(results):
    return obj_hash(sorted({i for r in results for i in r.get("inputs", [])}))


def evaluate_gate(store, gate, _shallow=False) -> dict:
    ident, policy = store.identity, store.policy
    rev = ident["revision"]
    gcfg = policy["gates"].get(gate, {})
    if gate == "change" and not ident.get("previous_revision") and not gcfg.get("not_applicable"):
        gcfg = dict(gcfg, not_applicable=f"initial revision {rev}: no predecessor to analyse change impact against")
    if gcfg.get("not_applicable"):
        return {"gate": gate, "state": "not_applicable", "automation_state": "not_applicable",
                "rationale": gcfg["not_applicable"], "checks": [], "revision": rev, "variant": ident["variant"],
                "evidence_fingerprint": evidence_fingerprint([]), "approval": None, "approval_note": None,
                "blocking": [], "missing_evidence": [], "next_action": None, "evaluated_at": now_iso(),
                "explanation": (f"Gate '{gate}' for {ident['design_id']} rev {rev}: not applicable.\n"
                                f"Rationale: {gcfg['not_applicable']}")}
    results = [run_check(store, rev, policy, gate, c) for c in gcfg.get("checks", [])
               if not (_shallow and c == "prior_gates_approved")]
    fp = evidence_fingerprint(results)
    failed = [r for r in results if r["result"] == "fail"]
    missing = [r for r in results if r["result"] == "missing"]
    passed = [r for r in results if r["result"] in ("pass", "not_applicable")]
    if failed:
        auto = "blocked"
    elif missing and not passed:
        auto = "not_started"
    elif missing:
        auto = "in_progress"
    else:
        auto = "ready_for_review"
    state, approval, approval_note = auto, None, None
    approvals = [a for a in store.list("approval", revision=rev) if a.get("gate") == gate and not a.get("superseded")]
    if approvals:
        approval = sorted(approvals, key=lambda a: a.get("updated_at", ""))[-1]
        if approval["decision"] == "rejected":
            state = "rejected"
        elif approval.get("evidence_fingerprint") != fp:
            approval_note = (f"approval {approval['id']} is stale: evidence changed since approval "
                             f"({approval.get('evidence_fingerprint')} → {fp}); re-review required")
        elif auto in ("ready_for_review",) or (auto == "blocked" and approval["decision"] == "approved_with_exception"):
            state = approval["decision"] if approval["decision"] in ("approved", "approved_with_exception") else state
        else:
            approval_note = f"approval {approval['id']} recorded but gate checks now show '{auto}'"
    nxt = next((r["next_action"] for r in failed + missing if r.get("next_action")), None)
    if state == "ready_for_review" and not nxt:
        from .permissions import GATE_APPROVER_ROLES
        nxt = f"Request {'/'.join(GATE_APPROVER_ROLES.get(gate, ()))} review and approval."
    lines = [f"Gate '{gate}' for {ident['design_id']} rev {rev} variant {ident['variant']} evaluated {now_iso()}.",
             f"Rule: policy {policy.get('policy_version')} checks {gcfg.get('checks', [])}."]
    for r in results:
        lines.append(f"  [{r['result'].upper():>14}] {r['check']}: {r['detail']}" + (f" (N/A: {r['rationale']})" if r.get("rationale") else ""))
    lines.append(f"Automation result: {auto}. Displayed state: {state}.")
    if approval_note:
        lines.append(approval_note)
    if nxt:
        lines.append(f"Next action: {nxt}")
    return {
        "gate": gate, "state": state, "automation_state": auto, "revision": rev, "variant": ident["variant"],
        "checks": results, "evidence_fingerprint": fp, "approval": approval["id"] if approval else None,
        "approval_note": approval_note, "blocking": [m for r in failed for m in r["missing"]],
        "missing_evidence": [m for r in missing for m in r["missing"]], "next_action": nxt,
        "evaluated_at": now_iso(), "explanation": "\n".join(lines),
    }


def evaluate_all(store, persist: bool = False) -> list[dict]:
    out = []
    for g in GATE_ORDER:
        ev = evaluate_gate(store, g)
        out.append(ev)
        if persist:
            store.put({"type": "gate", "id": f"GATE-{g.upper()}-{store.identity['revision']}", "gate": g,
                       "state": ev["state"], "explanation": ev["explanation"], "evaluation": ev,
                       "severity": {"blocked": "blocking", "rejected": "blocking", "ready_for_review": "attention",
                                    "approved": "approved", "approved_with_exception": "warning"}.get(ev["state"], "info"),
                       "timestamp": ev["evaluated_at"], "source": "edagov gate engine", "owner": store.identity.get("design_authority"),
                       "linked_evidence": sorted({i for c in ev["checks"] for i in c["inputs"]}), "next_action": ev["next_action"]},
                      enforce=False, reason="gate evaluation")
    return out


def approve(store, gate, decision, *, note="", exceptions=None) -> dict:
    """Record a human gate decision bound to the current evidence fingerprint."""
    from . import permissions
    from .util import new_id
    action = "approve_release" if gate == "release" else "approve_gate"
    actor, verified, roles = store.check(action)
    permissions.require_gate_approver(gate, actor, roles)
    ev = evaluate_gate(store, gate)
    if decision in ("approved",) and ev["automation_state"] != "ready_for_review":
        raise ValueError(f"cannot approve '{gate}': automation state is {ev['automation_state']}. "
                         "Use approved_with_exception with exception IDs, or resolve blockers.")
    if decision == "approved_with_exception":
        if not exceptions:
            raise ValueError("approved_with_exception requires --exception IDs")
        for e in exceptions:
            if not store.get("exception", e):
                raise ValueError(f"exception {e} not found")
    n = len([a for a in store.list("approval") if a.get("gate") == gate]) + 1
    rec = {"type": "approval", "id": new_id("approval", f"{gate}-{store.identity['revision']}-{n}"),
           "gate": gate, "decision": decision, "approver": actor, "approver_verified": verified, "approver_role": roles[0],
           "approver_roles": roles, "target_revision": store.identity["revision"],
           "evidence": sorted({i for c in ev["checks"] for i in c["inputs"]}), "evidence_fingerprint": ev["evidence_fingerprint"],
           "automation_state_at_approval": ev["automation_state"], "note": note, "exceptions": exceptions or [],
           "explanation_at_approval": ev["explanation"],
           "state": decision if decision in ("approved", "approved_with_exception", "rejected") else "blocked",
           "severity": "approved" if decision.startswith("approved") else "blocking", "timestamp": now_iso(),
           "source": "human decision via edagov", "owner": actor, "linked_evidence": [], "next_action": None}
    return store.put(rec, action=action, reason=f"{gate} {decision}: {note}")
