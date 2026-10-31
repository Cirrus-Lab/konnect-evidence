"""Controlled vocabularies shared by the toolkit, skill, and dashboard.

Every state here comes straight from the specifications:
- Workflow Guide §12 / Dashboard Spec §2.2 (gate states, freshness)
- Dashboard Spec §3.6 (review states) and §10 (failure/uncertainty states)
- Workflow Guide §4.2 (simulation run classes) and §7 (alternate states)

Nothing in this module may collapse "no data", "not applicable",
"not checked" and "passed" into one value (Dashboard Spec §2.2).
"""

GATE_STATES = (
    "not_started",
    "in_progress",
    "ready_for_review",
    "approved",
    "approved_with_exception",
    "blocked",
    "rejected",
    "superseded",
    "not_applicable",
)

# States that automation alone may assign. "approved*" and "rejected" need a
# human review record (Workflow Guide §14, Skill Spec §6).
AUTOMATION_GATE_STATES = ("not_started", "in_progress", "ready_for_review", "blocked")

FRESHNESS = ("current", "stale", "future-dated", "unknown", "missing")

REVIEW_STATES = (
    "not_started",
    "in_progress",
    "approved",
    "requested_changes",
    "blocked",
    "abstained",
    "expired",
    "superseded",
)

FAILURE_STATES = (
    "loading",
    "empty",
    "not_configured",
    "stale",
    "partial",
    "unavailable",
    "unauthorized",
    "conflict",
    "invalid",
    "timeout",
    "queued/retrying",
    "dead_lettered",
)

# Result classes for a tool run. "not_checked" is distinct from "passed".
RESULT_CLASSES = (
    "clean",                    # tool ran, zero violations under recorded policy
    "violations",               # tool ran, violations present
    "converged_with_warnings",  # simulation only
    "altered_settings",         # simulation: solver settings changed vs baseline
    "failed",                   # tool ran and failed / did not converge
    "tool_error",               # tool could not run to completion
    "conflict",                 # exit code and parsed report disagree
    "not_checked",              # nothing ran
    "invalid",                  # report failed schema validation
)

SIM_RUN_CLASSES = ("clean", "converged_with_warnings", "altered_settings", "failed")

ALTERNATE_STATES = (
    "candidate",
    "engineering_approved",
    "production_approved",
    "disallowed",
)

SEVERITY = ("info", "attention", "warning", "blocking", "approved")

ISSUE_SEVERITY = ("low", "medium", "high", "critical")
ISSUE_STATES = ("open", "contained", "accepted", "closed", "superseded")

DECISIONS = (
    "approved",
    "approved_with_exception",
    "blocked",
    "rejected",
    "not_checked",
    "not_applicable",
)

ROLES = (
    "viewer",
    "contributor",
    "design_reviewer",
    "supply_reviewer",
    "manufacturing_reviewer",
    "release_approver",
    "connector_admin",
    "auditor",
)

# Workflow Guide §12 — ordered gates.
GATES = (
    ("requirements", "Requirements gate"),
    ("architecture", "Architecture gate"),
    ("schematic_library", "Schematic/library gate"),
    ("simulation", "Simulation gate"),
    ("pcb", "PCB gate"),
    ("supply", "Supply gate"),
    ("release", "Release gate"),
    ("change", "Change gate"),
)

GITFLOW_LANES = ("production", "integration", "feature", "release", "hotfix", "other")

# Effect classes Konnect assigns to every MCP tool (see crates/konnect-core/src/governance).
TOOL_EFFECTS = ("read", "plan", "ui", "output", "config_write", "external", "design_write")
WINDOW_STATES = ("requested", "approved", "rejected", "closed", "expired")

CONNECTOR_ACTIONS = ("read", "create", "change", "publish", "purchase", "release", "delete")
# Actions that always need an explicit human approval record (Skill Spec §3 step 7).
SENSITIVE_ACTIONS = ("publish", "purchase", "release", "delete")

ENTITY_TYPES = (
    "product",
    "design",
    "requirement",
    "architecture_block",
    "artifact",
    "run",
    "bom_line",
    "manufacturing_package",
    "issue",
    "review",
    "connector",
    "approval",
    "exception",
    "decision",
    "assumption",
    "gate",
    "connector_action",
    "github_pr",
    "change_window",
)

ID_PREFIX = {
    "product": "PRD",
    "design": "DES",
    "requirement": "REQ",
    "architecture_block": "BLK",
    "artifact": "ART",
    "run": "RUN",
    "bom_line": "BOM",
    "manufacturing_package": "MFG",
    "issue": "ISS",
    "review": "REV",
    "connector": "CON",
    "approval": "APR",
    "exception": "EXC",
    "decision": "ADR",
    "assumption": "ASM",
    "gate": "GATE",
    "connector_action": "ACT",
    "github_pr": "GH",
    "change_window": "WIN",
}


def check(value, allowed, field):
    """Raise ValueError when value is not in an allowed vocabulary."""
    if value not in allowed:
        raise ValueError(f"{field}={value!r} is not one of {list(allowed)}")
    return value
