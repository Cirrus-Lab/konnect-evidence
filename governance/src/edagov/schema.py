"""Design-level evidence schema (Dashboard Spec §2.1, Skill Spec §3 step 3).

Validation is intentionally strict on identity/linkage fields and on
controlled vocabularies, and permissive on domain-specific extras so teams
can extend records without forking the schema.
"""
from __future__ import annotations

from . import vocab

COMMON_REQUIRED = ("id", "type", "created_at")
# Every status-bearing record must carry these (Dashboard Spec §2.2).
STATUS_FIELDS = ("state", "severity", "timestamp", "source", "owner", "linked_evidence", "next_action")

SCHEMA: dict[str, dict] = {
    "product": {"required": ("product_id", "revision", "owner", "lifecycle"), "vocab": {}},
    "design": {
        "required": ("design_id", "board_id", "revision", "variant", "release_state", "design_authority"),
        "vocab": {},
    },
    "requirement": {
        "required": ("text", "source", "owner", "priority", "verification_method", "acceptance", "status"),
        "vocab": {
            "verification_method": (
                "inspection", "analysis", "simulation", "test", "demonstration",
                "supplier_confirmation", "review",
            ),
            "status": ("draft", "approved", "at_risk", "verified", "unmet", "superseded"),
        },
    },
    "architecture_block": {"required": ("name", "purpose", "owner", "interfaces", "allocated_requirements"), "vocab": {}},
    "artifact": {
        "required": ("kind", "path", "hash", "source_revision", "owner"),
        "vocab": {
            "kind": (
                "schematic", "pcb", "project", "symbol_library", "footprint_library", "model_3d",
                "spice_model", "netlist", "drawing", "report", "fab_output", "assembly_output",
                "configuration", "rules", "jobset", "worksheet", "bom", "other",
            )
        },
    },
    "run": {
        "required": ("tool", "tool_version", "inputs", "result_class", "claim_scope", "executed"),
        "vocab": {"result_class": vocab.RESULT_CLASSES},
    },
    "bom_line": {
        "required": ("internal_item", "manufacturer", "mpn", "references", "quantity", "lifecycle"),
        "vocab": {"alternate_state": vocab.ALTERNATE_STATES},
    },
    "manufacturing_package": {
        "required": ("board_id", "revision", "variant", "files", "completeness"),
        "vocab": {},
    },
    "issue": {
        "required": ("title", "severity", "state", "owner", "affected"),
        "vocab": {"severity": vocab.ISSUE_SEVERITY, "state": vocab.ISSUE_STATES},
    },
    "exception": {
        "required": ("title", "rationale", "approver", "approved_at", "review_trigger", "affected_claims"),
        "vocab": {},
    },
    "review": {
        "required": ("target", "target_revision", "reviewer", "reviewer_role", "state"),
        "vocab": {"state": vocab.REVIEW_STATES, "reviewer_role": vocab.ROLES},
    },
    "approval": {
        "required": ("gate", "decision", "approver", "approver_role", "target_revision", "evidence"),
        "vocab": {"decision": vocab.DECISIONS, "approver_role": vocab.ROLES},
    },
    "connector": {
        "required": ("provider", "protocol", "protocol_version", "transport", "scopes", "trust_tier", "sync_state"),
        "vocab": {
            "trust_tier": ("untrusted", "verified_read", "verified_write"),
            "sync_state": vocab.FAILURE_STATES + ("synced",),
        },
    },
    "connector_action": {
        "required": ("connector", "action", "target", "inputs", "affected_revision", "idempotency_key", "action_state"),
        "vocab": {
            "action": vocab.CONNECTOR_ACTIONS,
            "action_state": ("proposed", "approved", "rejected", "executed", "failed", "unknown", "compensated", "dead_lettered"),
        },
    },
    "github_pr": {
        "required": ("provider", "repository", "number", "sync_state", "last_sync_attempt", "correlation_id"),
        "vocab": {"sync_state": vocab.FAILURE_STATES + ("synced",)},
    },
    "change_window": {
        "required": ("scope", "reason", "requested_by", "window_state", "expires_at", "max_calls"),
        "vocab": {"window_state": vocab.WINDOW_STATES},
    },
    "decision": {"required": ("title", "rationale", "alternatives", "consequences", "status"), "vocab": {}},
    "assumption": {"required": ("text", "owner", "review_condition"), "vocab": {}},
    "gate": {"required": ("gate", "state", "explanation"), "vocab": {"state": vocab.GATE_STATES}},
}

# Records that must be tied to a design identity.
DESIGN_SCOPED = set(SCHEMA) - {"product", "connector"}


class SchemaError(ValueError):
    pass


def validate(record: dict) -> list[str]:
    """Return a list of problems (empty == valid)."""
    problems: list[str] = []
    for f in COMMON_REQUIRED:
        if f not in record or record[f] in (None, ""):
            problems.append(f"missing common field '{f}'")
    rtype = record.get("type")
    if rtype not in SCHEMA:
        problems.append(f"unknown record type {rtype!r}")
        return problems
    spec = SCHEMA[rtype]
    for f in spec["required"]:
        if f not in record or record[f] in (None, ""):
            problems.append(f"{rtype}: missing required field '{f}'")
    for f, allowed in spec["vocab"].items():
        if f in record and record[f] not in (None, "") and record[f] not in allowed:
            problems.append(f"{rtype}: {f}={record[f]!r} not in {list(allowed)}")
    if rtype in DESIGN_SCOPED:
        for f in ("design_id", "revision", "variant"):
            if not record.get(f):
                problems.append(f"{rtype}: missing design identity field '{f}'")
    # Run records: executed must be explicit; non-executed runs cannot be clean.
    if rtype == "run":
        if record.get("executed") is False and record.get("result_class") == "clean" and not record.get("ingested_report"):
            problems.append("run: a run that was not executed and has no ingested report cannot be 'clean'")
    if rtype == "bom_line" and record.get("alternate_state") in ("engineering_approved", "production_approved"):
        if not record.get("equivalence_matrix") or not record.get("qualification_evidence"):
            problems.append("bom_line: approved alternate requires equivalence_matrix and qualification_evidence")
    if rtype == "approval" and record.get("decision") == "approved_with_exception" and not record.get("exceptions"):
        problems.append("approval: approved_with_exception must link exception IDs")
    return problems


def require_valid(record: dict) -> dict:
    problems = validate(record)
    if problems:
        raise SchemaError("; ".join(problems))
    return record
