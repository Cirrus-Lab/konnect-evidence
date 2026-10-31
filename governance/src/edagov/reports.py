"""ERC/DRC report parsing and classification (Workflow Guide §6).

JSON field names follow KiCad's `rc_json_schema.h`:
  ERC: $schema, source, date, kicad_version, coordinate_units, sheets[{uuid_path, path, violations[]}],
       included_severities[], ignored_checks[{key, description}]
  DRC: ... violations[], unconnected_items[], schematic_parity[], included_severities[], ignored_checks[]
  VIOLATION: type, description, severity, items[{uuid, description, pos{x,y}}], excluded?, comment?

A clean report is a *consistency* result under recorded inputs and policy. It
is never presented as proof of function, SI/PI, thermal, EMC,
manufacturability or safety.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

DOCUMENTED_VIOLATION_EXIT = 5  # KiCad 10 CLI docs: 0 = none, 5 = violations (with --exit-code-violations)

CLAIM_LIMITS = {
    "erc": "ERC is a rule-based consistency check. It does not show that the circuit functions.",
    "drc": ("DRC is a rule-based consistency check against the recorded board constraints. It does not show "
            "function, SI/PI, thermal or EMC adequacy, manufacturability, or safety."),
}


def _violation_list(raw, sheet=None, bucket="violations"):
    out = []
    for v in raw or []:
        out.append({
            "type": v.get("type"),
            "description": v.get("description"),
            "severity": v.get("severity"),
            "excluded": bool(v.get("excluded", False)),
            "comment": v.get("comment"),
            "items": v.get("items", []),
            "sheet": sheet,
            "bucket": bucket,
        })
    return out


def parse_json_report(path: str | Path, kind: str) -> dict:
    problems = []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"kind": kind, "schema_valid": False, "problems": [f"unreadable JSON: {e}"], "violations": []}
    for key in ("source", "kicad_version", "date"):
        if key not in data:
            problems.append(f"missing top-level key '{key}'")
    violations = []
    if kind == "erc":
        if "sheets" not in data:
            problems.append("ERC report missing 'sheets'")
        for sh in data.get("sheets", []):
            violations += _violation_list(sh.get("violations"), sheet=sh.get("path"))
    elif kind == "drc":
        if "violations" not in data:
            problems.append("DRC report missing 'violations'")
        violations += _violation_list(data.get("violations"))
        violations += _violation_list(data.get("unconnected_items"), bucket="unconnected_items")
        violations += _violation_list(data.get("schematic_parity"), bucket="schematic_parity")
    else:
        problems.append(f"unknown report kind {kind!r}")
    for v in violations:
        if v["severity"] not in ("error", "warning", "exclusion", "info", "ignore", "debug"):
            problems.append(f"violation {v['type']}: unexpected severity {v['severity']!r}")
            break
    return summarize(kind, data, violations, problems, parse_confidence="schema")


def parse_text_report(path: str | Path, kind: str) -> dict:
    """Best-effort count extraction from the human-readable .rpt format."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    counts = {m.group(2).lower(): int(m.group(1)) for m in re.finditer(r"\*\* Found (\d+) (DRC violations|unconnected pads|Footprint errors|ERC violations|errors|warnings)", text, re.I)}
    ver = re.search(r"KiCad version[:\s]+([^\n]+)", text, re.I)
    data = {"source": None, "kicad_version": ver.group(1).strip() if ver else None, "date": None}
    total = sum(counts.values())
    violations = [{"type": "unparsed", "description": f"{k}", "severity": "error", "excluded": False,
                   "items": [], "sheet": None, "bucket": "violations"} for k, n in counts.items() for _ in range(n)]
    res = summarize(kind, data, violations, ["text report: severities and exclusions cannot be read reliably; "
                                             "re-run with --format json"], parse_confidence="low")
    res["text_counts"] = counts
    res["text_total"] = total
    return res


def summarize(kind, data, violations, problems, parse_confidence):
    active = [v for v in violations if not v["excluded"] and v["severity"] not in ("ignore", "exclusion")]
    excluded = [v for v in violations if v["excluded"] or v["severity"] == "exclusion"]
    sev = Counter(v["severity"] for v in active)
    included = data.get("included_severities")
    limitations = [CLAIM_LIMITS.get(kind, "")]
    if included is not None and set(included) != {"error", "warning"} and "warning" not in (included or []):
        limitations.append(f"report includes only severities {included}; warnings were not reported")
    ignored = data.get("ignored_checks") or []
    if ignored:
        limitations.append(f"{len(ignored)} check type(s) ignored in project settings; ignored checks are disabled "
                           "and each needs a recorded justification")
    if excluded:
        limitations.append(f"{len(excluded)} violation(s) excluded; each exclusion needs rationale and reviewer")
    return {
        "kind": kind,
        "schema": data.get("$schema"),
        "source": data.get("source"),
        "report_date": data.get("date"),
        "kicad_version": data.get("kicad_version"),
        "coordinate_units": data.get("coordinate_units"),
        "included_severities": included,
        "ignored_checks": ignored,
        "counts": {"active": len(active), "error": sev.get("error", 0), "warning": sev.get("warning", 0),
                   "excluded": len(excluded),
                   "unconnected": sum(1 for v in active if v["bucket"] == "unconnected_items"),
                   "parity": sum(1 for v in active if v["bucket"] == "schematic_parity")},
        "by_type": dict(Counter(v["type"] for v in active)),
        "violations": violations,
        "excluded": [{"type": v["type"], "comment": v.get("comment")} for v in excluded],
        "schema_valid": not problems,
        "parse_confidence": parse_confidence,
        "problems": problems,
        "limitations": [l for l in limitations if l],
    }


def classify(parsed: dict, exit_code: int | None, used_exit_code_flag: bool, executed: bool) -> tuple[str, list[str]]:
    """Return (result_class, notes). Disagreement between sources is preserved as 'conflict'."""
    notes = []
    if not parsed.get("schema_valid", False) and parsed.get("parse_confidence") == "schema":
        return "invalid", ["report failed schema validation: " + "; ".join(parsed.get("problems", []))]
    active = parsed.get("counts", {}).get("active", 0)
    report_class = "violations" if active else "clean"
    if parsed.get("parse_confidence") == "low":
        notes.append("text report: classification is low confidence")
    if not executed:
        notes.append("ingested report: the toolkit did not execute this check")
        return report_class, notes
    if exit_code is None:
        return "tool_error", ["tool did not exit normally (timeout or missing binary)"]
    if not used_exit_code_flag:
        if exit_code != 0:
            return "tool_error", [f"tool exited with {exit_code}"]
        return report_class, notes
    if exit_code == 0 and active == 0:
        return "clean", notes
    if exit_code == DOCUMENTED_VIOLATION_EXIT and active > 0:
        return "violations", notes
    if exit_code == 0 and active > 0:
        return "conflict", [f"exit code 0 but report lists {active} active violation(s)"]
    if exit_code == DOCUMENTED_VIOLATION_EXIT and active == 0:
        return "conflict", ["exit code 5 (violations) but report lists no active violations; excluded items may be counted"]
    return "tool_error", [f"undocumented exit code {exit_code} (documented: 0 none, 5 violations); report shows {active} active"]
