"""Authorized, reproducibility-capturing tool execution (Skill Spec §3 step 8).

Nothing runs unless the caller passes an explicit authorization (a reason
string). Every run captures: exact command, working directory, tool version,
platform, locale/timezone, input hashes, exit code, stdout/stderr logs,
output hashes and an unsigned SLSA-v1-shaped provenance statement.

The reproducibility level promised by default is "exact_rerun" (same inputs,
same tool build, same command); bit-for-bit output is never claimed because
KiCad embeds timestamps in several outputs.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from .util import file_hash, now_iso, write_json

SAFE_ENV_KEYS = ("LANG", "LC_ALL", "LC_NUMERIC", "TZ", "KICAD_CONFIG_HOME")


class NotAuthorized(PermissionError):
    pass


class ToolMissing(FileNotFoundError):
    pass


def require_authorization(authorize: str | None, what: str) -> str:
    """Execution needs an explicit reason, or EDAGOV_EXECUTION=allow in CI."""
    if authorize:
        return authorize
    env = os.environ.get("EDAGOV_EXECUTION")
    if env and env.startswith("allow"):
        return f"environment EDAGOV_EXECUTION={env}"
    raise NotAuthorized(
        f"execution of {what} is not authorized. Re-run with --authorize \"<reason>\" "
        "(or set EDAGOV_EXECUTION=allow in CI). Documentation-only mode can ingest existing reports instead."
    )


def which(candidates: list[str]) -> str | None:
    for c in candidates:
        if not c:
            continue
        if os.path.sep in c and Path(c).exists():
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def run(cmd: list[str], *, cwd: Path, run_dir: Path, timeout: int = 900, inputs: list[Path] | None = None) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("TZ", "UTC")
    env.setdefault("LC_ALL", env.get("LC_ALL", "C.UTF-8"))
    started = now_iso()
    t0 = time.monotonic()
    out_log, err_log = run_dir / "stdout.log", run_dir / "stderr.log"
    status = "completed"
    try:
        with open(out_log, "wb") as so, open(err_log, "wb") as se:
            proc = subprocess.run(cmd, cwd=str(cwd), stdout=so, stderr=se, timeout=timeout, env=env)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code, status = None, "timeout"
    except FileNotFoundError as e:
        code, status = None, "tool_missing"
        err_log.write_text(str(e))
    duration = round(time.monotonic() - t0, 3)
    return {
        "command": cmd,
        "cwd": str(cwd),
        "started_at": started,
        "finished_at": now_iso(),
        "duration_s": duration,
        "exit_code": code,
        "status": status,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(),
                     "python": platform.python_version()},
        "env": {k: env.get(k) for k in SAFE_ENV_KEYS if env.get(k) is not None},
        "inputs": [{"path": str(p), "hash": file_hash(p)} for p in (inputs or []) if Path(p).exists()],
        "logs": {"stdout": str(out_log), "stderr": str(err_log),
                 "stdout_hash": file_hash(out_log) if out_log.exists() else None,
                 "stderr_hash": file_hash(err_log) if err_log.exists() else None},
    }


def provenance(run_id: str, tool: str, tool_version: str | None, exec_rec: dict, outputs: list[Path],
               builder_id: str, run_dir: Path) -> Path:
    """Write an unsigned in-toto Statement with a SLSA v1 provenance predicate."""
    def digest(h):
        alg, _, hexd = h.partition(":")
        return {alg: hexd}

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": str(p), "digest": digest(file_hash(p))} for p in outputs if Path(p).is_file()],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "urn:edagov:buildtype:tool-run:v1",
                "externalParameters": {"command": exec_rec["command"], "cwd": exec_rec["cwd"], "tool": tool},
                "internalParameters": {"env": exec_rec["env"], "platform": exec_rec["platform"]},
                "resolvedDependencies": (
                    [{"uri": f"tool:{tool}", "annotations": {"version": tool_version}}]
                    + [{"uri": i["path"], "digest": digest(i["hash"])} for i in exec_rec["inputs"]]
                ),
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {"invocationId": run_id, "startedOn": exec_rec["started_at"],
                             "finishedOn": exec_rec["finished_at"]},
                "byproducts": [{"name": "stdout.log", "digest": digest(exec_rec["logs"]["stdout_hash"])}]
                if exec_rec["logs"].get("stdout_hash") else [],
            },
        },
        "_edagov_caveat": "Unsigned statement generated locally. It records what ran; it is not a SLSA build-level claim.",
    }
    path = run_dir / "provenance.intoto.json"
    write_json(path, statement)
    return path
