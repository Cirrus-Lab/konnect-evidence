"""Hashing, IDs, time and canonical JSON helpers."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

from .vocab import ID_PREFIX

HASH_ALG = "sha256"


def now_iso() -> str:
    """UTC timestamp with seconds precision, ISO 8601 with Z suffix."""
    override = os.environ.get("EDAGOV_NOW")  # deterministic tests / reruns
    if override:
        return override
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None):
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        # Python < 3.11 rejects "+HHMM" offsets (KiCad report format); add the colon.
        v = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", v)
        d = _dt.datetime.fromisoformat(v)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d
    except ValueError:
        return None


def utf8_stdio() -> None:
    """Use UTF-8 and LF on this process's own stdio.

    Windows defaults pipes to the ANSI code page and CRLF, which corrupts non-ASCII JSON
    (MCP responses, ``--format kv`` output read by the Konnect bridge). Streams that were
    replaced (tests, embedding) are left alone.
    """
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or stream is not getattr(sys, f"__{name}__", None) or not hasattr(stream, "reconfigure"):
            continue
        try:
            if name == "stdin":
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace", newline="\n")
        except (ValueError, OSError):
            pass


def file_hash(path: str | Path, alg: str = HASH_ALG) -> str:
    h = hashlib.new(alg)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{alg}:{h.hexdigest()}"


def bytes_hash(data: bytes, alg: str = HASH_ALG) -> str:
    return f"{alg}:{hashlib.new(alg, data).hexdigest()}"


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def obj_hash(obj) -> str:
    return bytes_hash(canonical_json(obj))


def slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").upper()
    return s[:maxlen] or "X"


def new_id(entity_type: str, hint: str | None = None) -> str:
    """Stable, human-readable ID. With a hint the ID is deterministic."""
    prefix = ID_PREFIX.get(entity_type, entity_type[:3].upper())
    if hint:
        return f"{prefix}-{slug(hint)}"
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def new_event_id() -> str:
    return f"EVT-{uuid.uuid4().hex}"


def correlation_id() -> str:
    return os.environ.get("EDAGOV_CORRELATION_ID") or f"COR-{uuid.uuid4().hex[:16]}"


def plain_path(path: str | Path) -> Path:
    """Resolve a path and drop a Windows verbatim prefix (\\\\?\\C:\\..., \\\\?\\UNC\\...), which callers such
    as Rust's canonicalize emit; a verbatim path never compares equal to the plain spelling of the same file."""
    s = str(Path(path).resolve())
    if s.startswith("\\\\?\\UNC\\"):
        s = "\\\\" + s[8:]
    elif s.startswith("\\\\?\\"):
        s = s[4:]
    return Path(s)


def read_json(path: str | Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str | Path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)


def freshness(timestamp: str | None, max_age_days: float | None, now: str | None = None) -> str:
    """Classify evidence freshness. Freshness is independent of approval."""
    if not timestamp:
        return "missing"
    t = parse_iso(timestamp)
    if t is None:
        return "unknown"
    n = parse_iso(now or now_iso())
    if t > n + _dt.timedelta(minutes=5):
        return "future-dated"
    if max_age_days is None:
        return "current"
    return "stale" if (n - t).total_seconds() > max_age_days * 86400 else "current"
