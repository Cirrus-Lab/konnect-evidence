"""Helpers that create well-formed design-level records with the status envelope."""
from __future__ import annotations

from pathlib import Path

from .util import file_hash, new_id, now_iso
from .gitinfo import source_revision


def _env(store, *, state, severity, source, next_action, linked=None, owner=None):
    return {"state": state, "severity": severity, "timestamp": now_iso(), "source": source,
            "owner": owner or store.identity.get("design_authority"), "linked_evidence": linked or [],
            "next_action": next_action}


def requirement(store, rid, text, *, source, owner, priority, method, acceptance, status="draft",
                conditions=None, standard=None, variant_scope=None):
    rec = {"type": "requirement", "id": rid or new_id("requirement"), "text": text, "source": source, "owner": owner,
           "priority": priority, "verification_method": method, "acceptance": acceptance, "status": status,
           "conditions": conditions, "standard_edition": standard, "variant_scope": variant_scope,
           "evidence_links": [],
           **_env(store, state="ready_for_review" if status == "approved" else "in_progress",
                  severity="blocking" if status == "unmet" else "info", source=source,
                  next_action="Link verification evidence." if status != "verified" else None, owner=owner)}
    return store.put(rec, reason="requirement captured")


def block(store, bid, name, *, purpose, owner, interfaces, allocated, boundaries=None):
    rec = {"type": "architecture_block", "id": bid or new_id("architecture_block", name), "name": name,
           "purpose": purpose, "owner": owner, "interfaces": interfaces, "allocated_requirements": allocated,
           "boundaries": boundaries or {},
           **_env(store, state="in_progress", severity="info", source="architecture record",
                  next_action="Allocate verification evidence.", owner=owner)}
    return store.put(rec, reason="architecture block recorded")


def issue(store, title, *, severity, owner, affected, gates=None, due=None, containment=None, iid=None, external=None):
    store.check("create_issue")
    rec = {"type": "issue", "id": iid or new_id("issue"), "title": title, "severity": severity, "state": "open",
           "owner": owner, "affected": affected, "gates": gates or [], "due_or_trigger": due, "containment": containment,
           "disposition": None, "closure_evidence": [], "external_ref": external,
           **_env(store, state="blocked" if severity in ("high", "critical") else "in_progress",
                  severity="blocking" if severity in ("high", "critical") else "warning",
                  source="issue record", next_action=f"{owner}: disposition by {due or 'trigger date TBD'}",
                  linked=affected, owner=owner)}
    # Issue severity/state use the issue vocabulary; the display tone is derived from it.
    rec["gate_effect"] = rec["state"]
    rec["state"] = "open"
    rec["severity"] = severity
    return store.put(rec, action="create_issue", reason=f"issue opened: {title}")


def close_issue(store, iid, *, disposition, closure_evidence):
    store.check("create_issue")
    rec = dict(store.get("issue", iid))
    if not closure_evidence:
        raise ValueError("closing an issue requires closure evidence IDs/links")
    rec.update(state="closed", disposition=disposition, closure_evidence=closure_evidence, gate_effect="none",
               closed_at=now_iso(), next_action=None)
    return store.put(rec, action="create_issue", reason=f"issue closed: {disposition}")


def exception(store, title, *, rationale, affected_claims, review_trigger, limitations=None, eid=None):
    actor, verified, roles = store.check("record_exception")
    rec = {"type": "exception", "id": eid or new_id("exception"), "title": title, "rationale": rationale,
           "approver": actor, "approver_verified": verified, "approver_roles": roles, "approved_at": now_iso(),
           "review_trigger": review_trigger, "affected_claims": affected_claims, "limitations": limitations or [],
           "note": "Accepted means a named authority accepted the stated risk; it does not mean the risk disappeared.",
           **_env(store, state="approved_with_exception", severity="warning", source="exception record",
                  next_action=f"Re-review at trigger: {review_trigger}", linked=affected_claims, owner=actor)}
    return store.put(rec, action="record_exception", reason=f"exception: {title}")


def review(store, target, *, state, role, comments="", requested_changes=None):
    action = {"design_reviewer": "review:design", "supply_reviewer": "review:supply",
              "manufacturing_reviewer": "review:manufacturing", "release_approver": "approve_release"}.get(role, "review:design")
    actor, verified, roles = store.check(action)
    if role not in roles:
        from .permissions import PermissionDenied
        raise PermissionDenied(f"actor {actor} does not hold role {role}")
    rec = {"type": "review", "id": new_id("review"), "target": target, "target_revision": store.identity["revision"],
           "reviewer": actor, "reviewer_verified": verified, "reviewer_role": role, "state": state,
           "comments": comments, "requested_changes": requested_changes or [],
           **_env(store, state={"approved": "approved", "requested_changes": "blocked"}.get(state, "in_progress"),
                  severity="approved" if state == "approved" else "attention", source="review record",
                  next_action=None if state == "approved" else "Address review comments.", linked=[target], owner=actor)}
    stored = store.put(rec, action=action, reason=f"review of {target}: {state}")
    # Mark the reviewed evidence with its reviewer (used by evidence_tag checks).
    for rtype in ("artifact", "run"):
        tgt = store.get(rtype, target)
        if tgt and state == "approved":
            tgt = dict(tgt, reviewer=actor, reviewer_role=role, reviewed_at=now_iso(), review_id=stored["id"])
            store.put(tgt, action=action, reason=f"reviewed by {actor}")
    return stored


def evidence(store, path_or_url, *, kind, tags, owner, claim_scope, aid=None, standard=None, method=None):
    p = Path(path_or_url)
    is_file = p.exists() and p.is_file()
    rec = {"type": "artifact", "id": aid or new_id("artifact", f"{kind}-{p.name}-{store.identity['revision']}"),
           "kind": kind, "path": str(p.resolve()) if is_file else str(path_or_url),
           "hash": file_hash(p) if is_file else "unhashed:external-reference",
           "source_revision": source_revision(store.root), "owner": owner, "tags": tags, "claim_scope": claim_scope,
           "standard_edition": standard, "method": method, "reviewer": None,
           **_env(store, state="ready_for_review", severity="attention", source="evidence attachment",
                  next_action="Name a reviewer.", linked=[str(path_or_url)], owner=owner)}
    if not is_file:
        rec["limitations"] = ["external reference not hashed; content may change"]
    return store.put(rec, reason=f"evidence attached: {tags}")


def decision(store, title, *, rationale, alternatives, consequences, tags=None, status="accepted", did=None):
    rec = {"type": "decision", "id": did or new_id("decision", title), "title": title, "rationale": rationale,
           "alternatives": alternatives, "consequences": consequences, "status": status, "tags": tags or [],
           **_env(store, state="ready_for_review", severity="info", source="decision record", next_action=None)}
    return store.put(rec, reason=f"decision: {title}")


def assumption(store, text, *, owner, review_condition, aid=None):
    rec = {"type": "assumption", "id": aid or new_id("assumption"), "text": text, "owner": owner,
           "review_condition": review_condition,
           **_env(store, state="in_progress", severity="attention", source="assumption record",
                  next_action=f"Verify or retire by: {review_condition}", owner=owner)}
    return store.put(rec, reason="assumption recorded")


def library(store, path, *, provenance, license, reviewer_note=None):
    """Record provenance and license for a library asset found by inventory (Workflow Guide §3.3)."""
    store.check("record_evidence")
    hits = [a for a in store.list("artifact", revision=store.identity["revision"])
            if a.get("kind") in ("symbol_library", "footprint_library", "model_3d", "spice_model")
            and (a.get("path") == path or a.get("path", "").endswith(path))]
    if not hits:
        raise ValueError(f"no library artifact for '{path}' in this revision; run `edagov inventory` first")
    out = []
    for a in hits:
        rec = dict(a, provenance=provenance, license=license, provenance_note=reviewer_note)
        out.append(store.put(rec, reason=f"library provenance for {a['path']}"))
    return out[-1]
