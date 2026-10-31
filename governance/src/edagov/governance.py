"""Konnect ↔ edagov governance bridge.

Konnect (the MCP server) classifies every tool call by effect and asks this
module before it runs a design-changing tool, then reports what happened:

    konnect dispatch ─► edagov konnect authorize ─► allow / deny (+ pre-hashes)
                   └──► tool handler runs (only on allow)
                   └──► edagov konnect record    ─► post-hashes, changed files,
                                                     evidence capture, audit

Design edits are authorized by **change windows**: a contributor requests a
scoped window (toolsets/tools, optional file globs, call budget, duration), a
different person with a reviewer role approves it, and every edit made inside
it is recorded with before/after file hashes in a hash-chained call ledger
that is itself anchored in the store's audit chain.

Effects (assigned by Konnect, see crates/konnect-core/src/governance/effects.rs):
  read, plan, ui        -> never need a window; not recorded here
  output, config_write,
  external              -> allowed for permitted actors; recorded
  design_write          -> needs an approved, unexpired window covering the tool
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import os
from pathlib import Path

from . import permissions
from .util import file_hash, new_id, now_iso, obj_hash, parse_iso, write_json
from .vocab import TOOL_EFFECTS

DEFAULTS = {
    "window_approver_roles": ["design_reviewer", "release_approver"],
    "allow_self_approved_windows": False,
    "max_window_hours": 24,
    "max_window_calls": 2000,
    "record_outputs": True,
    "capture_evidence_tools": [],
}
RECORDED_EFFECTS = ("output", "config_write", "external", "design_write")
DESIGN_SUFFIXES = (".kicad_sch", ".kicad_pcb", ".kicad_pro", ".kicad_sym", ".kicad_mod", ".kicad_dru",
                   ".kicad_wks", "sym-lib-table", "fp-lib-table")


def gov_policy(store) -> dict:
    return {**DEFAULTS, **(store.policy.get("governance") or {})}


# ------------------------------------------------------------------ ledger
class Ledger:
    """Hash-chained JSONL of Konnect calls (details the audit log only hashes)."""

    GENESIS = "sha256:" + "0" * 64

    def __init__(self, store):
        self.path = store.dir / "konnect" / "calls.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def entries(self) -> list[dict]:
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def append(self, entry: dict) -> dict:
        es = self.entries()
        entry = dict(entry, prev_hash=es[-1]["hash"] if es else self.GENESIS)
        entry["hash"] = obj_hash(entry)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        return entry

    def verify(self) -> tuple[bool, list[str]]:
        prev, problems = self.GENESIS, []
        for i, e in enumerate(self.entries(), start=1):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev_hash") != prev:
                problems.append(f"ledger entry {i}: chain broken")
            if obj_hash(body) != e.get("hash"):
                problems.append(f"ledger entry {i}: content altered")
            prev = e.get("hash")
        return not problems, problems


# ----------------------------------------------------------------- windows
def _window_expired(w: dict) -> bool:
    exp = parse_iso(w.get("expires_at"))
    return exp is not None and exp < parse_iso(now_iso())


def request_window(store, *, scope: list[str], reason: str, issue: str | None = None, hours: float = 8,
                   max_calls: int = 500, files: list[str] | None = None, branch: str | None = None) -> dict:
    actor, verified, _ = store.check("record_evidence")
    pol = gov_policy(store)
    if not scope:
        raise ValueError("scope is required: toolset names, 'tool:<name>' entries, or '*'")
    if hours <= 0 or hours > pol["max_window_hours"]:
        raise ValueError(f"hours must be in (0, {pol['max_window_hours']}] per policy")
    if max_calls <= 0 or max_calls > pol["max_window_calls"]:
        raise ValueError(f"max_calls must be in (0, {pol['max_window_calls']}] per policy")
    if not reason.strip():
        raise ValueError("reason is required")
    wid = new_id("change_window")
    rec = {
        "type": "change_window", "id": wid, "scope": sorted(set(scope)),
        "files": files or [], "reason": reason, "issue": issue, "branch": branch,
        "hours": hours, "max_calls": max_calls, "requested_by": actor, "requested_by_verified": verified,
        "window_state": "requested", "expires_at": "pending approval",
        "state": "ready_for_review", "severity": "attention", "timestamp": now_iso(),
        "source": "change window request", "owner": actor, "linked_evidence": [issue] if issue else [],
        "next_action": (f"A {' or '.join(pol['window_approver_roles'])} other than {actor} approves: "
                        f"edagov konnect window approve {wid}"),
    }
    return store.put(rec, reason=f"change window requested: {reason}")


def approve_window(store, wid: str, *, decision: str = "approved", note: str = "") -> dict:
    actor, verified, roles = store.actor()
    pol = gov_policy(store)
    if not any(r in pol["window_approver_roles"] for r in roles):
        store.audit.append(actor=actor, actor_verified=verified, action="denied:window_approve", object_type="change_window",
                           object_id=wid, reason="approver role missing", authorization="denied", result="denied")
        raise permissions.PermissionDenied(f"{actor} lacks a window approver role {pol['window_approver_roles']}")
    w = store.get("change_window", wid)
    if not w:
        raise ValueError(f"change window {wid} not found")
    if w["window_state"] != "requested":
        raise ValueError(f"{wid} is '{w['window_state']}', not awaiting approval")
    if actor == w["requested_by"] and not pol["allow_self_approved_windows"]:
        raise permissions.PermissionDenied("segregation of duties: the requester cannot approve their own change window")
    if w.get("revision") != store.identity["revision"]:
        raise ValueError("design revision changed since the request; request a new window")
    w = dict(w)
    if decision == "approved":
        exp = parse_iso(now_iso()) + dt.timedelta(hours=float(w["hours"]))
        w.update(window_state="approved", state="approved", severity="approved",
                 expires_at=exp.isoformat().replace("+00:00", "Z"),
                 next_action="Konnect design edits inside this scope are allowed until expiry or budget.")
    else:
        w.update(window_state="rejected", state="rejected", severity="blocking", next_action=None)
    w.update(approved_by=actor, approver_verified=verified, approver_roles=roles, decided_at=now_iso(), decision_note=note)
    return store.put(w, action="record_evidence", enforce=False, reason=f"window {decision}: {note}")


def close_window(store, wid: str, *, reason: str = "") -> dict:
    actor, verified, roles = store.actor()
    w = store.get("change_window", wid)
    if not w:
        raise ValueError(f"change window {wid} not found")
    pol = gov_policy(store)
    if actor != w["requested_by"] and not any(r in pol["window_approver_roles"] for r in roles):
        raise permissions.PermissionDenied("only the requester or an approver can close a window")
    w = dict(w, window_state="closed", state="superseded", severity="info", closed_by=actor, closed_at=now_iso(),
             close_reason=reason, next_action="Re-run ERC/DRC and gates on the changed design.")
    return store.put(w, action="record_evidence", enforce=False, reason=f"window closed: {reason}")


def calls_used(store, wid: str) -> int:
    return sum(1 for e in Ledger(store).entries() if e.get("window") == wid and e.get("phase") == "authorize"
               and e.get("decision") == "allow")


def windows(store) -> list[dict]:
    out = []
    for w in store.list("change_window"):
        w = dict(w)
        if w["window_state"] == "approved" and _window_expired(w):
            w["window_state_effective"] = "expired"
        else:
            w["window_state_effective"] = w["window_state"]
        w["calls_used"] = calls_used(store, w["id"])
        out.append(w)
    return out


def _covers(w: dict, tool: str, toolset: str | None) -> bool:
    for s in w.get("scope", []):
        if s == "*" or s == f"tool:{tool}" or (toolset and s == toolset):
            return True
    return False


def _rel(store, p: str) -> str | None:
    try:
        return Path(p).resolve().relative_to(store.root).as_posix()
    except (ValueError, OSError):
        return None


def _design_paths(store, paths: list[str]) -> tuple[list[str], list[str]]:
    """Split path arguments into (inside the governed root, outside it)."""
    inside, outside = [], []
    for p in paths:
        if not p:
            continue
        r = _rel(store, p)
        (inside if r is not None else outside).append(p)
    return inside, outside


def _hashes(paths: list[str]) -> dict:
    out = {}
    for p in paths:
        pp = Path(p)
        if pp.is_file():
            out[str(pp.resolve())] = file_hash(pp)
        elif pp.exists():
            out[str(pp.resolve())] = "directory"
        else:
            out[str(pp.resolve()) if pp.is_absolute() else p] = "absent"
    return out


# --------------------------------------------------------------- authorize
def authorize(store, *, tool: str, toolset: str | None, effect: str, call_id: str, paths: list[str],
              audit_only: bool = False) -> dict:
    if effect not in TOOL_EFFECTS:
        raise ValueError(f"effect must be one of {TOOL_EFFECTS}")
    actor, verified, roles = store.actor()
    ident = store.identity
    decision, reason, window, next_action = "allow", "", None, None
    inside, outside = _design_paths(store, paths)
    if effect in ("read", "plan", "ui"):
        reason = f"{effect} effect needs no authorization"
    elif not permissions.allowed("record_evidence", roles):
        decision = "deny"
        reason = f"actor '{actor}' has no role permitting Konnect {effect} actions on this design (roles: {roles or 'none'})"
        next_action = "A release approver grants a contributor role: edagov roles grant <actor> contributor"
    elif effect == "design_write":
        if ident.get("release_state") == "released":
            decision, reason = "deny", f"revision {ident['revision']} is released; released revisions are frozen"
            next_action = "Move to a new revision first: edagov revision <next> --reason ..."
        elif outside:
            decision, reason = "deny", f"design files outside the governed root {store.root}: {outside[:3]}"
            next_action = "Edit files inside the governed repository, or govern that design separately."
        else:
            candidates = [w for w in windows(store)
                          if w["window_state_effective"] == "approved" and w.get("revision") == ident["revision"]
                          and _covers(w, tool, toolset)]
            budget_ok = [w for w in candidates if w["calls_used"] < int(w["max_calls"])]
            file_ok = []
            for w in budget_ok:
                globs = w.get("files") or []
                rels = [_rel(store, p) for p in inside]
                if not globs or all(any(fnmatch.fnmatch(r, g) for g in globs) for r in rels if r):
                    file_ok.append(w)
            if file_ok:
                window = sorted(file_ok, key=lambda w: w.get("expires_at", ""))[0]["id"]
                reason = f"inside approved change window {window}"
            else:
                decision = "deny"
                if not candidates:
                    reason = f"no approved, unexpired change window covers '{tool}' (toolset {toolset or '?'}) for rev {ident['revision']}"
                elif not budget_ok:
                    reason = f"change window call budget exhausted for '{tool}'"
                else:
                    reason = f"target files are outside the window's file scope: {[_rel(store, p) for p in inside][:3]}"
                next_action = (f"Request a window: edagov konnect window request --scope {toolset or 'tool:' + tool} "
                               f"--reason \"...\"; a reviewer approves it.")
    else:
        reason = f"{effect} effect allowed for permitted actors; recorded"
    final = decision
    if audit_only and decision == "deny":
        final, reason = "allow", f"AUDIT MODE (would deny): {reason}"
    entry = Ledger(store).append({
        "phase": "authorize", "call_id": call_id, "tool": tool, "toolset": toolset, "effect": effect,
        "decision": final, "would_deny": audit_only and decision == "deny", "window": window, "reason": reason,
        "actor": actor, "actor_verified": verified, "agent": "konnect-mcp", "revision": ident["revision"],
        "variant": ident["variant"], "paths": paths, "pre_hashes": _hashes(inside) if final == "allow" else {},
        "timestamp": now_iso(),
    })
    store.audit.append(actor=actor, actor_verified=verified,
                       action="konnect.authorize" if final == "allow" else "denied:konnect.design_write",
                       object_type="konnect_tool", object_id=tool, revision=ident["revision"], after=entry,
                       reason=reason, source=f"konnect-mcp:{window or '-'}", corr=call_id,
                       authorization="allowed" if final == "allow" else "denied",
                       result="success" if final == "allow" else "denied")
    return {"decision": final, "window": window, "reason": reason, "next_action": next_action, "call_id": call_id,
            "effect": effect, "actor": actor}


# ------------------------------------------------------------------ record
def _result_status(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {"format": "text"}
    if isinstance(data, dict) and "content" in data and isinstance(data["content"], list):
        for c in data["content"]:
            if c.get("type") == "text":
                try:
                    data = json.loads(c.get("text", ""))
                except ValueError:
                    data = {"text": c.get("text", "")[:2000]}
                break
    summary = {}
    if isinstance(data, dict):
        for k in ("status", "verdict", "ready", "result", "passed", "score", "summary", "violation_count",
                  "error_count", "warning_count", "outcome"):
            if k in data:
                summary[k] = data[k] if not isinstance(data[k], (dict, list)) else obj_hash(data[k])
    return summary


def record(store, *, call_id: str, tool: str, toolset: str | None, effect: str, status: str, paths: list[str],
           result_text: str | None = None, capture: bool = False) -> dict:
    actor, verified, _ = store.actor()
    ident = store.identity
    ledger = Ledger(store)
    pre = next((e for e in reversed(ledger.entries()) if e.get("call_id") == call_id and e.get("phase") == "authorize"), None)
    inside, _ = _design_paths(store, paths)
    post = _hashes(inside)
    pre_h = (pre or {}).get("pre_hashes", {})
    changed = sorted(p for p in set(pre_h) | set(post) if pre_h.get(p) != post.get(p))
    design_changed = [p for p in changed if p.endswith(DESIGN_SUFFIXES)]
    out = {"call_id": call_id, "tool": tool, "status": status, "changed_files": changed, "evidence": None}
    pol = gov_policy(store)
    if capture and status == "ok" and tool in pol["capture_evidence_tools"] and result_text:
        rdir = store.run_dir("konnect")
        rpath = rdir / f"{call_id}-{tool}.json"
        rpath.write_text(result_text, encoding="utf-8")
        summary = _result_status(result_text)
        art = {
            "type": "artifact", "id": new_id("artifact", f"konnect-{tool}-{ident['revision']}-{call_id[-8:]}"),
            "kind": "report", "path": str(rpath), "hash": file_hash(rpath), "source_revision": ident["revision"],
            "owner": actor, "tags": [f"konnect:{tool}"], "konnect_summary": summary,
            "inputs": [{"path": p, "hash": h} for p, h in post.items() if h not in ("directory", "absent")],
            "claim_scope": (f"Automated Konnect `{tool}` result for rev {ident['revision']}. It records what the tool "
                            "reported; it is not a human review and not gate evidence until a reviewer accepts it."),
            "reviewer": None, "state": "ready_for_review", "severity": "attention", "timestamp": now_iso(),
            "source": "konnect-mcp (automated)", "linked_evidence": [str(rpath)],
            "next_action": "Reviewer inspects the result; promote with edagov review <id> if accepted.",
        }
        out["evidence"] = store.put(art, enforce=False, reason=f"Konnect {tool} result captured")["id"]
    if effect in RECORDED_EFFECTS or out["evidence"]:
        entry = ledger.append({
            "phase": "complete", "call_id": call_id, "tool": tool, "toolset": toolset, "effect": effect,
            "status": status, "window": (pre or {}).get("window"), "actor": actor, "revision": ident["revision"],
            "post_hashes": post, "changed_files": changed, "evidence": out["evidence"], "timestamp": now_iso(),
        })
        store.audit.append(actor=actor, actor_verified=verified, action=f"konnect.complete.{effect}",
                           object_type="konnect_tool", object_id=tool, revision=ident["revision"], after=entry,
                           reason=f"{status}; {len(changed)} file(s) changed", source=f"konnect-mcp:{(pre or {}).get('window') or '-'}",
                           corr=call_id, result="success" if status == "ok" else "failure")
    if design_changed:
        out["note"] = ("Design files changed: ERC/DRC/simulation evidence bound to the old file hashes is now stale "
                       "and the affected gates will ask for a re-run.")
    return out


def status(store) -> dict:
    ok, problems = Ledger(store).verify()
    ws = windows(store)
    return {
        "identity": {k: store.identity.get(k) for k in ("design_id", "board_id", "revision", "variant", "release_state")},
        "actor": store.actor()[0], "roles": store.actor()[2],
        "windows": [{k: w.get(k) for k in ("id", "scope", "files", "window_state_effective", "expires_at", "calls_used",
                                            "max_calls", "requested_by", "approved_by", "reason")} for w in ws],
        "active_windows": [w["id"] for w in ws if w["window_state_effective"] == "approved"],
        "pending_human_decisions": [f"edagov konnect window approve {w['id']}" for w in ws if w["window_state"] == "requested"],
        "ledger_verified": ok, "ledger_problems": problems, "ledger_entries": len(Ledger(store).entries()),
    }
