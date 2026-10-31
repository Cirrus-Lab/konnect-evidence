"""Store, audit chain, schema and permission behaviour (Dashboard Spec §8–§9, acceptance criteria 9–10)."""
import json

import pytest

from edagov import permissions, records, schema
from edagov.audit import AuditLog
from edagov.store import Store


def test_store_versions_are_immutable_and_audited(design, as_actor):
    st = design
    records.requirement(st, "REQ-1", "3V3 rail", source="spec", owner="designer@x", priority="high",
                        method="test", acceptance="3.234-3.366 V")
    records.requirement(st, "REQ-1", "3V3 rail ±2%", source="spec", owner="designer@x", priority="high",
                        method="test", acceptance="3.234-3.366 V")
    hist = st.history("requirement", "REQ-1")
    assert [h["record_version"] for h in hist] == [1, 2]
    assert hist[0]["text"] == "3V3 rail"  # earlier version preserved, not edited
    ok, problems = st.audit.verify()
    assert ok, problems


def test_audit_tamper_is_detected(design):
    log = design.audit.path
    lines = log.read_text().splitlines()
    ev = json.loads(lines[1])
    ev["actor"] = "mallory"
    lines[1] = json.dumps(ev, sort_keys=True)
    log.write_text("\n".join(lines) + "\n")
    ok, problems = AuditLog(log).verify()
    assert not ok and any("hash mismatch" in p for p in problems)


def test_schema_keeps_states_distinct():
    bad = {"type": "run", "id": "RUN-X", "created_at": "t", "design_id": "D", "revision": "B", "variant": "v",
           "tool": "kicad-cli", "tool_version": "10", "inputs": [], "result_class": "clean", "claim_scope": "x",
           "executed": False}
    assert any("cannot be 'clean'" in p for p in schema.validate(bad))
    bad["result_class"] = "passed"
    assert any("not in" in p for p in schema.validate(bad))


def test_viewer_cannot_approve_or_mutate(design, as_actor):
    as_actor("viewer@x")
    with pytest.raises(permissions.PermissionDenied):
        records.issue(design, "x", severity="low", owner="v", affected=[])
    from edagov import gates
    with pytest.raises(permissions.PermissionDenied):
        gates.approve(design, "requirements", "approved")
    denied = [e for e in design.audit.events() if e["result"] == "denied"]
    assert denied, "denials are audited"


def test_unknown_actor_is_denied_by_default(design, as_actor):
    as_actor("stranger@x")
    with pytest.raises(permissions.PermissionDenied):
        records.requirement(design, None, "t", source="s", owner="o", priority="p", method="test", acceptance="1 V")


def test_reviewer_cannot_administer_connectors(design, as_actor):
    from edagov import connectors
    as_actor("reviewer@x")
    with pytest.raises(permissions.PermissionDenied):
        connectors.register(design, provider="p", protocol="mcp", protocol_version="2026-07-28", transport="stdio",
                            endpoint="local", scopes=[], data_classes=[])


def test_gate_approval_role_separation(design, as_actor):
    from edagov import gates
    as_actor("supply@x")
    with pytest.raises(permissions.PermissionDenied):
        gates.approve(design, "pcb", "approved")


def test_store_requires_init(tmp_path):
    from edagov.store import StoreError
    with pytest.raises(StoreError):
        Store(tmp_path)
