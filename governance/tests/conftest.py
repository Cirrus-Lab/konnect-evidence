import os
import shutil
from pathlib import Path

import pytest

from edagov.store import Store

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "buck-demo"
FAKES = Path(__file__).resolve().parent / "fakes"

ROLES = {
    "designer@x": "contributor", "reviewer@x": "design_reviewer", "supply@x": "supply_reviewer",
    "fab@x": "manufacturing_reviewer", "release@x": "release_approver", "admin@x": "connector_admin",
    "viewer@x": "viewer", "release2@x": "release_approver",
}


@pytest.fixture
def as_actor(monkeypatch):
    def _as(actor):
        monkeypatch.setenv("EDAGOV_ACTOR", actor)
    return _as


@pytest.fixture
def design(tmp_path, monkeypatch, as_actor):
    """A copy of the demo design with an initialised store."""
    for d in ("kicad", "reports", "bom", "sim", "fab", "github"):
        shutil.copytree(DEMO / d, tmp_path / d)
    monkeypatch.delenv("EDAGOV_EXECUTION", raising=False)
    monkeypatch.setenv("KICAD_CLI", str(FAKES / "kicad-cli"))
    monkeypatch.setenv("NGSPICE", str(FAKES / "ngspice"))
    as_actor("designer@x")
    roles = {"actors": {}}
    for a, r in ROLES.items():
        roles["actors"].setdefault(a, []).append(r)
    st = Store.init(tmp_path, product_id="PRD-T", design_id="DES-T", board_id="PCB-T", revision="B",
                    design_authority="designer@x", roles=roles)
    return st
