"""Review console: decisions go through governance.approve_window behind PIN, CSRF and ID confirmation."""
import pytest

pytest.importorskip("flask")

from edagov import governance  # noqa: E402
from edagov.review.app import MAX_PIN_FAILURES, create_app  # noqa: E402

PIN = "123456"


@pytest.fixture
def requested(design, as_actor):
    as_actor("designer@x")
    return governance.request_window(design, scope=["sch_wiring"], reason="add pull-up", files=["kicad/**"])


@pytest.fixture
def client(design):
    app = create_app([design.root], pin=PIN)
    c = app.test_client()
    c.csrf = app.config["CSRF"]
    return c


def _decide(client, wid, *, pin=PIN, confirm=None, decision="approved", note="", csrf=None):
    return client.post(f"/api/windows/0/{wid}/decision", headers={"X-CSRF-Token": client.csrf if csrf is None else csrf},
                       json={"pin": pin, "confirm_id": wid if confirm is None else confirm, "decision": decision, "note": note})


def test_state_shows_requested_window_and_gates(client, requested, as_actor):
    as_actor("reviewer@x")
    s = client.get("/api/state/0").get_json()
    assert s["viewer"] == {"actor": "reviewer@x", "verified": False, "roles": ["design_reviewer"], "can_decide": True}
    assert [w["id"] for w in s["windows"]] == [requested["id"]]
    assert s["windows"][0]["window_state_effective"] == "requested"
    assert {g["gate"] for g in s["gates"]} >= {"requirements", "schematic_library", "release"}
    assert s["ledger"]["verified"]


def test_reviewer_approves_with_pin_and_confirmation(client, design, requested, as_actor):
    as_actor("reviewer@x")
    r = _decide(client, requested["id"], note="looks fine")
    assert r.status_code == 200, r.get_json()
    w = r.get_json()["window"]
    assert w["window_state"] == "approved" and w["approved_by"] == "reviewer@x" and w["decision_note"] == "looks fine"


def test_requester_cannot_approve_through_the_console(client, requested, as_actor):
    as_actor("designer@x")
    r = _decide(client, requested["id"])
    assert r.status_code == 403


@pytest.mark.parametrize("kwargs, code", [
    ({"csrf": "forged"}, 403),
    ({"pin": "000000"}, 403),
    ({"confirm": "WIN-WRONG"}, 400),
    ({"decision": "maybe"}, 400),
    ({"decision": "rejected"}, 400),  # rejection needs a reason
])
def test_decision_guards(client, design, requested, as_actor, kwargs, code):
    as_actor("reviewer@x")
    assert _decide(client, requested["id"], **kwargs).status_code == code
    assert governance.windows(design)[0]["window_state"] == "requested"


def test_wrong_pins_lock_decisions(client, requested, as_actor):
    as_actor("reviewer@x")
    for _ in range(MAX_PIN_FAILURES):
        assert _decide(client, requested["id"], pin="999999").status_code == 403
    assert _decide(client, requested["id"]).status_code == 423


def test_reject_with_reason(client, design, requested, as_actor):
    as_actor("reviewer@x")
    r = _decide(client, requested["id"], decision="rejected", note="scope too wide")
    assert r.status_code == 200
    assert governance.windows(design)[0]["window_state_effective"] == "rejected"


def test_index_serves_page_with_strict_csp(client):
    r = client.get("/")
    assert r.status_code == 200 and b"review.js" in r.data
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
