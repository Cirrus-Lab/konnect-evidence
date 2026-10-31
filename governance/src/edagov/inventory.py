"""KiCad project inventory (Workflow Guide §3.1, Skill Spec §3 step 2).

Reads the project folder without modifying it. Produces:
  * a file inventory with kinds and content hashes,
  * dependency findings (missing sheets, libraries outside the project,
    unassigned footprints, hidden power-input pins, Edge.Cuts closure, version skew),
  * the version context that every later run must be bound to.

The inventory never infers electrical meaning: it records structure and
provenance only (Dashboard Spec §1).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import sexpr
from .gitinfo import info as git_info
from .util import file_hash

KIND_BY_SUFFIX = {
    ".kicad_pro": "project",
    ".kicad_sch": "schematic",
    ".kicad_pcb": "pcb",
    ".kicad_sym": "symbol_library",
    ".kicad_mod": "footprint_library",
    ".kicad_dru": "rules",
    ".kicad_jobset": "jobset",
    ".kicad_wks": "worksheet",
    ".step": "model_3d", ".stp": "model_3d", ".wrl": "model_3d",
    ".lib": "spice_model", ".sub": "spice_model", ".mod": "spice_model", ".cir": "netlist",
    ".net": "netlist",
}
LOCAL_ONLY = {".kicad_prl", ".lck"}
LOCAL_ONLY_NAMES = {"fp-info-cache"}
SKIP_DIRS = {".git", ".edagov", "__pycache__", "node_modules"}
ENV_VAR = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def _finding(severity, code, message, next_action, path=None):
    return {"severity": severity, "code": code, "message": message, "next_action": next_action, "path": path}


def _read_sexpr(path: Path, findings: list):
    try:
        return sexpr.parse(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        findings.append(_finding("blocking", "parse_error", f"cannot parse {path.name}: {e}",
                                 "Restore the file from version control and re-run inventory.", str(path)))
        return None


def _file_version(tree) -> dict:
    return {
        "format_version": str(sexpr.value(tree, "version")) if sexpr.value(tree, "version") is not None else None,
        "generator": sexpr.value(tree, "generator"),
        "generator_version": sexpr.value(tree, "generator_version"),
    }


def _lib_table(path: Path, project_dir: Path) -> list[dict]:
    if not path.exists():
        return []
    tree = sexpr.parse(path.read_text(encoding="utf-8"))
    libs = []
    for lib in sexpr.children(tree, "lib"):
        uri = sexpr.value(lib, "uri", "")
        vars_used = ENV_VAR.findall(uri)
        resolved = uri.replace("${KIPRJMOD}", str(project_dir))
        project_local = "${KIPRJMOD}" in uri or not (vars_used or Path(uri).is_absolute())
        libs.append({
            "name": sexpr.value(lib, "name"),
            "type": sexpr.value(lib, "type"),
            "uri": uri,
            "env_vars": [v for v in vars_used if v != "KIPRJMOD"],
            "project_local": project_local,
            "exists": Path(resolved).exists() if project_local else None,
        })
    return libs


def _schematic_walk(root_sch: Path, findings: list) -> tuple[list[dict], dict]:
    """Follow the sheet hierarchy from the root schematic."""
    sheets, seen = [], set()
    facts = {"symbols": [], "hidden_power_pins": [], "lib_ids": set(), "versions": {}}

    def visit(path: Path, parent: str | None):
        key = str(path.resolve())
        if key in seen:
            sheets.append({"file": path.name, "parent": parent, "reused_instance": True})
            return
        seen.add(key)
        if not path.exists():
            findings.append(_finding("blocking", "missing_sheet", f"hierarchical sheet file missing: {path.name}",
                                     "Restore the sheet file; the schematic is not reproducible without it.", str(path)))
            sheets.append({"file": path.name, "parent": parent, "missing": True})
            return
        tree = _read_sexpr(path, findings)
        if tree is None:
            return
        facts["versions"][path.name] = _file_version(tree)
        sheets.append({"file": path.name, "parent": parent, "hash": file_hash(path)})
        # Hidden power-input pins in embedded library symbols (Workflow Guide §3.2).
        libsyms = sexpr.child(tree, "lib_symbols")
        for sym in sexpr.children(libsyms, "symbol") if libsyms else []:
            name = str(sym[1])
            for pin in sexpr.walk(sym, "pin"):
                if len(pin) > 1 and str(pin[1]) == "power_in" and sexpr.has_flag(pin, "hide"):
                    facts["hidden_power_pins"].append({"sheet": path.name, "symbol": name,
                                                       "pin": sexpr.value(pin, "number")})
        for sym in sexpr.children(tree, "symbol"):
            lib_id = sexpr.value(sym, "lib_id")
            props = sexpr.properties(sym)
            ref = props.get("Reference", "?")
            if lib_id:
                facts["lib_ids"].add(str(lib_id))
            facts["symbols"].append({
                "sheet": path.name, "reference": ref, "lib_id": lib_id, "value": props.get("Value"),
                "footprint": props.get("Footprint", ""), "mpn": props.get("MPN") or props.get("Manufacturer_Part_Number"),
                "dnp": sexpr.has_flag(sym, "dnp"), "power_symbol": ref.startswith("#"),
            })
        for sh in sexpr.children(tree, "sheet"):
            props = sexpr.properties(sh)
            fname = props.get("Sheetfile") or props.get("Sheet file")
            if fname:
                visit(path.parent / fname, path.name)

    visit(root_sch, None)
    facts["lib_ids"] = sorted(facts["lib_ids"])
    return sheets, facts


def _pt(node):
    return (float(node[1]), float(node[2])) if node and len(node) >= 3 else None


def _edge_cuts(board) -> dict:
    """Check Edge.Cuts outline closure using segment endpoints (Workflow Guide §6)."""
    ends, closed_shapes, unknown, count = [], 0, 0, 0
    for item in sexpr.walk(board):
        h = sexpr.head(item)
        if h not in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly", "gr_curve"):
            continue
        if sexpr.value(item, "layer") != "Edge.Cuts":
            continue
        count += 1
        if h in ("gr_rect", "gr_circle", "gr_poly"):
            closed_shapes += 1
        elif h in ("gr_line", "gr_arc"):
            a, b = _pt(sexpr.child(item, "start")), _pt(sexpr.child(item, "end"))
            if a and b:
                ends.extend([a, b])
            else:
                unknown += 1
        else:
            unknown += 1
    if count == 0:
        return {"state": "absent", "items": 0}
    tol = 1e-3
    dangling = 0
    for i, p in enumerate(ends):
        matches = sum(1 for j, q in enumerate(ends) if i != j and math.dist(p, q) <= tol)
        if matches != 1:
            dangling += 1
    if unknown:
        state = "unknown"
    elif dangling:
        state = "open"
    else:
        state = "closed"
    return {"state": state, "items": count, "closed_shapes": closed_shapes, "dangling_endpoints": dangling}


def _board_facts(path: Path, findings: list) -> dict:
    tree = _read_sexpr(path, findings)
    if tree is None:
        return {}
    setup = sexpr.child(tree, "setup")
    stackup = sexpr.child(setup, "stackup") if setup else None
    fps, models = [], []
    for fp in sexpr.children(tree, "footprint"):
        props = sexpr.properties(fp)
        fps.append({"lib_id": str(fp[1]) if len(fp) > 1 else None, "reference": props.get("Reference"),
                    "layer": sexpr.value(fp, "layer")})
        for m in sexpr.children(fp, "model"):
            models.append({"reference": props.get("Reference"), "model": str(m[1]) if len(m) > 1 else None})
    layers = sexpr.child(tree, "layers")
    copper = [str(l[1]) for l in (layers[1:] if layers else []) if isinstance(l, list) and len(l) > 1 and str(l[1]).endswith(".Cu")]
    return {
        "version": _file_version(tree),
        "thickness_mm": sexpr.value(sexpr.child(tree, "general"), "thickness") if sexpr.child(tree, "general") else None,
        "copper_layers": copper,
        "stackup_defined": stackup is not None,
        "stackup_layers": [str(l[1]) for l in sexpr.children(stackup, "layer")] if stackup else [],
        "footprints": fps,
        "models": models,
        "edge_cuts": _edge_cuts(tree),
        "zones": len(sexpr.children(tree, "zone")),
        "nets": len(sexpr.children(tree, "net")),
    }


def inventory(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    findings: list[dict] = []
    pros = sorted(project_dir.glob("*.kicad_pro"))
    if not pros:
        findings.append(_finding("blocking", "no_project", "no *.kicad_pro in folder",
                                 "Point inventory at the KiCad project folder; a board outside its project omits design information."))
        return {"project_dir": str(project_dir), "findings": findings, "files": [], "complete": False}
    if len(pros) > 1:
        findings.append(_finding("warning", "multiple_projects", f"{len(pros)} project files found; using {pros[0].name}",
                                 "Keep one project per folder or name the project explicitly."))
    pro = pros[0]
    stem = pro.stem
    try:
        pro_json = json.loads(pro.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        pro_json = {}
        findings.append(_finding("blocking", "parse_error", f"project file unreadable: {e}", "Restore the .kicad_pro file."))

    # ---- files
    files = []
    for p in sorted(project_dir.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(project_dir).parts):
            continue
        rel = str(p.relative_to(project_dir))
        local_only = p.suffix in LOCAL_ONLY or p.name in LOCAL_ONLY_NAMES or p.name.startswith("~") or p.name.endswith(".bak")
        kind = KIND_BY_SUFFIX.get(p.suffix.lower(), "other")
        if p.name in ("sym-lib-table", "fp-lib-table"):
            kind = "configuration"
        if p.suffix.lower() == ".kicad_mod" or p.parent.suffix == ".pretty":
            kind = "footprint_library"
        files.append({"path": rel, "kind": kind, "hash": file_hash(p), "bytes": p.stat().st_size,
                      "distribution": "local_only" if local_only else "controlled"})

    # ---- schematic hierarchy
    root_sch = project_dir / f"{stem}.kicad_sch"
    sheets, sch_facts = ([], {"symbols": [], "hidden_power_pins": [], "lib_ids": [], "versions": {}})
    if root_sch.exists():
        sheets, sch_facts = _schematic_walk(root_sch, findings)
    else:
        findings.append(_finding("blocking", "missing_root_schematic", f"{root_sch.name} not found",
                                 "Restore the root schematic."))

    # ---- board
    board_path = project_dir / f"{stem}.kicad_pcb"
    board = _board_facts(board_path, findings) if board_path.exists() else {}
    if not board_path.exists():
        findings.append(_finding("warning", "missing_board", f"{board_path.name} not found",
                                 "If layout has not started, mark PCB evidence not_started; otherwise restore the board."))

    # ---- libraries
    sym_libs = _lib_table(project_dir / "sym-lib-table", project_dir)
    fp_libs = _lib_table(project_dir / "fp-lib-table", project_dir)
    project_sym = {l["name"] for l in sym_libs}
    project_fp = {l["name"] for l in fp_libs}
    for l in sym_libs + fp_libs:
        if l["project_local"] and l["exists"] is False:
            findings.append(_finding("blocking", "missing_library", f"project library '{l['name']}' not found at {l['uri']}",
                                     "Restore the project-local library or fix the table entry.", l["uri"]))
        if l["env_vars"]:
            findings.append(_finding("attention", "external_library", f"library '{l['name']}' depends on {l['env_vars']}",
                                     "Record the library release/commit bound to this design revision."))
    global_sym = sorted({lid.split(":")[0] for lid in sch_facts["lib_ids"] if ":" in lid} - project_sym)
    if global_sym:
        findings.append(_finding("attention", "global_symbol_libraries",
                                 f"symbols resolve through the global table: {global_sym}",
                                 "Pin the KiCad library release/commit, or vendor these libraries into the project."))
    global_fp = sorted({f["lib_id"].split(":")[0] for f in board.get("footprints", []) if f.get("lib_id") and ":" in f["lib_id"]} - project_fp)
    if global_fp:
        findings.append(_finding("attention", "global_footprint_libraries",
                                 f"footprints resolve through the global table: {global_fp}",
                                 "Pin the KiCad library release/commit, or vendor these libraries into the project."))

    # ---- schematic findings
    unassigned = [s["reference"] for s in sch_facts["symbols"] if not s["power_symbol"] and not s["footprint"]]
    if unassigned:
        findings.append(_finding("warning", "footprint_unassigned", f"{len(unassigned)} symbol(s) without footprint: {unassigned[:10]}",
                                 "Assign footprints, or document that the symbol is intentionally generic/virtual."))
    if sch_facts["hidden_power_pins"]:
        findings.append(_finding("attention", "hidden_power_pins",
                                 f"{len(sch_facts['hidden_power_pins'])} hidden power-input pin(s) create implicit nets",
                                 "Review each implicit connection; prefer visible power pins for new designs."))

    # ---- board findings
    if board:
        ec = board.get("edge_cuts", {})
        if ec.get("state") in ("open", "absent"):
            findings.append(_finding("blocking", "edge_cuts_" + ec["state"], f"Edge.Cuts outline is {ec['state']}",
                                     "Close the outline (coincident endpoints, no overlaps); DRC behaviour depends on it."))
        elif ec.get("state") == "unknown":
            findings.append(_finding("attention", "edge_cuts_unverified", "Edge.Cuts contains shapes this inventory cannot verify",
                                     "Confirm outline closure with DRC and a plotted-view review."))
        if not board.get("stackup_defined"):
            findings.append(_finding("warning", "stackup_undefined", "board has no physical stackup in setup",
                                     "Define the stackup with the fabricator before routing controlled-impedance nets."))
        fps_no_model = [f["reference"] for f in board.get("footprints", [])
                        if f["reference"] not in {m["reference"] for m in board.get("models", [])}]
        if fps_no_model:
            findings.append(_finding("info", "no_3d_reference", f"{len(fps_no_model)} footprint(s) without a 3D model reference",
                                     "Record whether each is virtual or the model is intentionally absent."))

    if (project_dir / f"{stem}.kicad_dru").exists():
        dru = f"{stem}.kicad_dru"
    else:
        dru = None

    # ---- version skew
    versions = {**sch_facts["versions"]}
    if board.get("version"):
        versions[board_path.name] = board["version"]
    gens = sorted({str(v.get("generator_version")) for v in versions.values() if v.get("generator_version")})
    if len(gens) > 1:
        findings.append(_finding("attention", "version_skew", f"files written by different KiCad versions: {gens}",
                                 "Re-save all files with the controlled KiCad version, or record why skew is acceptable."))

    local_only = [f["path"] for f in files if f["distribution"] == "local_only"]
    return {
        "project_dir": str(project_dir),
        "project_file": pro.name,
        "project_meta": {
            "meta": pro_json.get("meta", {}),
            "text_variables": pro_json.get("text_variables", {}),
            "net_classes": [c.get("name") for c in pro_json.get("net_settings", {}).get("classes", [])],
            "erc_rule_severities": pro_json.get("erc", {}).get("rule_severities", {}),
            "drc_rule_severities": pro_json.get("board", {}).get("design_settings", {}).get("rule_severities", {}),
        },
        "custom_rules": dru,
        "sheets": sheets,
        "symbols": sch_facts["symbols"],
        "board": board,
        "symbol_libraries": sym_libs,
        "footprint_libraries": fp_libs,
        "file_versions": versions,
        "kicad_generator_versions": gens,
        "files": files,
        "local_only_files": local_only,
        "git": git_info(project_dir),
        "findings": findings,
        "complete": not any(f["severity"] == "blocking" for f in findings),
    }
