from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

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


def load_duo_acts(path: Path) -> frozenset[str]:
    """Return a frozenset of normalised duo-act names from *path*.

    Lines starting with '#' and blank lines are ignored.
    """
    acts: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            acts.add(normalize_name(line))
    return frozenset(acts)


def load_artist_aliases(path: Path) -> dict[str, str]:
    """Return {normalised_billing_name: ra_artist_id} from *path*.

    Lines starting with '#' are stripped before parsing so comments can appear
    anywhere in the file (including before the header row).
    Rows whose ra_artist_id column is blank are skipped.
    """
    aliases: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        ra_id = (row.get("ra_artist_id") or "").strip()
        if not ra_id:
            continue
        name = normalize_name(row["billing_name"])
        if name:
            aliases[name] = ra_id
    return aliases


def is_duo_act(billing: str, duo_acts: frozenset[str]) -> bool:
    """Return True if *billing* matches a known duo/group act."""
    return normalize_name(billing) in duo_acts
