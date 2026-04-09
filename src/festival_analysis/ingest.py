from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from . import db
from .config import CACHE_DIR, DB_PATH, FESTIVALS_CSV
from .normalize import normalize_name, split_b2b
from .parser import parse_event_listing
from .ra_client import RAClient

logger = logging.getLogger(__name__)


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_festivals_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `festival-analysis resolve-slugs` first."
        )
    with path.open() as f:
        return list(csv.DictReader(f))


def run(
    festival_filter: str | None = None,
    festivals_csv: Path | None = None,
    db_path: Path | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    first_year: int = 2005,
    last_year: int | None = None,
) -> None:
    festivals_csv = festivals_csv or FESTIVALS_CSV
    db_path = db_path or DB_PATH
    cache_dir = cache_dir or CACHE_DIR

    rows = _read_festivals_csv(festivals_csv)
    con = db.connect(db_path)
    db.init_schema(con)

    eligible = [
        r for r in rows
        if not festival_filter or r["name"] == festival_filter
    ]
    with_id = [r for r in eligible if (r.get("ra_club_id") or "").strip()]
    logger.info(
        "ingesting %d/%d festivals (skipping %d without ra_club_id)",
        len(with_id),
        len(eligible),
        len(eligible) - len(with_id),
    )

    country_to_iso2 = db.load_country_lookup(con)

    with RAClient(cache_dir=cache_dir, refresh=refresh) as client:
        for idx, row in enumerate(eligible, 1):
            name = row["name"]
            ra_club_id = (row.get("ra_club_id") or "").strip()
            ra_slug = (row.get("ra_slug") or "").strip()
            title_filter = (row.get("title_filter") or "").strip() or None
            festival_id = db.upsert_festival(
                con,
                name=name,
                size=(row.get("size") or "").strip() or None,
                ra_slug=row.get("ra_slug") or None,
                ra_club_id=ra_club_id or None,
                notes=row.get("notes") or None,
            )
            if not ra_club_id:
                logger.info("  [%d/%d] skipping %s (no ra_club_id)", idx, len(eligible), name)
                continue

            logger.info("  [%d/%d] %s", idx, len(eligible), name)
            con.begin()
            try:
                _ingest_festival(
                    con,
                    client,
                    festival_id,
                    ra_slug or f"promoters/{ra_club_id}",
                    ra_club_id,
                    first_year,
                    last_year,
                    title_filter,
                    country_to_iso2,
                )
                con.commit()
            except Exception:
                con.rollback()
                logger.exception("ingest failed for %s", name)


def _ingest_festival(
    con,
    client: RAClient,
    festival_id: int,
    ra_slug: str,
    ra_id: str,
    first_year: int,
    last_year: int | None = None,
    title_filter: str | None = None,
    country_to_iso2: dict | None = None,
) -> None:
    for ev in client.fetch_events_for_entity(
        ra_slug, ra_id, first_year=first_year, last_year=last_year
    ):
        if title_filter:
            event_title = ev.get("title") or ""
            if title_filter.lower() not in event_title.lower():
                continue
        cache_key = client.cache_key(
            "event_entity_entry", {"event_id": ev.get("id")}
        )
        db.insert_raw_event(con, cache_key, festival_id, json.dumps(ev))

        ra_event = parse_event_listing({"event": ev})
        if ra_event is None:
            continue

        edition_year = ra_event.event_date.year if ra_event.event_date else None
        country_name = ra_event.venue.country
        country = (country_to_iso2 or {}).get(country_name) if country_name else None
        if country_name and country is None:
            logger.warning("unknown country %r — location_country will be NULL", country_name)
        festival_event_id = db.upsert_festival_event(
            con,
            festival_id=festival_id,
            ra_event_id=ra_event.id,
            edition_year=edition_year,
            start_date=ra_event.event_date,
            end_date=ra_event.event_date,
            location_country=country,
            location_city=ra_event.venue.city,
            venue_name=ra_event.venue.name,
        )

        for artist in ra_event.artists:
            for piece in split_b2b(artist.name):
                norm = normalize_name(piece)
                if not norm:
                    continue
                # If the original RA artist record had an id but we b2b-split,
                # the id only safely applies when there was a single artist.
                ra_artist_id = artist.id if len(split_b2b(artist.name)) == 1 else None
                artist_id = db.upsert_artist(
                    con,
                    display_name=piece,
                    normalized_name=norm,
                    ra_artist_id=ra_artist_id,
                )
                db.upsert_lineup_entry(
                    con,
                    festival_event_id=festival_event_id,
                    artist_id=artist_id,
                    raw_billing=artist.name,
                )
