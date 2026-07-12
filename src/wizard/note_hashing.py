"""Normalized content hashing for note dedup — shared by save_note and the Stop hook."""
from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def normalize_for_hash(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip ends.

    Case is preserved so genuinely distinct content does not collapse.
    """
    return _WS_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """SHA-256 hex of the normalized content."""
    return hashlib.sha256(normalize_for_hash(text).encode()).hexdigest()
