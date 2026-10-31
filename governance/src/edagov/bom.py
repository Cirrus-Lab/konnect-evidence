"""BOM ingestion and sourcing-evidence checks (Workflow Guide §7).

Each line must identify an exact orderable part. Lifecycle is
manufacturer-specific and dated; alternates are explicit states with an
equivalence matrix and qualification evidence. Headline equivalence
("drop-in", same package, distributor cross-reference) is never accepted as
evidence. Authorized distribution reduces risk; it does not prove authenticity.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .util import file_hash, freshness, new_id, now_iso, slug
from .vocab import ALTERNATE_STATES

COLUMN_ALIASES = {
    "internal_item": ["internal item", "internal_item", "item", "part number", "internal pn", "ipn"],
    "references": ["references", "reference", "refs", "designator", "designators", "refdes"],
    "quantity": ["qty", "quantity", "qnty"],
    "manufacturer": ["manufacturer", "mfr", "mfg", "manufacturer_name"],
    "mpn": ["mpn", "manufacturer part number", "manufacturer_part_number", "mfr part", "mfg pn", "orderable"],
    "description": ["description", "desc", "value"],
    "package": ["package", "case", "footprint"],
    "lifecycle": ["lifecycle", "lifecycle status", "status"],
    "lifecycle_source": ["lifecycle source", "lifecycle_source"],
    "lifecycle_date": ["lifecycle date", "lifecycle_date", "lifecycle evidence date"],
    "approved_source": ["approved source", "source", "distributor", "channel"],
    "alternate_state": ["alternate state", "alternate_state", "alt state"],
    "alternate_for": ["alternate for", "alternate_for", "replaces"],
    "equivalence_matrix": ["equivalence matrix", "equivalence_matrix"],
    "qualification_evidence": ["qualification evidence", "qualification_evidence"],
    "risk_class": ["risk", "risk class", "risk_class"],
    "compliance": ["compliance", "rohs/reach", "certificates"],
    "dnp": ["dnp", "do not populate", "not fitted"],
    "pcn_eol": ["pcn/eol", "pcn", "eol", "last buy"],
}
GENERIC_MPN = re.compile(r"^(tbd|any|generic|n/?a|-|\d+(\.\d+)?\s*([kmunp]|meg)?(f|h|r|ohm|Ω)?)$", re.I)
RISKY_LIFECYCLE = re.compile(r"eol|obsolete|nrnd|not recommended|last[- ]time|discontinued", re.I)
HEADLINE_EQUIV = re.compile(r"drop[- ]?in|pin[- ]compatible|direct replacement|cross[- ]ref|same package", re.I)
BROKER = re.compile(r"broker|independent|marketplace|grey|gray", re.I)


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def _map_columns(headers: list[str]) -> dict[str, str]:
    norm = {_norm_header(h): h for h in headers}
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in norm:
                mapping[field] = norm[a]
                break
    return mapping


def split_refs(text: str) -> list[str]:
    refs = []
    for tok in re.split(r"[,\s;]+", text or ""):
        tok = tok.strip()
        m = re.match(r"^([A-Za-z_#]+)(\d+)-\1?(\d+)$", tok)
        if m:  # R1-R4 or R1-4
            refs += [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        elif tok:
            refs.append(tok)
    return refs


def validate_line(line: dict, policy: dict, now: str | None = None) -> list[dict]:
    f = []

    def add(sev, code, msg, action):
        f.append({"severity": sev, "code": code, "message": msg, "next_action": action})

    if not line.get("manufacturer"):
        add("blocking", "no_manufacturer", "manufacturer missing", "Record the exact manufacturer.")
    mpn = (line.get("mpn") or "").strip()
    if not mpn:
        add("blocking", "no_mpn", "manufacturer part number missing", "Record the exact orderable MPN including suffix.")
    elif GENERIC_MPN.match(mpn):
        add("blocking", "generic_mpn", f"'{mpn}' is not an orderable part number", "Replace with the exact orderable MPN.")
    refs = line.get("references_list", [])
    try:
        qty = int(float(line.get("quantity") or 0))
    except ValueError:
        qty = -1
    if refs and qty != len(refs) and not line.get("dnp"):
        add("blocking", "qty_mismatch", f"quantity {line.get('quantity')} != {len(refs)} reference(s)",
            "Reconcile quantity with reference designators.")
    lc = (line.get("lifecycle") or "").strip()
    if not lc:
        add("warning", "lifecycle_unknown", "lifecycle state not recorded",
            "Record manufacturer lifecycle status with source and evidence date.")
    else:
        if RISKY_LIFECYCLE.search(lc):
            sev = "blocking" if not line.get("pcn_eol") else "warning"
            add(sev, "lifecycle_risk", f"lifecycle '{lc}'", "Record PCN/EOL notice, last-buy date and mitigation/alternate plan.")
        if not line.get("lifecycle_source"):
            add("warning", "lifecycle_source_missing", "lifecycle source not recorded", "Cite the manufacturer notice/program.")
        fr = freshness(line.get("lifecycle_date"), policy.get("freshness_days", {}).get("lifecycle", 90), now)
        if fr in ("stale", "missing", "future-dated", "unknown"):
            add("warning", f"lifecycle_{fr.replace('-', '_')}", f"lifecycle evidence is {fr}", "Refresh lifecycle evidence.")
    alt = (line.get("alternate_state") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if alt:
        if alt not in ALTERNATE_STATES:
            add("blocking", "alternate_state_invalid", f"alternate state '{alt}' not in {list(ALTERNATE_STATES)}",
                "Use candidate / engineering_approved / production_approved / disallowed.")
        elif alt in ("engineering_approved", "production_approved"):
            if not line.get("equivalence_matrix") or not line.get("qualification_evidence"):
                add("blocking", "alternate_unsupported", f"'{alt}' alternate without equivalence matrix and qualification evidence",
                    "Attach the equivalence matrix and qualification evidence, or downgrade to candidate.")
        if alt == "disallowed" and not line.get("dnp"):
            add("blocking", "disallowed_part_in_bom", "a disallowed alternate is in the build BOM", "Remove or re-disposition.")
    text = " ".join(str(line.get(k) or "") for k in ("description", "equivalence_matrix", "notes"))
    if HEADLINE_EQUIV.search(text):
        add("attention", "headline_equivalence", "'drop-in'/cross-reference language is not equivalence evidence",
            "Replace with an equivalence matrix covering ratings, tolerances, package, firmware and process impact.")
    src = line.get("approved_source") or ""
    allow = [s.lower() for s in policy.get("approved_sources", [])]
    if not src:
        add("warning", "no_approved_source", "approved source/channel not recorded", "Record the approved source.")
    elif BROKER.search(src):
        add("warning", "broker_source", f"source '{src}' is a broker/independent channel",
            "Escalate per procurement policy: CoC, traceability, inspection, quarantine.")
    elif allow and src.lower() not in allow:
        add("attention", "source_not_allowlisted", f"source '{src}' not on approved-source allowlist", "Confirm or add to allowlist.")
    return f


def ingest_csv(store, csv_path, *, mapping_override: dict | None = None, cross_check_symbols: list[dict] | None = None) -> dict:
    store.check("record_evidence")
    csv_path = Path(csv_path).resolve()
    ident, policy = store.identity, store.policy
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        headers = reader.fieldnames or []
        mapping = {**_map_columns(headers), **(mapping_override or {})}
        rows = list(reader)
    unmapped = [k for k in ("mpn", "manufacturer", "references", "quantity") if k not in mapping]
    file_art = store.put({"type": "artifact", "id": new_id("artifact", f"bom-{csv_path.name}-{ident['revision']}"),
                          "kind": "bom", "path": str(csv_path), "hash": file_hash(csv_path),
                          "source_revision": ident["revision"], "owner": ident.get("design_authority"),
                          "column_mapping": mapping, "unmapped_required_columns": unmapped})
    seen_refs: dict[str, str] = {}
    out, all_refs = [], set()
    for i, row in enumerate(rows, start=2):
        line = {k: (row.get(col) or "").strip() for k, col in mapping.items()}
        line["references_list"] = split_refs(line.get("references", ""))
        line["dnp"] = str(line.get("dnp", "")).lower() in ("1", "yes", "true", "dnp", "x")
        findings = validate_line(line, policy)
        for r in line["references_list"]:
            if r in seen_refs:
                findings.append({"severity": "blocking", "code": "duplicate_reference",
                                 "message": f"{r} also on line {seen_refs[r]}", "next_action": "Remove the duplicate reference."})
            seen_refs[r] = str(i)
            if not line["dnp"]:
                all_refs.add(r)
        worst = ("blocking" if any(x["severity"] == "blocking" for x in findings)
                 else "warning" if any(x["severity"] == "warning" for x in findings)
                 else "attention" if findings else "info")
        key = line.get("internal_item") or line.get("mpn") or f"line{i}"
        rec = {
            "type": "bom_line", "id": new_id("bom_line", f"{key}-{ident['variant']}"),
            "internal_item": line.get("internal_item") or "(none)", "manufacturer": line.get("manufacturer") or "",
            "mpn": line.get("mpn") or "", "references": line["references_list"], "quantity": line.get("quantity") or "0",
            "lifecycle": line.get("lifecycle") or "unknown", "lifecycle_source": line.get("lifecycle_source"),
            "lifecycle_date": line.get("lifecycle_date"), "approved_source": line.get("approved_source"),
            "alternate_state": (line.get("alternate_state") or "").lower().replace(" ", "_").replace("-", "_") or None,
            "alternate_for": line.get("alternate_for"), "equivalence_matrix": line.get("equivalence_matrix"),
            "qualification_evidence": line.get("qualification_evidence"), "risk_class": line.get("risk_class"),
            "compliance": line.get("compliance"), "package": line.get("package"), "description": line.get("description"),
            "dnp": line["dnp"], "pcn_eol": line.get("pcn_eol"), "csv_line": i, "bom_artifact": file_art["id"],
            "findings": findings,
            "state": "blocked" if worst == "blocking" else "ready_for_review",
            "severity": worst, "timestamp": now_iso(), "source": f"BOM {csv_path.name} line {i}",
            "owner": ident.get("design_authority"), "linked_evidence": [file_art["id"]],
            "next_action": findings[0]["next_action"] if findings else "Supply reviewer approval.",
        }
        if rec["alternate_state"] not in (None,) + ALTERNATE_STATES:
            rec["alternate_state_raw"], rec["alternate_state"] = rec["alternate_state"], None
        if rec["alternate_state"] in ("engineering_approved", "production_approved") and not (
                rec["equivalence_matrix"] and rec["qualification_evidence"]):
            # Keep the claim visible but do not accept it as the line's state.
            rec["alternate_state_claimed"], rec["alternate_state"] = rec["alternate_state"], None
        out.append(store.put(rec, reason=f"BOM line {i} from {csv_path.name}"))
    cross = None
    if cross_check_symbols is not None:
        sch_refs = {s["reference"] for s in cross_check_symbols if not s.get("power_symbol") and not s.get("dnp")}
        cross = {"in_bom_not_schematic": sorted(all_refs - sch_refs), "in_schematic_not_bom": sorted(sch_refs - all_refs)}
    return {"artifact": file_art, "lines": out, "unmapped_required_columns": unmapped, "cross_check": cross,
            "blocking_lines": sum(1 for r in out if r["severity"] == "blocking")}


def bom_line_id(key: str, variant: str) -> str:
    return f"BOM-{slug(key + '-' + variant)}"
