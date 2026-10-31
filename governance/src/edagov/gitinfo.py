"""Source-revision context from git (read-only)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(root, *args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def info(root: str | Path = ".") -> dict:
    commit = _git(root, "rev-parse", "HEAD")
    if not commit:
        return {"vcs": "none", "commit": None, "branch": None, "dirty": None, "tag": None, "remote": None}
    status = _git(root, "status", "--porcelain") or ""
    return {
        "vcs": "git",
        "commit": commit,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status.strip()),
        "tag": _git(root, "describe", "--tags", "--exact-match"),
        "remote": _redact_url(_git(root, "config", "--get", "remote.origin.url")),
    }


def _redact_url(url: str | None) -> str | None:
    """Strip credentials embedded in remote URLs (https://user:token@host/...)."""
    if not url:
        return url
    return re.sub(r"//[^/@]+@", "//", url)


def source_revision(root: str | Path = ".") -> str:
    gi = info(root)
    if gi["commit"]:
        return gi["commit"] + ("+dirty" if gi["dirty"] else "")
    return "untracked"


GITFLOW = [
    (re.compile(r"^(main|master)$"), "production"),
    (re.compile(r"^develop(ment)?$"), "integration"),
    (re.compile(r"^feature/"), "feature"),
    (re.compile(r"^release/"), "release"),
    (re.compile(r"^hotfix/"), "hotfix"),
]

# Conventional merge targets (Workflow Guide §11).
MERGE_TARGETS = {
    "feature": ["develop"],
    "release": ["main", "develop"],
    "hotfix": ["main", "develop"],
    "integration": ["main (via release/*)"],
    "production": [],
    "other": ["undeclared — document intent"],
}


def lane(branch: str | None) -> str:
    if not branch:
        return "other"
    for rx, name in GITFLOW:
        if rx.search(branch):
            return name
    return "other"
