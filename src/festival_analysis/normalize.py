from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_B2B_RE = re.compile(r"\s+(?:b2b|b3b|b4b|vs\.?|&)\s+", re.IGNORECASE)
_PUNCT_STRIP = " \t\n\r\".,;:!?()[]{}"


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.strip(_PUNCT_STRIP)
    s = s.lower()
    s = _WS_RE.sub(" ", s)
    return s


def split_b2b(billing: str) -> list[str]:
    """Split a billing string like 'A b2b B' into constituent artist names.

    Returns a list with at least one element. Empty fragments are dropped.
    """
    parts = [p.strip() for p in _B2B_RE.split(billing)]
    return [p for p in parts if p]
