from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .config import CACHE_DIR, DB_PATH
from . import db
from .queries import build_artist_batch_query
from .ra_client import RAClient

logger = logging.getLogger(__name__)

def _upsert_artist_profile(
    con: duckdb.DuckDBPyConnection,
    profile: dict,
    country_to_iso2: dict[str, str],
) -> None:
    artist_id_str = profile.get("id")
    if not artist_id_str:
        return

    country_name = (profile.get("country") or {}).get("name")
    country = country_to_iso2.get(country_name) if country_name else None
    if country_name and country is None:
        logger.warning("unknown artist country %r — will be stored as NULL", country_name)
    area = (profile.get("area") or {}).get("name")
    status = profile.get("status")
    instagram = profile.get("instagram") or None
    soundcloud = profile.get("soundcloud") or None
    twitter = profile.get("twitter") or None
    now = datetime.now(timezone.utc)

    con.execute(
        """
        UPDATE artists SET
          country        = ?,
          area           = ?,
          ra_status      = ?,
          instagram_url  = ?,
          soundcloud_url = ?,
          twitter_url    = ?,
          enriched_at    = ?
        WHERE ra_artist_id = ?
        """,
        [country, area, status, instagram, soundcloud, twitter, now, artist_id_str],
    )



def enrich_artists(
    con: duckdb.DuckDBPyConnection,
    client: RAClient,
    refresh: bool = False,
    batch_size: int = 20,
) -> None:
    if refresh:
        rows = con.execute(
            "SELECT ra_artist_id FROM artists WHERE ra_artist_id IS NOT NULL"
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT ra_artist_id FROM artists WHERE ra_artist_id IS NOT NULL AND enriched_at IS NULL"
        ).fetchall()

    ids = [r[0] for r in rows]
    total = len(ids)
    logger.info("enriching %d artists in batches of %d", total, batch_size)

    country_to_iso2 = db.load_country_lookup(con)

    done = 0
    for start in range(0, total, batch_size):
        batch = ids[start : start + batch_size]
        query = build_artist_batch_query(batch)
        try:
            body = client.post(query, {})
            data = body.get("data") or {}
        except Exception:
            logger.exception("batch fetch failed at offset %d, skipping", start)
            continue

        con.begin()
        try:
            for key, profile in data.items():
                if profile:
                    _upsert_artist_profile(con, profile, country_to_iso2)
            con.commit()
        except Exception:
            con.rollback()
            logger.exception("upsert failed for batch at offset %d", start)

        done += len(batch)
        if done % 500 == 0 or done == total:
            logger.info("  enriched %d/%d artists", done, total)


def run(
    db_path: Path | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    batch_size: int = 20,
) -> None:
    db_path = db_path or DB_PATH
    cache_dir = cache_dir or CACHE_DIR
    con = db.connect(db_path)
    db.init_schema(con)
    with RAClient(cache_dir=cache_dir, refresh=refresh) as client:
        enrich_artists(con, client, refresh=refresh, batch_size=batch_size)
