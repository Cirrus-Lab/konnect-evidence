"""Minimal, dependency-free S-expression reader for KiCad native files.

Only reading is supported: the toolkit never writes CAD sources
(Dashboard Spec §1: no mutation of source artifacts).
"""
from __future__ import annotations

import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """Unquoted atom (distinguishes `hide` from the string "hide")."""


_ESC = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(1)), s)


def parse(text: str):
    stack: list[list] = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"unparseable S-expression near offset {pos}: {text[pos:pos+40]!r}")
        pos = m.end()
        lpar, rpar, qstr, atom = m.groups()
        if lpar:
            stack.append([])
        elif rpar:
            if len(stack) == 1:
                raise ValueError(f"unbalanced ')' at offset {pos}")
            done = stack.pop()
            stack[-1].append(done)
        elif qstr is not None:
            stack[-1].append(_unescape(qstr) if "\\" in qstr else qstr)
        elif atom is not None:
            stack[-1].append(Sym(atom))
    if len(stack) != 1:
        raise ValueError("unbalanced '(' — file truncated?")
    top = stack[0]
    return top[0] if len(top) == 1 else top


def head(node) -> str | None:
    return str(node[0]) if isinstance(node, list) and node else None


def children(node, name: str | None = None):
    if not isinstance(node, list):
        return []
    return [c for c in node[1:] if isinstance(c, list) and (name is None or head(c) == name)]


def child(node, name: str):
    for c in children(node, name):
        return c
    return None


def value(node, name: str, default=None):
    c = child(node, name)
    if c is None or len(c) < 2:
        return default
    return c[1]


def walk(node, name: str | None = None):
    """Depth-first iterator over list nodes (optionally filtered by head)."""
    if isinstance(node, list):
        if name is None or head(node) == name:
            yield node
        for c in node[1:]:
            if isinstance(c, list):
                yield from walk(c, name)


def properties(node) -> dict:
    out = {}
    for p in children(node, "property"):
        if len(p) >= 3:
            out[str(p[1])] = p[2]
    return out


def has_flag(node, flag: str) -> bool:
    """True for `(... hide ...)` atoms or `(hide yes)` sub-lists (KiCad 8+)."""
    if not isinstance(node, list):
        return False
    for c in node[1:]:
        if isinstance(c, Sym) and c == flag:
            return True
        if isinstance(c, list) and head(c) == flag and (len(c) == 1 or str(c[1]) in ("yes", "true")):
            return True
    return False
