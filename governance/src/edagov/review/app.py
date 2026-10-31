"""edagov review console.

A small Flask app, served on the loopback interface only, that shows a governed
design's change windows, gates and Konnect call ledger as a live visual workflow
and lets the reviewer who launched it approve or reject change windows.

Decisions go through ``governance.approve_window``, the same function behind
``edagov konnect window approve``, so segregation of duties, approver roles and
the audit trail are enforced exactly as on the command line. The console acts as
the identity it was started with (``--actor`` / ``EDAGOV_ACTOR``).

Each decision needs, besides the session's CSRF token, a PIN printed only in the
terminal that launched the console, and the window ID typed back. An automated
client on the same machine can reach the port, but not the launching terminal.
"""
from __future__ import annotations

import argparse
import hmac
import os
import secrets
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from .. import gates, governance, permissions
from ..store import Store

MAX_PIN_FAILURES = 5
LEDGER_LIMIT = 300


def _store(roots: list[Path], idx: int) -> Store:
    if not 0 <= idx < len(roots):
        abort(404)
    return Store(roots[idx])


def _state(st: Store) -> dict:
    actor, verified, roles = st.actor()
    pol = governance.gov_policy(st)
    ledger = governance.Ledger(st)
    ok, problems = ledger.verify()
    entries = ledger.entries()
    return {
        "identity": {k: st.identity.get(k) for k in ("product_id", "design_id", "board_id", "revision", "variant",
                                                     "release_state")},
        "root": str(st.root),
        "viewer": {"actor": actor, "verified": verified, "roles": roles,
                   "can_decide": any(r in pol["window_approver_roles"] for r in roles)},
        "policy": {"approver_roles": pol["window_approver_roles"],
                   "self_approval": pol["allow_self_approved_windows"]},
        "windows": sorted(governance.windows(st), key=lambda w: w.get("timestamp", ""), reverse=True),
        "gates": gates.evaluate_all(st, persist=False),
        "ledger": {"verified": ok, "problems": problems, "count": len(entries),
                   "entries": list(reversed(entries[-LEDGER_LIMIT:]))},
    }


def create_app(roots: list[Path], *, pin: str) -> Flask:
    app = Flask(__name__)
    app.config.update(ROOTS=[Path(r).resolve() for r in roots], PIN=pin, CSRF=secrets.token_urlsafe(32),
                      PIN_FAILURES=0)

    @app.after_request
    def _headers(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self' data:"
        return resp

    @app.get("/")
    def index():
        return render_template("index.html", csrf=app.config["CSRF"],
                               roots=[(i, r.name, str(r)) for i, r in enumerate(app.config["ROOTS"])])

    @app.get("/api/state/<int:idx>")
    def state(idx: int):
        return jsonify(_state(_store(app.config["ROOTS"], idx)))

    @app.post("/api/windows/<int:idx>/<wid>/decision")
    def decide(idx: int, wid: str):
        body = request.get_json(silent=True) or {}
        if not hmac.compare_digest(str(request.headers.get("X-CSRF-Token", "")), app.config["CSRF"]):
            return jsonify(error="Missing or invalid session token. Reload the page."), 403
        if app.config["PIN_FAILURES"] >= MAX_PIN_FAILURES:
            return jsonify(error="Decisions are locked after repeated wrong PINs. Restart the console."), 423
        if not hmac.compare_digest(str(body.get("pin", "")), app.config["PIN"]):
            app.config["PIN_FAILURES"] += 1
            left = MAX_PIN_FAILURES - app.config["PIN_FAILURES"]
            return jsonify(error=f"Wrong PIN. {left} attempt(s) left before decisions lock."), 403
        if body.get("confirm_id") != wid:
            return jsonify(error="Type the window ID exactly to confirm."), 400
        decision = body.get("decision")
        if decision not in ("approved", "rejected"):
            return jsonify(error="Decision must be 'approved' or 'rejected'."), 400
        note = str(body.get("note", "")).strip()
        if decision == "rejected" and not note:
            return jsonify(error="Say why the window is rejected."), 400
        st = _store(app.config["ROOTS"], idx)
        try:
            w = governance.approve_window(st, wid, decision=decision, note=note)
        except permissions.PermissionDenied as e:
            return jsonify(error=str(e)), 403
        except ValueError as e:
            return jsonify(error=str(e)), 409
        return jsonify(window=w)

    return app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="edagov-review",
                                 description="Local review console for edagov change windows, gates and the Konnect ledger.")
    ap.add_argument("--root", action="append", required=True,
                    help="design repository root holding .edagov/ (repeat for several designs)")
    ap.add_argument("--actor", help="identity to review and decide as (default: EDAGOV_ACTOR or git user.email)")
    ap.add_argument("--port", type=int, default=5077)
    a = ap.parse_args(argv)
    if a.actor:
        os.environ["EDAGOV_ACTOR"] = a.actor
    roots = [Path(r).resolve() for r in a.root]
    for r in roots:
        if not (r / ".edagov").is_dir():
            ap.error(f"{r} has no .edagov evidence store")
    actor, _, _ = Store(roots[0]).actor()
    pin = f"{secrets.randbelow(10**6):06d}"
    print(f"edagov review console  http://127.0.0.1:{a.port}/", flush=True)
    print(f"  deciding as: {actor}", flush=True)
    print(f"  decision PIN: {pin}   (shown only here; do not paste it into an AI session)", flush=True)
    create_app(roots, pin=pin).run(host="127.0.0.1", port=a.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
