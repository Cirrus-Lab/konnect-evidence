//! Effect classification for every registered Konnect tool.
//!
//! Standard library only, so it can be unit-tested without the workspace.
//!
//! Every tool in the registry must appear in [`TABLE`]. A tool that is not
//! classified is treated as [`Effect::DesignWrite`] (fail-closed), and the
//! `every_registered_tool_is_classified` test in `governance::mod` fails so a
//! new upstream tool cannot slip through unclassified.

/// What a tool call can do to the world. Ordered from harmless to consequential.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Effect {
    /// Reads design, library, editor or catalogue state. Changes nothing.
    Read,
    /// Produces a plan or dry run. Changes nothing.
    Plan,
    /// Changes editor/viewer UI state only (selection, launching an app).
    Ui,
    /// Writes derived outputs (exports, renders, netlists, snapshots), not design sources.
    Output,
    /// Writes assistant/user configuration outside the design sources.
    ConfigWrite,
    /// Reaches a network service or downloads data.
    External,
    /// Changes design sources: schematic, board, project, libraries, rules, netclasses.
    DesignWrite,
}

impl Effect {
    pub fn as_str(self) -> &'static str {
        match self {
            Effect::Read => "read",
            Effect::Plan => "plan",
            Effect::Ui => "ui",
            Effect::Output => "output",
            Effect::ConfigWrite => "config_write",
            Effect::External => "external",
            Effect::DesignWrite => "design_write",
        }
    }

    /// Effects that are recorded in a governed design's evidence store.
    pub fn is_recorded(self) -> bool {
        matches!(
            self,
            Effect::Output | Effect::ConfigWrite | Effect::External | Effect::DesignWrite
        )
    }
}

/// How a tool's effect is decided.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rule {
    Fixed(Effect),
    /// Plans unless `dry_run` is explicitly `false`.
    DryRunDefaultTrue,
    /// Writes unless `dry_run` is explicitly `true`.
    DryRunDefaultFalse,
    /// Plans unless `apply` is explicitly `true`.
    ApplyDefaultFalse,
    /// Reads when `mode` is `"inspect"`, writes otherwise.
    ModeInspect,
}

/// Minimal read access to tool arguments, so this module needs no JSON crate.
pub trait ArgView {
    fn get_bool(&self, key: &str) -> Option<bool>;
    fn get_str(&self, key: &str) -> Option<String>;
}

use Effect::*;
use Rule::*;

const R: Rule = Fixed(Read);
const W: Rule = Fixed(DesignWrite);
const O: Rule = Fixed(Output);

/// Every registered tool, grouped by toolset (order follows `router/registry.rs`).
pub const TABLE: &[(&str, Rule)] = &[
    // project
    ("create_project", W),
    ("open_project", R),
    ("save_project", W),
    ("get_project_info", R),
    ("rename_project", DryRunDefaultFalse),
    ("snapshot_project", O),
    ("open_schematic_viewer", Fixed(Ui)),
    // editor_navigation
    ("get_editor_state", R),
    ("get_editor_selection", R),
    ("resolve_navigation_target", R),
    ("mutate_editor_selection", Fixed(Ui)),
    ("resolve_cross_probe_target", R),
    // sch_components
    ("add_schematic_component", W),
    ("delete_schematic_component", W),
    ("edit_schematic_component", W),
    ("get_schematic_component", R),
    ("list_schematic_components", R),
    ("move_schematic_component", W),
    ("rotate_schematic_component", W),
    ("move_connected", W),
    ("move_region", W),
    ("annotate_schematic", W),
    ("get_schematic_pin_locations", R),
    ("batch_get_schematic_pin_locations", R),
    ("add_component_annotation", W),
    ("group_components", W),
    ("replace_component", W),
    ("update_symbols_from_library", W),
    ("reset_schematic_field_positions", W),
    ("get_schematic_view", O),
    // sch_wiring
    ("add_wire", W),
    ("batch_add_wire", W),
    ("delete_schematic_wire", W),
    ("batch_delete_schematic_wire", W),
    ("split_wire_at_point", W),
    ("add_schematic_net_label", W),
    ("delete_schematic_net_label", W),
    ("rotate_schematic_label", W),
    ("move_labels_by_offset", W),
    ("batch_rotate_labels", W),
    ("add_power_symbol", W),
    ("add_no_connect", W),
    ("delete_no_connect", W),
    ("batch_delete_no_connect", W),
    ("batch_add_no_connect", W),
    ("add_junction", W),
    ("batch_add_junction", W),
    ("connect_to_net", W),
    ("connect_pins", W),
    ("add_schematic_connection", W),
    // sch_bus
    ("add_bus", W),
    ("batch_add_bus", W),
    ("add_bus_entry", W),
    ("connect_pins_to_bus", W),
    // sch_analysis
    ("list_schematic_wires", R),
    ("list_schematic_nets", R),
    ("list_schematic_labels", R),
    ("get_net_connections", R),
    ("get_net_connectivity", R),
    ("get_pin_connections", R),
    ("get_pin_net_name", R),
    ("get_component_nets", R),
    ("get_net_components", R),
    ("trace_from_point", R),
    ("find_orphan_items", R),
    ("find_shorted_nets", R),
    ("find_single_pin_nets", R),
    ("get_connected_items", R),
    ("check_schematic_overlaps", R),
    // sch_batch
    ("batch_connect_to_net", W),
    ("batch_delete", W),
    ("bulk_move_schematic_components", W),
    ("batch_edit_schematic_components", W),
    ("batch_delete_schematic_components", W),
    ("connect_passthrough", W),
    ("add_schematic_text", W),
    ("get_schematic_layout", R),
    ("validate_wire_connections", R),
    ("validate_component_connections", R),
    ("batch_place_components", W),
    ("batch_connect_pins", W),
    // sch_export
    ("export_schematic_svg", O),
    ("render_schematic_png", O),
    ("set_visual_baseline", O),
    ("compare_visual_baseline", R),
    ("export_schematic_pdf", O),
    ("generate_netlist", O),
    ("export_netlist_summary", R),
    ("run_erc", R),
    ("fix_connectivity", DryRunDefaultFalse),
    ("update_pcb_from_schematic", DryRunDefaultTrue),
    // sch_hierarchy
    ("create_schematic", W),
    ("set_schematic_page", W),
    ("add_hierarchical_sheet", W),
    ("edit_sheet", W),
    ("move_sheet", W),
    ("delete_sheet", W),
    ("duplicate_sheet", W),
    ("get_sheet_hierarchy", R),
    ("renumber_sheet_pages", W),
    ("import_sheet_pins", W),
    ("add_sheet_pin", W),
    ("edit_sheet_pin", W),
    ("delete_sheet_pin", W),
    ("validate_sheet_pins", R),
    // pcb_board
    ("set_board_size", W),
    ("get_board_info", R),
    ("get_board_extents", R),
    ("get_layer_list", R),
    ("get_board_stackup", R),
    ("add_layer", W),
    ("set_active_layer", R),
    ("add_board_outline", W),
    ("delete_graphics", DryRunDefaultFalse),
    ("add_mounting_hole", W),
    ("add_board_text", W),
    ("add_zone", W),
    ("import_svg_logo", W),
    // pcb_components
    ("place_component", W),
    ("move_component", W),
    ("rotate_component", W),
    ("set_component_placements", W),
    ("flip_component", W),
    ("delete_component", W),
    ("edit_component", W),
    ("repair_corrupted_footprints", DryRunDefaultTrue),
    ("find_component", R),
    ("update_footprints_from_library", DryRunDefaultTrue),
    ("list_board_footprint_graphics", R),
    ("edit_board_footprint_graphic", W),
    ("set_placed_footprint_models", ModeInspect),
    ("get_component_pads", R),
    ("get_pad_position", R),
    ("get_component_list", R),
    ("place_component_array", W),
    ("align_components", W),
    ("duplicate_component", W),
    ("get_board_2d_view", R),
    // pcb_routing
    ("add_net", W),
    ("route_trace", W),
    ("route_pad_to_pad", W),
    ("add_via", W),
    ("plan_specctra_ses_import", Fixed(Plan)),
    ("apply_specctra_ses", W),
    ("add_copper_pour", W),
    ("delete_trace", W),
    ("query_traces", R),
    ("get_nets_list", R),
    ("modify_trace", W),
    ("create_netclass", W),
    ("get_netclasses", R),
    ("assign_net_to_class", W),
    ("route_differential_pair", W),
    // placement
    ("score_placement", R),
    ("place_decoupling_caps", DryRunDefaultTrue),
    ("plan_bga_fanout", ApplyDefaultFalse),
    ("auto_place_from_schematic", DryRunDefaultTrue),
    ("refine_placement_force_directed", DryRunDefaultTrue),
    // pcb_export
    ("export_gerber", O),
    ("export_pdf", O),
    ("export_svg", O),
    ("export_3d", O),
    ("export_bom", O),
    ("export_netlist", O),
    ("export_specctra_dsn", O),
    ("export_position_file", O),
    ("export_dxf", O),
    ("export_gencad", O),
    ("export_ipc2581", O),
    ("export_odb", O),
    ("refill_zones", W),
    ("get_drc_violations", R),
    // library
    ("create_footprint", W),
    ("edit_footprint_pad", W),
    ("set_footprint_graphics", W),
    ("set_footprint_metadata", W),
    ("set_footprint_models", W),
    ("register_footprint_library", W),
    ("list_footprint_libraries", R),
    ("create_symbol", W),
    ("delete_symbol", W),
    ("list_symbols_in_library", R),
    ("register_symbol_library", W),
    ("list_symbol_libraries", R),
    ("search_symbols", R),
    ("list_library_footprints", R),
    ("get_footprint_info", R),
    ("search_footprints", R),
    ("get_symbol_info", R),
    // integration
    ("download_jlcpcb_database", Fixed(External)),
    ("search_jlcpcb_parts", R),
    ("get_jlcpcb_part", R),
    ("suggest_jlcpcb_alternatives", R),
    ("get_jlcpcb_database_stats", R),
    ("enrich_datasheets", W),
    ("get_datasheet_url", Fixed(External)),
    ("check_freerouting", R),
    ("route_specctra_dsn", O),
    // verification
    ("run_drc", R),
    ("set_design_rules", W),
    ("get_design_rules", R),
    ("set_predefined_sizes", W),
    ("get_predefined_sizes", R),
    ("check_kicad_ui", R),
    ("launch_kicad_ui", Fixed(Ui)),
    ("copy_routing_pattern", W),
    ("set_layer_constraints", W),
    ("check_clearance", R),
    // config
    ("load_user_config", R),
    ("save_user_config", Fixed(ConfigWrite)),
    ("load_project_config", R),
    ("save_project_config", Fixed(ConfigWrite)),
    ("get_effective_config", R),
    ("add_design_rule", Fixed(ConfigWrite)),
    ("list_design_rules", R),
    // design_review
    ("audit_decoupling", R),
    ("audit_connections", R),
    ("audit_power_rails", R),
    ("audit_manufacturing", R),
    ("run_design_review", R),
    ("check_bom_health", R),
    // templates
    ("search_templates", R),
    ("get_template", R),
    ("apply_template", W),
    ("list_template_categories", R),
    // manufacturing
    ("export_manufacturing_package", O),
    ("validate_for_manufacturing", R),
    ("estimate_cost", R),
];

/// Tools whose successful results are captured as (unreviewed) evidence in a
/// governed design. Mirrors `governance.capture_evidence_tools` in edagov's policy.
pub const CAPTURE_EVIDENCE: &[&str] = &[
    "run_erc",
    "run_drc",
    "get_drc_violations",
    "run_design_review",
    "audit_decoupling",
    "audit_connections",
    "audit_power_rails",
    "audit_manufacturing",
    "check_bom_health",
    "validate_for_manufacturing",
    "score_placement",
    "validate_sheet_pins",
    "validate_wire_connections",
    "validate_component_connections",
    "check_clearance",
    "find_orphan_items",
    "find_shorted_nets",
    "find_single_pin_nets",
    "check_schematic_overlaps",
    "compare_visual_baseline",
];

pub fn rule_for(tool: &str) -> Option<Rule> {
    TABLE
        .iter()
        .find(|(name, _)| *name == tool)
        .map(|(_, r)| *r)
}

/// Classify one call. Returns the effect and whether the tool was explicitly
/// classified (`false` means unknown, treated as a design write).
pub fn classify(tool: &str, args: &dyn ArgView) -> (Effect, bool) {
    let Some(rule) = rule_for(tool) else {
        return (DesignWrite, false);
    };
    let effect = match rule {
        Fixed(e) => e,
        DryRunDefaultTrue => {
            if args.get_bool("dry_run") == Some(false) {
                DesignWrite
            } else {
                Plan
            }
        }
        DryRunDefaultFalse => {
            if args.get_bool("dry_run") == Some(true) {
                Plan
            } else {
                DesignWrite
            }
        }
        ApplyDefaultFalse => {
            if args.get_bool("apply") == Some(true) {
                DesignWrite
            } else {
                Plan
            }
        }
        ModeInspect => {
            if args.get_str("mode").as_deref() == Some("inspect") {
                Read
            } else {
                DesignWrite
            }
        }
    };
    (effect, true)
}

pub fn captures_evidence(tool: &str) -> bool {
    CAPTURE_EVIDENCE.contains(&tool)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    struct Args(HashMap<&'static str, &'static str>);
    impl ArgView for Args {
        fn get_bool(&self, key: &str) -> Option<bool> {
            self.0.get(key).and_then(|v| v.parse().ok())
        }
        fn get_str(&self, key: &str) -> Option<String> {
            self.0.get(key).map(|v| v.to_string())
        }
    }
    fn args(pairs: &[(&'static str, &'static str)]) -> Args {
        Args(pairs.iter().copied().collect())
    }

    #[test]
    fn table_has_no_duplicates_and_228_tools() {
        let mut seen = std::collections::HashSet::new();
        for (name, _) in TABLE {
            assert!(seen.insert(*name), "duplicate entry {name}");
        }
        assert_eq!(TABLE.len(), 228);
    }

    #[test]
    fn unknown_tools_fail_closed() {
        assert_eq!(classify("brand_new_tool", &args(&[])), (DesignWrite, false));
    }

    #[test]
    fn dry_run_defaults_follow_each_handler() {
        assert_eq!(classify("update_pcb_from_schematic", &args(&[])).0, Plan);
        assert_eq!(
            classify("update_pcb_from_schematic", &args(&[("dry_run", "false")])).0,
            DesignWrite
        );
        assert_eq!(classify("fix_connectivity", &args(&[])).0, DesignWrite);
        assert_eq!(
            classify("fix_connectivity", &args(&[("dry_run", "true")])).0,
            Plan
        );
        assert_eq!(classify("plan_bga_fanout", &args(&[])).0, Plan);
        assert_eq!(
            classify("plan_bga_fanout", &args(&[("apply", "true")])).0,
            DesignWrite
        );
        assert_eq!(
            classify("set_placed_footprint_models", &args(&[("mode", "inspect")])).0,
            Read
        );
        assert_eq!(
            classify("set_placed_footprint_models", &args(&[("mode", "append")])).0,
            DesignWrite
        );
    }

    #[test]
    fn representative_effects() {
        let none = args(&[]);
        assert_eq!(classify("add_wire", &none).0, DesignWrite);
        assert_eq!(classify("run_erc", &none).0, Read);
        assert_eq!(classify("export_gerber", &none).0, Output);
        assert_eq!(classify("download_jlcpcb_database", &none).0, External);
        assert_eq!(classify("save_user_config", &none).0, ConfigWrite);
        assert_eq!(classify("launch_kicad_ui", &none).0, Ui);
        assert!(!Read.is_recorded() && !Plan.is_recorded() && !Ui.is_recorded());
        assert!(DesignWrite.is_recorded() && Output.is_recorded());
    }

    #[test]
    fn every_capture_tool_is_classified_read() {
        for t in CAPTURE_EVIDENCE {
            assert_eq!(
                rule_for(t),
                Some(Fixed(Read)),
                "{t} should be a read-only check"
            );
        }
    }
}
