from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from .config import COUNTRIES_CSV, DB_PATH

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# 63-bit signed range so values fit in BIGINT
_HASH_MASK = (1 << 63) - 1


def stable_id(*parts: str | int | None) -> int:
    """Deterministic 63-bit hash for use as a primary key."""
    h = hashlib.blake2b(digest_size=8)
    for p in parts:
        h.update(b"\x1f")
        h.update(str(p if p is not None else "").encode("utf-8"))
    return int.from_bytes(h.digest(), "big") & _HASH_MASK


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def _seed_countries(con: duckdb.DuckDBPyConnection) -> None:
    """Upsert source-data/countries.csv into the countries table."""
    con.execute(
        f"""
        INSERT INTO countries (country, name, continent, population)
        SELECT country, name, continent, population
        FROM read_csv(
            '{COUNTRIES_CSV}',
            header    = true,
            columns   = {{
                'name':       'TEXT',
                'country':    'TEXT',
                'continent':  'TEXT',
                'population': 'INTEGER'
            }},
            nullstr = ''
        )
        ON CONFLICT (country) DO UPDATE SET
            name       = excluded.name,
            continent  = excluded.continent,
            population = excluded.population
        """
    )


def load_country_lookup(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Return {country_name: country_code} for use during ingest and enrichment."""
    rows = con.execute("SELECT name, country FROM countries").fetchall()
    return {name: code for name, code in rows if name}


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_PATH.read_text())
    _seed_countries(con)


def upsert_festival(
    con: duckdb.DuckDBPyConnection,
    name: str,
    size: str | None,
    ra_slug: str | None,
    ra_club_id: str | None,
    notes: str | None,
) -> int:
    festival_id = stable_id(name)
    con.execute(
        """
        INSERT INTO festivals (festival_id, name, size_band, ra_slug, ra_club_id, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (festival_id) DO UPDATE SET
          size_band = excluded.size_band,
          ra_slug = excluded.ra_slug,
          ra_club_id = excluded.ra_club_id,
          notes = excluded.notes
        """,
        [festival_id, name, size, ra_slug, ra_club_id, notes],
    )
    return festival_id


def upsert_festival_event(
    con: duckdb.DuckDBPyConnection,
    festival_id: int,
    ra_event_id: str,
    edition_year: int | None,
    start_date,
    end_date,
    location_country: str | None,
    location_city: str | None,
    venue_name: str | None,
) -> int:
    festival_event_id = stable_id(festival_id, ra_event_id)
    con.execute(
        """
        INSERT INTO festival_events (
          festival_event_id, festival_id, ra_event_id, edition_year,
          start_date, end_date, location_country, location_city, venue_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (festival_event_id) DO NOTHING
        """,
        [
            festival_event_id,
            festival_id,
            ra_event_id,
            edition_year,
            start_date,
            end_date,
            location_country,
            location_city,
            venue_name,
        ],
    )
    return festival_event_id


def upsert_artist(
    con: duckdb.DuckDBPyConnection,
    display_name: str,
    normalized_name: str,
    ra_artist_id: str | None,
) -> int:
    # 1. If we have an RA ID, check whether this artist already exists by that ID.
    if ra_artist_id:
        row = con.execute(
            "SELECT artist_id FROM artists WHERE ra_artist_id = ?", [ra_artist_id]
        ).fetchone()
        if row:
            return row[0]

    # 2. Look up by normalised name.
    row = con.execute(
        "SELECT artist_id, ra_artist_id FROM artists WHERE normalized_name = ? LIMIT 1",
        [normalized_name],
    ).fetchone()
    if row:
        existing_id, existing_ra_id = row
        if not existing_ra_id:
            # Existing record has no RA link — safe to reuse it.
            # Note: we deliberately do NOT update ra_artist_id here because
            # DuckDB implements unique-key updates as delete+insert internally,
            # which triggers a spurious FK-constraint error against lineup_entries
            # inside a transaction.  The fix_artist_dupes.py Part A migration
            # handles linking these records after ingest completes.
            return existing_id
        # Both have RA IDs and they differ → treat as distinct artists
        # (e.g. "Mika." RA:163793 vs "Mika" RA:28630).

    # 3. Greedy prefix match — only for unlinked splits (no ra_artist_id).
    # If this name is a unique prefix of exactly one RA-linked artist already in
    # the DB, use that artist rather than creating a new ghost record.
    if not ra_artist_id:
        rows = con.execute(
            """SELECT artist_id FROM artists
               WHERE ra_artist_id IS NOT NULL
                 AND normalized_name LIKE ? || ' %'""",
            [normalized_name],
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0]

    # 4. Create a new record.
    artist_id = stable_id(normalized_name, ra_artist_id or "")
    con.execute(
        """
        INSERT INTO artists (artist_id, ra_artist_id, display_name, normalized_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (artist_id) DO NOTHING
        """,
        [artist_id, ra_artist_id, display_name, normalized_name],
    )
    return artist_id


def merge_artists(
    con: duckdb.DuckDBPyConnection,
    keep_id: int,
    drop_id: int,
) -> int:
    """Move all lineup entries from *drop_id* to *keep_id*, then delete *drop_id*.

    Returns the number of entries reassigned.  Safe to call when *drop_id*
    no longer exists (returns 0).
    """
    rows = con.execute(
        "SELECT festival_event_id, raw_billing FROM lineup_entries WHERE artist_id = ?",
        [drop_id],
    ).fetchall()
    for event_id, raw_billing in rows:
        new_entry_id = stable_id(event_id, keep_id)
        con.execute(
            """
            INSERT INTO lineup_entries (entry_id, festival_event_id, artist_id, raw_billing)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (entry_id) DO NOTHING
            """,
            [new_entry_id, event_id, keep_id, raw_billing],
        )
    con.execute("DELETE FROM lineup_entries WHERE artist_id = ?", [drop_id])
    con.execute("DELETE FROM artists WHERE artist_id = ?", [drop_id])
    return len(rows)


def upsert_lineup_entry(
    con: duckdb.DuckDBPyConnection,
    festival_event_id: int,
    artist_id: int,
    raw_billing: str | None,
) -> None:
    entry_id = stable_id(festival_event_id, artist_id)
    con.execute(
        """
        INSERT INTO lineup_entries (entry_id, festival_event_id, artist_id, raw_billing)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (entry_id) DO NOTHING
        """,
        [entry_id, festival_event_id, artist_id, raw_billing],
    )


def insert_raw_event(
    con: duckdb.DuckDBPyConnection,
    cache_key: str,
    festival_id: int | None,
    payload_json: str,
) -> None:
    con.execute(
        """
        INSERT INTO raw_events (cache_key, festival_id, payload)
        VALUES (?, ?, ?)
        ON CONFLICT (cache_key) DO NOTHING
        """,
        [cache_key, festival_id, payload_json],
    )
