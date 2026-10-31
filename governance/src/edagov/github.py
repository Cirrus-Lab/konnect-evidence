"""Read-only GitHub synchronization (Dashboard Spec §6, Workflow Guide §11).

Records provider identity, repository, object number, URL, last observed
state, sync timestamp and correlation ID. Never assumes sync is complete:
failures are recorded with their failure state. Never writes to GitHub.

Data sources, in order: `gh api` (if installed and authenticated), then the
REST API with a token from GITHUB_TOKEN/GH_TOKEN (read from the environment,
never stored), or an offline JSON fixture (`--from-json`).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

from .gitinfo import lane, MERGE_TARGETS
from .util import correlation_id, now_iso

CLOSING = re.compile(r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+(?:([\w.-]+/[\w.-]+))?#(\d+)", re.I)
REVIEW_MAP = {"APPROVED": "approve", "CHANGES_REQUESTED": "request_changes", "COMMENTED": "comment",
              "DISMISSED": "stale_dismissed", "PENDING": "pending"}


class SyncError(RuntimeError):
    def __init__(self, state, msg):
        super().__init__(msg)
        self.state = state


def _api(path: str):
    if shutil.which("gh"):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return json.loads(r.stdout)
        err = (r.stderr or "").lower()
        if "404" in err:
            raise SyncError("empty" if "protection" in path else "unavailable", f"404 for {path}")
        if "401" in err or "403" in err or "auth" in err:
            raise SyncError("unauthorized", f"not authorized for {path}")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(f"https://api.github.com/{path.lstrip('/')}",
                                 headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        state = {401: "unauthorized", 403: "unauthorized", 404: "empty" if "protection" in path else "unavailable"}.get(e.code, "unavailable")
        raise SyncError(state, f"HTTP {e.code} for {path}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SyncError("timeout" if isinstance(e, TimeoutError) else "unavailable", str(e)) from None


def fetch(repo: str, number: int) -> dict:
    data = {"repo": repo}
    data["repository"] = _api(f"repos/{repo}")
    data["pull"] = _api(f"repos/{repo}/pulls/{number}")
    data["reviews"] = _api(f"repos/{repo}/pulls/{number}/reviews")
    sha = data["pull"]["head"]["sha"]
    try:
        data["check_runs"] = _api(f"repos/{repo}/commits/{sha}/check-runs").get("check_runs", [])
    except SyncError as e:
        data["check_runs_error"] = e.state
        data["check_runs"] = []
    base = data["pull"]["base"]["ref"]
    try:
        data["protection"] = _api(f"repos/{repo}/branches/{base}/protection")
    except SyncError as e:
        data["protection"] = None
        data["protection_error"] = e.state
    return data


def interpret(data: dict) -> dict:
    repo = data["repo"]
    pr = data["pull"]
    default_branch = data.get("repository", {}).get("default_branch") or data.get("default_branch") or "main"
    head_sha = pr["head"]["sha"]
    base, head = pr["base"]["ref"], pr["head"]["ref"]
    # Latest review per reviewer; a review on an older commit is stale for the current diff.
    latest = {}
    for r in data.get("reviews", []):
        latest[r["user"]["login"]] = r
    reviews = []
    for login, r in latest.items():
        state = REVIEW_MAP.get(r.get("state"), r.get("state", "").lower())
        stale = r.get("commit_id") not in (None, head_sha)
        reviews.append({"reviewer": login, "state": "stale_dismissed" if state == "approve" and stale else state,
                        "commit": r.get("commit_id"), "stale_for_current_diff": stale, "submitted_at": r.get("submitted_at")})
    prot = data.get("protection") or {}
    rpr = prot.get("required_pull_request_reviews") or {}
    required_approvals = rpr.get("required_approving_review_count")
    current_approvals = sum(1 for r in reviews if r["state"] == "approve" and not r["stale_for_current_diff"])
    required_checks = (prot.get("required_status_checks") or {}).get("contexts", [])
    checks = [{"name": c["name"], "status": c.get("status"), "conclusion": c.get("conclusion")} for c in data.get("check_runs", [])]
    by_name = {c["name"]: c for c in checks}
    blocking_checks = [n for n in required_checks if (by_name.get(n) or {}).get("conclusion") != "success"]
    body = pr.get("body") or ""
    issue_links = []
    for m in CLOSING.finditer(body):
        other_repo = m.group(3)
        auto_close = (base == default_branch) and (other_repo in (None, repo))
        issue_links.append({"issue": f"{other_repo or repo}#{m.group(4)}", "keyword": m.group(1),
                            "auto_close": auto_close,
                            "note": None if auto_close else f"PR targets '{base}', not default branch '{default_branch}': issue is linked, not auto-closed"})
    for m in re.finditer(r"(?<![\w/])#(\d+)", body):
        ref = f"{repo}#{m.group(1)}"
        if not any(l["issue"] == ref for l in issue_links):
            issue_links.append({"issue": ref, "keyword": None, "auto_close": False, "note": "mention only"})
    head_lane = lane(head)
    expected = MERGE_TARGETS.get(head_lane, [])
    lane_ok = (not expected) or any(base == t.split(" ")[0] for t in expected) or head_lane == "other"
    if required_approvals is None:
        approvals_state = "unknown (branch protection not readable: " + str(data.get("protection_error", "absent")) + ")"
    else:
        approvals_state = "satisfied" if current_approvals >= required_approvals else "not_satisfied"
    return {
        "provider": "github", "repository": repo, "number": pr["number"], "url": pr.get("html_url"),
        "title": pr.get("title"), "observed_state": "merged" if pr.get("merged") else pr.get("state"),
        "base": base, "head": head, "head_sha": head_sha, "default_branch": default_branch,
        "gitflow_lane": head_lane, "base_lane": lane(base), "intended_merge_targets": expected,
        "merge_target_matches_convention": lane_ok, "reviews": reviews,
        "required_approvals": required_approvals, "current_diff_approvals": current_approvals,
        "approvals_state": approvals_state,
        "codeowner_review_required": rpr.get("require_code_owner_reviews"),
        "dismiss_stale_reviews": rpr.get("dismiss_stale_reviews"),
        "required_checks": required_checks, "checks": checks, "blocking_checks": blocking_checks,
        "conversation_resolution_required": (prot.get("required_conversation_resolution") or {}).get("enabled"),
        "signed_commits_required": (prot.get("required_signatures") or {}).get("enabled"),
        "issue_links": issue_links,
        "protection_readable": data.get("protection") is not None,
        "partial": bool(data.get("check_runs_error") or data.get("protection_error")),
    }


def sync(store, repo: str, number: int, *, from_json: str | None = None) -> dict:
    store.check("record_evidence")
    corr = correlation_id()
    rid = f"GH-{repo.replace('/', '-').upper()}-PR{number}"
    try:
        data = json.load(open(from_json)) if from_json else fetch(repo, number)
        info = interpret(data)
        sync_state = "partial" if info["partial"] else "synced"
        err = None
    except SyncError as e:
        prev = store.get("github_pr", rid)
        info = dict(prev or {"provider": "github", "repository": repo, "number": number})
        sync_state, err = e.state, str(e)
    except (OSError, ValueError, KeyError) as e:
        prev = store.get("github_pr", rid)
        info = dict(prev or {"provider": "github", "repository": repo, "number": number})
        sync_state, err = "invalid", f"{type(e).__name__}: {e}"
    blocked = (sync_state not in ("synced", "partial") or info.get("blocking_checks")
               or info.get("approvals_state") == "not_satisfied")
    for k in ("id", "type", "record_version", "supersedes_version", "created_at", "updated_at"):
        info.pop(k, None)
    rec = {**info, "type": "github_pr", "id": rid, "sync_state": sync_state, "sync_error": err,
           "last_sync_attempt": now_iso(), "correlation_id": corr,
           "last_successful_sync": now_iso() if sync_state in ("synced", "partial") else info.get("last_successful_sync"),
           "state": "blocked" if blocked else "ready_for_review",
           "severity": "blocking" if blocked else "info", "timestamp": now_iso(),
           "source": "github (read-only)" + (" fixture" if from_json else ""), "owner": store.identity.get("design_authority"),
           "linked_evidence": [info.get("url")] if info.get("url") else [],
           "next_action": (f"Sync failed ({sync_state}): {err}" if err else
                           "Resolve blocking checks / approvals for the current diff." if blocked else "Proceed to merge per policy."),
           "provisional": sync_state != "synced"}
    return store.put(rec, reason=f"GitHub sync {repo}#{number}: {sync_state}")
