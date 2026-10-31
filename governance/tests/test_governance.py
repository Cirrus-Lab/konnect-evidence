"""Konnect integration: change windows, authorize/record, ledger, stale evidence, MCP server."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from edagov import gates, governance, kicad, mcp_server, permissions


def _window(design, as_actor, scope=("sch_wiring",), files=None, max_calls=5, approve=True):
    as_actor("designer@x")
    w = governance.request_window(design, scope=list(scope), reason="add pull-up", files=files, max_calls=max_calls)
    if approve:
        as_actor("reviewer@x")
        w = governance.approve_window(design, w["id"])
        as_actor("designer@x")
    return w


def _auth(design, tool="add_wire", toolset="sch_wiring", effect="design_write", paths=None, call="C1", audit=False):
    return governance.authorize(design, tool=tool, toolset=toolset, effect=effect, call_id=call,
                                paths=paths if paths is not None else [str(design.root / "kicad" / "buck-demo.kicad_sch")],
                                audit_only=audit)


def test_design_write_denied_without_window(design):
    res = _auth(design)
    assert res["decision"] == "deny" and "no approved" in res["reason"]
    assert "window request" in res["next_action"]
    assert governance.Ledger(design).entries()[-1]["decision"] == "deny"
    assert any(e["action"] == "denied:konnect.design_write" for e in design.audit.events())


def test_requested_window_is_not_enough(design, as_actor):
    _window(design, as_actor, approve=False)
    assert _auth(design)["decision"] == "deny"


def test_requester_cannot_approve_own_window(design, as_actor):
    as_actor("release@x")
    w = governance.request_window(design, scope=["*"], reason="r")
    with pytest.raises(permissions.PermissionDenied):
        governance.approve_window(design, w["id"])
    as_actor("viewer@x")
    with pytest.raises(permissions.PermissionDenied):
        governance.approve_window(design, w["id"])


def test_window_allows_scoped_tools_and_records_changes(design, as_actor):
    w = _window(design, as_actor)
    sch = design.root / "kicad" / "buck-demo.kicad_sch"
    res = _auth(design, paths=[str(sch)], call="C2")
    assert res["decision"] == "allow" and res["window"] == w["id"]
    sch.write_text(sch.read_text() + "\n")  # simulate Konnect's edit
    rec = governance.record(design, call_id="C2", tool="add_wire", toolset="sch_wiring", effect="design_write",
                            status="ok", paths=[str(sch)])
    assert rec["changed_files"] == [str(sch.resolve())] and "stale" in rec["note"]
    # tool outside scope is refused
    assert _auth(design, tool="move_component", toolset="pcb_components", call="C3")["decision"] == "deny"
    ok, problems = governance.Ledger(design).verify()
    assert ok, problems


def test_window_budget_and_file_scope(design, as_actor):
    _window(design, as_actor, files=["kicad/power.kicad_sch"], max_calls=1)
    root_sch = str(design.root / "kicad" / "buck-demo.kicad_sch")
    power = str(design.root / "kicad" / "power.kicad_sch")
    assert "outside the window's file scope" in _auth(design, paths=[root_sch], call="A")["reason"]
    assert _auth(design, paths=[power], call="B")["decision"] == "allow"
    assert "budget exhausted" in _auth(design, paths=[power], call="C")["reason"]


def test_paths_outside_root_and_released_revisions(design, as_actor, tmp_path_factory):
    _window(design, as_actor, scope=["*"])
    other = tmp_path_factory.mktemp("other") / "x.kicad_sch"
    other.write_text("(kicad_sch)")
    assert "outside the governed root" in _auth(design, paths=[str(other)], call="O")["reason"]
    from edagov.util import read_json, write_json
    ident = read_json(design.dir / "design.json")
    write_json(design.dir / "design.json", dict(ident, release_state="released"))
    assert "released" in _auth(design, call="R")["reason"]


def test_viewer_actor_cannot_drive_writes(design, as_actor):
    _window(design, as_actor, scope=["*"])
    as_actor("viewer@x")
    res = _auth(design, effect="output", tool="export_gerber", toolset="pcb_export", call="V")
    assert res["decision"] == "deny" and "no role" in res["reason"]


def test_audit_only_mode_never_blocks_but_records(design):
    res = _auth(design, audit=True, call="AU")
    assert res["decision"] == "allow" and res["reason"].startswith("AUDIT MODE")
    assert governance.Ledger(design).entries()[-1]["would_deny"] is True


def test_evidence_capture(design):
    result = json.dumps({"content": [{"type": "text", "text": json.dumps({"verdict": "INCOMPLETE", "score": 70})}]})
    rec = governance.record(design, call_id="E1", tool="run_design_review", toolset="design_review", effect="read",
                            status="ok", paths=[str(design.root / "kicad" / "buck-demo.kicad_sch")],
                            result_text=result, capture=True)
    art = design.get("artifact", rec["evidence"])
    assert art["tags"] == ["konnect:run_design_review"] and art["reviewer"] is None
    assert art["konnect_summary"] == {"verdict": "INCOMPLETE", "score": 70}
    assert "not a human review" in art["claim_scope"]


def test_gate_flags_evidence_whose_inputs_changed(design, monkeypatch):
    monkeypatch.setenv("FAKE_VIOLATIONS", "0")
    run = kicad.run_check(design, "drc", design.root / "kicad", authorize="t")
    assert gates.run_check(design, "B", design.policy, "pcb", "run_clean:drc")["result"] == "pass"
    pcb = design.root / "kicad" / "buck-demo.kicad_pcb"
    pcb.write_text(pcb.read_text() + "\n")  # Konnect moved a footprint
    res = gates.run_check(design, "B", design.policy, "pcb", "run_clean:drc")
    assert res["result"] == "fail" and "changed since this run" in res["detail"]


def test_cli_kv_protocol_used_by_konnect(design, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    env = {"EDAGOV_ACTOR": "designer@x", "PATH": "/usr/bin:/bin"}
    cmd = [str(root / "bin" / "edagov"), "--root", str(design.root), "konnect", "authorize", "--tool", "add_wire",
           "--toolset", "sch_wiring", "--effect", "design_write", "--call-id", "K1", "--format", "kv",
           "--path", str(design.root / "kicad" / "buck-demo.kicad_sch")]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    kv = dict(l.split("=", 1) for l in r.stdout.strip().splitlines())
    assert kv["decision"] == "deny" and kv["effect"] == "design_write"
    r = subprocess.run([str(root / "bin" / "edagov"), "--root", str(design.root), "konnect", "record", "--tool",
                        "run_drc", "--effect", "read", "--call-id", "K2", "--status", "ok", "--capture", "--format", "kv"],
                       input='{"violation_count": 0}', capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert dict(l.split("=", 1) for l in r.stdout.strip().splitlines())["evidence"].startswith("ART-KONNECT-RUN-DRC")


def _mcp(lines):
    out = io.StringIO()
    mcp_server.serve(io.StringIO("\n".join(json.dumps(l) for l in lines) + "\n"), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_mcp_server_protocol_and_tools(design, monkeypatch):
    monkeypatch.setenv("EDAGOV_ROOT", str(design.root))
    resp = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "gov_window_request",
                                                                       "arguments": {"scope": ["sch_wiring"], "reason": "fix net"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "gov_inventory", "arguments": {"project": str(design.root / "kicad")}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "gov_pending_human_actions", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "gov_window_request", "arguments": {"reason": "x"}}},
    ])
    assert [r["id"] for r in resp] == [1, 2, 3, 4, 5, 6], "notifications get no response"
    assert resp[0]["result"]["protocolVersion"] == "2025-06-18"
    names = {t["name"] for t in resp[1]["result"]["tools"]}
    assert "gov_window_request" in names and not any("approve" in n for n in names), "approvals are human-only"
    assert resp[2]["result"]["isError"] is False
    assert json.loads(resp[3]["result"]["content"][0]["text"])["complete"] is True
    pending = json.loads(resp[4]["result"]["content"][0]["text"])
    assert any("window approve" in p["command"] for p in pending)
    assert resp[5]["result"]["isError"] is True and "scope" in resp[5]["result"]["content"][0]["text"]


def test_mcp_server_runs_as_subprocess(design):
    root = Path(__file__).resolve().parents[1]
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "gov_status", "arguments": {"root": str(design.root)}}}]
    r = subprocess.run([str(root / "bin" / "edagov-mcp")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, env={"EDAGOV_ACTOR": "designer@x", "PATH": "/usr/bin:/bin"}, timeout=60)
    lines = [json.loads(l) for l in r.stdout.splitlines()]
    assert lines[0]["result"]["protocolVersion"] == "2026-07-28"
    status = json.loads(lines[1]["result"]["content"][0]["text"])
    assert status["governance"]["identity"]["design_id"] == "DES-T"
