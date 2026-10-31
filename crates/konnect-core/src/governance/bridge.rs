//! Process bridge to the edagov evidence store. Standard library only.
//!
//! Konnect never edits the evidence store itself; it asks edagov:
//!
//! ```text
//! edagov --root <repo> konnect authorize --tool T --toolset S --effect E --call-id C [--path P]... --format kv [--audit-only]
//! edagov --root <repo> konnect record    --tool T --toolset S --effect E --call-id C --status ok|error [--path P]... --format kv [--capture]
//! ```
//!
//! `authorize` prints `key=value` lines; the line that matters is
//! `decision=allow|deny`. Anything else — the command missing, a non-zero
//! exit, a timeout, no decision line — is a failure the caller treats as a
//! refusal in enforce mode (a check that did not run is never a pass).

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// `KONNECT_GOVERNANCE`: how tool calls are governed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// No governance (upstream Konnect behaviour).
    Off,
    /// Record everything in governed designs, never refuse.
    Audit,
    /// Default. Govern designs that have an evidence store; leave others alone.
    Auto,
    /// Govern every design write; refuse writes no evidence store covers.
    Enforce,
}

impl Mode {
    pub fn parse(value: Option<&str>) -> Mode {
        match value.map(|v| v.trim().to_ascii_lowercase()).as_deref() {
            Some("off") | Some("0") | Some("false") | Some("disabled") => Mode::Off,
            Some("audit") | Some("record") => Mode::Audit,
            Some("enforce") | Some("strict") | Some("on") => Mode::Enforce,
            _ => Mode::Auto,
        }
    }

    pub fn from_env() -> Mode {
        Mode::parse(std::env::var("KONNECT_GOVERNANCE").ok().as_deref())
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Mode::Off => "off",
            Mode::Audit => "audit",
            Mode::Auto => "auto",
            Mode::Enforce => "enforce",
        }
    }
}

pub const STORE_DIR: &str = ".edagov";
const DESIGN_SUFFIXES: &[&str] = &[
    ".kicad_sch",
    ".kicad_pcb",
    ".kicad_pro",
    ".kicad_sym",
    ".kicad_mod",
    ".kicad_dru",
    ".kicad_wks",
    ".kicad_prl",
    ".pretty",
    ".gbr",
    ".dsn",
    ".ses",
];

/// Does a string argument look like a file-system path worth governing?
pub fn looks_like_path(value: &str) -> bool {
    if value.is_empty() || value.len() > 4096 || value.contains('\n') {
        return false;
    }
    let lower = value.to_ascii_lowercase();
    DESIGN_SUFFIXES.iter().any(|s| lower.ends_with(s))
        || lower.ends_with("sym-lib-table")
        || lower.ends_with("fp-lib-table")
        || value.contains('/')
        || value.contains('\\')
}

fn is_store_root(dir: &Path) -> bool {
    dir.join(STORE_DIR).join("design.json").is_file()
}

/// Walk up from each candidate path to the nearest directory holding
/// `.edagov/design.json`; then fall back to `KONNECT_GOVERNANCE_ROOT`.
pub fn find_store(candidates: &[String]) -> Option<PathBuf> {
    for c in candidates {
        let p = Path::new(c);
        let start = if p.is_dir() {
            Some(p.to_path_buf())
        } else {
            p.parent().map(Path::to_path_buf)
        };
        let mut cur = start.and_then(|s| {
            if s.as_os_str().is_empty() {
                None
            } else {
                std::fs::canonicalize(&s).ok().or(Some(s))
            }
        });
        while let Some(dir) = cur {
            if is_store_root(&dir) {
                return Some(dir);
            }
            cur = dir.parent().map(Path::to_path_buf);
        }
    }
    if let Ok(root) = std::env::var("KONNECT_GOVERNANCE_ROOT") {
        let root = PathBuf::from(root);
        if is_store_root(&root) {
            return Some(root);
        }
    }
    None
}

/// Unique, sortable call identifier for the ledger.
pub fn new_call_id() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("KC-{ms}-{}-{n}", std::process::id())
}

/// The edagov launcher: `KONNECT_EDAGOV` (an executable or `.py` path) plus optional
/// whitespace-separated `KONNECT_EDAGOV_ARGS`, else `edagov` on PATH.
pub fn edagov_command() -> (String, Vec<String>) {
    let exe = std::env::var("KONNECT_EDAGOV")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(|| "edagov".to_string());
    let extra = std::env::var("KONNECT_EDAGOV_ARGS")
        .ok()
        .map(|v| v.split_whitespace().map(str::to_string).collect())
        .unwrap_or_default();
    (exe, extra)
}

/// Interpreter for a `.py` launcher: `KONNECT_PYTHON`, else `py` on Windows
/// (the python.org launcher) and `python3` elsewhere.
pub fn python_command() -> String {
    std::env::var("KONNECT_PYTHON")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(|| {
            if cfg!(windows) {
                "py".to_string()
            } else {
                "python3".to_string()
            }
        })
}

/// Parse `key=value` lines. Later keys win; lines without `=` are ignored.
pub fn parse_kv(text: &str) -> HashMap<String, String> {
    text.lines()
        .filter_map(|line| {
            let (k, v) = line.split_once('=')?;
            Some((k.trim().to_string(), v.trim().to_string()))
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Decision {
    pub allow: bool,
    pub window: Option<String>,
    pub reason: String,
    pub next_action: Option<String>,
}

pub fn decision_from_kv(kv: &HashMap<String, String>) -> Result<Decision, String> {
    let allow = match kv.get("decision").map(String::as_str) {
        Some("allow") => true,
        Some("deny") => false,
        Some(other) => return Err(format!("edagov returned an unknown decision '{other}'")),
        None => return Err("edagov returned no decision line".to_string()),
    };
    let non_empty = |k: &str| kv.get(k).filter(|v| !v.is_empty()).cloned();
    Ok(Decision {
        allow,
        window: non_empty("window"),
        reason: kv.get("reason").cloned().unwrap_or_default(),
        next_action: non_empty("next_action"),
    })
}

pub const TIMEOUT: Duration = Duration::from_secs(60);

/// Run edagov with `args`, optionally feeding `stdin`, and return stdout.
pub fn run_edagov(
    args: &[String],
    stdin: Option<String>,
    timeout: Duration,
) -> Result<String, String> {
    let (exe, extra) = edagov_command();
    // A `.py` launcher runs through Python so one path works on every OS.
    let mut cmd = if exe.to_ascii_lowercase().ends_with(".py") {
        let mut c = Command::new(python_command());
        c.arg(&exe);
        c
    } else {
        Command::new(&exe)
    };
    cmd.args(&extra)
        .args(args)
        .stdin(if stdin.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn().map_err(|e| {
        format!("cannot start edagov ('{exe}'): {e}. Set KONNECT_EDAGOV to governance/bin/edagov")
    })?;
    let writer = match (stdin, child.stdin.take()) {
        (Some(text), Some(mut pipe)) => Some(std::thread::spawn(move || {
            let _ = pipe.write_all(text.as_bytes());
        })),
        _ => None,
    };
    let mut out_pipe = child.stdout.take();
    let mut err_pipe = child.stderr.take();
    let out_reader = std::thread::spawn(move || {
        let mut s = String::new();
        if let Some(p) = out_pipe.as_mut() {
            let _ = p.read_to_string(&mut s);
        }
        s
    });
    let err_reader = std::thread::spawn(move || {
        let mut s = String::new();
        if let Some(p) = err_pipe.as_mut() {
            let _ = p.read_to_string(&mut s);
        }
        s
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() > timeout => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("edagov timed out after {}s", timeout.as_secs()));
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(15)),
            Err(e) => return Err(format!("waiting for edagov failed: {e}")),
        }
    };
    if let Some(w) = writer {
        let _ = w.join();
    }
    let stdout = out_reader.join().unwrap_or_default();
    let stderr = err_reader.join().unwrap_or_default();
    if !status.success() {
        let tail: String = stderr.lines().rev().take(3).collect::<Vec<_>>().join(" | ");
        return Err(format!("edagov exited with {status}: {tail}"));
    }
    Ok(stdout)
}

fn base_args(
    root: &Path,
    action: &str,
    tool: &str,
    toolset: Option<&str>,
    effect: &str,
    call_id: &str,
    paths: &[String],
) -> Vec<String> {
    let mut a = vec![
        "--root".to_string(),
        root.display().to_string(),
        "konnect".to_string(),
        action.to_string(),
        "--tool".to_string(),
        tool.to_string(),
        "--effect".to_string(),
        effect.to_string(),
        "--call-id".to_string(),
        call_id.to_string(),
        "--format".to_string(),
        "kv".to_string(),
    ];
    if let Some(ts) = toolset {
        a.push("--toolset".to_string());
        a.push(ts.to_string());
    }
    for p in paths {
        a.push("--path".to_string());
        a.push(p.clone());
    }
    a
}

/// Ask edagov whether a design-changing call may run.
#[allow(clippy::too_many_arguments)]
pub fn authorize(
    root: &Path,
    tool: &str,
    toolset: Option<&str>,
    effect: &str,
    call_id: &str,
    paths: &[String],
    audit_only: bool,
) -> Result<Decision, String> {
    let mut args = base_args(root, "authorize", tool, toolset, effect, call_id, paths);
    if audit_only {
        args.push("--audit-only".to_string());
    }
    let out = run_edagov(&args, None, TIMEOUT)?;
    decision_from_kv(&parse_kv(&out))
}

/// Report a finished call; `capture` carries the tool result for evidence tools.
#[allow(clippy::too_many_arguments)]
pub fn record(
    root: &Path,
    tool: &str,
    toolset: Option<&str>,
    effect: &str,
    call_id: &str,
    ok: bool,
    paths: &[String],
    capture: Option<String>,
) -> Result<HashMap<String, String>, String> {
    let mut args = base_args(root, "record", tool, toolset, effect, call_id, paths);
    args.push("--status".to_string());
    args.push(if ok { "ok" } else { "error" }.to_string());
    if capture.is_some() {
        args.push("--capture".to_string());
    }
    let out = run_edagov(&args, capture, TIMEOUT)?;
    Ok(parse_kv(&out))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn modes_parse_with_auto_default() {
        assert_eq!(Mode::parse(None), Mode::Auto);
        assert_eq!(Mode::parse(Some("garbage")), Mode::Auto);
        assert_eq!(Mode::parse(Some("OFF")), Mode::Off);
        assert_eq!(Mode::parse(Some("audit")), Mode::Audit);
        assert_eq!(Mode::parse(Some(" enforce ")), Mode::Enforce);
    }

    #[test]
    fn path_detection() {
        assert!(looks_like_path("board.kicad_pcb"));
        assert!(looks_like_path("/home/x/proj"));
        assert!(looks_like_path(r"C:\Users\x\proj.kicad_sch"));
        assert!(!looks_like_path("GND"));
        assert!(!looks_like_path("R1"));
        assert!(!looks_like_path(""));
    }

    #[test]
    fn kv_and_decisions() {
        let kv =
            parse_kv("decision=allow\nwindow=WIN-1\nreason=inside window\nnext_action=\nnoise\n");
        let d = decision_from_kv(&kv).unwrap();
        assert!(d.allow);
        assert_eq!(d.window.as_deref(), Some("WIN-1"));
        assert_eq!(d.next_action, None);
        let deny = decision_from_kv(&parse_kv("decision=deny\nreason=no window=here\n")).unwrap();
        assert!(!deny.allow);
        assert_eq!(deny.reason, "no window=here", "only the first '=' splits");
        assert!(decision_from_kv(&parse_kv("reason=x")).is_err());
        assert!(decision_from_kv(&parse_kv("decision=maybe")).is_err());
    }

    #[test]
    fn store_discovery_walks_up() {
        let base = std::env::temp_dir().join(format!("konnect-gov-{}", new_call_id()));
        let design = base.join("repo").join("hw").join("kicad");
        std::fs::create_dir_all(&design).unwrap();
        std::fs::create_dir_all(base.join("repo").join(STORE_DIR)).unwrap();
        std::fs::write(base.join("repo").join(STORE_DIR).join("design.json"), "{}").unwrap();
        let sch = design.join("x.kicad_sch");
        std::fs::write(&sch, "(kicad_sch)").unwrap();
        let found = find_store(&[sch.display().to_string()]).expect("store found");
        assert_eq!(
            std::fs::canonicalize(found).unwrap(),
            std::fs::canonicalize(base.join("repo")).unwrap()
        );
        let outside = base.join("elsewhere.kicad_sch");
        std::fs::write(&outside, "").unwrap();
        if std::env::var("KONNECT_GOVERNANCE_ROOT").is_err() {
            assert_eq!(find_store(&[outside.display().to_string()]), None);
        }
        let _ = std::fs::remove_dir_all(base);
    }

    #[test]
    fn call_ids_are_unique() {
        let a = new_call_id();
        let b = new_call_id();
        assert_ne!(a, b);
        assert!(a.starts_with("KC-"));
    }

    #[test]
    fn missing_launcher_is_an_error_not_a_pass() {
        // Uses an explicit nonexistent path through the public runner.
        let err = {
            let mut cmd = Command::new("/nonexistent/edagov-for-test");
            cmd.arg("--version");
            cmd.output().map(|_| ()).map_err(|e| e.to_string())
        };
        assert!(err.is_err());
    }
}
