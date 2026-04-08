from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from .config import FESTIVAL_NAMES_CSV, FESTIVALS_CSV, RA_USER_AGENT
from .normalize import normalize_name
from .ra_client import RAClient

logger = logging.getLogger(__name__)

CSV_FIELDS = ["name", "size", "ra_slug", "ra_club_id", "confidence", "title_filter", "notes"]
SCORE_THRESHOLD = 0.6

# Matches /clubs/<id> or /promoters/<id> in an RA URL
_RA_URL_RE = re.compile(r"ra\.co/(clubs|promoters)/(\d+)", re.IGNORECASE)


@dataclass
class ResolveResult:
    ra_slug: str | None
    ra_club_id: str | None
    confidence: float
    source: str  # auto:ra-search | auto:google | unresolved


def _score(name: str, candidate: str) -> float:
    return SequenceMatcher(None, normalize_name(name), normalize_name(candidate)).ratio()


def resolve_via_ra(client: RAClient, name: str) -> ResolveResult | None:
    hits = client.search(name, indices=["CLUB", "PROMOTER"])
    best: tuple[float, dict] | None = None
    for hit in hits:
        score = _score(name, hit.get("value") or "")
        if best is None or score > best[0]:
            best = (score, hit)
    if best is None:
        return None
    score, hit = best
    if score < SCORE_THRESHOLD:
        return None
    content_url = hit.get("contentUrl") or ""
    slug = content_url.lstrip("/")
    return ResolveResult(
        ra_slug=slug or None,
        ra_club_id=str(hit.get("id")) if hit.get("id") else None,
        confidence=round(score, 3),
        source="auto:ra-search",
    )


def resolve_via_google(name: str) -> ResolveResult | None:
    """Best-effort fallback: parse the first ra.co club/promoter URL out of
    a Google results page. Google may rate-limit/block; we just give up on
    failure.
    """
    query = f"site:ra.co {name}"
    url = "https://www.google.com/search"
    try:
        resp = httpx.get(
            url,
            params={"q": query},
            headers={"User-Agent": RA_USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
    except httpx.HTTPError as exc:
        logger.debug("google fallback failed for %s: %s", name, exc)
        return None
    match = _RA_URL_RE.search(resp.text)
    if not match:
        return None
    kind, ra_id = match.group(1).lower(), match.group(2)
    return ResolveResult(
        ra_slug=f"{kind}/{ra_id}",
        ra_club_id=ra_id,
        confidence=0.5,
        source="auto:google",
    )


def resolve_festival(client: RAClient, name: str) -> ResolveResult:
    result = resolve_via_ra(client, name)
    if result is not None:
        return result
    fallback = resolve_via_google(name)
    if fallback is not None:
        return fallback
    return ResolveResult(None, None, 0.0, "unresolved")


def _read_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            rows[row["name"]] = row
    return rows


def _read_names(path: Path) -> list[str]:
    with path.open() as f:
        return [line.strip() for line in f if line.strip()]


def resolve_all(
    client: RAClient,
    names_csv: Path | None = None,
    out_csv: Path | None = None,
) -> Path:
    names_csv = names_csv or FESTIVAL_NAMES_CSV
    out_csv = out_csv or FESTIVALS_CSV
    existing = _read_existing(out_csv)
    names = _read_names(names_csv)

    rows: list[dict] = []
    for name in names:
        prior = existing.get(name)
        if prior and prior.get("ra_club_id"):
            rows.append({k: prior.get(k, "") for k in CSV_FIELDS})
            continue
        logger.info("resolving %s", name)
        result = resolve_festival(client, name)
        rows.append(
            {
                "name": name,
                "size": (prior or {}).get("size", ""),
                "ra_slug": result.ra_slug or "",
                "ra_club_id": result.ra_club_id or "",
                "confidence": f"{result.confidence:.3f}",
                "title_filter": (prior or {}).get("title_filter", ""),
                "notes": result.source,
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return out_csv
