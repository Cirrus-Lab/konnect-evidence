"""Deny-by-default role permissions (Dashboard Spec §8).

Read permission never implies approval or mutation. Roles are assigned per
actor in `.edagov/roles.json`:

    {"actors": {"alice@example.com": ["design_reviewer"], ...}}

Actor identity comes from EDAGOV_ACTOR or git config. Unless a verified
integration supplies it, identity is recorded as *unverified*.
"""
from __future__ import annotations

import os
import subprocess

# action -> roles allowed to perform it
POLICY: dict[str, tuple[str, ...]] = {
    "read": ("viewer", "contributor", "design_reviewer", "supply_reviewer", "manufacturing_reviewer",
             "release_approver", "connector_admin", "auditor"),
    "record_evidence": ("contributor", "design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver"),
    "run_tool": ("contributor", "design_reviewer", "manufacturing_reviewer", "release_approver"),
    "create_issue": ("contributor", "design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver"),
    "acknowledge": ("contributor", "design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver"),
    "review:design": ("design_reviewer", "release_approver"),
    "review:supply": ("supply_reviewer", "release_approver"),
    "review:manufacturing": ("manufacturing_reviewer", "release_approver"),
    "approve_gate": ("design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver"),
    "approve_release": ("release_approver",),
    "record_exception": ("release_approver", "design_reviewer"),
    "connector_admin": ("connector_admin",),
    "connector_approve": ("release_approver",),
    "export_snapshot": ("design_reviewer", "supply_reviewer", "manufacturing_reviewer", "release_approver", "auditor"),
    "audit_read": ("auditor", "release_approver"),
}

# Which reviewer role may approve which gate (role separation, Workflow Guide §8).
GATE_APPROVER_ROLES = {
    "requirements": ("design_reviewer", "release_approver"),
    "architecture": ("design_reviewer", "release_approver"),
    "schematic_library": ("design_reviewer",),
    "simulation": ("design_reviewer",),
    "pcb": ("design_reviewer",),
    "supply": ("supply_reviewer",),
    "release": ("release_approver",),
    "change": ("design_reviewer", "release_approver"),
}


class PermissionDenied(PermissionError):
    pass


def current_actor() -> tuple[str, bool]:
    """Return (actor, verified). Identity is never claimed as verified locally."""
    actor = os.environ.get("EDAGOV_ACTOR")
    if not actor:
        try:
            actor = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=5).stdout.strip()
        except Exception:
            actor = ""
    verified = os.environ.get("EDAGOV_ACTOR_VERIFIED_BY") is not None  # set only by a verified integration (e.g. CI OIDC)
    return (actor or "unknown"), verified


def roles_for(actor: str, roles_doc: dict | None) -> list[str]:
    if not roles_doc:
        return []
    return list(roles_doc.get("actors", {}).get(actor, []))


def allowed(action: str, roles: list[str]) -> bool:
    permitted = POLICY.get(action)
    if permitted is None:
        return False  # unknown action -> deny
    return any(r in permitted for r in roles)


def require(action: str, actor: str, roles: list[str]) -> None:
    if not allowed(action, roles):
        raise PermissionDenied(
            f"actor '{actor}' with roles {roles or '[none]'} is not permitted to '{action}' "
            f"(allowed: {list(POLICY.get(action, ()))}); deny-by-default"
        )


def require_gate_approver(gate: str, actor: str, roles: list[str]) -> None:
    permitted = GATE_APPROVER_ROLES.get(gate, ())
    if not any(r in permitted for r in roles):
        raise PermissionDenied(f"actor '{actor}' with roles {roles} cannot approve gate '{gate}' (needs one of {list(permitted)})")
