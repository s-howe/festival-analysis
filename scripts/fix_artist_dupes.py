#!/usr/bin/env python
"""One-time migration to fix duplicate and incorrectly-split artist records.

Run with:  uv run python scripts/fix_artist_dupes.py

Safe to re-run — all operations are idempotent.

Steps
-----
A. Merge same-name duplicates where one record has an RA artist ID and the
   other does not (caused by the old stable_id(name, ra_id) hashing scheme).

B. Collapse incorrectly-split duo acts: for each entry in duo_acts.txt,
   find the two ghost "split-part" artists (those that ONLY appear from that
   billing and have no RA ID), create a single duo artist record, move all
   lineup entries to it, then delete the ghost records.

C. Greedy prefix match: for any remaining unlinked artist whose normalised
   name is a unique prefix of exactly one RA-linked artist in the DB, merge
   them (handles e.g. "Hamish" -> "Hamish Cole").

D. Apply artist_aliases.csv: for any remaining unlinked artist whose
   normalised billing name appears in the alias map, merge to the target
   RA-linked artist (handles cases the prefix match can't reach).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from festival_analysis import db
from festival_analysis.config import ARTIST_ALIASES_CSV, DB_PATH, DUO_ACTS_FILE
from festival_analysis.normalize import (
    load_artist_aliases,
    load_duo_acts,
    normalize_name,
    split_b2b,
)


def _merge(con, keep_id: int, drop_id: int, label: str) -> None:
    n = db.merge_artists(con, keep_id, drop_id)
    print(f"  merged {n} entries: {label} → keep {keep_id}")


def part_a(con) -> None:
    """Merge no-RA-ID duplicates into their RA-linked counterpart."""
    print("\n=== Part A: merge same-name duplicates (one with RA ID, one without) ===")
    pairs = con.execute("""
        WITH dupes AS (
            SELECT normalized_name
            FROM artists
            GROUP BY normalized_name
            HAVING count(*) > 1
        )
        SELECT
            a_ra.artist_id   AS keep_id,
            a_none.artist_id AS drop_id,
            a_ra.display_name
        FROM dupes d
        JOIN artists a_ra   ON a_ra.normalized_name   = d.normalized_name
                            AND a_ra.ra_artist_id  IS NOT NULL
        JOIN artists a_none ON a_none.normalized_name = d.normalized_name
                            AND a_none.ra_artist_id IS NULL
    """).fetchall()

    if not pairs:
        print("  nothing to do")
        return
    for keep_id, drop_id, name in pairs:
        _merge(con, keep_id, drop_id, name)


def part_b(con, duo_acts: frozenset[str]) -> None:
    """Collapse ghost split-part artists back into single duo records."""
    print("\n=== Part B: collapse incorrectly-split duo acts ===")

    for duo_name in sorted(duo_acts):
        # Use the original (un-normalised) display name from the file;
        # we need the pretty version for the artist record.
        # We stored normalised forms in duo_acts; recover display from billing.
        pass  # will be handled below per-billing

    # Work from raw billings that are known duo acts and have been split.
    billings_in_db = con.execute("""
        SELECT DISTINCT raw_billing
        FROM lineup_entries
        WHERE raw_billing IS NOT NULL
    """).fetchall()

    found_any = False
    for (billing,) in billings_in_db:
        if normalize_name(billing) not in duo_acts:
            continue
        parts = split_b2b(billing)
        if len(parts) <= 1:
            continue  # already stored as single — nothing to do

        # Find ghost artists: split parts with no RA ID whose ALL bookings
        # come from this exact billing.
        ghost_ids: list[int] = []
        for part in parts:
            norm = normalize_name(part)
            rows = con.execute("""
                SELECT a.artist_id
                FROM artists a
                JOIN lineup_entries le USING (artist_id)
                WHERE a.normalized_name = ?
                  AND a.ra_artist_id IS NULL
                GROUP BY a.artist_id
                HAVING COUNT(DISTINCT le.raw_billing) = 1
                   AND MAX(le.raw_billing) = ?
            """, [norm, billing]).fetchall()
            ghost_ids.extend(r[0] for r in rows)

        if not ghost_ids:
            continue  # already fixed or parts have solo appearances

        found_any = True
        duo_norm = normalize_name(billing)

        # Find or create the duo artist record.
        existing = con.execute(
            "SELECT artist_id FROM artists WHERE normalized_name = ? LIMIT 1",
            [duo_norm],
        ).fetchone()
        if existing:
            duo_id = existing[0]
        else:
            duo_id = db.stable_id(duo_norm, "")
            con.execute("""
                INSERT INTO artists (artist_id, display_name, normalized_name)
                VALUES (?, ?, ?)
                ON CONFLICT (artist_id) DO NOTHING
            """, [duo_id, billing, duo_norm])
            print(f"  created duo artist: {billing!r} (id={duo_id})")

        # Move lineup entries from each ghost to the duo record.
        for ghost_id in ghost_ids:
            _merge(con, duo_id, ghost_id, f"ghost part of {billing!r}")

    if not found_any:
        print("  nothing to do")


def part_c(con) -> None:
    """Greedy prefix match: link unlinked artists to unique RA-prefix matches."""
    print("\n=== Part C: greedy prefix match ===")

    unlinked = con.execute("""
        SELECT a.artist_id, a.normalized_name, a.display_name
        FROM artists a
        WHERE a.ra_artist_id IS NULL
          AND EXISTS (SELECT 1 FROM lineup_entries le WHERE le.artist_id = a.artist_id)
    """).fetchall()

    merged = 0
    for artist_id, norm_name, display_name in unlinked:
        matches = con.execute("""
            SELECT artist_id FROM artists
            WHERE ra_artist_id IS NOT NULL
              AND normalized_name LIKE ? || ' %'
        """, [norm_name]).fetchall()

        if len(matches) != 1:
            continue
        target_id = matches[0][0]
        _merge(con, target_id, artist_id, f"{display_name!r} → prefix match")
        merged += 1

    if not merged:
        print("  nothing to do")


def part_d(con, aliases: dict[str, str]) -> None:
    """Apply manual alias overrides from artist_aliases.csv."""
    print("\n=== Part D: apply artist_aliases.csv ===")

    if not aliases:
        print("  no aliases defined")
        return

    merged = 0
    for billing_norm, ra_id in aliases.items():
        # Find the target (RA-linked) artist.
        target = con.execute(
            "SELECT artist_id, display_name FROM artists WHERE ra_artist_id = ?",
            [ra_id],
        ).fetchone()
        if not target:
            print(f"  skipping alias {billing_norm!r}: RA artist {ra_id!r} not in DB")
            continue
        target_id, target_name = target

        # Find unlinked artists with this normalised billing name.
        ghosts = con.execute("""
            SELECT artist_id, display_name FROM artists
            WHERE normalized_name = ?
              AND ra_artist_id IS NULL
        """, [billing_norm]).fetchall()

        for ghost_id, ghost_name in ghosts:
            _merge(con, target_id, ghost_id,
                   f"alias {ghost_name!r} → {target_name!r} (RA {ra_id})")
            merged += 1

    if not merged:
        print("  nothing to do")


def part_e(con, duo_acts: frozenset[str]) -> None:
    """Reassign lineup_entries whose raw_billing is a known duo act.

    Corrects cases where a billing like 'Gin & Tonic' was split by b2b-splitting
    and the parts were then incorrectly merged into unrelated RA artists by the
    greedy prefix match (Part C).  We reassign ALL entries whose raw_billing
    matches the duo act name to a canonical duo artist record, regardless of the
    current artist_id.
    """
    print("\n=== Part E: raw_billing-based duo act reassignment ===")

    billings_in_db = con.execute("""
        SELECT DISTINCT raw_billing
        FROM lineup_entries
        WHERE raw_billing IS NOT NULL
    """).fetchall()

    found_any = False
    for (billing,) in billings_in_db:
        duo_norm = normalize_name(billing)
        if duo_norm not in duo_acts:
            continue

        # Only act on billings that would be split — if split_b2b returns a
        # single part it's already stored correctly.
        parts = split_b2b(billing)
        if len(parts) <= 1:
            continue

        # Find or create the canonical duo artist record.
        existing = con.execute(
            "SELECT artist_id FROM artists WHERE normalized_name = ? LIMIT 1",
            [duo_norm],
        ).fetchone()
        if existing:
            duo_id = existing[0]
        else:
            duo_id = db.stable_id(duo_norm, "")
            con.execute("""
                INSERT INTO artists (artist_id, display_name, normalized_name)
                VALUES (?, ?, ?)
                ON CONFLICT (artist_id) DO NOTHING
            """, [duo_id, billing, duo_norm])
            print(f"  created duo artist: {billing!r} (id={duo_id})")

        # Find entries with this raw_billing that point at the wrong artist.
        entries = con.execute("""
            SELECT festival_event_id, artist_id
            FROM lineup_entries
            WHERE raw_billing = ? AND artist_id != ?
        """, [billing, duo_id]).fetchall()

        if not entries:
            continue

        found_any = True
        for event_id, old_artist_id in entries:
            new_entry_id = db.stable_id(event_id, duo_id)
            con.execute("""
                INSERT INTO lineup_entries (entry_id, festival_event_id, artist_id, raw_billing)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (entry_id) DO NOTHING
            """, [new_entry_id, event_id, duo_id, billing])
            old_entry_id = db.stable_id(event_id, old_artist_id)
            con.execute(
                "DELETE FROM lineup_entries WHERE entry_id = ?", [old_entry_id]
            )
            print(
                f"  reassigned {billing!r} (event {event_id}): "
                f"artist {old_artist_id} → {duo_id}"
            )

    if not found_any:
        print("  nothing to do")


def main() -> None:
    duo_acts = load_duo_acts(DUO_ACTS_FILE) if DUO_ACTS_FILE.exists() else frozenset()
    aliases = load_artist_aliases(ARTIST_ALIASES_CSV) if ARTIST_ALIASES_CSV.exists() else {}

    # DuckDB evaluates FK constraints against the committed state, not the
    # in-progress transaction snapshot.  Running merge_artists inside a long
    # outer transaction therefore causes a spurious "still referenced" error
    # when we try to delete an artist whose lineup entries were deleted in the
    # same transaction.  Each merge is tiny and idempotent, so running in
    # autocommit (no explicit begin/commit) is safe and avoids the issue.
    con = db.connect(DB_PATH)

    part_a(con)
    part_b(con, duo_acts)
    part_c(con)
    part_d(con, aliases)
    part_e(con, duo_acts)
    print("\nDone.")


if __name__ == "__main__":
    main()
