//! Evidence governance for Konnect tool calls.
//!
//! Every domain tool call passes through [`pre_call`] before its handler runs
//! and [`post_call`] after. The tool's [`effects::Effect`] decides what happens:
//!
//! * `read`, `plan`, `ui` — run untouched (results of check tools listed in
//!   [`effects::CAPTURE_EVIDENCE`] are captured as unreviewed evidence when the
//!   design is governed);
//! * `output`, `config_write`, `external` — run, then recorded;
//! * `design_write` — run only if edagov finds an approved, unexpired change
//!   window covering the tool, then recorded with before/after file hashes.
//!
//! A design is governed when an `.edagov/` evidence store sits at or above the
//! file the call targets (or at `KONNECT_GOVERNANCE_ROOT`). `KONNECT_GOVERNANCE`
//! selects the mode — see [`bridge::Mode`]. Following the gate contract in
//! `crate::gates`, a governance check that could not run never counts as a pass:
//! in `auto`/`enforce` mode a governed design write is refused when edagov is
//! unavailable.

pub mod bridge;
pub mod effects;

use crate::mcp::error::ToolErrorKind;
use crate::mcp::protocol::CallToolResult;
use serde_json::Value;
use std::path::PathBuf;
use tracing::{info, warn};

use bridge::Mode;
use effects::Effect;

/// What `post_call` needs to know about an allowed call.
#[derive(Debug, Clone)]
pub struct Ticket {
    root: PathBuf,
    tool: String,
    toolset: Option<String>,
    effect: Effect,
    call_id: String,
    paths: Vec<String>,
    capture: bool,
}

/// Outcome of the pre-call check.
pub enum PreCall {
    /// Run the handler; record afterwards when a ticket is present.
    Proceed(Option<Ticket>),
    /// Do not run the handler; return this refusal instead.
    Refuse(CallToolResult),
}

struct JsonArgs<'a>(&'a Value);

impl effects::ArgView for JsonArgs<'_> {
    fn get_bool(&self, key: &str) -> Option<bool> {
        self.0.get(key).and_then(Value::as_bool)
    }
    fn get_str(&self, key: &str) -> Option<String> {
        self.0.get(key).and_then(Value::as_str).map(str::to_string)
    }
}

/// Path-like string arguments, top level and inside top-level arrays.
///
/// URLs (a symbol's `datasheet`) are not files. Relative paths and
/// `${KIPRJMOD}` paths are resolved the way the tool resolves them, against the
/// directory of the call's absolute design path (the parent schematic, project
/// or library), so edagov judges the file the tool will actually touch rather
/// than resolving `power.kicad_sch` against its own working directory. `..` is
/// kept, so a path that escapes the governed root is still refused; without an
/// absolute anchor, relative paths are passed through unchanged.
pub fn collect_paths(args: &Value) -> Vec<String> {
    let mut raw: Vec<String> = Vec::new();
    let mut push = |s: &str| {
        if bridge::looks_like_path(s) && !s.contains("://") && !raw.iter().any(|p| p == s) {
            raw.push(s.to_string());
        }
    };
    if let Some(map) = args.as_object() {
        for value in map.values() {
            match value {
                Value::String(s) => push(s),
                Value::Array(items) => {
                    for item in items {
                        if let Value::String(s) = item {
                            push(s);
                        }
                    }
                }
                _ => {}
            }
        }
    }
    let anchor = raw
        .iter()
        .map(std::path::Path::new)
        .find(|p| p.is_absolute())
        .and_then(|p| {
            if p.extension().is_some() {
                p.parent().map(std::path::Path::to_path_buf)
            } else {
                Some(p.to_path_buf())
            }
        });
    let mut out: Vec<String> = Vec::new();
    for s in raw {
        let resolved = match &anchor {
            Some(dir) => {
                if let Some(rest) = s.strip_prefix("${KIPRJMOD}") {
                    dir.join(rest.trim_start_matches(['/', '\\']))
                        .to_string_lossy()
                        .into_owned()
                } else if std::path::Path::new(&s).is_relative() {
                    dir.join(&s).to_string_lossy().into_owned()
                } else {
                    s
                }
            }
            None => s,
        };
        if !out.contains(&resolved) {
            out.push(resolved);
        }
    }
    out
}

fn refusal(tool: &str, reasons: Vec<String>) -> CallToolResult {
    let message = format!(
        "Konnect did not run '{tool}': evidence governance refused the call. {}",
        reasons.join(" ")
    );
    CallToolResult::error_kind(
        ToolErrorKind::PlanBlocked {
            operation: format!("governance:{tool}"),
            reasons,
        },
        message,
    )
}

/// Decide whether a tool call may run, before its handler executes.
pub async fn pre_call(tool: &str, toolset: Option<&str>, args: &Value) -> PreCall {
    let mode = Mode::from_env();
    if mode == Mode::Off {
        return PreCall::Proceed(None);
    }
    let (effect, explicit) = effects::classify(tool, &JsonArgs(args));
    let capture = effects::captures_evidence(tool);
    if !effect.is_recorded() && !capture {
        return PreCall::Proceed(None);
    }
    let paths = collect_paths(args);
    let Some(root) = bridge::find_store(&paths) else {
        if mode == Mode::Enforce && effect == Effect::DesignWrite {
            return PreCall::Refuse(refusal(
                tool,
                vec![
                    "No evidence store governs the target design (KONNECT_GOVERNANCE=enforce).".to_string(),
                    "Run `edagov init` in the design repository, or set KONNECT_GOVERNANCE_ROOT to it.".to_string(),
                ],
            ));
        }
        return PreCall::Proceed(None);
    };
    let ticket = Ticket {
        root,
        tool: tool.to_string(),
        toolset: toolset.map(str::to_string),
        effect,
        call_id: bridge::new_call_id(),
        paths,
        capture,
    };
    if effect != Effect::DesignWrite {
        return PreCall::Proceed(Some(ticket));
    }
    let audit_only = mode == Mode::Audit;
    let t = ticket.clone();
    let decided = tokio::task::spawn_blocking(move || {
        bridge::authorize(
            &t.root,
            &t.tool,
            t.toolset.as_deref(),
            t.effect.as_str(),
            &t.call_id,
            &t.paths,
            audit_only,
        )
    })
    .await;
    let mut reasons = Vec::new();
    match decided {
        Ok(Ok(d)) if d.allow => {
            info!(
                tool,
                window = d.window.as_deref().unwrap_or("-"),
                explicit,
                "governance_allowed"
            );
            return PreCall::Proceed(Some(ticket));
        }
        Ok(Ok(d)) => {
            reasons.push(d.reason);
            if let Some(next) = d.next_action {
                reasons.push(format!("Next: {next}"));
            }
        }
        Ok(Err(e)) => reasons.push(format!("The governance check could not run: {e}.")),
        Err(e) => reasons.push(format!("The governance check could not run: {e}.")),
    }
    if !explicit {
        reasons.push(format!(
            "'{tool}' is not in Konnect's effect table, so it is treated as a design write."
        ));
    }
    if audit_only {
        warn!(tool, reasons = %reasons.join(" "), "governance_audit_would_refuse");
        return PreCall::Proceed(Some(ticket));
    }
    warn!(tool, reasons = %reasons.join(" "), "governance_refused");
    PreCall::Refuse(refusal(tool, reasons))
}

/// Record a finished call in the governed design's evidence store.
pub async fn post_call(ticket: Option<Ticket>, result: &CallToolResult, ok: bool) {
    let Some(t) = ticket else {
        return;
    };
    let capture = if t.capture && ok {
        serde_json::to_string(result).ok()
    } else {
        None
    };
    if !t.effect.is_recorded() && capture.is_none() {
        return;
    }
    let tool = t.tool.clone();
    let recorded = tokio::task::spawn_blocking(move || {
        bridge::record(
            &t.root,
            &t.tool,
            t.toolset.as_deref(),
            t.effect.as_str(),
            &t.call_id,
            ok,
            &t.paths,
            capture,
        )
    })
    .await;
    match recorded {
        Ok(Ok(_)) => {}
        Ok(Err(e)) => warn!(tool = %tool, error = %e, "governance_record_failed"),
        Err(e) => warn!(tool = %tool, error = %e, "governance_record_failed"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn every_registered_tool_is_classified() {
        let mut missing = Vec::new();
        for toolset in crate::router::registry::ALL_TOOLSETS {
            for def in crate::router::registry::tools_for(toolset.name).unwrap_or_default() {
                if effects::rule_for(def.name).is_none() {
                    missing.push(format!("{}::{}", toolset.name, def.name));
                }
            }
        }
        assert!(
            missing.is_empty(),
            "classify these tools in governance/effects.rs: {missing:?}"
        );
    }

    #[test]
    fn effect_table_has_no_stale_entries() {
        let registered: std::collections::HashSet<&str> = crate::router::registry::ALL_TOOLSETS
            .iter()
            .flat_map(|t| crate::router::registry::tools_for(t.name).unwrap_or_default())
            .map(|d| d.name)
            .collect();
        for (name, _) in effects::TABLE {
            assert!(
                registered.contains(name),
                "{name} is classified but not registered"
            );
        }
    }

    #[test]
    fn paths_are_collected_from_strings_and_arrays() {
        let args = json!({
            "schematic": "/tmp/a/x.kicad_sch",
            "reference": "R1",
            "files": ["/tmp/a/y.kicad_pcb", "GND"],
            "count": 3
        });
        let p = collect_paths(&args);
        assert!(p.contains(&"/tmp/a/x.kicad_sch".to_string()));
        assert!(p.contains(&"/tmp/a/y.kicad_pcb".to_string()));
        assert!(!p.iter().any(|s| s == "R1" || s == "GND"));
    }

    #[test]
    fn relative_and_kiprjmod_paths_resolve_against_the_call_and_urls_are_skipped() {
        let dir = std::env::temp_dir().join("konnect-paths").join("kicad");
        let parent = dir.join("root.kicad_sch");
        let p = collect_paths(&json!({
            "schematic": parent.to_string_lossy(),
            "sheet_file": "power.kicad_sch",
            "datasheet": "https://www.ti.com/lit/ds/symlink/tps7a16.pdf",
        }));
        assert!(
            p.contains(&dir.join("power.kicad_sch").to_string_lossy().into_owned()),
            "{p:?}"
        );
        assert!(!p.iter().any(|s| s.contains("://")), "{p:?}");

        let project = dir.join("soil.kicad_pro");
        let p = collect_paths(&json!({
            "project": project.to_string_lossy(),
            "library_path": "${KIPRJMOD}/lib/soil.kicad_sym",
        }));
        assert!(
            p.contains(
                &dir.join("lib/soil.kicad_sym")
                    .to_string_lossy()
                    .into_owned()
            ),
            "{p:?}"
        );

        // No absolute anchor: relative paths are passed through unchanged (and judged strictly).
        assert_eq!(
            collect_paths(&json!({ "sheet_file": "power.kicad_sch" })),
            vec!["power.kicad_sch"]
        );
    }

    #[test]
    fn refusals_are_plan_blocked() {
        let r = refusal("add_wire", vec!["no window".to_string()]);
        assert!(r.is_error);
        assert_eq!(
            crate::mcp::error::extract_error_kind(&r).as_deref(),
            Some("plan_blocked")
        );
    }

    #[tokio::test]
    async fn ungoverned_reads_proceed_without_a_ticket() {
        // No store above a temp path: auto/enforce both let a read through untouched.
        let args = json!({ "schematic": "/nonexistent-konnect-gov/x.kicad_sch" });
        match pre_call("list_schematic_wires", Some("sch_analysis"), &args).await {
            PreCall::Proceed(None) => {}
            _ => panic!("a read with no store must proceed without governance"),
        }
    }
}
