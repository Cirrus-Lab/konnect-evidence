"""KiCad CLI integration: ERC/DRC and fabrication/assembly exports.

Two modes:
  * executed  — requires explicit authorization; runs kicad-cli and captures provenance.
  * ingested  — documentation-only; reads an existing JSON/RPT report and records
                that the toolkit did NOT execute the check.

The toolkit never passes `--save-board` and never writes CAD sources.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import executor, reports
from .gitinfo import source_revision
from .util import file_hash, new_id, now_iso, write_json

CLI_CANDIDATES = [
    "kicad-cli",
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
]

# kind -> (subcommand words, input suffix, output is directory?)
EXPORTS = {
    "gerbers": (["pcb", "export", "gerbers"], ".kicad_pcb", True),
    "drill": (["pcb", "export", "drill"], ".kicad_pcb", True),
    "pos": (["pcb", "export", "pos"], ".kicad_pcb", False),
    "ipc2581": (["pcb", "export", "ipc2581"], ".kicad_pcb", False),
    "odb": (["pcb", "export", "odb"], ".kicad_pcb", False),
    "step": (["pcb", "export", "step"], ".kicad_pcb", False),
    "bom": (["sch", "export", "bom"], ".kicad_sch", False),
    "netlist": (["sch", "export", "netlist"], ".kicad_sch", False),
    "spice_netlist": (["sch", "export", "netlist"], ".kicad_sch", False),
}
# Exports that accept --variant in the KiCad 10 docs.
VARIANT_EXPORTS = {"gerbers", "ipc2581", "odb", "step"}
DEFAULT_EXPORT_FLAGS = {
    "drill": ["--generate-map", "--map-format", "gerberx2"],
    "pos": ["--format", "csv", "--units", "mm", "--side", "both"],
    "bom": [],
    "spice_netlist": ["--format", "spice"],
}
OUT_NAME = {"pos": "positions.csv", "ipc2581": "ipc2581.xml", "odb": "odb.zip", "step": "board.step",
            "bom": "bom.csv", "netlist": "netlist.net", "spice_netlist": "netlist.cir"}


def locate_cli() -> str | None:
    return executor.which([os.environ.get("KICAD_CLI", ""), *CLI_CANDIDATES])


def tool_version(cli: str, run_dir: Path) -> str | None:
    rec = executor.run([cli, "version"], cwd=run_dir, run_dir=run_dir / "version")
    try:
        txt = Path(rec["logs"]["stdout"]).read_text().strip()
    except OSError:
        return None
    return txt.splitlines()[0] if txt else None


def _project_files(project_dir: Path):
    pros = sorted(project_dir.glob("*.kicad_pro"))
    if not pros:
        raise FileNotFoundError(f"no .kicad_pro in {project_dir}")
    stem = pros[0].stem
    return pros[0], project_dir / f"{stem}.kicad_sch", project_dir / f"{stem}.kicad_pcb"


def _check_inputs(project_dir: Path) -> list[Path]:
    """Inputs that determine an ERC/DRC result: project, all sheets, board, rules, lib tables."""
    keep = []
    for pat in ("*.kicad_pro", "*.kicad_sch", "*.kicad_pcb", "*.kicad_dru", "sym-lib-table", "fp-lib-table"):
        keep += sorted(project_dir.glob(pat))
    return keep


def _claim_scope(kind, parsed, version, inputs, severities):
    c = parsed.get("counts", {})
    sev = ",".join(parsed.get("included_severities") or severities or ["default"])
    base = (f"{kind.upper()} completed by KiCad {version or 'unknown version'} on {len(inputs)} recorded input file(s) "
            f"with severities [{sev}]: {c.get('active', 0)} active violation(s) "
            f"({c.get('error', 0)} error, {c.get('warning', 0)} warning), {c.get('excluded', 0)} excluded.")
    return base + " " + reports.CLAIM_LIMITS[kind]


def _run_record(store, *, kind, version, inputs, parsed, result_class, notes, executed, settings, exec_rec,
                report_copy, provenance_path, authorization, run_id):
    ident = store.identity
    active = parsed.get("counts", {}).get("active", 0)
    state = {"clean": "ready_for_review", "violations": "blocked"}.get(result_class, "blocked")
    severity = {"clean": "info", "violations": "blocking"}.get(result_class, "blocking")
    next_action = {
        "clean": f"Design reviewer reviews {kind.upper()} configuration, exclusions and limitations.",
        "violations": f"Fix or disposition {active} active {kind.upper()} violation(s); record exceptions with rationale.",
        "conflict": "Exit code and report disagree: inspect the report and logs, then re-run.",
        "tool_error": "Inspect stderr log, confirm kicad-cli version and inputs, re-run.",
        "invalid": "Report failed schema validation: regenerate with --format json.",
    }.get(result_class, "Investigate.")
    return {
        "type": "run",
        "id": run_id,
        "check": kind,
        "tool": "kicad-cli",
        "tool_version": version or "unknown",
        "inputs": [{"path": str(p), "hash": file_hash(p)} for p in inputs if Path(p).exists()],
        "source_revision": source_revision(store.root),
        "settings": settings,
        "result_class": result_class,
        "counts": parsed.get("counts", {}),
        "by_type": parsed.get("by_type", {}),
        "excluded": parsed.get("excluded", []),
        "ignored_checks": parsed.get("ignored_checks", []),
        "limitations": parsed.get("limitations", []) + notes,
        "claim_scope": _claim_scope(kind, parsed, version, inputs, settings.get("severities")),
        "executed": executed,
        "ingested_report": not executed,
        "report": {"path": str(report_copy), "hash": file_hash(report_copy)} if report_copy and Path(report_copy).exists() else None,
        "execution": exec_rec,
        "provenance": str(provenance_path) if provenance_path else None,
        "authorization": authorization,
        "reviewer": None,
        # status envelope (Dashboard Spec §2.2)
        "state": state,
        "severity": severity,
        "timestamp": parsed.get("report_date") or now_iso(),
        "source": "kicad-cli (executed)" if executed else "ingested report (not executed by edagov)",
        "owner": ident.get("design_authority"),
        "linked_evidence": [str(report_copy)] if report_copy else [],
        "next_action": next_action,
        "evidence_kind": kind,
    }


def run_check(store, kind: str, project_dir, *, authorize: str | None, severities=("error", "warning"),
              parity: bool = True, refill_zones: bool = False, units: str = "mm", timeout: int = 900) -> dict:
    assert kind in ("erc", "drc")
    actor, verified, _ = store.check("run_tool")
    reason = executor.require_authorization(authorize, f"kicad-cli {kind}")
    cli = locate_cli()
    if not cli:
        raise executor.ToolMissing("kicad-cli not found (set KICAD_CLI or install KiCad 10). "
                                   "Use `edagov ingest` to record an existing report instead.")
    project_dir = Path(project_dir).resolve()
    pro, sch, pcb = _project_files(project_dir)
    target = sch if kind == "erc" else pcb
    run_id = new_id("run")
    rdir = store.run_dir(run_id)
    version = tool_version(cli, rdir)
    report = rdir / f"{kind}.json"
    cmd = [cli, "sch" if kind == "erc" else "pcb", kind, "--format", "json", "--units", units,
           "--output", str(report), "--exit-code-violations"]
    sev_flag = {"error": "--severity-error", "warning": "--severity-warning", "exclusions": "--severity-exclusions",
                "all": "--severity-all"}
    cmd += [sev_flag[s] for s in severities]
    if kind == "drc":
        if parity:
            cmd.append("--schematic-parity")
        if refill_zones:
            cmd.append("--refill-zones")  # in-memory refill only; --save-board is never used
    cmd.append(str(target))
    inputs = _check_inputs(project_dir)
    exec_rec = executor.run(cmd, cwd=project_dir, run_dir=rdir, timeout=timeout, inputs=inputs)
    parsed = reports.parse_json_report(report, kind) if report.exists() else {
        "schema_valid": False, "problems": ["no report produced"], "parse_confidence": "schema", "counts": {}}
    result_class, notes = reports.classify(parsed, exec_rec["exit_code"], True, executed=exec_rec["status"] == "completed")
    if not report.exists():
        result_class = "tool_error"
    prov = executor.provenance(run_id, "kicad-cli", version, exec_rec, [report], f"edagov@{actor}", rdir)
    settings = {"severities": list(severities), "units": units, "schematic_parity": parity if kind == "drc" else None,
                "zone_refill": "refilled in memory (not saved)" if refill_zones else "as saved in board file",
                "exit_code_flag": True, "rules_file": next((p.name for p in inputs if p.suffix == ".kicad_dru"), None)}
    rec = _run_record(store, kind=kind, version=version, inputs=inputs, parsed=parsed, result_class=result_class,
                      notes=notes, executed=True, settings=settings, exec_rec=exec_rec, report_copy=report,
                      provenance_path=prov, authorization={"reason": reason, "actor": actor, "actor_verified": verified},
                      run_id=run_id)
    write_json(rdir / "parsed.json", parsed)
    return store.put(rec, action="run_tool", reason=f"{kind} executed: {reason}")


def ingest_report(store, kind: str, report_path, project_dir=None, *, tool_version_hint: str | None = None) -> dict:
    """Documentation-only: record an existing report without executing anything."""
    assert kind in ("erc", "drc")
    store.check("record_evidence")
    report_path = Path(report_path).resolve()
    run_id = new_id("run")
    rdir = store.run_dir(run_id)
    copy = rdir / report_path.name
    shutil.copy2(report_path, copy)
    parsed = (reports.parse_json_report(copy, kind) if copy.suffix.lower() == ".json"
              else reports.parse_text_report(copy, kind))
    result_class, notes = reports.classify(parsed, None, False, executed=False)
    inputs = _check_inputs(Path(project_dir).resolve()) if project_dir else []
    if not inputs:
        notes.append("input files not supplied: the report cannot be bound to input hashes")
    settings = {"severities": parsed.get("included_severities"), "units": parsed.get("coordinate_units"),
                "zone_refill": "unknown (ingested)", "exit_code_flag": None}
    rec = _run_record(store, kind=kind, version=parsed.get("kicad_version") or tool_version_hint, inputs=inputs,
                      parsed=parsed, result_class=result_class, notes=notes, executed=False, settings=settings,
                      exec_rec=None, report_copy=copy, provenance_path=None,
                      authorization={"reason": "documentation-only ingestion", "actor": store.actor()[0]}, run_id=run_id)
    write_json(rdir / "parsed.json", parsed)
    return store.put(rec, reason=f"ingested {kind} report {report_path.name}")


def run_export(store, kind: str, project_dir, out_dir, *, authorize: str | None, variant: str | None = None,
               extra: list[str] | None = None, timeout: int = 900) -> dict:
    if kind not in EXPORTS:
        raise ValueError(f"unknown export {kind!r}; choose from {sorted(EXPORTS)}")
    actor, verified, _ = store.check("run_tool")
    reason = executor.require_authorization(authorize, f"kicad-cli export {kind}")
    cli = locate_cli()
    if not cli:
        raise executor.ToolMissing("kicad-cli not found (set KICAD_CLI or install KiCad 10).")
    project_dir = Path(project_dir).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pro, sch, pcb = _project_files(project_dir)
    words, suffix, is_dir = EXPORTS[kind]
    target = sch if suffix == ".kicad_sch" else pcb
    out = out_dir if is_dir else out_dir / OUT_NAME[kind]
    cmd = [cli, *words, "--output", str(out) + (os.sep if is_dir else "")]
    cmd += DEFAULT_EXPORT_FLAGS.get(kind, [])
    if variant and kind in VARIANT_EXPORTS:
        cmd += ["--variant", variant]
    cmd += extra or []
    cmd.append(str(target))
    run_id = new_id("run")
    rdir = store.run_dir(run_id)
    version = tool_version(cli, rdir)
    t_start = time.time() - 1
    exec_rec = executor.run(cmd, cwd=project_dir, run_dir=rdir, timeout=timeout, inputs=_check_inputs(project_dir))
    # Only files written by this run count as its outputs.
    produced = sorted(p for p in out_dir.rglob("*") if p.is_file() and p.stat().st_mtime >= t_start)
    ok = exec_rec["status"] == "completed" and exec_rec["exit_code"] == 0 and bool(produced)
    prov = executor.provenance(run_id, "kicad-cli", version, exec_rec, produced, f"edagov@{actor}", rdir)
    ident = store.identity
    rec = {
        "type": "run", "id": run_id, "check": f"export:{kind}", "tool": "kicad-cli", "tool_version": version or "unknown",
        "inputs": exec_rec["inputs"], "source_revision": source_revision(store.root),
        "settings": {"variant": variant or "default", "flags": cmd[len(words) + 1:-1]},
        "result_class": "clean" if ok else "tool_error",
        "claim_scope": (f"kicad-cli {version} generated {len(produced)} {kind} file(s) for variant "
                        f"{variant or 'default'}. Generation is not manufacturing review; plotted-view and DFM review "
                        "are still required."),
        "outputs": [{"path": str(p), "hash": file_hash(p)} for p in produced],
        "executed": True, "ingested_report": False, "execution": exec_rec, "provenance": str(prov),
        "authorization": {"reason": reason, "actor": actor, "actor_verified": verified},
        "state": "ready_for_review" if ok else "blocked", "severity": "info" if ok else "blocking",
        "timestamp": now_iso(), "source": "kicad-cli (executed)", "owner": ident.get("design_authority"),
        "linked_evidence": [str(out_dir)],
        "next_action": "Build the release manifest and review plotted views." if ok else "Inspect stderr log and re-run.",
        "evidence_kind": "manufacturing_output",
        "limitations": [] if variant is None or kind in VARIANT_EXPORTS else
        [f"--variant is not documented for '{kind}'; output reflects the default variant"],
    }
    return store.put(rec, action="run_tool", reason=f"export {kind}: {reason}")
