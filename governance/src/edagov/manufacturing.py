"""Manufacturing release manifest (Workflow Guide §8, Dashboard Spec §3.5).

Builds a revision-consistent, hashed manifest from a fabrication/assembly
output folder and reconciles it across files. Generating or listing files is
not manufacturing review: plotted-view review, DFM/DFA disposition and
separate sign-offs are tracked as explicit, initially `not_started`, states.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .util import file_hash, new_id, now_iso

GERBER_EXT = re.compile(r"\.(gbr|gtl|gbl|gts|gbs|gto|gbo|gtp|gbp|gm\d*|gko|g\d+|gp\d+|pho)$", re.I)
DRILL_EXT = re.compile(r"\.(drl|xln|exc|txt)$", re.I)
TF = re.compile(r"%TF\.(\w+),([^*]*)\*%")
SIGNOFF_ROLES = ("design_owner", "fabrication_dfm", "assembly_dfa", "release_control")


def _gerber_meta(p: Path) -> dict:
    head = p.read_text(encoding="ascii", errors="replace")[:8192]
    attrs = {k: v for k, v in TF.findall(head)}
    units = "mm" if "%MOMM*%" in head else "in" if "%MOIN*%" in head else None
    fs = re.search(r"%FS(L|T)A(X\d\d)(Y\d\d)\*%", head)
    proj = attrs.get("ProjectId", "")
    pparts = proj.split(",") if proj else []
    return {
        "x2": bool(attrs),
        "file_function": attrs.get("FileFunction"),
        "polarity": attrs.get("FilePolarity"),
        "generation_software": attrs.get("GenerationSoftware"),
        "creation_date": attrs.get("CreationDate"),
        "project_name": pparts[0] if pparts else None,
        "project_revision": pparts[2] if len(pparts) > 2 else None,
        "same_coordinates": attrs.get("SameCoordinates"),
        "units": units,
        "format": f"Gerber {'X2' if attrs else 'RS-274X (no X2 attributes)'}" + (f" {fs.group(2)}{fs.group(3)}" if fs else ""),
    }


def _drill_meta(p: Path) -> dict:
    head = p.read_text(encoding="ascii", errors="replace")[:4096]
    if "M48" not in head and "%TF" not in head:
        return {}
    units = "mm" if re.search(r"^METRIC", head, re.M) else "in" if re.search(r"^INCH", head, re.M) else None
    gen = re.search(r";\s*DRILL file\s*\{([^}]*)\}\s*date\s*([^\n]+)", head)
    ff = re.search(r"TF\.FileFunction,([^\n*]+)", head)
    return {"format": "Excellon", "units": units, "generation_software": gen.group(1) if gen else None,
            "creation_date": gen.group(2).strip() if gen else None, "file_function": ff.group(1) if ff else None}


def _pos_refs(p: Path) -> tuple[list[str], dict]:
    with open(p, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    refs = [r.get("Ref") or r.get("Reference") or r.get("Designator") for r in rows]
    sides = sorted({(r.get("Side") or "").lower() for r in rows})
    keys = list(rows[0].keys()) if rows else []
    units = "mm" if any("mm" in k.lower() for k in keys) else None
    return [r for r in refs if r], {"sides": sides, "columns": keys, "units_hint": units}


def _norm_sw(s: str) -> str:
    """'KiCad,Pcbnew,10.0.0' and 'KiCad 10.0.0' and 'Kicad,Pcbnew,10.0.0' -> 'kicad 10.0.0'."""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", s or "")
    vendor = re.split(r"[\s,{}]+", (s or "").strip())[0].lower() if s else ""
    return f"{vendor} {m.group(1)}" if m else (s or "").lower()


def classify(p: Path) -> tuple[str, dict]:
    name = p.name.lower()
    if name.endswith(".gbrjob"):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return "gerber_job", {"invalid": True}
        gs = job.get("GeneralSpecs", {})
        pid = gs.get("ProjectId", {})
        return "gerber_job", {"format": "Gerber Job", "generation_software": json.dumps(job.get("Header", {}).get("GenerationSoftware")),
                              "creation_date": job.get("Header", {}).get("CreationDate"),
                              "project_name": pid.get("Name"), "project_revision": pid.get("Revision"),
                              "layer_count": gs.get("LayerNumber"), "board_thickness": gs.get("BoardThickness"),
                              "files_listed": [f.get("Path") for f in job.get("FilesAttributes", [])],
                              "material_stackup": bool(job.get("MaterialStackup"))}
    if GERBER_EXT.search(name):
        meta = _gerber_meta(p)
        ff = (meta.get("file_function") or "").lower()
        if ff.startswith("drillmap") or "drl_map" in name:
            return "drill_map", meta
        if ff.startswith("paste"):
            return "paste", meta
        if ff.startswith(("plated", "nonplated")):
            return "drill", meta
        return "gerber", meta
    if DRILL_EXT.search(name):
        meta = _drill_meta(p)
        if meta:
            return "drill", meta
    if name.endswith((".pos",)) or (name.endswith(".csv") and ("pos" in name or "position" in name or "centroid" in name or "cpl" in name)):
        refs, meta = _pos_refs(p)
        return "position", {"format": "Placement CSV", "references": refs, **meta}
    if name.endswith(".csv") and "bom" in name:
        return "bom", {"format": "BOM CSV"}
    if name.endswith(".xml") and "ipc-2581" in p.read_text(encoding="utf-8", errors="replace")[:4096].lower():
        return "ipc2581", {"format": "IPC-2581"}
    if ("odb" in name) and name.endswith((".tgz", ".zip", ".tar.gz")):
        return "odb", {"format": "ODB++ archive"}
    if name.endswith(".pdf"):
        return "drawing", {"format": "PDF"}
    if name.endswith((".step", ".stp")):
        return "model_3d", {"format": "STEP"}
    return "other", {}


def build(store, out_dir, *, variant: str | None = None, origin: str = "unknown — record drill/placement origin",
          supplier_assumptions: list[str] | None = None) -> dict:
    store.check("record_evidence")
    ident, policy = store.identity, store.policy
    out_dir = Path(out_dir).resolve()
    variant = variant or ident["variant"]
    files, findings = [], []

    def add(sev, code, msg, action):
        findings.append({"severity": sev, "code": code, "message": msg, "next_action": action})

    for p in sorted(x for x in out_dir.rglob("*") if x.is_file()):
        kind, meta = classify(p)
        files.append({"filename": str(p.relative_to(out_dir)), "kind": kind, "hash": file_hash(p), "bytes": p.stat().st_size,
                      "format": meta.get("format"), "file_function": meta.get("file_function"),
                      "units": meta.get("units") or meta.get("units_hint"), "generated": meta.get("creation_date"),
                      "generation_software": meta.get("generation_software"),
                      "project_revision": meta.get("project_revision"), "variant": variant,
                      "origin": origin if kind in ("gerber", "drill", "position") else None,
                      "meta": {k: v for k, v in meta.items() if k not in ("references",)},
                      "references": meta.get("references")})
    if not files:
        add("blocking", "empty", f"no files in {out_dir}", "Generate outputs (authorized export) or point at the release folder.")

    kinds = {f["kind"] for f in files}
    mcfg = policy.get("manufacturing", {})
    for k in mcfg.get("required_kinds", []):
        if k not in kinds:
            add("blocking", f"missing_{k}", f"required output kind '{k}' not present", f"Add the {k} output to the package.")
    functions = {(f.get("file_function") or "").replace(" ", "") for f in files if f["kind"] in ("gerber", "paste", "drill")}
    for fn in mcfg.get("required_functions", []):
        if not any(x.lower().startswith(fn.replace(" ", "").lower()) for x in functions):
            add("blocking", "missing_function", f"no Gerber with FileFunction '{fn}'",
                "Export the layer, or update the required-function policy for this layer count with rationale.")
    gerbers = [f for f in files if f["kind"] == "gerber"]
    if gerbers and not all(f["meta"].get("x2") for f in gerbers):
        add("attention", "no_x2", "some Gerbers lack X2 attributes; file functions cannot be verified from content",
            "Prefer X2 Gerbers plus a Gerber job file; record the recipient's accepted format.")
    revs = {f["project_revision"] for f in files if f.get("project_revision")}
    if len(revs) > 1:
        add("blocking", "revision_conflict", f"files declare different project revisions: {sorted(revs)}",
            "Regenerate all outputs from one design revision.")
    if revs and ident["revision"] not in revs:
        add("blocking", "revision_mismatch", f"outputs declare revision {sorted(revs)} but design record is {ident['revision']}",
            "Confirm the design identity and regenerate, or correct the KiCad title-block revision.")
    if not revs:
        add("attention", "revision_unverifiable", "no output declares a project revision (X2 ProjectId / job file)",
            "Set the KiCad title-block revision so outputs carry it.")
    units = {f["units"] for f in files if f["kind"] in ("gerber", "drill") and f["units"]}
    if len(units) > 1:
        add("warning", "mixed_units", f"mixed units across Gerber/drill: {sorted(units)}", "Confirm with the fabricator or regenerate in one unit.")
    sw = {_norm_sw(f["generation_software"]) for f in files if f["generation_software"] and f["kind"] in ("gerber", "drill")}
    if len(sw) > 1:
        add("warning", "mixed_generators", f"outputs from different generator versions: {sorted(sw)}", "Regenerate with one controlled KiCad version.")
    same = {f["meta"].get("same_coordinates") for f in gerbers if f["meta"].get("x2")}
    if len(same) > 1:
        add("warning", "coordinate_mismatch", f"SameCoordinates attributes differ: {sorted(map(str, same))}", "Regenerate from one plot origin.")
    for job in [f for f in files if f["kind"] == "gerber_job"]:
        listed = set(job["meta"].get("files_listed") or [])
        present = {Path(f["filename"]).name for f in files}
        missing = sorted(Path(x).name for x in listed if Path(x).name not in present)
        if missing:
            add("blocking", "job_lists_missing_files", f"job file lists files not in package: {missing}", "Add the missing files or regenerate.")
    # Cross-file reference reconciliation with BOM records and placement.
    pos_refs = set()
    for f in files:
        if f["kind"] == "position" and f.get("references"):
            pos_refs |= set(f["references"])
    bom_refs = set()
    for line in store.list("bom_line", revision=ident["revision"]):
        if not line.get("dnp") and not line.get("superseded"):
            bom_refs |= set(line.get("references", []))
    if pos_refs and bom_refs:
        only_pos, only_bom = sorted(pos_refs - bom_refs), sorted(bom_refs - pos_refs)
        if only_pos or only_bom:
            add("blocking", "reference_mismatch",
                f"placement vs BOM mismatch: only in placement {only_pos[:15]}, only in BOM {only_bom[:15]}",
                "Reconcile variants/DNP and regenerate placement and BOM from the same revision.")
    elif "position" in kinds and not bom_refs:
        add("attention", "bom_not_ingested", "no BOM records for this revision; placement cannot be reconciled",
            "Run `edagov ingest bom` for this revision.")
    blocking = any(x["severity"] == "blocking" for x in findings)
    conflict = any(x["code"] in ("revision_conflict", "revision_mismatch", "reference_mismatch") for x in findings)
    completeness = "conflict" if conflict else ("incomplete" if blocking else "complete")
    rec = {
        "type": "manufacturing_package",
        "id": new_id("manufacturing_package", f"{ident['board_id']}-{ident['revision']}-{variant}"),
        "board_id": ident["board_id"], "assembly_id": ident.get("assembly_id"), "revision": ident["revision"],
        "variant": variant, "output_dir": str(out_dir), "files": files, "completeness": completeness,
        "consistency_findings": findings, "units": sorted(units), "origin": origin,
        "supplier_assumptions": supplier_assumptions or [],
        "dfm_findings": [], "plotted_view_review": "not_started",
        "signoffs": {r: {"state": "not_started"} for r in SIGNOFF_ROLES},
        "limitations": [
            "Gerber plus drill carries image and hole data, not complete stackup, material or design intent.",
            "This manifest does not prove manufacturability, solderability or assembly quality; supplier feedback and inspection are required.",
        ],
        "state": "blocked" if blocking else "ready_for_review", "severity": "blocking" if blocking else "info",
        "timestamp": now_iso(), "source": f"manifest of {out_dir.name}", "owner": ident.get("design_authority"),
        "linked_evidence": [f["filename"] for f in files],
        "next_action": findings[0]["next_action"] if blocking else "Plotted-view review, DFM/DFA disposition, and four separate sign-offs.",
    }
    # Preserve dispositions/sign-offs made on an earlier version of this same package.
    prev = store.get("manufacturing_package", rec["id"])
    if prev and [f["hash"] for f in prev.get("files", [])] == [f["hash"] for f in files]:
        for k in ("dfm_findings", "plotted_view_review", "signoffs", "supplier_assumptions"):
            rec[k] = prev.get(k, rec[k]) or rec[k]
    elif prev:
        rec["previous_manifest_invalidated"] = "file hashes changed; prior DFM dispositions and sign-offs do not carry over"
    return store.put(rec, reason=f"manifest of {out_dir}")


def verify(pkg: dict) -> tuple[bool, list[str]]:
    """Re-hash every file in the manifest against the folder on disk."""
    problems = []
    base = Path(pkg["output_dir"])
    for f in pkg.get("files", []):
        p = base / f["filename"]
        if not p.exists():
            problems.append(f"missing: {f['filename']}")
        elif file_hash(p) != f["hash"]:
            problems.append(f"hash changed: {f['filename']}")
    return (not problems), problems


def add_dfm_finding(store, pkg_id: str, *, rule: str, description: str, disposition: str, rationale: str,
                    approver: str | None = None, tool: str | None = None) -> dict:
    if disposition not in ("open", "corrected", "accepted", "waived"):
        raise ValueError("disposition must be open/corrected/accepted/waived")
    if disposition in ("accepted", "waived") and not (rationale and approver):
        raise ValueError("accepted/waived DFM findings need rationale and approver")
    store.check("record_evidence")
    pkg = dict(store.get("manufacturing_package", pkg_id))
    pkg["dfm_findings"] = pkg.get("dfm_findings", []) + [{
        "id": f"DFM-{len(pkg.get('dfm_findings', [])) + 1:03d}", "rule": rule, "description": description,
        "disposition": disposition, "rationale": rationale, "approver": approver, "tool": tool, "recorded_at": now_iso()}]
    return store.put(pkg, reason=f"DFM finding {rule}: {disposition}")


def signoff(store, pkg_id: str, role: str, decision: str, note: str = "") -> dict:
    if role not in SIGNOFF_ROLES:
        raise ValueError(f"role must be one of {SIGNOFF_ROLES}")
    action = {"design_owner": "review:design", "fabrication_dfm": "review:manufacturing",
              "assembly_dfa": "review:manufacturing", "release_control": "approve_release"}[role]
    actor, verified, roles = store.check(action)
    pkg = dict(store.get("manufacturing_package", pkg_id))
    ok, problems = verify(pkg)
    if decision == "approved" and not ok:
        raise ValueError(f"cannot sign off: manifest no longer matches files ({problems[:3]})")
    pkg["signoffs"] = dict(pkg.get("signoffs", {}))
    pkg["signoffs"][role] = {"state": decision, "actor": actor, "actor_verified": verified, "roles": roles,
                             "at": now_iso(), "note": note, "manifest_hash_set": [f["hash"] for f in pkg["files"]]}
    return store.put(pkg, action=action, reason=f"{role} sign-off: {decision}")
