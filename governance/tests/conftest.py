import os
import shutil
import sys
from pathlib import Path

import pytest

from edagov.store import Store

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "buck-demo"
FAKES = Path(__file__).resolve().parent / "fakes"
WINDOWS = os.name == "nt"


def fake_tool(name: str, bin_dir: Path) -> str:
    """Path to a fake tool. The fakes are Python scripts with a shebang, which Windows
    cannot execute directly, so there they are wrapped in a .cmd shim."""
    script = FAKES / name
    if not WINDOWS:
        return str(script)
    shim = bin_dir / f"{name}.cmd"
    shim.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    return str(shim)


def launcher(name: str) -> list[str]:
    """Command for a bundled launcher (edagov, edagov-mcp): the POSIX shell script,
    or the cross-platform .py launcher on Windows (what the Konnect bridge uses there)."""
    if WINDOWS:
        return [sys.executable, str(ROOT / "bin" / f"{name}.py")]
    return [str(ROOT / "bin" / name)]


def child_env(**extra: str) -> dict:
    """Minimal environment for launcher subprocesses: no inherited EDAGOV_* or Python I/O settings."""
    if WINDOWS:
        keep = ("SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
                "USERPROFILE", "LOCALAPPDATA", "APPDATA")
        env = {k: os.environ[k] for k in keep if k in os.environ}
    else:
        env = {"PATH": "/usr/bin:/bin"}
    env.update(extra)
    return env

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
def design(tmp_path, tmp_path_factory, monkeypatch, as_actor):
    """A copy of the demo design with an initialised store."""
    for d in ("kicad", "reports", "bom", "sim", "fab", "github"):
        shutil.copytree(DEMO / d, tmp_path / d)
    monkeypatch.delenv("EDAGOV_EXECUTION", raising=False)
    fakebin = tmp_path_factory.mktemp("fakebin")
    monkeypatch.setenv("KICAD_CLI", fake_tool("kicad-cli", fakebin))
    monkeypatch.setenv("NGSPICE", fake_tool("ngspice", fakebin))
    as_actor("designer@x")
    roles = {"actors": {}}
    for a, r in ROLES.items():
        roles["actors"].setdefault(a, []).append(r)
    st = Store.init(tmp_path, product_id="PRD-T", design_id="DES-T", board_id="PCB-T", revision="B",
                    design_authority="designer@x", roles=roles)
    return st
