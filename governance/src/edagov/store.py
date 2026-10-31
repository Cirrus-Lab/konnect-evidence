"""Evidence store: a versioned, audited record set kept beside the design.

Layout (inside the design repository):

    .edagov/
      design.json            design identity (product/board/assembly/revision/variant)
      policy.json            gate rules, freshness windows, required outputs
      roles.json             actor -> roles (deny by default)
      audit.jsonl            hash-chained append-only audit log
      records/<type>/<ID>.v0001.json   immutable record versions (latest wins)
      runs/<RUN-ID>/         logs, reports, outputs, provenance for each run
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import permissions, schema
from .audit import AuditLog
from .policy import DEFAULT_POLICY
from .util import now_iso, obj_hash, read_json, write_json, new_id

STORE_DIR = ".edagov"


class StoreError(RuntimeError):
    pass


class Store:
    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self.dir = self.root / STORE_DIR
        if not (self.dir / "design.json").exists():
            raise StoreError(f"no evidence store at {self.dir}; run `edagov init` first")
        self.audit = AuditLog(self.dir / "audit.jsonl")

    # ------------------------------------------------------------------ init
    @classmethod
    def init(cls, root, *, product_id, design_id, board_id, revision, variant="default",
             assembly_id=None, release_state="in_development", design_authority="unassigned",
             repository=None, standards=None, owner="unassigned", lifecycle="development",
             roles=None) -> "Store":
        root = Path(root).resolve()
        d = root / STORE_DIR
        if (d / "design.json").exists():
            raise StoreError(f"store already initialised at {d}")
        d.mkdir(parents=True, exist_ok=True)
        identity = {
            "product_id": product_id,
            "design_id": design_id,
            "board_id": board_id,
            "assembly_id": assembly_id or f"{board_id}-ASM",
            "revision": revision,
            "variant": variant,
            "release_state": release_state,
            "design_authority": design_authority,
            "repository": repository,
            "applicable_standards": standards or [],
            "owner": owner,
            "lifecycle": lifecycle,
            "created_at": now_iso(),
            "execution_mode": "documentation_only",  # flipped per-run only when a run is authorized and executed
        }
        write_json(d / "design.json", identity)
        write_json(d / "policy.json", DEFAULT_POLICY)
        write_json(d / "roles.json", roles or {"actors": {}})
        (d / "records").mkdir(exist_ok=True)
        (d / "runs").mkdir(exist_ok=True)
        st = cls(root)
        actor, verified = permissions.current_actor()
        st.audit.append(actor=actor, actor_verified=verified, action="store.init", object_type="design",
                        object_id=design_id, revision=revision, after=identity, reason="initialise evidence store")
        # Design and product records so they are traceable like everything else.
        st.put({"type": "product", "id": new_id("product", product_id), "product_id": product_id,
                "revision": revision, "owner": owner, "lifecycle": lifecycle,
                "applicable_standards": standards or []}, action="record_evidence", enforce=False)
        st.put({"type": "design", "id": new_id("design", design_id), **{k: identity[k] for k in (
            "design_id", "board_id", "assembly_id", "revision", "variant", "release_state", "design_authority", "repository")}},
            action="record_evidence", enforce=False)
        return st

    # ------------------------------------------------------------- identity
    @property
    def identity(self) -> dict:
        return read_json(self.dir / "design.json")

    @property
    def policy(self) -> dict:
        p = self.dir / "policy.json"
        return read_json(p) if p.exists() else copy.deepcopy(DEFAULT_POLICY)

    @property
    def roles_doc(self) -> dict:
        p = self.dir / "roles.json"
        return read_json(p) if p.exists() else {"actors": {}}

    def actor(self) -> tuple[str, bool, list[str]]:
        actor, verified = permissions.current_actor()
        return actor, verified, permissions.roles_for(actor, self.roles_doc)

    def check(self, action: str) -> tuple[str, bool, list[str]]:
        actor, verified, roles = self.actor()
        try:
            permissions.require(action, actor, roles)
        except permissions.PermissionDenied as e:
            self.audit.append(actor=actor, actor_verified=verified, action=f"denied:{action}", object_type="permission",
                              object_id=action, reason=str(e), authorization="denied", result="denied")
            raise
        return actor, verified, roles

    def set_revision(self, revision: str, variant: str | None = None, reason: str = "") -> dict:
        actor, verified, _ = self.check("record_evidence")
        before = self.identity
        after = dict(before, revision=revision, variant=variant or before["variant"])
        write_json(self.dir / "design.json", after)
        self.audit.append(actor=actor, actor_verified=verified, action="design.set_revision", object_type="design",
                          object_id=before["design_id"], revision=revision, before=before, after=after, reason=reason)
        return after

    # -------------------------------------------------------------- records
    def _rdir(self, rtype: str) -> Path:
        return self.dir / "records" / rtype

    def _versions(self, rtype: str, rid: str) -> list[Path]:
        return sorted(self._rdir(rtype).glob(f"{rid}.v*.json"))

    def get(self, rtype: str, rid: str, version: int | None = None) -> dict | None:
        vs = self._versions(rtype, rid)
        if not vs:
            return None
        if version is None:
            return read_json(vs[-1])
        for p in vs:
            if p.name.endswith(f".v{version:04d}.json"):
                return read_json(p)
        return None

    def history(self, rtype: str, rid: str) -> list[dict]:
        return [read_json(p) for p in self._versions(rtype, rid)]

    def list(self, rtype: str, *, include_superseded: bool = True, revision: str | None = None) -> list[dict]:
        d = self._rdir(rtype)
        if not d.exists():
            return []
        latest: dict[str, Path] = {}
        for p in sorted(d.glob("*.v*.json")):
            rid = p.name.rsplit(".v", 1)[0]
            latest[rid] = p
        out = [read_json(p) for p in latest.values()]
        if not include_superseded:
            out = [r for r in out if r.get("state") != "superseded" and r.get("status") != "superseded"]
        if revision:
            out = [r for r in out if r.get("revision") == revision]
        return sorted(out, key=lambda r: r["id"])

    def all_records(self) -> dict[str, list[dict]]:
        base = self.dir / "records"
        return {d.name: self.list(d.name) for d in sorted(base.iterdir()) if d.is_dir()} if base.exists() else {}

    def put(self, record: dict, *, action: str = "record_evidence", reason: str = "", enforce: bool = True,
            idempotency_key: str | None = None) -> dict:
        """Validate and store a new immutable version of a record."""
        if enforce:
            actor, verified, _ = self.check(action)
        else:
            actor, verified = permissions.current_actor()
        rec = copy.deepcopy(record)
        ident = self.identity
        rec.setdefault("created_at", now_iso())
        rec["updated_at"] = now_iso()
        if rec.get("type") in schema.DESIGN_SCOPED:
            rec.setdefault("design_id", ident["design_id"])
            rec.setdefault("revision", ident["revision"])
            rec.setdefault("variant", ident["variant"])
        rec.setdefault("id", new_id(rec.get("type", "artifact")))
        schema.require_valid(rec)
        if idempotency_key:
            prior = self.audit.find_idempotent(idempotency_key)
            if prior:
                existing = self.get(rec["type"], rec["id"])
                if existing is not None:
                    return existing
        prev = self.get(rec["type"], rec["id"])
        n = len(self._versions(rec["type"], rec["id"])) + 1
        rec["record_version"] = n
        rec["supersedes_version"] = n - 1 if n > 1 else None
        if prev is not None:
            rec["created_at"] = prev.get("created_at", rec["created_at"])
        write_json(self._rdir(rec["type"]) / f"{rec['id']}.v{n:04d}.json", rec)
        self.audit.append(actor=actor, actor_verified=verified, action=f"{rec['type']}.put", object_type=rec["type"],
                          object_id=rec["id"], revision=rec.get("revision"), before=prev, after=rec,
                          reason=reason, idempotency_key=idempotency_key)
        return rec

    def supersede(self, rtype: str, rid: str, by: str, reason: str) -> dict:
        rec = self.get(rtype, rid)
        if rec is None:
            raise StoreError(f"{rtype}/{rid} not found")
        rec = dict(rec)
        rec["superseded_by"] = by
        if "state" in rec:
            rec["state"] = "superseded"
        if "status" in rec:
            rec["status"] = "superseded"
        rec["superseded"] = True
        return self.put(rec, reason=f"superseded by {by}: {reason}")

    # ---------------------------------------------------------------- runs
    def run_dir(self, run_id: str) -> Path:
        p = self.dir / "runs" / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def fingerprint(self) -> str:
        """Hash of the current state of every record (for snapshots/diffs)."""
        return obj_hash({k: [(r["id"], r.get("record_version")) for r in v] for k, v in self.all_records().items()})

    def dump(self) -> dict:
        return {"identity": self.identity, "policy": self.policy, "records": self.all_records(),
                "generated_at": now_iso(), "fingerprint": self.fingerprint()}


def load_or_none(root=".") -> Store | None:
    try:
        return Store(root)
    except StoreError:
        return None


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
