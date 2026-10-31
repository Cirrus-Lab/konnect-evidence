"""Default gate policy (Workflow Guide §12). Copied into .edagov/policy.json on
init; teams edit the JSON, never this default, so the policy in force is part
of the reviewed record.

A check may be marked not applicable only with a rationale, e.g.:

    "overrides": {"pcb": {"evidence_tag:emc_plan": {"not_applicable": "no external ports; reviewed ADR-0007"}}}
"""

DEFAULT_POLICY = {
    "policy_version": "1.0.0",
    "freshness_days": {
        "erc": 14,
        "drc": 14,
        "simulation": 90,
        "lifecycle": 90,
        "manufacturing_output": 7,
        "analysis": 180,
        "github": 1,
        "default": 30,
    },
    "gates": {
        "requirements": {
            "checks": ["requirements_complete", "assumptions_owned", "no_blocking_issues"],
        },
        "architecture": {
            "checks": ["requirements_allocated", "blocks_owned", "no_blocking_issues"],
        },
        "schematic_library": {
            "checks": ["run_clean:erc", "library_provenance", "no_blocking_issues"],
        },
        "simulation": {
            "checks": ["simulation_qualified", "no_blocking_issues"],
        },
        "pcb": {
            "checks": [
                "run_clean:drc",
                "drc_parity_checked",
                "evidence_tag:stackup",
                "evidence_tag:pi_analysis",
                "evidence_tag:si_analysis",
                "evidence_tag:thermal_analysis",
                "evidence_tag:emc_plan",
                "no_blocking_issues",
            ],
        },
        "supply": {
            "checks": ["bom_present", "bom_lines_valid", "no_blocking_issues"],
        },
        "release": {
            "checks": ["manifest_complete", "manifest_hashes_verify", "dfm_dispositioned",
                       "prior_gates_approved", "no_blocking_issues"],
        },
        "change": {
            "checks": ["change_impact_recorded", "no_blocking_issues"],
        },
    },
    "overrides": {},
    "manufacturing": {
        "required_functions": [
            "Copper,L1,Top",
            "Copper,L2,Bot",
            "Soldermask,Top",
            "Soldermask,Bot",
            "Legend,Top",
            "Profile,NP",
        ],
        "required_kinds": ["gerber", "drill", "position", "bom"],
        "optional_kinds": ["ipc2581", "odb", "gerber_job", "drill_map", "drawing", "paste"],
    },
    "issue_blocking_severities": ["high", "critical"],
    # Konnect integration: how MCP design edits are authorized.
    "governance": {
        "window_approver_roles": ["design_reviewer", "release_approver"],
        "allow_self_approved_windows": False,
        "max_window_hours": 24,
        "max_window_calls": 2000,
        "record_outputs": True,
        "capture_evidence_tools": [
            "run_erc", "run_drc", "get_drc_violations", "run_design_review", "audit_decoupling",
            "audit_connections", "audit_power_rails", "audit_manufacturing", "check_bom_health",
            "validate_for_manufacturing", "score_placement", "validate_sheet_pins",
            "validate_wire_connections", "validate_component_connections", "check_clearance",
            "find_orphan_items", "find_shorted_nets", "find_single_pin_nets", "check_schematic_overlaps",
            "compare_visual_baseline",
        ],
    },
}
