"""BOM, manufacturing manifest, gates, connectors, GitHub, claims, snapshots, dashboard."""
import json
import subprocess
from pathlib import Path

import pytest

from edagov import (bom, claims, connectors, gates, github, inventory, kicad, manufacturing, records,
                    snapshot)
from edagov.dashboard import render


def _codes(line):
    return {f["code"] for f in line["findings"]}


def test_bom_findings(design):
    syms = inventory.inventory(design.root / "kicad")["symbols"]
    res = bom.ingest_csv(design, design.root / "bom" / "bom-revB.csv", cross_check_symbols=syms)
    by = {l["internal_item"]: l for l in res["lines"]}
    assert "generic_mpn" in _codes(by["EH-3001"])
    alt = by["EH-2001-ALT"]
    assert alt["alternate_state"] is None and alt["alternate_state_claimed"] == "production_approved"
    assert {"alternate_unsupported", "headline_equivalence", "broker_source"} <= _codes(alt)
    assert "lifecycle_stale" in _codes(by["EH-1003"])
    assert res["cross_check"] == {"in_bom_not_schematic": [], "in_schematic_not_bom": []}


def test_bom_qty_and_duplicate(design, tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("References,Qty,Manufacturer,MPN,Lifecycle,Lifecycle Source,Lifecycle Date,Approved Source\n"
                 "R1-R3,2,Yageo,RC0603FR-0710KL,Active,x,2026-10-30,Mouser\nR3,1,Yageo,RC0603FR-0710KL,Active,x,2026-10-30,Mouser\n")
    res = bom.ingest_csv(design, p)
    assert "qty_mismatch" in _codes(res["lines"][0])
    assert "duplicate_reference" in _codes(res["lines"][1])


def test_manifest_complete_and_tamper(design):
    bom.ingest_csv(design, design.root / "bom" / "bom-revB.csv")
    pkg = manufacturing.build(design, design.root / "fab")
    assert pkg["completeness"] == "complete", pkg["consistency_findings"]
    assert all(s["state"] == "not_started" for s in pkg["signoffs"].values())
    (design.root / "fab" / "buck-demo-F_Cu.gbr").write_text("changed")
    ok, problems = manufacturing.verify(pkg)
    assert not ok and "hash changed" in problems[0]


def test_manifest_revision_mismatch(design):
    design.set_revision("C", reason="test")
    pkg = manufacturing.build(design, design.root / "fab")
    assert pkg["completeness"] == "conflict"
    assert any(f["code"] == "revision_mismatch" for f in pkg["consistency_findings"])


def test_signoffs_are_separate_roles(design, as_actor):
    bom.ingest_csv(design, design.root / "bom" / "bom-revB.csv")
    pkg = manufacturing.build(design, design.root / "fab")
    as_actor("fab@x")
    manufacturing.signoff(design, pkg["id"], "fabrication_dfm", "approved")
    from edagov.permissions import PermissionDenied
    with pytest.raises(PermissionDenied):
        manufacturing.signoff(design, pkg["id"], "release_control", "approved")


def _reqs(st):
    records.requirement(st, "REQ-1", "3V3", source="s", owner="designer@x", priority="h", method="test",
                        acceptance="3.234-3.366 V", status="approved")
    records.block(st, "BLK-1", "Power", purpose="p", owner="designer@x", interfaces=["J1"], allocated=["REQ-1"])


def test_gate_states_and_stale_approval(design, as_actor):
    _reqs(design)
    ev = gates.evaluate_gate(design, "requirements")
    assert ev["automation_state"] == "ready_for_review" and ev["state"] == "ready_for_review"
    as_actor("reviewer@x")
    apr = gates.approve(design, "requirements", "approved", note="ok")
    assert gates.evaluate_gate(design, "requirements")["state"] == "approved"
    as_actor("designer@x")
    records.requirement(design, "REQ-2", "ripple", source="s", owner="designer@x", priority="h", method="test",
                        acceptance="30 mVpp", status="approved")
    ev = gates.evaluate_gate(design, "requirements")
    assert ev["state"] == "ready_for_review" and "stale" in ev["approval_note"], "approval bound to old evidence"
    assert apr["evidence_fingerprint"] != ev["evidence_fingerprint"]


def test_cannot_approve_blocked_gate_without_exception(design, as_actor):
    kicad.ingest_report(design, "drc", design.root / "reports" / "drc.json", design.root / "kicad")
    as_actor("reviewer@x")
    with pytest.raises(ValueError):
        gates.approve(design, "pcb", "approved")
    with pytest.raises(ValueError):
        gates.approve(design, "pcb", "approved_with_exception")


def test_exception_covers_violation(design, as_actor):
    drc = kicad.ingest_report(design, "drc", design.root / "reports" / "drc.json", design.root / "kicad")
    as_actor("release@x")
    records.exception(design, "Silk clip accepted", rationale="cosmetic; fixed rev C", affected_claims=[drc["id"]],
                      review_trigger="rev C layout")
    res = gates.run_check(design, "B", design.policy, "pcb", "run_clean:drc")
    assert res["result"] == "pass" and "exception" in res["detail"]


def test_missing_vs_not_applicable(design):
    pol = design.policy
    pol["overrides"] = {"pcb": {"evidence_tag:emc_plan": {"not_applicable": "battery-only, no ports (ADR-9)"}}}
    from edagov.util import write_json
    write_json(design.dir / "policy.json", pol)
    ev = gates.evaluate_gate(design, "pcb")
    res = {c["check"]: c["result"] for c in ev["checks"]}
    assert res["evidence_tag:emc_plan"] == "not_applicable"
    assert res["evidence_tag:si_analysis"] == "missing"
    assert res["run_clean:drc"] == "missing"


def test_connector_governance(design, as_actor):
    as_actor("admin@x")
    connectors.register(design, cid="CON-F", provider="fab", protocol="mcp", protocol_version="2026-07-28",
                        transport="streamable-http", endpoint="https://mcp.fab.example/mcp", scopes=["q"], data_classes=["m"])
    as_actor("release@x")
    with pytest.raises(ValueError):
        connectors.propose(design, connector_id="CON-F", action="publish", target="t",
                           inputs={"token": "ghp_" + "a" * 36}, side_effects=[], reversible=False)
    act = connectors.propose(design, connector_id="CON-F", action="publish", target="quote", inputs={"qty": "5"},
                             side_effects=["sends data"], reversible=False, compensation="delete request")
    assert act["requires_human_approval"] and not connectors.check(design, act["id"])[0]
    with pytest.raises(PermissionError):
        connectors.approve(design, act["id"])  # proposer cannot approve sensitive action
    as_actor("release2@x")
    connectors.approve(design, act["id"])
    assert connectors.check(design, act["id"])[0]
    with pytest.raises(ValueError):
        connectors.record_outcome(design, act["id"], result="success", evidence="")
    connectors.record_outcome(design, act["id"], result="success", evidence="quote Q-123 response sha256:ab")
    ok, why = connectors.check(design, act["id"])
    assert not ok and "already executed" in why


def test_github_interpretation(design):
    rec = github.sync(design, "example-hw/buck-demo", 42, from_json=str(design.root / "github" / "pr-42.json"))
    assert rec["sync_state"] == "synced" and rec["gitflow_lane"] == "feature"
    stale = [r for r in rec["reviews"] if r["reviewer"] == "layout-lead"][0]
    assert stale["state"] == "stale_dismissed"
    assert rec["current_diff_approvals"] == 0 and rec["approvals_state"] == "not_satisfied"
    assert rec["blocking_checks"] == ["edagov-gates"]
    closes = [l for l in rec["issue_links"] if l["issue"].endswith("#17")][0]
    assert closes["auto_close"] is False, "develop is not the default branch"


def test_github_failure_is_visible(design, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    rec = github.sync(design, "o/r", 1, from_json=str(bad))
    assert rec["sync_state"] == "invalid" and rec["state"] == "blocked" and rec["provisional"]


def test_claim_lint_and_secret_scan(tmp_path):
    hits = claims.lint_claims("The board is EMC compliant. The alternate is a drop-in replacement.")
    assert {h["rule"] for h in hits} >= {"compliant", "drop_in"}
    assert not claims.lint_claims("ERC clean does not prove the circuit functions.")
    p = tmp_path / "x.md"
    p.write_text("token: ghp_" + "b" * 36 + "\n")
    assert claims.scan_paths([p])[0]["type"] in ("github_token", "password_assignment")


def test_snapshot_diff_and_dashboard(design, as_actor, tmp_path):
    _reqs(design)
    as_actor("reviewer@x")
    a = snapshot.build(design, tmp_path / "s")
    as_actor("designer@x")
    kicad.ingest_report(design, "drc", design.root / "reports" / "drc.json", design.root / "kicad")
    as_actor("reviewer@x")
    b = snapshot.build(design, tmp_path / "s")
    d = snapshot.compare(snapshot.load(a["zip"]), snapshot.load(b["zip"]))
    assert any(x.startswith("run/") for x in d["added"])
    assert any(g["gate"] == "pcb" for g in d["gate_changes"])
    html = render(design, tmp_path / "dash.html", diff=d).read_text()
    assert "Documentation-only" in html and "aria-live" in html and 'role="tablist"' in html
    assert not claims.scan_text(html)
    assert b["manifest"]["read_only"] and b["manifest"]["caveats"]


def test_viewer_cannot_export(design, as_actor, tmp_path):
    as_actor("viewer@x")
    from edagov.permissions import PermissionDenied
    with pytest.raises(PermissionDenied):
        snapshot.build(design, tmp_path)


def test_demo_script_end_to_end(tmp_path):
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(["sh", str(root / "examples/buck-demo/build_demo.sh"), str(tmp_path / "w")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "Audit chain verified." in r.stdout
    assert (tmp_path / "w" / "dashboard.html").exists()
