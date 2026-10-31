"""SPICE netlist manifest, ngspice execution, and run classification (Workflow Guide §4).

Convergence is a numerical stopping criterion for the selected equations and
settings; it is never reported as physical validation. Failed runs are kept;
a retry links back to the failure and lists exactly which settings changed.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from . import executor
from .gitinfo import source_revision
from .util import file_hash, new_id, now_iso, write_json

NGSPICE_CANDIDATES = ["ngspice", "/opt/homebrew/bin/ngspice", "/usr/local/bin/ngspice"]

# ngspice defaults (ngspice manual, .options): loosening any of these marks a run "altered_settings".
NGSPICE_DEFAULTS = {"reltol": 1e-3, "abstol": 1e-12, "vntol": 1e-6, "chgtol": 1e-14, "gmin": 1e-12,
                    "trtol": 7.0, "itl1": 100, "itl2": 50, "itl4": 10}
LOOSER_IF_GREATER = {"reltol", "abstol", "vntol", "chgtol", "gmin", "trtol", "itl1", "itl2", "itl4"}

ANALYSES = (".op", ".ac", ".dc", ".tran", ".noise", ".tf", ".sens", ".disto", ".pz", ".sp")
FAIL_PATTERNS = [
    r"timestep too small", r"singular matrix", r"no convergence", r"gmin stepping failed",
    r"source stepping failed", r"simulation\(s\) aborted", r"doanalyses:.*(failed|aborted)", r"fatal error",
    r"^\s*error\b", r"error on line", r"unknown subckt", r"could not find", r"unable to find definition",
]
WARN_PATTERNS = [r"^\s*warning\b", r"warning:"]
SCALE = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "mil": 25.4e-6, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}

CLAIM_LIMIT = ("Convergence means the numerical stopping criteria were met for these equations and settings. "
               "It does not show the topology, models, operating region or physical assumptions are correct, and "
               "it is not hardware validation.")


def spice_number(tok: str) -> float | None:
    m = re.match(r"^([-+]?\d*\.?\d+(?:e[-+]?\d+)?)(meg|mil|[tgkmunpf])?", tok.strip().lower())
    if not m:
        return None
    return float(m.group(1)) * SCALE.get(m.group(2) or "", 1.0)


def _logical_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        else:
            lines.append(raw.rstrip())
    return lines


def _subckts(text: str) -> dict[str, int]:
    out = {}
    for ln in _logical_lines(text):
        toks = ln.split()
        if toks and toks[0].lower() == ".subckt" and len(toks) >= 2:
            pins = [t for t in toks[2:] if "=" not in t and t.lower() not in ("params:",)]
            out[toks[1].lower()] = len(pins)
    return out


def locate_ngspice() -> str | None:
    return executor.which([os.environ.get("NGSPICE", ""), *NGSPICE_CANDIDATES])


def manifest(netlist_path: str | Path) -> dict:
    p = Path(netlist_path).resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = _logical_lines(text)
    findings, includes, analyses, options, instances = [], [], [], {}, []
    params, temps, ics, saves = [], [], [], []
    has_end = any(l.strip().lower() == ".end" for l in lines)
    ground = False
    dialect = set()
    encrypted = bool(re.search(r"\.protect|<binary>|encrypted", text, re.I))
    subckt_defs = _subckts(text)
    for ln in lines[1:]:
        s = ln.strip()
        if not s or s.startswith("*"):
            continue
        toks = s.split()
        t0 = toks[0].lower()
        if t0 in (".include", ".inc", ".lib"):
            if len(toks) < 2:
                findings.append({"severity": "blocking", "message": f"malformed {t0} line: {s}"})
                continue
            rel = toks[1].strip("\"'")
            target = (p.parent / rel) if not Path(rel).is_absolute() else Path(rel)
            entry = {"directive": t0, "path": rel, "section": toks[2] if t0 == ".lib" and len(toks) > 2 else None,
                     "exists": target.exists(), "hash": file_hash(target) if target.exists() else None}
            includes.append(entry)
            if target.exists():
                inc_text = target.read_text(encoding="utf-8", errors="replace")
                subckt_defs.update(_subckts(inc_text))
                if re.search(r"\.protect|encrypted", inc_text, re.I):
                    encrypted = True
            else:
                findings.append({"severity": "blocking", "message": f"included file not found: {rel}"})
        elif t0 in ANALYSES:
            analyses.append({"type": t0[1:], "args": toks[1:]})
        elif t0 in (".options", ".option", ".opt"):
            for kv in toks[1:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    num = spice_number(v)
                    options[k.lower()] = num if num is not None else v
                else:
                    options[kv.lower()] = True
        elif t0 == ".param":
            params.append(" ".join(toks[1:]))
        elif t0 == ".temp":
            temps += toks[1:]
        elif t0 in (".ic", ".nodeset"):
            ics.append(s)
        elif t0 in (".save", ".probe", ".meas", ".measure"):
            saves.append(s)
        elif t0 in (".backanno", ".step") or re.search(r"\bRser=|\bRpar=|\bCpar=", s):
            dialect.add("ltspice-style")
        elif t0[0] in "rclvidegfhbjkmqswxzot" and not t0.startswith("."):
            nodes = toks[1:3] if t0[0] in "rclvi" else toks[1:]
            if any(n in ("0", "gnd") for n in nodes):
                ground = True
            if t0[0] == "x":
                pins = [t for t in toks[1:] if "=" not in t and t.lower() != "params:"]
                name = pins[-1].lower() if pins else None
                npins = len(pins) - 1
                instances.append({"instance": toks[0], "subckt": name, "pins": npins})
                if name not in subckt_defs:
                    findings.append({"severity": "blocking", "message": f"{toks[0]}: subcircuit '{name}' has no definition in netlist or includes"})
                elif subckt_defs[name] != npins:
                    findings.append({"severity": "blocking", "message": f"{toks[0]}: uses {npins} pins but .subckt {name} declares {subckt_defs[name]} (check ordered pin map)"})
    if not has_end:
        findings.append({"severity": "warning", "message": "no .end line"})
    if not ground:
        findings.append({"severity": "blocking", "message": "no element connects to ground node 0"})
    if not analyses:
        findings.append({"severity": "warning", "message": "no analysis directive (.op/.ac/.dc/.tran/...)"})
    if encrypted:
        findings.append({"severity": "attention", "message": "encrypted/proprietary model content detected; record vendor, revision and simulator support"})
    if "gnd" in text.lower().split():
        dialect.add("uses 'gnd' alias")
    altered = [f"{k}={v}" for k, v in options.items()
               if k in LOOSER_IF_GREATER and isinstance(v, (int, float)) and v > NGSPICE_DEFAULTS[k]]
    return {
        "netlist": str(p), "hash": file_hash(p), "title": lines[0] if lines else "",
        "has_end": has_end, "ground_node_0": ground, "includes": includes, "analyses": analyses,
        "options": options, "loosened_options": altered, "params": params, "temperatures": temps,
        "initial_conditions": ics, "outputs": saves, "subckt_instances": instances,
        "subckt_definitions": subckt_defs, "encrypted_models": encrypted, "dialect_hints": sorted(dialect),
        "findings": findings, "complete": not any(f["severity"] == "blocking" for f in findings),
    }


def classify_log(log_text: str, exit_code: int | None, man: dict) -> tuple[str, list[str], list[str]]:
    low = log_text.lower()
    fails = [ln.strip() for ln in log_text.splitlines() if any(re.search(p, ln.lower()) for p in FAIL_PATTERNS)]
    warns = [ln.strip() for ln in log_text.splitlines() if any(re.search(p, ln.lower()) for p in WARN_PATTERNS)]
    if fails or (exit_code not in (0, None)) or "simulation interrupted" in low:
        return "failed", fails[:20], warns[:20]
    if man.get("loosened_options"):
        return "altered_settings", fails, warns[:20]
    if warns:
        return "converged_with_warnings", fails, warns[:20]
    return "clean", fails, warns


def _record(store, *, run_id, man, version, result_class, fails, warns, executed, exec_rec, log_copy, raw,
            authorization, retry_of, validation, justification, simulator):
    prior = store.get("run", retry_of) if retry_of else None
    changed = []
    if prior:
        old = prior.get("manifest", {}).get("options", {})
        new = man.get("options", {})
        changed = sorted({k for k in set(old) | set(new) if old.get(k) != new.get(k)})
    state = {"clean": "ready_for_review", "converged_with_warnings": "ready_for_review",
             "altered_settings": "ready_for_review", "failed": "blocked"}[result_class]
    lim = [CLAIM_LIMIT]
    if not validation:
        lim.append("no validation data or acceptance criteria recorded for this run")
    if result_class == "altered_settings" and not justification:
        lim.append(f"solver settings loosened ({', '.join(man['loosened_options'])}) without recorded justification")
    if man.get("encrypted_models"):
        lim.append("encrypted/proprietary models: results are simulator-specific")
    ident = store.identity
    return {
        "type": "run", "id": run_id, "check": "simulation", "tool": simulator, "tool_version": version or "unknown",
        "inputs": [{"path": man["netlist"], "hash": man["hash"]}] +
                  [{"path": i["path"], "hash": i["hash"]} for i in man["includes"] if i["hash"]],
        "source_revision": source_revision(store.root),
        "manifest": man, "result_class": result_class, "failure_lines": fails, "warning_lines": warns,
        "retry_of": retry_of, "changed_settings_vs_retry_of": changed, "settings_justification": justification,
        "validation": validation, "limitations": lim,
        "claim_scope": (f"{simulator} {version or ''} run classified '{result_class}' for analyses "
                        f"{[a['type'] for a in man['analyses']]} with options {man['options'] or 'defaults'}. "
                        + CLAIM_LIMIT),
        "executed": executed, "ingested_report": not executed, "execution": exec_rec,
        "log": {"path": str(log_copy), "hash": file_hash(log_copy)} if log_copy and Path(log_copy).exists() else None,
        "raw_output": {"path": str(raw), "hash": file_hash(raw)} if raw and Path(raw).exists() else None,
        "authorization": authorization, "reviewer": None,
        "state": state, "severity": "blocking" if result_class == "failed" else ("warning" if result_class != "clean" else "info"),
        "timestamp": now_iso(), "source": f"{simulator} (executed)" if executed else "ingested log (not executed by edagov)",
        "owner": ident.get("design_authority"), "linked_evidence": [man["netlist"]],
        "next_action": {"failed": "Keep this failed run; inspect topology/models/ICs before changing tolerances, then retry with --retry-of.",
                        "altered_settings": "Reviewer confirms the loosened settings keep the run qualified.",
                        "converged_with_warnings": "Reviewer dispositions each warning.",
                        "clean": "Attach validation data / acceptance criteria and request review."}[result_class],
        "evidence_kind": "simulation",
    }


def run_ngspice(store, netlist, *, authorize: str | None, retry_of=None, validation=None, justification=None,
                timeout: int = 900) -> dict:
    actor, verified, _ = store.check("run_tool")
    reason = executor.require_authorization(authorize, "ngspice")
    cli = locate_ngspice()
    if not cli:
        raise executor.ToolMissing("ngspice not found (set NGSPICE or install ngspice). Use `edagov ingest spice` for an existing log.")
    man = manifest(netlist)
    run_id = new_id("run")
    rdir = store.run_dir(run_id)
    vrec = executor.run([cli, "-v"], cwd=rdir, run_dir=rdir / "version")
    vtxt = Path(vrec["logs"]["stdout"]).read_text(errors="replace")
    vm = re.search(r"ngspice[- ]?(\d+[\w.]*)", vtxt, re.I)
    version = f"ngspice-{vm.group(1)}" if vm else (vtxt.strip().splitlines()[0] if vtxt.strip() else None)
    # Copy the netlist so the run is bound to an immutable input.
    frozen = rdir / Path(netlist).name
    shutil.copy2(netlist, frozen)
    log, raw = rdir / "ngspice.log", rdir / "output.raw"
    cmd = [cli, "-b", "-o", str(log), "-r", str(raw), str(Path(netlist).resolve())]
    exec_rec = executor.run(cmd, cwd=Path(netlist).resolve().parent, run_dir=rdir, timeout=timeout,
                            inputs=[Path(man["netlist"])])
    text = log.read_text(errors="replace") if log.exists() else ""
    text += "\n" + Path(exec_rec["logs"]["stderr"]).read_text(errors="replace")
    rc, fails, warns = classify_log(text, exec_rec["exit_code"], man)
    if exec_rec["status"] != "completed":
        rc, fails = "failed", fails + [f"process status: {exec_rec['status']}"]
    prov = executor.provenance(run_id, "ngspice", version, exec_rec, [p for p in (log, raw) if p.exists()],
                               f"edagov@{actor}", rdir)
    rec = _record(store, run_id=run_id, man=man, version=version, result_class=rc, fails=fails, warns=warns,
                  executed=True, exec_rec=exec_rec, log_copy=log, raw=raw,
                  authorization={"reason": reason, "actor": actor, "actor_verified": verified},
                  retry_of=retry_of, validation=validation, justification=justification, simulator="ngspice")
    rec["provenance"] = str(prov)
    write_json(rdir / "manifest.json", man)
    return store.put(rec, action="run_tool", reason=f"ngspice: {reason}")


def ingest_log(store, netlist, log_path, *, simulator="ngspice", version=None, exit_code=None, retry_of=None,
               validation=None, justification=None) -> dict:
    store.check("record_evidence")
    man = manifest(netlist)
    run_id = new_id("run")
    rdir = store.run_dir(run_id)
    copy = rdir / Path(log_path).name
    shutil.copy2(log_path, copy)
    rc, fails, warns = classify_log(copy.read_text(errors="replace"), exit_code, man)
    rec = _record(store, run_id=run_id, man=man, version=version, result_class=rc, fails=fails, warns=warns,
                  executed=False, exec_rec=None, log_copy=copy, raw=None,
                  authorization={"reason": "documentation-only ingestion", "actor": store.actor()[0]},
                  retry_of=retry_of, validation=validation, justification=justification, simulator=simulator)
    write_json(rdir / "manifest.json", man)
    return store.put(rec, reason=f"ingested {simulator} log {Path(log_path).name}")
