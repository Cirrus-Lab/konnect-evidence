"""Append-only, hash-chained audit log (Dashboard Spec §9).

Each event carries the hash of the previous event, so any rewrite or deletion
breaks the chain and `verify()` reports where. Corrections are new events;
nothing here edits or deletes past events.
"""
from __future__ import annotations

import json
from pathlib import Path

from .util import new_event_id, now_iso, obj_hash, correlation_id

GENESIS = "sha256:" + "0" * 64

EVENT_FIELDS = (
    "event_id", "timestamp", "actor", "actor_verified", "action", "object_type", "object_id",
    "revision", "before", "after", "reason", "source", "correlation_id", "idempotency_key",
    "authorization", "result", "retention", "prev_hash",
)


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        last = GENESIS
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last = json.loads(line)["hash"]
        return last

    def events(self) -> list[dict]:
        out = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out

    def find_idempotent(self, key: str) -> dict | None:
        for ev in self.events():
            if ev.get("idempotency_key") == key and ev.get("result") == "success":
                return ev
        return None

    def append(self, *, actor: str, actor_verified: bool, action: str, object_type: str, object_id: str,
               revision: str | None = None, before=None, after=None, reason: str = "", source: str = "edagov",
               authorization: str = "allowed", result: str = "success", retention: str = "engineering-record",
               idempotency_key: str | None = None, corr: str | None = None) -> dict:
        event = {
            "event_id": new_event_id(),
            "timestamp": now_iso(),
            "actor": actor,
            "actor_verified": actor_verified,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "revision": revision,
            # Store hashes of states, not raw payloads: keeps secrets out of the log
            # and still lets reviewers prove what changed.
            "before": obj_hash(before) if before is not None else None,
            "after": obj_hash(after) if after is not None else None,
            "reason": reason,
            "source": source,
            "correlation_id": corr or correlation_id(),
            "idempotency_key": idempotency_key,
            "authorization": authorization,
            "result": result,
            "retention": retention,
            "prev_hash": self._last_hash(),
        }
        event["hash"] = obj_hash(event)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        return event

    def verify(self) -> tuple[bool, list[str]]:
        problems = []
        prev = GENESIS
        for i, ev in enumerate(self.events(), start=1):
            claimed = ev.get("hash")
            body = {k: v for k, v in ev.items() if k != "hash"}
            if ev.get("prev_hash") != prev:
                problems.append(f"event {i} ({ev.get('event_id')}): prev_hash does not match previous event")
            if obj_hash(body) != claimed:
                problems.append(f"event {i} ({ev.get('event_id')}): content hash mismatch (event altered)")
            prev = claimed
        return (not problems), problems
