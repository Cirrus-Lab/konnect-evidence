"""Read-only review snapshots and revision comparison (Dashboard Spec §5, §7).

A snapshot freezes what a reviewer saw: identity, filters, every record at
its version and hash, gate explanations, audit-chain verification and
caveats. Comparing two snapshots shows added / changed / removed /
superseded entities and unresolved issues, without opening raw KiCad files.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from . import gates
from .claims import redact, scan_text
from .util import now_iso, obj_hash, write_json

CAVEATS = [
    "Documentation-only evidence shows that a process was followed and that stated checks produced stated results.",
    "It does not by itself prove circuit function, yield, authenticity, equivalence, impedance, PI/SI, thermal, EMC or "
    "regulatory compliance, safety, reliability, or availability.",
    "Runs marked 'ingested' were not executed by this toolkit; identities marked unverified were not confirmed by a verified integration.",
]


def _filter(records: dict, filters: dict) -> dict:
    out = {}
    for t, rs in records.items():
        if filters.get("types") and t not in filters["types"]:
            continue
        sel = rs
        if filters.get("revision"):
            sel = [r for r in sel if r.get("revision") in (None, filters["revision"])]
        if filters.get("owner"):
            sel = [r for r in sel if r.get("owner") == filters["owner"]]
        if filters.get("severity"):
            sel = [r for r in sel if r.get("severity") == filters["severity"]]
        out[t] = sel
    return out


def build(store, out_dir, *, filters: dict | None = None, include_dashboard: bool = True) -> dict:
    actor, verified, _ = store.check("export_snapshot")
    filters = filters or {}
    ident = store.identity
    ts = now_iso()
    fp = store.fingerprint().split(":")[-1][:8]
    name = f"snapshot-{ident['design_id']}-{ident['revision']}-{ident['variant']}-{ts.replace(':', '')}-{fp}"
    root = Path(out_dir).resolve() / name
    root.mkdir(parents=True, exist_ok=True)
    records = _filter(store.all_records(), filters)
    redactions = []
    index = []
    for t, rs in records.items():
        for r in rs:
            text = json.dumps(r, sort_keys=True, ensure_ascii=False)
            hits = scan_text(text, f"{t}/{r['id']}")
            if hits:
                redactions += hits
                text = redact(text)
            p = root / "records" / t / f"{r['id']}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text + "\n", encoding="utf-8")
            index.append({"type": t, "id": r["id"], "record_version": r.get("record_version"), "hash": obj_hash(r),
                          "state": r.get("state"), "severity": r.get("severity"), "revision": r.get("revision")})
    evals = gates.evaluate_all(store)
    ok, problems = store.audit.verify()
    manifest = {
        "snapshot": name, "generated_at": ts, "generated_by": actor, "generator_verified": verified,
        "identity": ident, "filters": filters, "policy_version": store.policy.get("policy_version"),
        "store_fingerprint": store.fingerprint(), "records": index,
        "gates": [{k: e[k] for k in ("gate", "state", "automation_state", "evidence_fingerprint", "approval",
                                     "approval_note", "next_action", "explanation")} for e in evals],
        "audit_chain": {"verified": ok, "problems": problems, "events": len(store.audit.events())},
        "redactions": [{k: h[k] for k in ("type", "where")} for h in redactions],
        "caveats": CAVEATS, "read_only": True,
        "execution_mode_note": ("Contains executed runs" if any(r.get("executed") for r in records.get("run", []))
                                else "documentation-only / no live execution implied"),
    }
    write_json(root / "manifest.json", manifest)
    if include_dashboard:
        from .dashboard import render
        render(store, root / "dashboard.html", snapshot_manifest=manifest)
    zpath = root.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(root.parent))
    from .util import file_hash
    store.audit.append(actor=actor, actor_verified=verified, action="snapshot.export", object_type="snapshot",
                       object_id=name, revision=ident["revision"], after={"zip_hash": file_hash(zpath), "filters": filters},
                       reason="review snapshot exported", retention="review-record")
    return {"dir": str(root), "zip": str(zpath), "manifest": manifest}


def load(path) -> dict:
    p = Path(path)
    if p.suffix == ".zip":
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.endswith("/manifest.json"))
            return json.loads(z.read(name))
    if p.is_dir():
        p = p / "manifest.json"
    return json.loads(p.read_text())


def compare(a: dict, b: dict) -> dict:
    """Compare snapshot manifests a (before) and b (after)."""
    ia = {(r["type"], r["id"]): r for r in a["records"]}
    ib = {(r["type"], r["id"]): r for r in b["records"]}
    added = sorted(f"{t}/{i}" for (t, i) in ib.keys() - ia.keys())
    removed = sorted(f"{t}/{i}" for (t, i) in ia.keys() - ib.keys())
    changed, superseded = [], []
    for k in ia.keys() & ib.keys():
        if ia[k]["hash"] != ib[k]["hash"]:
            entry = {"record": f"{k[0]}/{k[1]}", "from_version": ia[k]["record_version"], "to_version": ib[k]["record_version"],
                     "state": [ia[k].get("state"), ib[k].get("state")]}
            (superseded if ib[k].get("state") == "superseded" else changed).append(entry)
    ga = {g["gate"]: g for g in a.get("gates", [])}
    gb = {g["gate"]: g for g in b.get("gates", [])}
    gate_changes = [{"gate": g, "from": ga.get(g, {}).get("state"), "to": gb[g]["state"]}
                    for g in gb if ga.get(g, {}).get("state") != gb[g]["state"]]
    unresolved = sorted(f"{r['type']}/{r['id']}" for r in b["records"]
                        if r["type"] == "issue" and r.get("state") in ("open", "contained"))
    return {"before": {"snapshot": a["snapshot"], "revision": a["identity"]["revision"], "variant": a["identity"]["variant"],
                       "fingerprint": a["store_fingerprint"]},
            "after": {"snapshot": b["snapshot"], "revision": b["identity"]["revision"], "variant": b["identity"]["variant"],
                      "fingerprint": b["store_fingerprint"]},
            "added": added, "removed": removed, "changed": sorted(changed, key=lambda e: e["record"]),
            "superseded": superseded, "gate_changes": gate_changes, "unresolved_issues": unresolved}
