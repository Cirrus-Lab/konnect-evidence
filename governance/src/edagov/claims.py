"""Claim control and secret scanning (Skill Spec §3 step 6, §7 checks 1, 5, 6, 7).

`lint_claims` flags unscoped absolute claims ("compliant", "manufacturable",
"drop-in", ...) unless the sentence carries scoping language and an evidence
reference. `scan_secrets` flags credential-shaped content before anything is
recorded, exported or published.
"""
from __future__ import annotations

import re
from pathlib import Path

PROHIBITED = {
    "functional": r"\b(is|are|proven|verified)\s+(fully\s+)?function(al|s correctly)\b",
    "compliant": r"\b(fully\s+)?(compliant|compliance (is )?(achieved|confirmed)|meets all)\b",
    "manufacturable": r"\bmanufacturab(le|ility (is )?(confirmed|proven))\b",
    "thermally_adequate": r"\bthermally (adequate|safe|validated)\b",
    "emc_certified": r"\b(emc|fcc|ce)[- ](certified|compliant|ready|approved)\b",
    "authentic": r"\b(guaranteed |verified )?authentic\b",
    "drop_in": r"\bdrop[- ]?in( replacement)?\b",
    "safe": r"\b(is|are)\s+(electrically\s+)?safe\b",
    "validated_by_sim": r"\bsimulation (proves|validates|confirms)\b",
    "erc_drc_proof": r"\b(erc|drc)\s+(clean|pass(ed)?)\s+(proves|means|so)\b",
    "ipc_compliant_unscoped": r"\bipc[- ]compliant\b",
}
SCOPING = re.compile(r"\b(under (these|the recorded)|with these inputs|for (revision|rev\.?)|as scoped|"
                     r"limited to|under rule set|per (run|evidence)|not (a|an) (claim|proof)|does not (show|prove)|"
                     r"no recorded violation|it does not|cannot by itself)\b", re.I)
EVIDENCE_REF = re.compile(r"\b(RUN|ART|EXC|APR|REV|MFG|REQ|ISS)-[A-Z0-9-]+|\[\d+\]")


EXAMPLE_MARKER = "claims:example"  # line-level marker for documentation that quotes prohibited wording


def lint_claims(text: str) -> list[dict]:
    out = []
    text = "\n".join(l for l in text.splitlines() if EXAMPLE_MARKER not in l)
    for n, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n", text), start=1):
        s = sentence.strip()
        if not s:
            continue
        for name, pat in PROHIBITED.items():
            if re.search(pat, s, re.I):
                scoped = bool(SCOPING.search(s))
                cited = bool(EVIDENCE_REF.search(s))
                negated = bool(re.search(r"\b(not|never|no|cannot|isn't|aren't|does not)\b", s, re.I))
                if negated or (scoped and cited):
                    continue
                out.append({"rule": name, "sentence": s[:240], "scoped": scoped, "cited": cited,
                            "fix": "Rewrite as a scoped statement naming inputs, policy, evidence ID and limits."})
    return out


SECRET_PATTERNS = {
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
    "github_token": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b",
    "slack_token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    "anthropic_key": r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
    "openai_key": r"\bsk-(proj-)?[A-Za-z0-9]{32,}\b",
    "google_api_key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
    "bearer": r"(?i)\bauthorization:\s*bearer\s+[A-Za-z0-9._~+/-]{20,}",
    "password_assignment": r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
    "url_credentials": r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]+@",
}
_SECRET_RX = {k: re.compile(v) for k, v in SECRET_PATTERNS.items()}
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".log", ".csv", ".html", ".yml", ".yaml", ".cir", ".net", ".rpt", ".xml", ""}


def scan_text(text: str, where: str = "") -> list[dict]:
    hits = []
    for name, rx in _SECRET_RX.items():
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append({"type": name, "where": where, "line": line, "preview": m.group(0)[:6] + "…[redacted]"})
    return hits


def scan_paths(paths) -> list[dict]:
    hits = []
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for p in files:
            if p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 20_000_000:
                continue
            try:
                hits += scan_text(p.read_text(encoding="utf-8", errors="ignore"), str(p))
            except OSError:
                continue
    return hits


def redact(text: str) -> str:
    for rx in _SECRET_RX.values():
        text = rx.sub("[REDACTED]", text)
    return text
