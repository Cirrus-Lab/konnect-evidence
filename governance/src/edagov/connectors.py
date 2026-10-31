"""Connector governance: registry, action proposals, human approval, outcomes
(Skill Spec §3 step 7 and §5, Workflow Guide §10).

MCP and other connectors are interoperability mechanisms, not authorization
or safety guarantees. The toolkit does not call connectors itself: the agent
does, and only after `check` says the proposal is approved, unexpired and
not already executed (idempotency). The outcome is then recorded with
evidence; downstream success is never inferred from a queue or a 2xx alone.
"""
from __future__ import annotations

import datetime as dt

from .claims import scan_text
from .util import new_id, now_iso, obj_hash, parse_iso
from .vocab import CONNECTOR_ACTIONS, SENSITIVE_ACTIONS

APPROVAL_TTL_HOURS = 24


def register(store, *, provider, protocol, protocol_version, transport, endpoint, scopes, data_classes,
             trust_tier="untrusted", secret_ref=None, owner=None, cid=None, notes=None) -> dict:
    actor, verified, _ = store.check("connector_admin")
    if scan_text(f"{endpoint} {secret_ref or ''} {notes or ''}"):
        raise ValueError("connector registration contains credential-shaped content; store only a logical secret reference")
    findings = []
    if transport in ("streamable-http", "http", "sse") and not endpoint.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        findings.append("remote HTTP endpoint without TLS")
    if transport == "stdio":
        findings.append("STDIO: stdout must carry only protocol messages; credentials come from the environment")
    if transport in ("streamable-http", "http"):
        findings.append("Streamable HTTP: server must validate Origin and authenticate; bind local servers to localhost")
    rec = {"type": "connector", "id": cid or new_id("connector", f"{provider}-{transport}"), "provider": provider,
           "protocol": protocol, "protocol_version": protocol_version, "transport": transport, "endpoint": endpoint,
           "scopes": scopes, "data_classes": data_classes, "trust_tier": trust_tier, "sync_state": "not_configured",
           "secret_ref": secret_ref, "last_successful_sync": None, "last_error": None, "notes": notes,
           "governance_notes": findings + ["tool annotations and provider status are untrusted metadata, not a security boundary"],
           "state": "in_progress", "severity": "attention" if trust_tier == "untrusted" else "info",
           "timestamp": now_iso(), "source": "connector registry", "owner": owner or actor,
           "linked_evidence": [], "next_action": "Verify server identity, scopes and token audience before raising trust tier."}
    return store.put(rec, action="connector_admin", reason=f"register connector {provider}")


def record_sync(store, cid, *, state, error=None, correlation=None) -> dict:
    store.check("record_evidence")
    rec = dict(store.get("connector", cid))
    rec["sync_state"] = state
    if state == "synced":
        rec["last_successful_sync"] = now_iso()
        rec["last_error"] = None
    else:
        rec["last_error"] = {"state": state, "error": (error or "")[:500], "at": now_iso(), "correlation_id": correlation}
    rec["timestamp"] = now_iso()
    return store.put(rec, reason=f"sync {state}")


def propose(store, *, connector_id, action, target, inputs: dict, side_effects: list[str], reversible: bool,
            compensation: str | None = None, dry_run_available: bool = False, idempotency_key: str | None = None) -> dict:
    actor, verified, _ = store.check("record_evidence")
    if action not in CONNECTOR_ACTIONS:
        raise ValueError(f"action must be one of {CONNECTOR_ACTIONS}")
    con = store.get("connector", connector_id)
    if not con:
        raise ValueError(f"connector {connector_id} not registered")
    secret_hits = scan_text(repr(inputs))
    if secret_hits:
        raise ValueError(f"proposal inputs contain credential-shaped values ({[h['type'] for h in secret_hits]}); "
                         "pass a logical secret reference instead")
    needs_approval = action in SENSITIVE_ACTIONS or not reversible or action != "read"
    if action == "read":
        needs_approval = False
    ident = store.identity
    key = idempotency_key or obj_hash({"c": connector_id, "a": action, "t": target, "i": inputs, "r": ident["revision"]})
    rec = {"type": "connector_action", "id": new_id("connector_action"), "connector": connector_id, "action": action,
           "target": target, "inputs": inputs, "affected_revision": ident["revision"], "variant": ident["variant"],
           "side_effects": side_effects, "reversible": reversible, "compensation": compensation,
           "dry_run_available": dry_run_available, "idempotency_key": key, "requires_human_approval": needs_approval,
           "proposed_by": actor, "action_state": "proposed" if needs_approval else "approved",
           "connector_trust_tier": con["trust_tier"], "connector_protocol_version": con["protocol_version"],
           "state": "ready_for_review" if needs_approval else "in_progress",
           "severity": "warning" if needs_approval else "info", "timestamp": now_iso(), "source": "connector proposal",
           "owner": actor, "linked_evidence": [connector_id],
           "next_action": "Human approver reviews exact inputs, target revision and side effects." if needs_approval
           else "Execute the read and record the outcome."}
    if action in SENSITIVE_ACTIONS and not reversible and not compensation:
        rec["limitations"] = ["irreversible sensitive action without a compensation path"]
    if con["trust_tier"] == "untrusted" and action != "read":
        rec["limitations"] = rec.get("limitations", []) + ["connector trust tier is 'untrusted'"]
    return store.put(rec, reason=f"propose {action} via {connector_id}")


def render_proposal(rec: dict) -> str:
    lines = [f"Connector action {rec['id']} — {rec['action'].upper()} via {rec['connector']}",
             f"  Target:            {rec['target']}",
             f"  Design revision:   {rec['affected_revision']} (variant {rec['variant']})",
             f"  Inputs:            {rec['inputs']}",
             f"  Side effects:      {rec['side_effects'] or 'none declared'}",
             f"  Reversible:        {rec['reversible']}   Compensation: {rec.get('compensation') or 'none'}",
             f"  Dry run available: {rec['dry_run_available']}",
             f"  Idempotency key:   {rec['idempotency_key']}",
             f"  Proposed by:       {rec['proposed_by']}",
             f"  Needs approval:    {rec['requires_human_approval']}"]
    for l in rec.get("limitations", []):
        lines.append(f"  ! {l}")
    return "\n".join(lines)


def approve(store, action_id, *, decision="approved", note="") -> dict:
    actor, verified, roles = store.check("connector_approve")
    rec = dict(store.get("connector_action", action_id))
    if rec["action_state"] not in ("proposed",):
        raise ValueError(f"{action_id} is '{rec['action_state']}', not awaiting approval")
    if rec["action"] in SENSITIVE_ACTIONS and actor == rec["proposed_by"]:
        raise PermissionError("segregation of duties: the proposer cannot approve a sensitive connector action")
    if store.identity["revision"] != rec["affected_revision"]:
        raise ValueError("design revision changed since the proposal; re-propose against the current revision")
    rec.update(action_state="approved" if decision == "approved" else "rejected", approved_by=actor,
               approver_verified=verified, approved_at=now_iso(), approval_note=note,
               approval_expires=(parse_iso(now_iso()) + dt.timedelta(hours=APPROVAL_TTL_HOURS)).isoformat().replace("+00:00", "Z"),
               state="approved" if decision == "approved" else "rejected",
               next_action="Agent may execute exactly these inputs once." if decision == "approved" else None)
    return store.put(rec, action="connector_approve", reason=f"{decision} {action_id}: {note}")


def check(store, action_id) -> tuple[bool, str]:
    rec = store.get("connector_action", action_id)
    if not rec:
        return False, "unknown action"
    if rec["action_state"] == "executed":
        return False, "already executed (idempotency key used)"
    if rec["action_state"] != "approved":
        return False, f"state is '{rec['action_state']}'"
    if rec.get("approval_expires") and parse_iso(rec["approval_expires"]) < parse_iso(now_iso()):
        return False, "approval expired"
    if store.identity["revision"] != rec["affected_revision"]:
        return False, "design revision changed since approval"
    if store.audit.find_idempotent(rec["idempotency_key"]):
        return False, "idempotency key already recorded as executed"
    return True, "approved: execute exactly the recorded inputs once, then record the outcome"


def record_outcome(store, action_id, *, result, evidence: str, external_id: str | None = None, error: str | None = None) -> dict:
    store.check("record_evidence")
    rec = dict(store.get("connector_action", action_id))
    if result not in ("success", "failed", "unknown", "compensated", "dead_lettered"):
        raise ValueError("result must be success/failed/unknown/compensated/dead_lettered")
    if result == "success" and not evidence:
        raise ValueError("success requires evidence (response hash, external object URL/ID); do not infer success")
    rec.update(action_state="executed" if result == "success" else result, outcome=result, outcome_evidence=evidence,
               external_id=external_id, error=(error or "")[:500] or None, executed_at=now_iso(),
               state={"success": "approved", "failed": "blocked", "unknown": "blocked",
                      "compensated": "superseded", "dead_lettered": "blocked"}[result],
               severity="info" if result == "success" else "blocking",
               next_action=None if result == "success" else "Human disposition required (retry, compensate, or close).")
    return store.put(rec, reason=f"outcome {result} for {action_id}",
                     idempotency_key=rec["idempotency_key"] if result == "success" else None)
