"""KiCad CLI and ngspice runners: authorization, exit-code cross-check, provenance, run classes."""
import json
from pathlib import Path

import pytest

from edagov import executor, kicad, reports, spice


def test_execution_requires_authorization(design):
    with pytest.raises(executor.NotAuthorized):
        kicad.run_check(design, "erc", design.root / "kicad", authorize=None)


def test_erc_clean_with_provenance(design, monkeypatch):
    monkeypatch.setenv("FAKE_VIOLATIONS", "0")
    rec = kicad.run_check(design, "erc", design.root / "kicad", authorize="unit test")
    assert rec["result_class"] == "clean" and rec["executed"] is True
    assert rec["tool_version"] == "10.0.0"
    assert any(i["path"].endswith("power.kicad_sch") for i in rec["inputs"]), "all sheets are bound inputs"
    prov = json.loads(Path(rec["provenance"]).read_text())
    assert prov["predicateType"] == "https://slsa.dev/provenance/v1"
    assert "--save-board" not in rec["execution"]["command"]
    assert "does not show that the circuit functions" in rec["claim_scope"]


def test_drc_violations_exit5(design, monkeypatch):
    monkeypatch.setenv("FAKE_VIOLATIONS", "2")
    rec = kicad.run_check(design, "drc", design.root / "kicad", authorize="unit test")
    assert rec["result_class"] == "violations" and rec["state"] == "blocked"
    assert rec["settings"]["schematic_parity"] is True
    assert "--schematic-parity" in rec["execution"]["command"]


def test_exit_code_and_report_disagree_is_conflict(design, monkeypatch):
    monkeypatch.setenv("FAKE_VIOLATIONS", "1")
    monkeypatch.setenv("FAKE_FORCE_EXIT", "0")
    rec = kicad.run_check(design, "drc", design.root / "kicad", authorize="unit test")
    assert rec["result_class"] == "conflict"


def test_undocumented_exit_code_is_tool_error(design, monkeypatch):
    monkeypatch.setenv("FAKE_VIOLATIONS", "1")
    monkeypatch.setenv("FAKE_EXIT", "2")
    rec = kicad.run_check(design, "erc", design.root / "kicad", authorize="unit test")
    assert rec["result_class"] == "tool_error"


def test_missing_tool(design, monkeypatch):
    monkeypatch.setenv("KICAD_CLI", "/nonexistent/kicad-cli")
    monkeypatch.setattr(kicad, "CLI_CANDIDATES", ["kicad-cli"])  # ignore a real KiCad install
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(executor.ToolMissing):
        kicad.run_check(design, "erc", design.root / "kicad", authorize="x")


def test_export_variant_and_outputs(design):
    rec = kicad.run_export(design, "gerbers", design.root / "kicad", design.root / "out", authorize="t", variant="lite")
    assert rec["result_class"] == "clean" and rec["outputs"]
    assert "--variant" in rec["execution"]["command"]
    rec = kicad.run_export(design, "pos", design.root / "kicad", design.root / "out", authorize="t", variant="lite")
    assert any("not documented" in l for l in rec["limitations"])


def test_ingested_reports_are_marked_not_executed(design):
    erc = kicad.ingest_report(design, "erc", design.root / "reports" / "erc.json", design.root / "kicad")
    assert erc["executed"] is False and erc["result_class"] == "clean"
    assert erc["counts"]["excluded"] == 1
    assert any("ignored" in l for l in erc["limitations"])
    drc = kicad.ingest_report(design, "drc", design.root / "reports" / "drc.json", design.root / "kicad")
    assert drc["result_class"] == "violations" and drc["by_type"] == {"silk_over_copper": 1}


def test_invalid_report(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"source": "x"}')
    parsed = reports.parse_json_report(p, "drc")
    assert reports.classify(parsed, 0, True, True)[0] == "invalid"


def test_spice_manifest_detects_pin_mismatch_and_missing_include(tmp_path):
    (tmp_path / "m.lib").write_text(".subckt AMP a b out\nR1 a out 1k\n.ends\n")
    n = tmp_path / "t.cir"
    n.write_text("title\n.include m.lib\n.include missing.lib\nV1 in 0 1\nX1 in out AMP\n.op\n.end\n")
    m = spice.manifest(n)
    msgs = " ".join(f["message"] for f in m["findings"])
    assert "uses 2 pins but .subckt amp declares 3" in msgs
    assert "missing.lib" in msgs and not m["complete"]


def test_spice_run_classes_and_retry_chain(design):
    sim = design.root / "sim"
    (sim / "fail.cir").write_text("FAIL deck\nV1 a 0 1\nR1 a 0 1k\n.tran 1n 1u\n.end\n")
    (sim / "ok.cir").write_text("ok deck\nV1 a 0 1\nR1 a 0 1k\n.options reltol=0.01\n.tran 1n 1u\n.end\n")
    r1 = spice.run_ngspice(design, sim / "fail.cir", authorize="t")
    assert r1["result_class"] == "failed" and r1["state"] == "blocked"
    r2 = spice.run_ngspice(design, sim / "ok.cir", authorize="t", retry_of=r1["id"])
    assert r2["result_class"] == "altered_settings"
    assert "reltol" in r2["changed_settings_vs_retry_of"]
    assert design.get("run", r1["id"])["result_class"] == "failed", "failed run is preserved"
    assert "not hardware validation" in r2["claim_scope"]


def test_spice_ingest_demo_logs(design):
    sim = design.root / "sim"
    r = spice.ingest_log(design, sim / "buck_tran_v1.cir", sim / "buck_tran_v1.log", exit_code=1)
    assert r["result_class"] == "failed" and r["executed"] is False
    r = spice.ingest_log(design, sim / "buck_loop_ac.cir", sim / "buck_loop_ac.log", exit_code=0)
    assert r["result_class"] == "clean"
